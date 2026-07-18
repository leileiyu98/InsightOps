"""End-to-end MySQL controls for the M1.2B deterministic evaluation harness."""

import json
import os
import subprocess
import sys
from collections.abc import Generator
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import Engine

from insightops.benchmark.contracts import BenchmarkCatalog, BenchmarkStatus
from insightops.benchmark.registry import load_benchmark_catalog
from insightops.core.config import load_settings
from insightops.evaluation.contracts import (
    CandidateSubmission,
    EvaluationAbortCode,
    EvaluationFailureCode,
    EvaluationReport,
    EvaluationRunStatus,
    EvaluationStatus,
    EvaluationSuiteManifest,
    ExecuteSqlResponse,
    ExpectedAction,
    RequestClarificationResponse,
)
from insightops.evaluation.execution import (
    ReadonlyDatabaseSettings,
    ReadonlySqlExecutor,
    SqlExecutionError,
    create_readonly_database_engine,
)
from insightops.evaluation.runner import EvaluationRunner
from insightops.evaluation.suite import load_evaluation_suite
from insightops.seed.dataset import load_seed_dataset
from insightops.seed.loader import DatasetLoader

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BENCHMARK_ROOT = PROJECT_ROOT / "benchmarks" / "m1_2a"
DATASET_ROOT = PROJECT_ROOT / "data" / "seed" / "m1_2a"
SUITE_PATH = PROJECT_ROOT / "evaluations" / "m1_2b" / "suite.json"
CATALOG_PATH = BENCHMARK_ROOT / "cases.json"
BUSINESS_DEFINITION_PATH = PROJECT_ROOT / "docs" / "business-definitions-v1.md"


@pytest.fixture(scope="module")
def evaluation_environment(
    database_engine: Engine,
) -> Generator[tuple[EvaluationRunner, CandidateSubmission, ReadonlySqlExecutor]]:
    writer_settings = load_settings()
    readonly_settings = ReadonlyDatabaseSettings(
        host=os.getenv("READONLY_DATABASE_HOST", writer_settings.database_host),
        port=int(os.getenv("READONLY_DATABASE_PORT", str(writer_settings.database_port))),
        name=os.getenv("READONLY_DATABASE_NAME", writer_settings.database_name),
        user=os.getenv("READONLY_DATABASE_USER", "insightops_readonly"),
        password=SecretStr(
            os.getenv(
                "READONLY_DATABASE_PASSWORD",
                "local_readonly_password_change_me",
            )
        ),
    )
    suite = load_evaluation_suite(SUITE_PATH, CATALOG_PATH)
    readonly_engine = create_readonly_database_engine(
        readonly_settings,
        timeout_ms=suite.execution_limits.timeout_ms,
    )
    catalog = load_benchmark_catalog(CATALOG_PATH)
    dataset = load_seed_dataset(DATASET_ROOT)
    loader = DatasetLoader(database_engine, dataset, app_env="test")
    loader.load()
    executor = ReadonlySqlExecutor(readonly_engine, readonly_settings, suite.execution_limits)
    runner = EvaluationRunner(
        suite=suite,
        catalog=catalog,
        dataset=dataset,
        writer_engine=database_engine,
        readonly_executor=executor,
        benchmark_root=BENCHMARK_ROOT,
        business_definition_path=BUSINESS_DEFINITION_PATH,
        app_env="test",
    )
    submission = _gold_control_submission(suite, catalog)
    try:
        yield runner, submission, executor
    finally:
        loader.unload()
        readonly_engine.dispose()


def test_gold_clarification_and_deferred_controls_are_28_6_14(
    evaluation_environment: tuple[EvaluationRunner, CandidateSubmission, ReadonlySqlExecutor],
) -> None:
    runner, submission, _executor = evaluation_environment

    report = runner.run(submission)
    payload = report.deterministic_payload
    assert payload is not None
    results = payload.case_results
    by_expected_action = {
        action: [result for result in results if result.expected_action is action]
        for action in ExpectedAction
    }

    assert report.run_status is EvaluationRunStatus.COMPLETED
    assert payload.summary.passed == 34
    assert payload.summary.not_evaluated == 14
    assert len(by_expected_action[ExpectedAction.EXECUTE_SQL]) == 28
    assert all(
        result.status is EvaluationStatus.PASS
        for result in by_expected_action[ExpectedAction.EXECUTE_SQL]
    )
    assert len(by_expected_action[ExpectedAction.REQUEST_CLARIFICATION]) == 6
    assert all(
        result.status is EvaluationStatus.PASS
        for result in by_expected_action[ExpectedAction.REQUEST_CLARIFICATION]
    )
    assert len(by_expected_action[ExpectedAction.DEFERRED]) == 14
    assert all(
        result.status is EvaluationStatus.NOT_EVALUATED
        for result in by_expected_action[ExpectedAction.DEFERRED]
    )
    serialized = report.model_dump_json()
    assert "gold_sql" not in serialized
    assert "expected_result_path" not in serialized
    assert "expected rows" not in serialized


