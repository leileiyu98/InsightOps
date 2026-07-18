"""Composition root for API and CLI Text2SQL demo execution."""

from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from insightops.benchmark.registry import load_benchmark_catalog
from insightops.core.config import Settings
from insightops.db.session import create_database_engine
from insightops.evaluation.execution import (
    ReadonlySqlExecutor,
    create_readonly_database_engine,
    load_readonly_database_settings,
)
from insightops.evaluation.runner import EvaluationRunner
from insightops.evaluation.suite import load_evaluation_suite
from insightops.query.providers.base import QueryProvider
from insightops.query.providers.fake import FakeQueryProvider
from insightops.query.providers.openai import OpenAIQueryProvider
from insightops.query.service import QueryService, QueryServiceError
from insightops.seed.dataset import load_seed_dataset
from insightops.seed.loader import DatasetLoader

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATASET_ROOT = PROJECT_ROOT / "data" / "seed" / "m1_2a"
BENCHMARK_ROOT = PROJECT_ROOT / "benchmarks" / "m1_2a"
CATALOG_PATH = BENCHMARK_ROOT / "cases.json"
SUITE_PATH = PROJECT_ROOT / "evaluations" / "m1_2b" / "suite.json"
BUSINESS_DEFINITION_PATH = PROJECT_ROOT / "docs" / "business-definitions-v1.md"


def build_query_service(
    settings: Settings,
    *,
    provider: QueryProvider | None = None,
) -> QueryService:
    """Compose the existing dataset, evaluator, and readonly execution boundaries."""
    try:
        dataset = load_seed_dataset(DATASET_ROOT)
        catalog = load_benchmark_catalog(CATALOG_PATH)
        suite = load_evaluation_suite(SUITE_PATH, CATALOG_PATH)
        readonly_settings = load_readonly_database_settings()
    except (OSError, ValidationError, ValueError):
        raise QueryServiceError(
            "evaluation_unavailable",
            "The deterministic query environment was not configured correctly.",
        ) from None
    selected_provider = provider or _provider_from_settings(settings)
    try:
        writer_engine = create_database_engine(settings)
        readonly_engine = create_readonly_database_engine(
            readonly_settings,
            timeout_ms=suite.execution_limits.timeout_ms,
        )
    except (SQLAlchemyError, ValueError):
        selected_provider.close()
        if "writer_engine" in locals():
            writer_engine.dispose()
        raise QueryServiceError(
            "evaluation_unavailable",
            "The deterministic query environment was not configured correctly.",
        ) from None
    readonly_executor = ReadonlySqlExecutor(
        readonly_engine,
        readonly_settings,
        suite.execution_limits,
    )
    return QueryService(
        provider=selected_provider,
        catalog=catalog,
        dataset=dataset,
        suite=suite,
        evaluator=EvaluationRunner(
            suite=suite,
            catalog=catalog,
            dataset=dataset,
            writer_engine=writer_engine,
            readonly_executor=readonly_executor,
            benchmark_root=BENCHMARK_ROOT,
            business_definition_path=BUSINESS_DEFINITION_PATH,
            app_env=settings.app_env,
        ),
        dataset_loader=DatasetLoader(writer_engine, dataset, app_env=settings.app_env),
        readonly_executor=readonly_executor,
        close_callbacks=(readonly_engine.dispose, writer_engine.dispose),
    )


def _provider_from_settings(settings: Settings) -> QueryProvider:
    if settings.query_provider == "fake":
        return FakeQueryProvider()
    if settings.openai_api_key is None or not settings.openai_api_key.get_secret_value():
        raise QueryServiceError(
            "provider_not_configured",
            "OPENAI_API_KEY is required when QUERY_PROVIDER=openai.",
        )
    return OpenAIQueryProvider(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_model,
        timeout_seconds=settings.openai_timeout_seconds,
    )
