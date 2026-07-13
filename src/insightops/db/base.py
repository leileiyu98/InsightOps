"""SQLAlchemy declarative metadata base."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for future SQLAlchemy models."""