def test_same_submission_has_same_deterministic_digest(
    evaluation_environment: tuple[EvaluationRunner, CandidateSubmission, ReadonlySqlExecutor],
) -> None:
    runner, submission, _executor = evaluation_environment

    first = runner.run(submission)
    second = runner.run(submission)
    first_payload = first.deterministic_payload
    second_payload = second.deterministic_payload
    assert first_payload is not None
    assert second_payload is not None

    assert first.run_envelope.run_id != second.run_envelope.run_id
    assert first_payload.deterministic_digest == second_payload.deterministic_digest


def test_dangerous_candidate_is_rejected_at_structure_stage(
    evaluation_environment: tuple[EvaluationRunner, CandidateSubmission, ReadonlySqlExecutor],
) -> None:
    runner, submission, _executor = evaluation_environment
    responses = list(submission.responses)
    response_index = next(
        index for index, response in enumerate(responses) if response.case_id == "GQ-SAA-001"
    )
    responses[response_index] = ExecuteSqlResponse(
        action="execute_sql",
        case_id="GQ-SAA-001",
        sql="DELETE FROM organization",
    )
    malicious_submission = submission.model_copy(update={"responses": tuple(responses)})

    report = runner.run(malicious_submission)
    payload = report.deterministic_payload
    assert payload is not None
    failed = next(result for result in payload.case_results if result.case_id == "GQ-SAA-001")

    assert failed.status is EvaluationStatus.FAIL_STRUCTURE
    assert failed.failure_code is EvaluationFailureCode.FORBIDDEN_DML
    assert failed.execution_result is None
    assert payload.summary.failed_structure == 1


def test_readonly_identity_rejects_write_even_if_executor_is_called_directly(
    evaluation_environment: tuple[EvaluationRunner, CandidateSubmission, ReadonlySqlExecutor],
) -> None:
    _runner, _submission, executor = evaluation_environment

    with pytest.raises(SqlExecutionError) as captured:
        executor.execute(
            "UPDATE organization SET organization_name = organization_name",
            {},
        )

    assert captured.value.failure_code is EvaluationFailureCode.DATABASE_PERMISSION_DENIED


def test_readonly_executor_enforces_row_and_output_limits(
    evaluation_environment: tuple[EvaluationRunner, CandidateSubmission, ReadonlySqlExecutor],
) -> None:
    _runner, _submission, executor = evaluation_environment
    excessive_rows = (
        "WITH digits AS ("
        "SELECT 0 AS n UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3 "
        "UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL SELECT 6 UNION ALL SELECT 7 "
        "UNION ALL SELECT 8 UNION ALL SELECT 9"
        ") SELECT a.n + b.n * 10 + c.n * 100 + d.n * 1000 AS n "
        "FROM digits a CROSS JOIN digits b CROSS JOIN digits c CROSS JOIN digits d "
        "LIMIT 1001"
    )

    with pytest.raises(SqlExecutionError) as row_error:
        executor.execute(excessive_rows, {})
    with pytest.raises(SqlExecutionError) as output_error:
        executor.execute("SELECT REPEAT('x', 1048576) AS oversized", {})

    assert row_error.value.failure_code is EvaluationFailureCode.ROW_LIMIT_EXCEEDED
    assert output_error.value.failure_code is EvaluationFailureCode.OUTPUT_LIMIT_EXCEEDED


def test_readonly_executor_recovers_with_a_new_connection_after_timeout(
    evaluation_environment: tuple[EvaluationRunner, CandidateSubmission, ReadonlySqlExecutor],
    database_engine: Engine,
) -> None:
    _runner, _submission, executor = evaluation_environment
    before = executor.execute("SELECT CONNECTION_ID() AS connection_id", {})
    slow_query = (
        "WITH digits AS ("
        "SELECT 0 AS n UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3 "
        "UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL SELECT 6 UNION ALL SELECT 7 "
        "UNION ALL SELECT 8 UNION ALL SELECT 9"
        ") SELECT SUM(a.n + b.n + c.n + d.n + e.n + f.n + g.n + h.n) AS total "
        "FROM digits a CROSS JOIN digits b CROSS JOIN digits c CROSS JOIN digits d "
        "CROSS JOIN digits e CROSS JOIN digits f CROSS JOIN digits g CROSS JOIN digits h"
    )

    with pytest.raises(SqlExecutionError) as captured:
        executor.execute(slow_query, {})
    after = executor.execute("SELECT CONNECTION_ID() AS connection_id", {})

    assert captured.value.failure_code is EvaluationFailureCode.QUERY_TIMEOUT
    assert before.rows[0][0].value != after.rows[0][0].value
    dataset = load_seed_dataset(DATASET_ROOT)
    DatasetLoader(database_engine, dataset, app_env="test").verify()


