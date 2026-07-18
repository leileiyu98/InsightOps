"""End-to-end Text2SQL API and service tests using fake generation and real MySQL."""

import os
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Protocol

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine

from insightops.app import create_app
from insightops.benchmark.registry import load_benchmark_catalog
from insightops.core.config import load_settings
from insightops.evaluation.contracts import EvaluationStatus
from insightops.evaluation.execution import (
    ReadonlyDatabaseSettings,
    ReadonlySqlExecutor,
    create_readonly_database_engine,
)
from insightops.evaluation.runner import EvaluationRunner
from insightops.evaluation.suite import load_evaluation_suite
from insightops.query.contracts import QueryRequest, StructuredCandidate
from insightops.query.providers.base import QueryProvider
from insightops.query.providers.fake import FakeQueryProvider
from insightops.query.service import QueryService
from insightops.query.summarization import BusinessSummarizer, SummaryError
from insightops.seed.dataset import load_seed_dataset
from insightops.seed.loader import DatasetLoader

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BENCHMARK_ROOT = PROJECT_ROOT / "benchmarks" / "m1_2a"
DATASET_ROOT = PROJECT_ROOT / "data" / "seed" / "m1_2a"
CATALOG_PATH = BENCHMARK_ROOT / "cases.json"
SUITE_PATH = PROJECT_ROOT / "evaluations" / "m1_2b" / "suite.json"
BUSINESS_DEFINITION_PATH = PROJECT_ROOT / "docs" / "business-definitions-v1.md"


class ServiceFactory(Protocol):
    def __call__(
        self,
        provider: QueryProvider,
        *,
        summarizer: BusinessSummarizer | None = None,
        close_callbacks: tuple[Callable[[], None], ...] = (),
    ) -> QueryService: ...


class FailingSummarizer(BusinessSummarizer):
    def summarize(
        self,
        columns: tuple[str, ...],
        rows: tuple[dict[str, str | int | bool | None], ...],
    ) -> str:
        raise SummaryError


class CloseTrackingProvider(FakeQueryProvider):
    def __init__(self) -> None:
        super().__init__()
        self.close_count = 0

    def close(self) -> None:
        self.close_count += 1


@pytest.fixture(scope="module")
def query_service_factory(database_engine: Engine) -> Generator[ServiceFactory]:
    writer_settings = load_settings()
    readonly_settings = ReadonlyDatabaseSettings(
        host=os.getenv("READONLY_DATABASE_HOST", writer_settings.database_host),
        port=int(os.getenv("READONLY_DATABASE_PORT", str(writer_settings.database_port))),
        name=os.getenv("READONLY_DATABASE_NAME", writer_settings.database_name),
        user=os.getenv("READONLY_DATABASE_USER", "insightops_readonly"),
        password=SecretStr(
            os.getenv("READONLY_DATABASE_PASSWORD", "local_readonly_password_change_me")
        ),
    )
    suite = load_evaluation_suite(SUITE_PATH, CATALOG_PATH)
    catalog = load_benchmark_catalog(CATALOG_PATH)
    dataset = load_seed_dataset(DATASET_ROOT)
    loader = DatasetLoader(database_engine, dataset, app_env="test")
    loader.load()
    readonly_engine = create_readonly_database_engine(
        readonly_settings,
        timeout_ms=suite.execution_limits.timeout_ms,
    )
    executor = ReadonlySqlExecutor(readonly_engine, readonly_settings, suite.execution_limits)

    def build(
        provider: QueryProvider,
        *,
        summarizer: BusinessSummarizer | None = None,
        close_callbacks: tuple[Callable[[], None], ...] = (),
    ) -> QueryService:
        return QueryService(
            provider=provider,
            catalog=catalog,
            dataset=dataset,
            suite=suite,
            evaluator=EvaluationRunner(
                suite=suite,
                catalog=catalog,
                dataset=dataset,
                writer_engine=database_engine,
                readonly_executor=executor,
                benchmark_root=BENCHMARK_ROOT,
                business_definition_path=BUSINESS_DEFINITION_PATH,
                app_env="test",
            ),
            dataset_loader=loader,
            readonly_executor=executor,
            summarizer=summarizer,
            close_callbacks=close_callbacks,
        )

    try:
        yield build
    finally:
        loader.verify()
        loader.unload()
        readonly_engine.dispose()


def test_executable_case_passes_complete_flow(query_service_factory: ServiceFactory) -> None:
    service = query_service_factory(FakeQueryProvider())

    response = service.query(
        QueryRequest(
            question="2025 年第二季度每个月的 SaaS Revenue 是多少？",
            case_id="GQ-SAA-002",
        )
    )

    assert response.action == "execute_sql"
    assert response.evaluation_status == EvaluationStatus.PASS.value
    assert response.failure_code is None
    assert response.columns == ("report_month", "saas_revenue")
    assert len(response.rows) == 3
    assert response.business_summary is not None


