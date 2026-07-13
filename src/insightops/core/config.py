"""Environment-backed application configuration."""

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    """Validated settings loaded from environment variables or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str
    app_env: str
    app_debug: bool
    database_host: str
    database_port: int
    database_name: str
    database_user: str
    database_password: SecretStr

    @property
    def database_url(self) -> URL:
        """Build a MySQL URL without embedding credentials in source code."""
        return URL.create(
            drivername="mysql+pymysql",
            username=self.database_user,
            password=self.database_password.get_secret_value(),
            host=self.database_host,
            port=self.database_port,
            database=self.database_name,
        )


def load_settings(*, env_file: str | Path | None = ".env") -> Settings:
    """Load validated settings from environment sources without global caching."""
    # Mypy models BaseSettings like a normal Pydantic model and cannot see values supplied
    # by environment sources. Runtime validation still requires every declared field.
    return Settings(_env_file=env_file)  # type: ignore[call-arg]