def test_cli_writes_a_complete_report(
    tmp_path: Path,
    evaluation_environment: tuple[EvaluationRunner, CandidateSubmission, ReadonlySqlExecutor],
) -> None:
    _runner, submission, _executor = evaluation_environment
    submission_path = tmp_path / "submission.json"
    report_path = tmp_path / "report.json"
    submission_path.write_text(submission.model_dump_json(indent=2), encoding="utf-8")
    writer_settings = load_settings()
    environment = {
        **os.environ,
        "READONLY_DATABASE_HOST": writer_settings.database_host,
        "READONLY_DATABASE_PORT": str(writer_settings.database_port),
        "READONLY_DATABASE_NAME": writer_settings.database_name,
        "READONLY_DATABASE_USER": os.getenv("READONLY_DATABASE_USER", "insightops_readonly"),
        "READONLY_DATABASE_PASSWORD": os.getenv(
            "READONLY_DATABASE_PASSWORD", "local_readonly_password_change_me"
        ),
    }

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "insightops.evaluation",
            "--suite",
            str(SUITE_PATH),
            "--submission",
            str(submission_path),
            "--output",
            str(report_path),
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    report = EvaluationReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    payload = report.deterministic_payload
    assert payload is not None

    assert completed.returncode == 0, completed.stderr
    assert payload.summary.passed == 34
    assert payload.summary.not_evaluated == 14


def test_suite_digest_tamper_aborts_cli_before_database_settings(
    tmp_path: Path,
) -> None:
    suite_payload = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    suite_payload["execution_limits"]["max_rows"] = 999
    tampered_suite = tmp_path / "suite.json"
    tampered_suite.write_text(json.dumps(suite_payload), encoding="utf-8")

    suite = load_evaluation_suite(SUITE_PATH, CATALOG_PATH)
    catalog = load_benchmark_catalog(CATALOG_PATH)
    submission = _gold_control_submission(suite, catalog)
    submission_path = tmp_path / "submission.json"
    submission_path.write_text(submission.model_dump_json(indent=2), encoding="utf-8")
    report_path = tmp_path / "report.json"
    environment = os.environ.copy()
    for key in tuple(environment):
        if key.startswith("READONLY_DATABASE_"):
            environment.pop(key)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "insightops.evaluation",
            "--suite",
            str(tampered_suite),
            "--submission",
            str(submission_path),
            "--output",
            str(report_path),
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    report = EvaluationReport.model_validate_json(report_path.read_text(encoding="utf-8"))

    assert completed.returncode == 2
    assert "Traceback" not in completed.stderr
    assert report.run_status is EvaluationRunStatus.ABORTED
    assert report.abort_code is EvaluationAbortCode.SUITE_DIGEST_MISMATCH
    assert report.deterministic_payload is None
    assert report.computed_digest() is None


