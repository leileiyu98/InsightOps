"""End-to-end deterministic evaluation orchestration with isolated oracle access."""

import hashlib
import time
from pathlib import Path

from sqlalchemy import Engine

from insightops.benchmark.contracts import BenchmarkCase, BenchmarkCatalog
from insightops.benchmark.registry import (
    load_expected_result,
    validate_benchmark_bundle,
)
from insightops.canonical import canonical_json_digest
from insightops.evaluation.comparison import compare_normalized_results
from insightops.evaluation.contracts import (
    CandidateAction,
    CandidateSubmission,
    CaseEvaluationResult,
    EvaluationAbortCode,
    EvaluationFailureCode,
    EvaluationReport,
    EvaluationStatus,
    EvaluationSuiteCase,
    EvaluationSuiteManifest,
    ExecuteSqlResponse,
    ExpectedAction,
    RequestClarificationResponse,
    StageEvaluationResult,
    StageStatus,
)
from insightops.evaluation.execution import ReadonlySqlExecutor, SqlExecutionError
from insightops.evaluation.normalization import (
    ResultNormalizationError,
    normalize_expected_result,
)
from insightops.evaluation.reporting import (
    build_aborted_report,
    build_case_result,
    build_evaluation_report,
)
from insightops.evaluation.sql_analysis import analyze_candidate_sql
from insightops.evaluation.suite import (
    validate_candidate_submission,
    validate_expected_column_type_bindings,
)
from insightops.seed.contracts import SeedDataset
from insightops.seed.loader import DatasetLoader, SeedDatasetError

_STRUCTURE_FAILURE_PRIORITY = (
    EvaluationFailureCode.PARSE_ERROR,
    EvaluationFailureCode.MULTIPLE_STATEMENTS,
    EvaluationFailureCode.FORBIDDEN_DML,
    EvaluationFailureCode.FORBIDDEN_DDL,
    EvaluationFailureCode.FORBIDDEN_COMMAND,
    EvaluationFailureCode.NON_QUERY_STATEMENT,
    EvaluationFailureCode.FORBIDDEN_FILE_OPERATION,
    EvaluationFailureCode.FORBIDDEN_LOCKING_CLAUSE,
    EvaluationFailureCode.FORBIDDEN_FUNCTION,
    EvaluationFailureCode.FORBIDDEN_USER_VARIABLE,
    EvaluationFailureCode.FORBIDDEN_SYSTEM_SCHEMA,
    EvaluationFailureCode.UNKNOWN_TABLE,
    EvaluationFailureCode.MISSING_REQUIRED_TABLE,
    EvaluationFailureCode.EXTRA_TABLE,
    EvaluationFailureCode.WILDCARD_SELECT,
    EvaluationFailureCode.UNKNOWN_BIND_PARAMETER,
)


