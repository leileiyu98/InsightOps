"""Production React static-hosting integration tests."""

from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from pydantic import SecretStr

from insightops.app import create_app
from insightops.core.config import Settings
from insightops.query.contracts import QueryResponse
from insightops.query.service import QueryService


def _settings() -> Settings:
    return Settings(
        app_name="InsightOps Test",
        app_env="test",
        app_debug=False,
        database_host="localhost",
        database_port=3306,
        database_name="insightops_test",
        database_user="test_user",
        database_password=SecretStr("test_password"),
    )


def test_root_returns_built_react_index_and_assets(tmp_path: Path) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    (tmp_path / "index.html").write_text(
        '<!doctype html><div id="root"></div><script src="/assets/app.js"></script>',
        encoding="utf-8",
    )
    (assets / "app.js").write_text("document.title = 'InsightOps';", encoding="utf-8")

    with TestClient(create_app(_settings(), frontend_dist=tmp_path)) as client:
        index_response = client.get("/")
        asset_response = client.get("/assets/app.js")

    assert index_response.status_code == 200
    assert '<div id="root"></div>' in index_response.text
    assert index_response.headers["content-type"].startswith("text/html")
    assert asset_response.status_code == 200
    assert asset_response.text == "document.title = 'InsightOps';"
    assert "javascript" in asset_response.headers["content-type"]


def test_missing_build_keeps_health_and_query_api_available(tmp_path: Path) -> None:
    service = MagicMock(spec=QueryService)
    service.query.return_value = QueryResponse(
        request_id="request-1",
        question="列出一个企业名称",
        action="execute_sql",
        generated_sql="SELECT organization_name FROM organization LIMIT 1",
        evaluation_status="not_benchmark_scored",
        columns=("organization_name",),
        rows=({"organization_name": "Acme"},),
        business_summary="Returned 1 row.",
        provider="fake",
        model="deterministic-v1",
    )

    with TestClient(
        create_app(_settings(), query_service=service, frontend_dist=tmp_path)
    ) as client:
        root_response = client.get("/")
        health_response = client.get("/health")
        query_response = client.post("/v1/query", json={"question": "列出一个企业名称"})

    assert root_response.status_code == 503
    assert root_response.text == (
        "InsightOps frontend not built. Run `npm run build` in frontend/."
    )
    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}
    assert query_response.status_code == 200
    assert query_response.json()["evaluation_status"] == "not_benchmark_scored"
    service.query.assert_called_once()
