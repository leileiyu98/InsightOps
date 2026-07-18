"""Readonly MySQL execution boundary for validated benchmark candidate SQL."""

from collections.abc import Mapping
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Connection, Engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError

from insightops.canonical import canonical_json_bytes
from insightops.db.session import create_mysql_engine
from insightops.evaluation.contracts import (
    EvaluationFailureCode,
    ExecutionLimits,
    NormalizedResult,
)
from insightops.evaluation.normalization import (
    ResultNormalizationError,
    normalize_database_result,
)

_PERMISSION_ERROR_CODES = frozenset({1044, 1045, 1142, 1143, 1227, 1792})
_TIMEOUT_ERROR_CODES = frozenset({1205, 2013, 3024})


class ReadonlyDatabaseSettings(BaseSettings):
    """Environment-backed credentials dedicated to candidate SQL execution."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="READONLY_DATABASE_",
        extra="ignore",
    )

    host: str
    port: int
    name: str = Field(pattern=r"^[A-Za-z0-9_]+$")
    user: str = Field(pattern=r"^[A-Za-z0-9_]+$")
    password: SecretStr

    @property
    def database_url(self) -> URL:
        """Build a credential-safe SQLAlchemy URL."""
        return URL.create(
            drivername="mysql+pymysql",
            username=self.user,
            password=self.password.get_secret_value(),
            host=self.host,
            port=self.port,
            database=self.name,
        )


def load_readonly_database_settings(
    *, env_file: str | Path | None = ".env"
) -> ReadonlyDatabaseSettings:
    """Load the independently configured candidate execution identity."""
    return ReadonlyDatabaseSettings(_env_file=env_file)  # type: ignore[call-arg]


def create_readonly_database_engine(
    settings: ReadonlyDatabaseSettings,
    *,
    timeout_ms: int = 5_000,
) -> Engine:
    """Create a lazy engine bound only to the readonly identity."""
    read_timeout_seconds = timeout_ms / 1_000 + 1.0
    return create_mysql_engine(
        settings.database_url,
        connect_args={"read_timeout": read_timeout_seconds},
    )


class SqlExecutionError(RuntimeError):
    """Stable execution failure safe for deterministic classification."""

    def __init__(self, failure_code: EvaluationFailureCode) -> None:
        self.failure_code = failure_code
        super().__init__(failure_code.value)


class ReadonlySqlExecutor:
    """Execute prevalidated SQL in a read-only transaction with fixed limits."""

    def __init__(
        self,
        engine: Engine,
        settings: ReadonlyDatabaseSettings,
        limits: ExecutionLimits,
    ) -> None:
        self._engine = engine
        self._settings = settings
        self._limits = limits

    def verify_identity(self) -> None:
        """Verify configured username and ensure grants contain only USAGE/SELECT."""
        try:
            with self._engine.connect() as connection:
                current_user = connection.scalar(text("SELECT CURRENT_USER()"))
                if not isinstance(current_user, str):
                    raise SqlExecutionError(EvaluationFailureCode.READONLY_TRANSACTION_FAILED)
                authenticated_user = current_user.split("@", maxsplit=1)[0]
                if authenticated_user != self._settings.user:
                    raise SqlExecutionError(EvaluationFailureCode.READONLY_TRANSACTION_FAILED)
                grants = tuple(
                    str(grant).upper()
                    for grant in connection.exec_driver_sql(
                        "SHOW GRANTS FOR CURRENT_USER"
                    ).scalars()
                )
                if not _grants_are_readonly_for_database(grants, self._settings.name):
                    raise SqlExecutionError(EvaluationFailureCode.READONLY_TRANSACTION_FAILED)
        except SqlExecutionError:
            raise
        except DBAPIError as error:
            raise SqlExecutionError(_database_failure_code(error)) from error

    def execute(
        self,
        sql: str,
        parameters: Mapping[str, object],
    ) -> NormalizedResult:
        """Execute without rewriting SQL and return a bounded normalized result."""
        connection: Connection | None = None
        try:
            with self._engine.connect() as connection:
                try:
                    self._verify_connection_user(connection)
                    connection.execute(
                        text("SET SESSION MAX_EXECUTION_TIME = :timeout_ms"),
                        {"timeout_ms": self._limits.timeout_ms},
                    )
                    connection.commit()
                    connection.exec_driver_sql("START TRANSACTION READ ONLY")
                    result = connection.execute(text(sql), dict(parameters))
                    columns = tuple(result.keys())
                    rows = result.mappings().fetchmany(self._limits.max_rows + 1)
                    if len(rows) > self._limits.max_rows:
                        raise SqlExecutionError(EvaluationFailureCode.ROW_LIMIT_EXCEEDED)
                    normalized = normalize_database_result(
                        columns,
                        [dict(row) for row in rows],
                    )
                    output_size = len(
                        canonical_json_bytes(
                            normalized.model_dump(mode="json", exclude={"result_digest"})
                        )
                    )
                    if output_size > self._limits.max_output_bytes:
                        raise SqlExecutionError(EvaluationFailureCode.OUTPUT_LIMIT_EXCEEDED)
                    return normalized
                except DBAPIError:
                    _rollback_and_invalidate(connection)
                    raise
                finally:
                    if not connection.invalidated:
                        connection.rollback()
        except SqlExecutionError:
            raise
        except ResultNormalizationError as error:
            raise SqlExecutionError(EvaluationFailureCode.RESULT_NORMALIZATION_ERROR) from error
        except DBAPIError as error:
            if connection is not None and not connection.closed and not connection.invalidated:
                connection.invalidate()
            raise SqlExecutionError(_database_failure_code(error)) from error

    def _verify_connection_user(self, connection: Connection) -> None:
        current_user = connection.scalar(text("SELECT CURRENT_USER()"))
        if not isinstance(current_user, str):
            raise SqlExecutionError(EvaluationFailureCode.READONLY_TRANSACTION_FAILED)
        if current_user.split("@", maxsplit=1)[0] != self._settings.user:
            raise SqlExecutionError(EvaluationFailureCode.READONLY_TRANSACTION_FAILED)


def _database_failure_code(error: DBAPIError) -> EvaluationFailureCode:
    original_args = getattr(error.orig, "args", ())
    error_code = original_args[0] if original_args and isinstance(original_args[0], int) else None
    if error_code in _TIMEOUT_ERROR_CODES:
        return EvaluationFailureCode.QUERY_TIMEOUT
    if error_code in _PERMISSION_ERROR_CODES:
        return EvaluationFailureCode.DATABASE_PERMISSION_DENIED
    return EvaluationFailureCode.DATABASE_ERROR


def _rollback_and_invalidate(connection: Connection) -> None:
    """Best-effort rollback and always discard a DBAPI-failed connection."""
    try:
        connection.rollback()
    except DBAPIError:
        pass
    finally:
        connection.invalidate()


def _grants_are_readonly_for_database(grants: tuple[str, ...], database_name: str) -> bool:
    select_prefix = f"GRANT SELECT ON `{database_name.upper()}`.* TO "
    select_grants = tuple(grant for grant in grants if grant.startswith("GRANT SELECT ON"))
    return bool(
        select_grants
        and all(grant.startswith(select_prefix) for grant in select_grants)
        and all(grant.startswith(("GRANT USAGE ON", "GRANT SELECT ON")) for grant in grants)
    )