def test_cli_preflight_failures_emit_stable_aborted_reports(tmp_path: Path) -> None:
    suite = load_evaluation_suite(SUITE_PATH, CATALOG_PATH)
    catalog = load_benchmark_catalog(CATALOG_PATH)
    submission = _gold_control_submission(suite, catalog)
    valid_submission = tmp_path / "submission.json"
    valid_submission.write_text(submission.model_dump_json(), encoding="utf-8")

    invalid_suite = tmp_path / "invalid-suite.json"
    invalid_suite.write_text("{", encoding="utf-8")
    invalid_submission = tmp_path / "invalid-submission.json"
    invalid_submission.write_text("{", encoding="utf-8")

    wrong_schema_payload = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    wrong_schema_payload["schema_revision"] = "9999"
    changed_suite = EvaluationSuiteManifest.model_validate_json(json.dumps(wrong_schema_payload))
    wrong_schema_payload["suite_digest"] = changed_suite.computed_digest()
    wrong_schema_suite = tmp_path / "wrong-schema-suite.json"
    wrong_schema_suite.write_text(json.dumps(wrong_schema_payload), encoding="utf-8")

    oracle_catalog_payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    oracle_catalog_payload["cases"][0]["gold_sql_digest"] = "0" * 64
    oracle_catalog = tmp_path / "oracle-tamper-catalog.json"
    oracle_catalog.write_text(json.dumps(oracle_catalog_payload), encoding="utf-8")

    scenarios = (
        (
            EvaluationAbortCode.INVALID_SUITE_MANIFEST,
            invalid_suite,
            valid_submission,
            (),
        ),
        (
            EvaluationAbortCode.INVALID_SUBMISSION,
            SUITE_PATH,
            invalid_submission,
            (),
        ),
        (
            EvaluationAbortCode.DATASET_BINDING_MISMATCH,
            SUITE_PATH,
            valid_submission,
            ("--dataset-root", str(tmp_path / "missing-seed")),
        ),
        (
            EvaluationAbortCode.SCHEMA_BINDING_MISMATCH,
            wrong_schema_suite,
            valid_submission,
            (),
        ),
        (
            EvaluationAbortCode.ORACLE_DIGEST_MISMATCH,
            SUITE_PATH,
            valid_submission,
            ("--catalog", str(oracle_catalog)),
        ),
    )

    for index, (expected_code, suite_path, submission_path, extra_args) in enumerate(scenarios):
        report_path = tmp_path / f"aborted-{index}.json"
        completed = _run_cli(
            suite_path=suite_path,
            submission_path=submission_path,
            report_path=report_path,
            extra_args=extra_args,
            environment=_without_readonly_environment(),
        )
        report = EvaluationReport.model_validate_json(report_path.read_text(encoding="utf-8"))

        assert completed.returncode == 2
        assert "Traceback" not in completed.stderr
        assert report.run_status is EvaluationRunStatus.ABORTED
        assert report.abort_code is expected_code
        assert report.deterministic_payload is None
        assert report.computed_digest() is None


def test_cli_wrong_readonly_credential_aborts_without_case_scores(
    tmp_path: Path,
    evaluation_environment: tuple[EvaluationRunner, CandidateSubmission, ReadonlySqlExecutor],
) -> None:
    _runner, submission, _executor = evaluation_environment
    submission_path = tmp_path / "submission.json"
    submission_path.write_text(submission.model_dump_json(), encoding="utf-8")
    writer_settings = load_settings()
    environment = {
        **os.environ,
        "READONLY_DATABASE_HOST": writer_settings.database_host,
        "READONLY_DATABASE_PORT": str(writer_settings.database_port),
        "READONLY_DATABASE_NAME": writer_settings.database_name,
        "READONLY_DATABASE_USER": "insightops_readonly",
        "READONLY_DATABASE_PASSWORD": "definitely_wrong_password",
    }
    report_path = tmp_path / "wrong-credential-report.json"

    completed = _run_cli(
        suite_path=SUITE_PATH,
        submission_path=submission_path,
        report_path=report_path,
        environment=environment,
    )
    report = EvaluationReport.model_validate_json(report_path.read_text(encoding="utf-8"))

    assert completed.returncode == 2
    assert "Traceback" not in completed.stderr
    assert report.abort_code is EvaluationAbortCode.READONLY_IDENTITY_VERIFICATION_FAILED
    assert report.deterministic_payload is None


def _gold_control_submission(
    suite_manifest: EvaluationSuiteManifest,
    benchmark_catalog: BenchmarkCatalog,
) -> CandidateSubmission:
    responses: list[ExecuteSqlResponse | RequestClarificationResponse] = []
    suite_by_id = {case.case_id: case for case in suite_manifest.cases}
    for case in benchmark_catalog.cases:
        suite_case = suite_by_id[case.case_id]
        if case.status is BenchmarkStatus.EXECUTABLE:
            assert case.gold_sql_path is not None
            responses.append(
                ExecuteSqlResponse(
                    action="execute_sql",
                    case_id=case.case_id,
                    sql=(BENCHMARK_ROOT / case.gold_sql_path).read_text(encoding="utf-8"),
                )
            )
        elif case.status is BenchmarkStatus.CLARIFICATION_REQUIRED:
            assert suite_case.clarification_code is not None
            responses.append(
                RequestClarificationResponse(
                    action="request_clarification",
                    case_id=case.case_id,
                    clarification_code=suite_case.clarification_code,
                )
            )
    return CandidateSubmission(
        submission_id="m1-2b-gold-control",
        suite_id=suite_manifest.suite_id,
        suite_version=suite_manifest.suite_version,
        responses=tuple(responses),
    )


def _run_cli(
    *,
    suite_path: Path,
    submission_path: Path,
    report_path: Path,
    extra_args: tuple[str, ...] = (),
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "insightops.evaluation",
            "--suite",
            str(suite_path),
            "--submission",
            str(submission_path),
            "--output",
            str(report_path),
            *extra_args,
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def _without_readonly_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for key in tuple(environment):
        if key.startswith("READONLY_DATABASE_"):
            environment.pop(key)
    return environment
