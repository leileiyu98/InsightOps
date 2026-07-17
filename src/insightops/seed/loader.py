"""Transactional load, verify, and unload lifecycle for deterministic seed data."""

from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Connection, Engine, Table, delete, insert, select, text

from insightops.db.models import Base
from insightops.seed.contracts import SeedDataset, SeedRecord, SeedReference, SeedTable

ALLOWED_APP_ENVS = frozenset({"local", "test", "ci"})


class SeedDatasetError(RuntimeError):
    """Raised when seed lifecycle safety or integrity checks fail."""


class DatasetLoader:
    """Apply one versioned dataset without relying on migration data changes."""

    def __init__(self, engine: Engine, dataset: SeedDataset, *, app_env: str) -> None:
        self._engine = engine
        self._dataset = dataset
        self._app_env = app_env

    def load(self) -> dict[str, int]:
        """Insert missing records transactionally and verify exact existing records."""
        self._validate_environment()
        with self._engine.begin() as connection:
            self._validate_database_revision(connection)
            resolved: dict[tuple[str, str], int] = {}
            counts: dict[str, int] = {}
            for table_seed in self._ordered_tables():
                table = self._metadata_table(table_seed.table_name)
                for record in table_seed.records:
                    row = self._resolve_values(record, resolved)
                    existing = self._find_existing(connection, table, table_seed, row)
                    if existing is None:
                        result = connection.execute(insert(table).values(**row))
                        inserted_primary_key = result.inserted_primary_key
                        if inserted_primary_key is None:
                            raise SeedDatasetError(
                                f"database did not return a primary key for {table_seed.table_name}"
                            )
                        primary_key = inserted_primary_key[0]
                        if not isinstance(primary_key, int):
                            raise SeedDatasetError(
                                f"expected integer primary key for {table_seed.table_name}"
                            )
                    else:
                        self._assert_row_matches(table_seed.table_name, record, row, existing)
                        primary_key = self._primary_key_value(table, existing)
                    resolved[(table_seed.table_name, record.record_id)] = primary_key
                    counts[table_seed.table_name] = counts.get(table_seed.table_name, 0) + 1
            self._assert_expected_counts(counts)
            return counts

    def verify(self) -> dict[str, int]:
        """Verify every manifest-owned row and return exact per-table counts."""
        self._validate_environment()
        with self._engine.connect() as connection:
            self._validate_database_revision(connection)
            resolved: dict[tuple[str, str], int] = {}
            counts: dict[str, int] = {}
            for table_seed in self._ordered_tables():
                table = self._metadata_table(table_seed.table_name)
                for record in table_seed.records:
                    row = self._resolve_values(record, resolved)
                    existing = self._find_existing(connection, table, table_seed, row)
                    if existing is None:
                        raise SeedDatasetError(
                            f"missing seed record {table_seed.table_name}:{record.record_id}"
                        )
                    self._assert_row_matches(table_seed.table_name, record, row, existing)
                    resolved[(table_seed.table_name, record.record_id)] = self._primary_key_value(
                        table, existing
                    )
                    counts[table_seed.table_name] = counts.get(table_seed.table_name, 0) + 1
            self._assert_expected_counts(counts)
            return counts

    def unload(self) -> dict[str, int]:
        """Delete only exact manifest-owned rows in reverse dependency order."""
        self._validate_environment()
        with self._engine.begin() as connection:
            self._validate_database_revision(connection)
            resolved = self._resolve_existing_records(connection)
            counts: dict[str, int] = {}
            for table_seed in reversed(self._ordered_tables()):
                table = self._metadata_table(table_seed.table_name)
                primary_key_column = self._single_primary_key_column(table)
                for record in reversed(table_seed.records):
                    primary_key = resolved[(table_seed.table_name, record.record_id)]
                    result = connection.execute(
                        delete(table).where(primary_key_column == primary_key)
                    )
                    if result.rowcount != 1:
                        raise SeedDatasetError(
                            f"failed to unload {table_seed.table_name}:{record.record_id}"
                        )
                    counts[table_seed.table_name] = counts.get(table_seed.table_name, 0) + 1
            self._assert_expected_counts(counts)
            return counts

    def _resolve_existing_records(self, connection: Connection) -> dict[tuple[str, str], int]:
        resolved: dict[tuple[str, str], int] = {}
        for table_seed in self._ordered_tables():
            table = self._metadata_table(table_seed.table_name)
            for record in table_seed.records:
                row = self._resolve_values(record, resolved)
                existing = self._find_existing(connection, table, table_seed, row)
                if existing is None:
                    seed_key = f"{table_seed.table_name}:{record.record_id}"
                    raise SeedDatasetError(f"cannot unload missing seed record {seed_key}")
                self._assert_row_matches(table_seed.table_name, record, row, existing)
                resolved[(table_seed.table_name, record.record_id)] = self._primary_key_value(
                    table, existing
                )
        return resolved

    def _ordered_tables(self) -> tuple[SeedTable, ...]:
        return tuple(table for source in self._dataset.sources for table in source.tables)

    def _validate_environment(self) -> None:
        if self._app_env not in ALLOWED_APP_ENVS:
            raise SeedDatasetError(f"seed lifecycle is disabled for APP_ENV={self._app_env!r}")

    def _validate_database_revision(self, connection: Connection) -> None:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        if revision != self._dataset.manifest.schema_revision:
            raise SeedDatasetError(
                f"dataset requires schema revision {self._dataset.manifest.schema_revision}, "
                f"database is {revision}"
            )

    def _metadata_table(self, table_name: str) -> Table:
        table = Base.metadata.tables.get(table_name)
        if table is None:
            raise SeedDatasetError(f"dataset references unknown ORM table {table_name}")
        return table

    def _resolve_values(
        self,
        record: SeedRecord,
        resolved: Mapping[tuple[str, str], int],
    ) -> dict[str, str | int | bool | None]:
        values: dict[str, str | int | bool | None] = {}
        for column_name, value in record.values.items():
            if isinstance(value, SeedReference):
                key = (value.table, value.record_id)
                if key not in resolved:
                    raise SeedDatasetError(f"seed reference is not yet resolvable: {key}")
                values[column_name] = resolved[key]
            else:
                values[column_name] = value
        return values

    def _find_existing(
        self,
        connection: Connection,
        table: Table,
        table_seed: SeedTable,
        row: Mapping[str, str | int | bool | None],
    ) -> Mapping[str, Any] | None:
        conditions = []
        for column_name in table_seed.match_columns:
            if column_name not in table.c:
                raise SeedDatasetError(
                    f"unknown match column {table_seed.table_name}.{column_name}"
                )
            conditions.append(table.c[column_name] == row[column_name])
        matches = connection.execute(select(table).where(*conditions).limit(2)).mappings().all()
        if len(matches) > 1:
            raise SeedDatasetError(
                f"match columns are not unique for {table_seed.table_name}: "
                f"{table_seed.match_columns}"
            )
        return dict(matches[0]) if matches else None

    def _assert_row_matches(
        self,
        table_name: str,
        record: SeedRecord,
        expected: Mapping[str, str | int | bool | None],
        actual: Mapping[str, Any],
    ) -> None:
        mismatches = [
            column_name
            for column_name, expected_value in expected.items()
            if not self._values_equal(actual[column_name], expected_value)
        ]
        if mismatches:
            raise SeedDatasetError(
                f"seed record conflicts with database {table_name}:{record.record_id}; "
                f"columns={mismatches}"
            )

    @staticmethod
    def _values_equal(actual: Any, expected: str | int | bool | None) -> bool:
        if isinstance(actual, Decimal):
            return actual == Decimal(str(expected))
        if isinstance(actual, datetime) and isinstance(expected, str):
            normalized = expected.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(UTC).replace(tzinfo=None)
            return actual == parsed
        if isinstance(actual, date) and isinstance(expected, str):
            return actual == date.fromisoformat(expected)
        if isinstance(actual, bool):
            return actual is bool(expected)
        return bool(actual == expected)

    def _primary_key_value(self, table: Table, row: Mapping[str, Any]) -> int:
        value = row[self._single_primary_key_column(table).name]
        if not isinstance(value, int):
            raise SeedDatasetError(f"expected integer primary key for {table.name}")
        return value

    @staticmethod
    def _single_primary_key_column(table: Table) -> Any:
        columns = list(table.primary_key.columns)
        if len(columns) != 1:
            raise SeedDatasetError(
                f"seed loader requires a single-column primary key: {table.name}"
            )
        return columns[0]

    def _assert_expected_counts(self, counts: Mapping[str, int]) -> None:
        expected = self._dataset.manifest.expected_row_counts
        normalized = {table_name: counts.get(table_name, 0) for table_name in expected}
        if normalized != expected:
            raise SeedDatasetError(
                f"seed row count mismatch: expected {expected}, got {normalized}"
            )
