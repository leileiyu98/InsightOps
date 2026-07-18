"""CLI contract and resource lifecycle tests for the Text2SQL demo."""

import json
from unittest.mock import MagicMock, patch

import pytest

from insightops.query.__main__ import main
from insightops.query.contracts import QueryResponse
from insightops.query.service import QueryService, QueryServiceError


def test_cli_closes_service_and_emits_oracle_free_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = MagicMock(spec=QueryService)
    service.query.return_value = QueryResponse(
        request_id="request-1",
        question="列出一个企业名称",
        action="execute_sql",
        generated_sql="SELECT organization_name FROM organization LIMIT 1",
        evaluation_status="not_benchmark_scored",
        columns=("organization_name",),
        rows=({"organization_name": "示例企业"},),
        business_summary="返回 1 行。",
        provider="fake",
        model="deterministic-v1",
    )

    with (
        patch("sys.argv", ["insightops.query", "--question", "列出一个企业名称"]),
        patch("insightops.query.__main__.load_settings", return_value=MagicMock()),
        patch("insightops.query.__main__.build_query_service", return_value=service),
    ):
        main()

    payload = json.loads(capsys.readouterr().out)
    service.close.assert_called_once_with()
    assert payload["evaluation_status"] == "not_benchmark_scored"
    serialized = json.dumps(payload).lower()
    for forbidden in (
        "gold_sql",
        "expected_result",
        "benchmarks/m1_2a",
        "sql/gq-saa-002.sql",
        "expected/gq-saa-002.json",
    ):
        assert forbidden not in serialized


def test_cli_closes_service_on_application_error() -> None:
    service = MagicMock(spec=QueryService)
    service.query.side_effect = QueryServiceError(
        "provider_unavailable",
        "The model provider could not generate a result.",
    )

    with (
        patch("sys.argv", ["insightops.query", "--question", "query"]),
        patch("insightops.query.__main__.load_settings", return_value=MagicMock()),
        patch("insightops.query.__main__.build_query_service", return_value=service),
        pytest.raises(SystemExit) as captured,
    ):
        main()

    service.close.assert_called_once_with()
    assert "provider_unavailable" in str(captured.value)
