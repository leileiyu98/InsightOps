"""SQLAlchemy engine and session factories."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from insightops.core.config import Settings


def create_database_engine(settings: Settings) -> Engine:
    """Create a lazy SQLAlchemy engine from validated settings."""
    return create_engine(settings.database_url, pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a typed session factory bound to the supplied engine."""
    return sessionmaker(bind=engine, expire_on_commit=False)