class EvaluationRunner:
    """Route all 48 suite cases through deterministic evaluation stages."""

    def __init__(
        self,
        *,
        suite: EvaluationSuiteManifest,
        catalog: BenchmarkCatalog,
        dataset: SeedDataset,
        writer_engine: Engine,
        readonly_executor: ReadonlySqlExecutor,
        benchmark_root: Path,
        business_definition_path: Path,
        app_env: str,
    ) -> None:
        self._suite = suite
        self._catalog = catalog
        self._dataset = dataset
        self._readonly_executor = readonly_executor
        self._benchmark_root = benchmark_root.resolve()
        self._business_definition_path = business_definition_path
        self._dataset_loader = DatasetLoader(writer_engine, dataset, app_env=app_env)

    def run(self, submission: CandidateSubmission) -> EvaluationReport:
        """Evaluate a complete submission and verify seed data before and after execution."""
        started = time.monotonic()
        try:
            validate_candidate_submission(
                submission,
                self._suite,
                validate_actions=False,
            )
        except ValueError:
            return self._abort(started, EvaluationAbortCode.INVALID_SUBMISSION)

        try:
            validate_benchmark_bundle(
                self._benchmark_root,
                self._catalog,
                self._dataset.manifest,
                self._business_definition_path,
            )
            validate_expected_column_type_bindings(
                self._suite,
                self._catalog,
                self._benchmark_root,
            )
        except ValueError:
            return self._abort(started, EvaluationAbortCode.ORACLE_DIGEST_MISMATCH)

        try:
            self._dataset_loader.verify()
        except SeedDatasetError:
            return self._abort(
                started,
                EvaluationAbortCode.DATASET_VERIFICATION_FAILED,
            )

        try:
            self._readonly_executor.verify_identity()
        except SqlExecutionError:
            return self._abort(
                started,
                EvaluationAbortCode.READONLY_IDENTITY_VERIFICATION_FAILED,
            )

        suite_cases = {case.case_id: case for case in self._suite.cases}
        catalog_cases = {case.case_id: case for case in self._catalog.cases}
        responses = {response.case_id: response for response in submission.responses}
        try:
            results = tuple(
                self._evaluate_case(
                    suite_cases[case_id],
                    catalog_cases[case_id],
                    responses.get(case_id),
                )
                for case_id in sorted(suite_cases)
            )
        except (ResultNormalizationError, ValueError):
            return self._abort(
                started,
                EvaluationAbortCode.INTERNAL_CONTRACT_VIOLATION,
            )

        try:
            self._dataset_loader.verify()
        except SeedDatasetError:
            return self._abort(
                started,
                EvaluationAbortCode.DATASET_VERIFICATION_FAILED,
            )

        return build_evaluation_report(
            suite=self._suite,
            submission=submission,
            case_results=results,
            duration_ms=_duration_ms(started),
        )

    def _evaluate_case(
        self,
        suite_case: EvaluationSuiteCase,
        catalog_case: BenchmarkCase,
        response: ExecuteSqlResponse | RequestClarificationResponse | None,
    ) -> CaseEvaluationResult:
        if suite_case.expected_action is ExpectedAction.DEFERRED:
            return build_case_result(
                case_id=suite_case.case_id,
                expected_action=ExpectedAction.DEFERRED,
                actual_action=None,
                status=EvaluationStatus.NOT_EVALUATED,
                failure_code=EvaluationFailureCode.DEFERRED_SCHEMA_DEPENDENCY,
            )
        if response is None:
            raise ValueError("validated submission is missing a response")
        if suite_case.expected_action is ExpectedAction.REQUEST_CLARIFICATION:
            return self._evaluate_clarification(suite_case, response)
        return self._evaluate_sql(suite_case, catalog_case, response)

    def _evaluate_clarification(
        self,
        suite_case: EvaluationSuiteCase,
        response: ExecuteSqlResponse | RequestClarificationResponse,
    ) -> CaseEvaluationResult:
        if not isinstance(response, RequestClarificationResponse):
            return _action_failure(
                suite_case,
                CandidateAction.EXECUTE_SQL,
                EvaluationFailureCode.EXPECTED_REQUEST_CLARIFICATION,
            )
        if response.clarification_code != suite_case.clarification_code:
            return _action_failure(
                suite_case,
                CandidateAction.REQUEST_CLARIFICATION,
                EvaluationFailureCode.CLARIFICATION_CODE_MISMATCH,
            )
        return build_case_result(
            case_id=suite_case.case_id,
            expected_action=suite_case.expected_action,
            actual_action=CandidateAction.REQUEST_CLARIFICATION,
            status=EvaluationStatus.PASS,
            failure_code=None,
            action_result=StageEvaluationResult(
                status=StageStatus.PASS,
                result_digest=canonical_json_digest(response.model_dump(mode="json")),
            ),
        )

    def _evaluate_sql(
        self,
        suite_case: EvaluationSuiteCase,
        catalog_case: BenchmarkCase,
        response: ExecuteSqlResponse | RequestClarificationResponse,
    ) -> CaseEvaluationResult:
        if not isinstance(response, ExecuteSqlResponse):
            return _action_failure(
                suite_case,
                CandidateAction.REQUEST_CLARIFICATION,
                EvaluationFailureCode.EXPECTED_EXECUTE_SQL,
            )

        candidate_sql_digest = hashlib.sha256(response.sql.encode("utf-8")).hexdigest()
        action_result = StageEvaluationResult(
            status=StageStatus.PASS,
            result_digest=canonical_json_digest(
                {"action": response.action, "case_id": response.case_id}
            ),
        )
        analysis = analyze_candidate_sql(
            case_id=suite_case.case_id,
            sql=response.sql,
            required_tables=catalog_case.required_tables,
            allowed_tables=self._dataset.manifest.table_order,
            allowed_bind_parameters=catalog_case.parameters,
        )
        if analysis.violations:
            primary = _primary_structure_failure(analysis.violations)
            secondary = tuple(code for code in analysis.violations if code is not primary)
            return build_case_result(
                case_id=suite_case.case_id,
                expected_action=suite_case.expected_action,
                actual_action=CandidateAction.EXECUTE_SQL,
                status=EvaluationStatus.FAIL_STRUCTURE,
                failure_code=primary,
                secondary_codes=secondary,
                action_result=action_result,
                structure_result=StageEvaluationResult(
                    status=StageStatus.FAIL,
                    failure_code=primary,
                    result_digest=analysis.analysis_digest,
                ),
                candidate_sql_digest=candidate_sql_digest,
                expected_result_digest=catalog_case.expected_result_digest,
            )

        structure_result = StageEvaluationResult(
            status=StageStatus.PASS,
            result_digest=analysis.analysis_digest,
        )
        parameters = {name: catalog_case.parameters[name] for name in analysis.bind_names}
        try:
            actual = self._readonly_executor.execute(response.sql, parameters)
        except SqlExecutionError as error:
            return build_case_result(
                case_id=suite_case.case_id,
                expected_action=suite_case.expected_action,
                actual_action=CandidateAction.EXECUTE_SQL,
                status=EvaluationStatus.FAIL_EXECUTION,
                failure_code=error.failure_code,
                action_result=action_result,
                structure_result=structure_result,
                execution_result=StageEvaluationResult(
                    status=StageStatus.FAIL,
                    failure_code=error.failure_code,
                ),
                candidate_sql_digest=candidate_sql_digest,
                expected_result_digest=catalog_case.expected_result_digest,
            )

        if catalog_case.expected_result_path is None or suite_case.comparison_mode is None:
            raise ValueError("executable case lacks oracle comparison metadata")
        expected_path = _safe_oracle_path(
            self._benchmark_root,
            catalog_case.expected_result_path,
        )
        if suite_case.expected_column_types is None:
            raise ValueError("executable case lacks expected column type metadata")
        expected = normalize_expected_result(
            load_expected_result(expected_path),
            suite_case.expected_column_types,
        )
        comparison = compare_normalized_results(
            actual,
            expected,
            suite_case.comparison_mode,
        )
        execution_result = StageEvaluationResult(
            status=StageStatus.PASS,
            result_digest=actual.result_digest,
        )
        if not comparison.matches:
            failure_code = comparison.failure_code
            if failure_code is None:
                raise ValueError("failed comparison lacks failure code")
            return build_case_result(
                case_id=suite_case.case_id,
                expected_action=suite_case.expected_action,
                actual_action=CandidateAction.EXECUTE_SQL,
                status=EvaluationStatus.FAIL_RESULT,
                failure_code=failure_code,
                action_result=action_result,
                structure_result=structure_result,
                execution_result=execution_result,
                comparison_result=StageEvaluationResult(
                    status=StageStatus.FAIL,
                    failure_code=failure_code,
                    result_digest=comparison.comparison_digest,
                ),
                candidate_sql_digest=candidate_sql_digest,
                expected_result_digest=catalog_case.expected_result_digest,
                actual_result_digest=actual.result_digest,
            )
        return build_case_result(
            case_id=suite_case.case_id,
            expected_action=suite_case.expected_action,
            actual_action=CandidateAction.EXECUTE_SQL,
            status=EvaluationStatus.PASS,
            failure_code=None,
            action_result=action_result,
            structure_result=structure_result,
            execution_result=execution_result,
            comparison_result=StageEvaluationResult(
                status=StageStatus.PASS,
                result_digest=comparison.comparison_digest,
            ),
            candidate_sql_digest=candidate_sql_digest,
            expected_result_digest=catalog_case.expected_result_digest,
            actual_result_digest=actual.result_digest,
        )

    def _abort(
        self,
        started: float,
        abort_code: EvaluationAbortCode,
    ) -> EvaluationReport:
        return build_aborted_report(abort_code, duration_ms=_duration_ms(started))


def _action_failure(
    suite_case: EvaluationSuiteCase,
    actual_action: CandidateAction,
    failure_code: EvaluationFailureCode,
) -> CaseEvaluationResult:
    return build_case_result(
        case_id=suite_case.case_id,
        expected_action=suite_case.expected_action,
        actual_action=actual_action,
        status=EvaluationStatus.FAIL_ACTION,
        failure_code=failure_code,
        action_result=StageEvaluationResult(
            status=StageStatus.FAIL,
            failure_code=failure_code,
        ),
    )


def _primary_structure_failure(
    violations: tuple[EvaluationFailureCode, ...],
) -> EvaluationFailureCode:
    violation_set = set(violations)
    for code in _STRUCTURE_FAILURE_PRIORITY:
        if code in violation_set:
            return code
    raise ValueError("structure violations contain no structure failure code")


def _safe_oracle_path(root: Path, relative_path: str) -> Path:
    path = (root / relative_path).resolve()
    if not path.is_relative_to(root):
        raise ValueError("oracle path escapes benchmark root")
    return path


def _duration_ms(started: float) -> int:
    return max(round((time.monotonic() - started) * 1_000), 0)
