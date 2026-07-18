"""SQLAlchemy engine and session factories."""

from collections.abc import Mapping

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry

from insightops.core.config import Settings


def _set_mysql_session_timezone(
    dbapi_connection: DBAPIConnection,
    _connection_record: ConnectionPoolEntry,
) -> None:
    """Set every newly created MySQL connection to the required UTC session timezone."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("SET time_zone = '+00:00'")
    finally:
        cursor.close()


def create_database_engine(settings: Settings) -> Engine:
    """Create a lazy SQLAlchemy engine from validated settings."""
    return create_mysql_engine(settings.database_url)


def create_mysql_engine(
    database_url: URL,
    *,
    connect_args: Mapping[str, object] | None = None,
) -> Engine:
    """Create a UTC MySQL engine for an explicitly supplied database identity."""
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args=dict(connect_args or {}),
    )
    event.listen(engine, "connect", _set_mysql_session_timezone)
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a typed session factory bound to the supplied engine."""
    return sessionmaker(bind=engine, expire_on_commit=False)
