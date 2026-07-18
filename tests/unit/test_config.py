"""Tests for environment-backed settings."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from insightops.core.config import load_settings
from insightops.query.providers.fake import FakeQueryProvider
from insightops.query.runtime import _provider_from_settings
from insightops.query.service import QueryServiceError

SETTING_NAMES = (
    "APP_NAME",
    "APP_ENV",
    "APP_DEBUG",
    "DATABASE_HOST",
    "DATABASE_PORT",
    "DATABASE_NAME",
    "DATABASE_USER",
    "DATABASE_PASSWORD",
)


def set_required_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set a complete deterministic environment for a settings instance."""
    values = {
        "APP_NAME": "InsightOps Test",
        "APP_ENV": "test",
        "APP_DEBUG": "true",
        "DATABASE_HOST": "db.example.test",
        "DATABASE_PORT": "3307",
        "DATABASE_NAME": "insightops_test",
        "DATABASE_USER": "test_user",
        "DATABASE_PASSWORD": "test_password",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_settings_read_and_convert_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_environment(monkeypatch)

    settings = load_settings(env_file=None)

    assert settings.app_name == "InsightOps Test"
    assert settings.app_env == "test"
    assert settings.app_debug is True
    assert settings.database_port == 3307
    assert settings.query_provider == "fake"
    assert settings.openai_model == "gpt-5.6-sol"
    assert settings.openai_api_key is None


def test_environment_overrides_dotenv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            (
                "APP_NAME=Name from file",
                "APP_ENV=test",
                "APP_DEBUG=false",
                "DATABASE_HOST=localhost",
                "DATABASE_PORT=3306",
                "DATABASE_NAME=insightops_test",
                "DATABASE_USER=test_user",
                "DATABASE_PASSWORD=file_password",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("APP_NAME", "Name from environment")

    settings = load_settings(env_file=env_file)

    assert settings.app_name == "Name from environment"


def test_missing_required_settings_fail_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in SETTING_NAMES:
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValidationError):
        load_settings(env_file=None)


def test_password_is_redacted_from_settings_representation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_required_environment(monkeypatch)

    settings = load_settings(env_file=None)

    assert "test_password" not in repr(settings)
    assert "**********" in repr(settings)


def test_openai_model_is_allowlisted(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_environment(monkeypatch)
    monkeypatch.setenv("OPENAI_MODEL", "user-supplied-model")

    with pytest.raises(ValidationError):
        load_settings(env_file=None)


def test_api_key_is_required_only_for_selected_openai_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_required_environment(monkeypatch)
    settings = load_settings(env_file=None)

    assert isinstance(_provider_from_settings(settings), FakeQueryProvider)

    with pytest.raises(QueryServiceError) as captured:
        _provider_from_settings(settings.model_copy(update={"query_provider": "openai"}))

    assert captured.value.code == "provider_not_configured"
