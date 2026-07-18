"""Builders for deterministic case outcomes and run-envelope-separated reports."""

import socket
from datetime import UTC, datetime
from uuid import uuid4

from insightops.evaluation.contracts import (
    CandidateAction,
    CandidateSubmission,
    CaseDigests,
    CaseEvaluationResult,
    DeterministicEvaluationPayload,
    EvaluationAbortCode,
    EvaluationFailureCode,
    EvaluationReport,
    EvaluationRunStatus,
    EvaluationStatus,
    EvaluationSuiteManifest,
    EvaluationSummary,
    ExpectedAction,
    RunEnvelope,
    StageEvaluationResult,
)

_EMPTY_DIGEST = "0" * 64


def build_case_result(
    *,
    case_id: str,
    expected_action: ExpectedAction,
    actual_action: CandidateAction | None,
    status: EvaluationStatus,
    failure_code: EvaluationFailureCode | None,
    secondary_codes: tuple[EvaluationFailureCode, ...] = (),
    action_result: StageEvaluationResult | None = None,
    structure_result: StageEvaluationResult | None = None,
    execution_result: StageEvaluationResult | None = None,
    comparison_result: StageEvaluationResult | None = None,
    candidate_sql_digest: str | None = None,
    expected_result_digest: str | None = None,
    actual_result_digest: str | None = None,
) -> CaseEvaluationResult:
    """Construct and validate a self-digested case result."""
    draft = CaseEvaluationResult.model_construct(
        case_id=case_id,
        expected_action=expected_action,
        actual_action=actual_action,
        status=status,
        failure_code=failure_code,
        secondary_codes=secondary_codes,
        action_result=action_result,
        structure_result=structure_result,
        execution_result=execution_result,
        comparison_result=comparison_result,
        digests=CaseDigests(
            candidate_sql_digest=candidate_sql_digest,
            expected_result_digest=expected_result_digest,
            actual_result_digest=actual_result_digest,
            case_evaluation_digest=_EMPTY_DIGEST,
        ),
    )
    return CaseEvaluationResult.model_validate(
        {
            **draft.model_dump(exclude={"digests"}),
            "digests": {
                "candidate_sql_digest": candidate_sql_digest,
                "expected_result_digest": expected_result_digest,
                "actual_result_digest": actual_result_digest,
                "case_evaluation_digest": draft.computed_digest(),
            },
        }
    )


def build_evaluation_report(
    *,
    suite: EvaluationSuiteManifest,
    submission: CandidateSubmission,
    case_results: tuple[CaseEvaluationResult, ...],
    duration_ms: int,
) -> EvaluationReport:
    """Build a report whose deterministic digest excludes its run envelope."""
    sorted_results = tuple(sorted(case_results, key=lambda result: result.case_id))
    summary = _summary(sorted_results)
    draft = DeterministicEvaluationPayload.model_construct(
        suite_id=suite.suite_id,
        suite_version=suite.suite_version,
        suite_digest=suite.suite_digest,
        submission_id=submission.submission_id,
        submission_digest=submission.computed_digest(),
        evaluator_id=suite.evaluator_id,
        evaluator_version=suite.evaluator_version,
        evaluator_contract_version=suite.evaluator_contract_version,
        run_status=EvaluationRunStatus.COMPLETED,
        abort_code=None,
        case_results=sorted_results,
        summary=summary,
        deterministic_digest=_EMPTY_DIGEST,
    )
    deterministic_payload = DeterministicEvaluationPayload.model_validate(
        {
            **draft.model_dump(exclude={"deterministic_digest"}),
            "deterministic_digest": draft.computed_digest(),
        }
    )
    return EvaluationReport(
        run_status=EvaluationRunStatus.COMPLETED,
        abort_code=None,
        deterministic_payload=deterministic_payload,
        run_envelope=_run_envelope(duration_ms),
    )


def build_aborted_report(
    abort_code: EvaluationAbortCode,
    *,
    duration_ms: int = 0,
) -> EvaluationReport:
    """Build an operational ABORTED report with no evaluation payload or digest."""
    return EvaluationReport(
        run_status=EvaluationRunStatus.ABORTED,
        abort_code=abort_code,
        deterministic_payload=None,
        run_envelope=_run_envelope(duration_ms),
    )


def _run_envelope(duration_ms: int) -> RunEnvelope:
    return RunEnvelope(
        run_id=uuid4(),
        timestamp=datetime.now(UTC),
        duration_ms=max(duration_ms, 0),
        host=socket.gethostname(),
    )


def _summary(results: tuple[CaseEvaluationResult, ...]) -> EvaluationSummary:
    counts: dict[EvaluationStatus, int] = {status: 0 for status in EvaluationStatus}
    for result in results:
        counts[result.status] += 1
    return EvaluationSummary(
        passed=counts[EvaluationStatus.PASS],
        failed_action=counts[EvaluationStatus.FAIL_ACTION],
        failed_structure=counts[EvaluationStatus.FAIL_STRUCTURE],
        failed_execution=counts[EvaluationStatus.FAIL_EXECUTION],
        failed_result=counts[EvaluationStatus.FAIL_RESULT],
        not_evaluated=counts[EvaluationStatus.NOT_EVALUATED],
    )
