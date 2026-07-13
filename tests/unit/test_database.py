"""Tests for SQLAlchemy configuration factories."""

from pydantic import SecretStr
from sqlalchemy.orm import Session

from insightops.core.config import Settings
from insightops.db.session import create_database_engine, create_session_factory


def make_settings(*, password: str = "test_password") -> Settings:
    """Create deterministic settings without reading the process environment."""
    return Settings(
        app_name="InsightOps Test",
        app_env="test",
        app_debug=False,
        database_host="unreachable.example.test",
        database_port=3306,
        database_name="insightops_test",
        database_user="test_user",
        database_password=SecretStr(password),
    )


def test_database_url_uses_mysql_pymysql_and_escapes_password() -> None:
    settings = make_settings(password="p@ss/word:value")

    rendered_url = settings.database_url.render_as_string(hide_password=False)

    assert settings.database_url.drivername == "mysql+pymysql"
    assert "p%40ss%2Fword%3Avalue" in rendered_url
    assert "p@ss/word:value" not in str(settings.database_url)


def test_engine_and_session_factory_are_created_without_connecting() -> None:
    engine = create_database_engine(make_settings())

    try:
        factory = create_session_factory(engine)

        assert engine.dialect.name == "mysql"
        assert issubclass(factory.class_, Session)
        assert factory.kw["bind"] is engine
        assert factory.kw["expire_on_commit"] is False
    finally:
        engine.dispose()
