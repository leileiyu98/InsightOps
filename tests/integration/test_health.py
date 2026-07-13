"""Integration tests for the FastAPI application boundary."""

from fastapi.testclient import TestClient
from pydantic import SecretStr

from insightops.app import create_app
from insightops.core.config import Settings


def make_test_client() -> TestClient:
    """Build an isolated application client with explicit test settings."""
    settings = Settings(
        app_name="InsightOps Test",
        app_env="test",
        app_debug=False,
        database_host="localhost",
        database_port=3306,
        database_name="insightops_test",
        database_user="test_user",
        database_password=SecretStr("test_password"),
    )
    return TestClient(create_app(settings))


def test_health_returns_ok() -> None:
    with make_test_client() as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ok"}


def test_unknown_route_returns_not_found() -> None:
    with make_test_client() as client:
        response = client.get("/not-found")

    assert response.status_code == 404
