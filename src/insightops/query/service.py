"""Application service for bounded Text2SQL generation, evaluation, and execution."""

from collections.abc import Callable
from uuid import uuid4

from insightops.benchmark.contracts import BenchmarkCatalog, BenchmarkStatus
from insightops.benchmark.registry import public_benchmark_cases
from insightops.evaluation.contracts import (
    EvaluationStatus,
    EvaluationSuiteManifest,
    ExecuteSqlResponse,
    NormalizedResult,
    RequestClarificationResponse,
)
from insightops.evaluation.execution import ReadonlySqlExecutor, SqlExecutionError
from insightops.evaluation.runner import EvaluationRunner
from insightops.evaluation.sql_analysis import analyze_candidate_sql
from insightops.query.context import build_query_context
from insightops.query.contracts import (
    QueryRequest,
    QueryResponse,
    QueryScalar,
    StructuredCandidate,
)
from insightops.query.providers.base import ProviderError, QueryProvider
from insightops.query.summarization import BusinessSummarizer, SummaryError
from insightops.seed.contracts import SeedDataset
from insightops.seed.loader import DatasetLoader, SeedDatasetError

_FREE_QUERY_CASE_ID = "GQ-FRE-000"


class QueryServiceError(RuntimeError):
    """Stable application error that does not retain external exception text."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(code)


class QueryService:
    """Orchestrate one query without allowing the provider to execute SQL directly."""

    def __init__(
        self,
        *,
        provider: QueryProvider,
        catalog: BenchmarkCatalog,
        dataset: SeedDataset,
        suite: EvaluationSuiteManifest,
        evaluator: EvaluationRunner,
        dataset_loader: DatasetLoader,
        readonly_executor: ReadonlySqlExecutor,
        summarizer: BusinessSummarizer | None = None,
        close_callbacks: tuple[Callable[[], None], ...] = (),
    ) -> None:
        self._provider = provider
        self._catalog = catalog
        self._dataset = dataset
        self._evaluator = evaluator
        self._dataset_loader = dataset_loader
        self._readonly_executor = readonly_executor
        self._summarizer = summarizer or BusinessSummarizer()
        self._close_callbacks = close_callbacks
        self._closed = False
        self._public_cases = {case.case_id: case for case in public_benchmark_cases(catalog)}
        self._catalog_cases = {case.case_id: case for case in catalog.cases}
        self._suite_cases = {case.case_id: case for case in suite.cases}

    def close(self) -> None:
        """Release provider and engine resources exactly once."""
        if self._closed:
            return
        self._closed = True
        errors: list[Exception] = []
        try:
            self._provider.close()
        except Exception as error:
            errors.append(error)
        for callback in self._close_callbacks:
            try:
                callback()
            except Exception as error:
                errors.append(error)
        if errors:
            raise ExceptionGroup("Query service resource cleanup failed.", errors)

    def query(self, request: QueryRequest) -> QueryResponse:
        """Generate and safely route one candidate to scored or unscored execution."""
        request_id = str(uuid4())
        public_case = None
        clarification_code = None
        if request.case_id is not None:
            public_case = self._public_cases.get(request.case_id)
            catalog_case = self._catalog_cases.get(request.case_id)
            suite_case = self._suite_cases.get(request.case_id)
            if public_case is None or catalog_case is None or suite_case is None:
                raise QueryServiceError(
                    "case_not_found", "The requested benchmark case was not found."
                )
            if catalog_case.status is BenchmarkStatus.DEFERRED:
                raise QueryServiceError(
                    "case_not_available",
                    "The requested benchmark case is deferred at the current schema revision.",
                )
            clarification_code = suite_case.clarification_code

        context = build_query_context(
            question=request.question,
            case=public_case,
            manifest=self._dataset.manifest,
            clarification_code=clarification_code,
        )
        try:
            generated = self._provider.generate(context)
        except ProviderError as error:
            raise QueryServiceError(
                error.code, "The model provider could not generate a result."
            ) from None

        if request.case_id is None:
            return self._run_unscored(
                request_id,
                request,
                generated.candidate,
                generated.provider,
                generated.model,
            )
        return self._run_benchmark(
            request_id,
            request,
            generated.candidate,
            generated.provider,
            generated.model,
        )

    def _run_benchmark(
        self,
        request_id: str,
        request: QueryRequest,
        candidate: StructuredCandidate,
        provider: str,
        model: str,
    ) -> QueryResponse:
        if request.case_id is None:
            raise QueryServiceError("provider_invalid_response", "The provider result was invalid.")
        response: ExecuteSqlResponse | RequestClarificationResponse
        if candidate.action == "request_clarification":
            assert candidate.clarification_code is not None
            assert candidate.clarification_question is not None
            response = RequestClarificationResponse(
                action="request_clarification",
                case_id=request.case_id,
                clarification_code=candidate.clarification_code,
            )
        else:
            assert candidate.sql is not None
            response = ExecuteSqlResponse(
                action="execute_sql",
                case_id=request.case_id,
                sql=candidate.sql,
            )

        evaluated = self._evaluator.run_case(response)
        if evaluated.abort_code is not None or evaluated.result is None:
            raise QueryServiceError(
                "evaluation_unavailable",
                "The deterministic evaluation environment was unavailable.",
            )
        result = evaluated.result
        if candidate.action == "request_clarification":
            assert candidate.clarification_code is not None
            assert candidate.clarification_question is not None
            return QueryResponse(
                request_id=request_id,
                question=request.question,
                action="request_clarification",
                clarification_code=candidate.clarification_code,
                clarification_question=candidate.clarification_question,
                evaluation_status=result.status.value,
                failure_code=result.failure_code.value if result.failure_code is not None else None,
                provider=provider,
                model=model,
            )

        assert candidate.sql is not None
        columns, rows = _public_result(evaluated.actual_result)
        summary = None
        if result.status is EvaluationStatus.PASS and evaluated.actual_result is not None:
            summary = self._safe_summary(columns, rows)
        return QueryResponse(
            request_id=request_id,
            question=request.question,
            action="execute_sql",
            generated_sql=candidate.sql,
            evaluation_status=result.status.value,
            failure_code=result.failure_code.value if result.failure_code is not None else None,
            columns=columns,
            rows=rows,
            business_summary=summary,
            provider=provider,
            model=model,
        )

    def _run_unscored(
        self,
        request_id: str,
        request: QueryRequest,
        candidate: StructuredCandidate,
        provider: str,
        model: str,
    ) -> QueryResponse:
        if candidate.action == "request_clarification":
            assert candidate.clarification_code is not None
            assert candidate.clarification_question is not None
            return QueryResponse(
                request_id=request_id,
                question=request.question,
                action="request_clarification",
                clarification_code=candidate.clarification_code,
                clarification_question=candidate.clarification_question,
                evaluation_status="not_benchmark_scored",
                provider=provider,
                model=model,
            )

        assert candidate.sql is not None
        try:
            self._dataset_loader.verify()
            self._readonly_executor.verify_identity()
        except (SeedDatasetError, SqlExecutionError):
            raise QueryServiceError(
                "evaluation_unavailable",
                "The readonly query environment was unavailable.",
            ) from None

        analysis = analyze_candidate_sql(
            case_id=_FREE_QUERY_CASE_ID,
            sql=candidate.sql,
            required_tables=(),
            allowed_tables=self._dataset.manifest.table_order,
            allowed_bind_parameters=(),
            enforce_required_tables=False,
        )
        if analysis.violations:
            return QueryResponse(
                request_id=request_id,
                question=request.question,
                action="execute_sql",
                generated_sql=candidate.sql,
                evaluation_status=EvaluationStatus.FAIL_STRUCTURE.value,
                failure_code=analysis.violations[0].value,
                provider=provider,
                model=model,
            )
        try:
            actual = self._readonly_executor.execute(candidate.sql, {})
        except SqlExecutionError as error:
            return QueryResponse(
                request_id=request_id,
                question=request.question,
                action="execute_sql",
                generated_sql=candidate.sql,
                evaluation_status=EvaluationStatus.FAIL_EXECUTION.value,
                failure_code=error.failure_code.value,
                provider=provider,
                model=model,
            )
        finally:
            try:
                self._dataset_loader.verify()
            except SeedDatasetError:
                raise QueryServiceError(
                    "dataset_verification_failed",
                    "Dataset verification failed after readonly execution.",
                ) from None

        columns, rows = _public_result(actual)
        return QueryResponse(
            request_id=request_id,
            question=request.question,
            action="execute_sql",
            generated_sql=candidate.sql,
            evaluation_status="not_benchmark_scored",
            columns=columns,
            rows=rows,
            business_summary=self._safe_summary(columns, rows),
            provider=provider,
            model=model,
        )

    def _safe_summary(
        self,
        columns: tuple[str, ...],
        rows: tuple[dict[str, QueryScalar], ...],
    ) -> str | None:
        try:
            return self._summarizer.summarize(columns, rows)
        except SummaryError:
            return None


def _public_result(
    result: NormalizedResult | None,
) -> tuple[tuple[str, ...], tuple[dict[str, QueryScalar], ...]]:
    if result is None:
        return (), ()
    rows = tuple(
        {column: cell.value for column, cell in zip(result.columns, row, strict=True)}
        for row in result.rows
    )
    return result.columns, rows