def test_clarification_case_passes(query_service_factory: ServiceFactory) -> None:
    provider = FakeQueryProvider(
        {
            "GQ-MKT-006": StructuredCandidate(
                action="request_clarification",
                clarification_code="attributed_revenue_type_required",
                clarification_question="这段展示文案不参与 benchmark truth 判定。",
            )
        }
    )
    service = query_service_factory(provider)

    response = service.query(
        QueryRequest(
            question="2025 年 6 月哪个活动的 ROAS 相比 4—5 月明显下降？",
            case_id="GQ-MKT-006",
        )
    )

    assert response.action == "request_clarification"
    assert response.evaluation_status == EvaluationStatus.PASS.value
    assert response.clarification_code == "attributed_revenue_type_required"
    assert response.clarification_question == "这段展示文案不参与 benchmark truth 判定。"


def test_executable_case_rejects_clarification_action(
    query_service_factory: ServiceFactory,
) -> None:
    provider = FakeQueryProvider(
        {
            "GQ-SAA-002": StructuredCandidate(
                action="request_clarification",
                clarification_code="metric_scope_required",
                clarification_question="请明确指标范围。",
            )
        }
    )

    response = query_service_factory(provider).query(
        QueryRequest(question="SaaS Revenue", case_id="GQ-SAA-002")
    )

    assert response.evaluation_status == EvaluationStatus.FAIL_ACTION.value
    assert response.failure_code == "expected_execute_sql"
    assert response.rows == ()


def test_clarification_case_rejects_wrong_policy_code(
    query_service_factory: ServiceFactory,
) -> None:
    provider = FakeQueryProvider(
        {
            "GQ-MKT-006": StructuredCandidate(
                action="request_clarification",
                clarification_code="metric_scope_required",
                clarification_question="请明确指标范围。",
            )
        }
    )

    response = query_service_factory(provider).query(
        QueryRequest(question="ROAS", case_id="GQ-MKT-006")
    )

    assert response.evaluation_status == EvaluationStatus.FAIL_ACTION.value
    assert response.failure_code == "clarification_code_mismatch"


def test_structurally_invalid_sql_is_not_executed(query_service_factory: ServiceFactory) -> None:
    provider = FakeQueryProvider(
        {"GQ-SAA-002": StructuredCandidate(action="execute_sql", sql="DROP TABLE subscription")}
    )

    response = query_service_factory(provider).query(
        QueryRequest(question="SaaS Revenue", case_id="GQ-SAA-002")
    )

    assert response.evaluation_status == EvaluationStatus.FAIL_STRUCTURE.value
    assert response.failure_code == "forbidden_ddl"
    assert response.rows == ()


def test_wrong_result_sql_gets_fail_result(query_service_factory: ServiceFactory) -> None:
    wrong_sql = """SELECT
        'wrong' AS report_month,
        CAST(COUNT(pa.invoice_payment_attempt_id) AS DECIMAL(19,4)) AS saas_revenue
    FROM organization AS o
    JOIN subscription AS s ON s.organization_id = o.organization_id
    JOIN subscription_invoice AS i ON i.subscription_id = s.subscription_id
    JOIN invoice_payment_attempt AS pa ON pa.subscription_invoice_id = i.subscription_invoice_id
    WHERE o.is_test = 0 AND s.is_test = 0 AND i.is_test = 0 AND pa.is_test = 0"""
    provider = FakeQueryProvider(
        {"GQ-SAA-002": StructuredCandidate(action="execute_sql", sql=wrong_sql)}
    )

    response = query_service_factory(provider).query(
        QueryRequest(question="SaaS Revenue", case_id="GQ-SAA-002")
    )

    assert response.evaluation_status == EvaluationStatus.FAIL_RESULT.value
    assert response.failure_code is not None


def test_free_query_is_safe_but_not_benchmark_scored(
    query_service_factory: ServiceFactory,
) -> None:
    provider = FakeQueryProvider(
        {
            None: StructuredCandidate(
                action="execute_sql",
                sql=(
                    "SELECT organization_name FROM organization "
                    "WHERE is_test = 0 ORDER BY organization_name LIMIT 1"
                ),
            )
        }
    )

    response = query_service_factory(provider).query(QueryRequest(question="列出一个企业名称"))

    assert response.evaluation_status == "not_benchmark_scored"
    assert response.columns == ("organization_name",)
    assert len(response.rows) == 1


@pytest.mark.parametrize(
    ("sql", "expected_code"),
    [
        ("DELETE FROM organization", "forbidden_dml"),
        ("DROP TABLE organization", "forbidden_ddl"),
        ("SELECT table_name FROM information_schema.tables", "forbidden_system_schema"),
        ("SELECT SLEEP(1) AS value", "forbidden_function"),
        ("SELECT value FROM unknown_table", "unknown_table"),
        ("SELECT * FROM organization", "wildcard_select"),
        (
            "SELECT organization_name FROM organization WHERE organization_id = :user_value",
            "unknown_bind_parameter",
        ),
    ],
)
def test_free_query_keeps_all_sql_safety_boundaries(
    query_service_factory: ServiceFactory,
    sql: str,
    expected_code: str,
) -> None:
    provider = FakeQueryProvider({None: StructuredCandidate(action="execute_sql", sql=sql)})

    response = query_service_factory(provider).query(QueryRequest(question="unsafe candidate"))

    assert response.evaluation_status == EvaluationStatus.FAIL_STRUCTURE.value
    assert response.failure_code == expected_code
    assert response.rows == ()


def test_api_provider_failure_is_stable_and_does_not_leak(
    query_service_factory: ServiceFactory,
) -> None:
    settings = load_settings()
    app = create_app(settings, query_service=query_service_factory(FakeQueryProvider(fail=True)))

    with TestClient(app) as client:
        response = client.post(
            "/v1/query",
            json={"question": "SaaS Revenue", "case_id": "GQ-SAA-002"},
        )

    serialized = response.text.lower()
    assert response.status_code == 502
    assert response.json()["code"] == "provider_unavailable"
    assert "traceback" not in serialized
    assert "api_key" not in serialized
    assert "password" not in serialized
    assert "oracle" not in serialized


def test_api_success_does_not_expose_internal_assets(query_service_factory: ServiceFactory) -> None:
    settings = load_settings()
    app = create_app(settings, query_service=query_service_factory(FakeQueryProvider()))

    with TestClient(app) as client:
        response = client.post(
            "/v1/query",
            json={
                "question": "2025 年第二季度每个月的 SaaS Revenue 是多少？",
                "case_id": "GQ-SAA-002",
            },
        )

    serialized = response.text.lower()
    assert response.status_code == 200
    for forbidden in (
        "api_key",
        "password",
        "gold_sql",
        "expected_result",
        "oracle_path",
        "traceback",
        "benchmarks/m1_2a",
        "expected/gq-saa-002.json",
        "sql/gq-saa-002.sql",
    ):
        assert forbidden not in serialized


def test_api_contract_rejects_extra_blank_and_invalid_case_id(
    query_service_factory: ServiceFactory,
) -> None:
    settings = load_settings()
    app = create_app(settings, query_service=query_service_factory(FakeQueryProvider()))

    with TestClient(app) as client:
        responses = (
            client.post("/v1/query", json={"question": "valid", "timeout": 999}),
            client.post("/v1/query", json={"question": "   "}),
            client.post("/v1/query", json={"question": "valid", "case_id": "bad"}),
        )

    assert all(response.status_code == 422 for response in responses)
    assert all(response.json()["code"] == "request_validation_error" for response in responses)
    assert len({response.json()["request_id"] for response in responses}) == len(responses)


def test_api_missing_case_and_request_ids_are_stable(
    query_service_factory: ServiceFactory,
) -> None:
    settings = load_settings()
    app = create_app(settings, query_service=query_service_factory(FakeQueryProvider()))

    with TestClient(app) as client:
        first = client.post(
            "/v1/query",
            json={"question": "unknown", "case_id": "GQ-AAA-999"},
        )
        second = client.post(
            "/v1/query",
            json={"question": "unknown", "case_id": "GQ-AAA-999"},
        )

    assert first.status_code == 404
    assert first.json()["code"] == "case_not_found"
    assert second.status_code == 404
    assert first.json()["request_id"] != second.json()["request_id"]


def test_health_does_not_require_openai_key_or_initialize_query_service() -> None:
    settings = load_settings().model_copy(update={"query_provider": "fake", "openai_api_key": None})
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert app.state.query_service is None


def test_fastapi_lifespan_closes_cached_service_once(
    query_service_factory: ServiceFactory,
) -> None:
    provider = CloseTrackingProvider()
    closed_resources: list[str] = []
    service = query_service_factory(
        provider,
        close_callbacks=(lambda: closed_resources.append("engines"),),
    )
    app = create_app(load_settings(), query_service=service)

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert provider.close_count == 0

    service.close()
    assert provider.close_count == 1
    assert closed_resources == ["engines"]


def test_dataset_is_unchanged_across_query(query_service_factory: ServiceFactory) -> None:
    service = query_service_factory(FakeQueryProvider())
    loader = service._dataset_loader  # noqa: SLF001
    before = loader.verify()

    service.query(QueryRequest(question="SaaS Revenue", case_id="GQ-SAA-002"))

    assert loader.verify() == before


def test_summary_failure_keeps_correct_sql_result(query_service_factory: ServiceFactory) -> None:
    service = query_service_factory(FakeQueryProvider(), summarizer=FailingSummarizer())

    response = service.query(QueryRequest(question="SaaS Revenue", case_id="GQ-SAA-002"))

    assert response.evaluation_status == EvaluationStatus.PASS.value
    assert len(response.rows) == 3
    assert response.business_summary is None
