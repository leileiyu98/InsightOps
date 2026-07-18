"""Unit tests for M1.2B evaluation contracts and routing constraints."""

import json
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

from insightops.evaluation.contracts import (
    CandidateSubmission,
    CaseEvaluationResult,
    DeterministicEvaluationPayload,
    EvaluationAbortCode,
    EvaluationFailureCode,
    EvaluationReport,
    EvaluationStatus,
    EvaluationSuiteManifest,
    ExpectedAction,
)
from insightops.evaluation.reporting import build_aborted_report, build_case_result
from insightops.evaluation.suite import validate_candidate_submission

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SUITE_PATH = PROJECT_ROOT / "evaluations" / "m1_2b" / "suite.json"


def _suite_payload() -> dict[str, object]:
    return cast(dict[str, object], json.loads(SUITE_PATH.read_text(encoding="utf-8")))


def _suite() -> EvaluationSuiteManifest:
    return EvaluationSuiteManifest.model_validate_json(SUITE_PATH.read_text(encoding="utf-8"))


def _submission_payload(suite: EvaluationSuiteManifest) -> dict[str, object]:
    responses: list[dict[str, str]] = []
    for case in suite.cases:
        if case.expected_action == "execute_sql":
            responses.append({"action": "execute_sql", "case_id": case.case_id, "sql": "SELECT 1"})
        elif case.expected_action == "request_clarification":
            assert case.clarification_code is not None
            responses.append(
                {
                    "action": "request_clarification",
                    "case_id": case.case_id,
                    "clarification_code": case.clarification_code,
                }
            )
    return {
        "submission_id": "candidate-001",
        "suite_id": suite.suite_id,
        "suite_version": suite.suite_version,
        "responses": responses,
    }


def test_valid_suite_contract() -> None:
    suite = _suite()

    assert len(suite.cases) == 48
    assert suite.computed_digest() == suite.suite_digest


def test_suite_rejects_extra_field() -> None:
    payload = _suite_payload()
    payload["oracle_path"] = "forbidden"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EvaluationSuiteManifest.model_validate_json(json.dumps(payload))


def test_suite_rejects_duplicate_case_id() -> None:
    payload = _suite_payload()
    cases = payload["cases"]
    assert isinstance(cases, list)
    cases.append(cases[0])

    with pytest.raises(ValidationError, match="case_id values must be unique"):
        EvaluationSuiteManifest.model_validate_json(json.dumps(payload))


def test_suite_rejects_invalid_digest() -> None:
    payload = _suite_payload()
    dataset = payload["dataset"]
    assert isinstance(dataset, dict)
    dataset["dataset_digest"] = "not-a-digest"

    with pytest.raises(ValidationError, match="String should match pattern"):
        EvaluationSuiteManifest.model_validate_json(json.dumps(payload))


def test_suite_rejects_invalid_version() -> None:
    payload = _suite_payload()
    payload["suite_version"] = "1.0"

    with pytest.raises(ValidationError, match="String should match pattern"):
        EvaluationSuiteManifest.model_validate_json(json.dumps(payload))


def test_suite_uses_strict_field_types() -> None:
    payload = _suite_payload()
    execution_limits = payload["execution_limits"]
    assert isinstance(execution_limits, dict)
    execution_limits["max_rows"] = "1000"

    with pytest.raises(ValidationError, match="valid integer"):
        EvaluationSuiteManifest.model_validate_json(json.dumps(payload))


def test_candidate_rejects_invalid_action() -> None:
    payload = _submission_payload(_suite())
    responses = payload["responses"]
    assert isinstance(responses, list)
    responses[0]["action"] = "run_sql"

    with pytest.raises(ValidationError, match="does not match any of the expected tags"):
        CandidateSubmission.model_validate_json(json.dumps(payload))


def test_candidate_rejects_missing_response() -> None:
    suite = _suite()
    payload = _submission_payload(suite)
    responses = payload["responses"]
    assert isinstance(responses, list)
    responses.pop()
    submission = CandidateSubmission.model_validate_json(json.dumps(payload))

    with pytest.raises(ValueError, match="missing candidate responses"):
        validate_candidate_submission(submission, suite)


def test_candidate_rejects_deferred_response() -> None:
    suite = _suite()
    payload = _submission_payload(suite)
    responses = payload["responses"]
    assert isinstance(responses, list)
    responses.append(
        {
            "action": "execute_sql",
            "case_id": "GQ-PRD-002",
            "sql": "SELECT 1",
        }
    )
    submission = CandidateSubmission.model_validate_json(json.dumps(payload))

    with pytest.raises(ValueError, match="deferred cases cannot have"):
        validate_candidate_submission(submission, suite)


def test_candidate_action_must_match_suite_case() -> None:
    suite = _suite()
    payload = _submission_payload(suite)
    responses = payload["responses"]
    assert isinstance(responses, list)
    responses[0] = {
        "action": "request_clarification",
        "case_id": "GQ-SAA-001",
        "clarification_code": "observable_churn_scope_required",
    }
    submission = CandidateSubmission.model_validate_json(json.dumps(payload))

    with pytest.raises(ValueError, match="GQ-SAA-001 requires execute_sql"):
        validate_candidate_submission(submission, suite)


def test_candidate_rejects_sql_over_byte_limit() -> None:
    payload: dict[str, object] = {
        "submission_id": "candidate-large",
        "suite_id": "insightcloud-m1-2b-sql-evaluation",
        "suite_version": "1.0.0",
        "responses": [
            {
                "action": "execute_sql",
                "case_id": "GQ-SAA-001",
                "sql": "数" * 21_846,
            }
        ],
    }

    with pytest.raises(ValidationError, match="65536 UTF-8 bytes"):
        CandidateSubmission.model_validate_json(json.dumps(payload))


def test_case_failure_stage_constraints_are_enforced() -> None:
    payload: dict[str, object] = {
        "case_id": "GQ-SAA-001",
        "expected_action": "execute_sql",
        "actual_action": "execute_sql",
        "status": "FAIL_STRUCTURE",
        "failure_code": "parse_error",
        "secondary_codes": [],
        "action_result": {"status": "PASS"},
        "structure_result": {"status": "FAIL", "failure_code": "parse_error"},
        "execution_result": {"status": "PASS"},
        "comparison_result": None,
        "digests": {"case_evaluation_digest": "a" * 64},
    }

    with pytest.raises(ValidationError, match="cannot have execution result"):
        CaseEvaluationResult.model_validate_json(json.dumps(payload))


def test_aborted_is_not_a_case_status() -> None:
    payload: dict[str, object] = {
        "case_id": "GQ-PRD-002",
        "expected_action": "deferred",
        "actual_action": None,
        "status": "ABORTED",
        "failure_code": "deferred_schema_dependency",
        "secondary_codes": [],
        "action_result": None,
        "structure_result": None,
        "execution_result": None,
        "comparison_result": None,
        "digests": {"case_evaluation_digest": "a" * 64},
    }

    with pytest.raises(ValidationError, match="ABORTED is run-level"):
        CaseEvaluationResult.model_validate_json(json.dumps(payload))


def test_pass_requires_actual_action_to_match_expected_action() -> None:
    payload: dict[str, object] = {
        "case_id": "GQ-SAA-001",
        "expected_action": "execute_sql",
        "actual_action": "request_clarification",
        "status": "PASS",
        "failure_code": None,
        "secondary_codes": [],
        "action_result": {"status": "PASS"},
        "structure_result": None,
        "execution_result": None,
        "comparison_result": None,
        "digests": {"case_evaluation_digest": "a" * 64},
    }

    with pytest.raises(ValidationError, match="actual_action to match expected_action"):
        CaseEvaluationResult.model_validate_json(json.dumps(payload))


def test_deterministic_payload_cannot_represent_aborted_run() -> None:
    payload: dict[str, object] = {
        "suite_id": "insightcloud-m1-2b-sql-evaluation",
        "suite_version": "1.0.0",
        "suite_digest": "b" * 64,
        "submission_id": "candidate-001",
        "submission_digest": "c" * 64,
        "evaluator_id": "insightops-deterministic-sql-evaluator",
        "evaluator_version": "1.0.0",
        "evaluator_contract_version": "1.0.0",
        "run_status": "ABORTED",
        "abort_code": None,
        "case_results": [],
        "summary": {
            "passed": 0,
            "failed_action": 0,
            "failed_structure": 0,
            "failed_execution": 0,
            "failed_result": 0,
            "not_evaluated": 0,
        },
        "deterministic_digest": "d" * 64,
    }

    with pytest.raises(ValidationError, match="completed-run only"):
        DeterministicEvaluationPayload.model_validate_json(json.dumps(payload))


def test_aborted_report_has_no_evaluation_payload_or_digest() -> None:
    report = build_aborted_report(EvaluationAbortCode.INVALID_SUBMISSION)

    assert report.run_status == "ABORTED"
    assert report.abort_code is EvaluationAbortCode.INVALID_SUBMISSION
    assert report.deterministic_payload is None
    assert report.computed_digest() is None
    serialized = report.model_dump_json()
    assert "deterministic_digest" not in serialized
    assert "case_results" not in serialized


def test_report_digest_excludes_run_envelope() -> None:
    case_result = build_case_result(
        case_id="GQ-PRD-002",
        expected_action=ExpectedAction.DEFERRED,
        actual_action=None,
        status=EvaluationStatus.NOT_EVALUATED,
        failure_code=EvaluationFailureCode.DEFERRED_SCHEMA_DEPENDENCY,
    )
    deterministic_payload: dict[str, object] = {
        "suite_id": "insightcloud-m1-2b-sql-evaluation",
        "suite_version": "1.0.0",
        "suite_digest": "b" * 64,
        "submission_id": "candidate-001",
        "submission_digest": "c" * 64,
        "evaluator_id": "insightops-deterministic-sql-evaluator",
        "evaluator_version": "1.0.0",
        "evaluator_contract_version": "1.0.0",
        "run_status": "COMPLETED",
        "abort_code": None,
        "case_results": [case_result.model_dump(mode="json")],
        "summary": {
            "passed": 0,
            "failed_action": 0,
            "failed_structure": 0,
            "failed_execution": 0,
            "failed_result": 0,
            "not_evaluated": 1,
        },
        "deterministic_digest": "d" * 64,
    }
    payload = DeterministicEvaluationPayload.model_validate_json(json.dumps(deterministic_payload))
    deterministic_payload["deterministic_digest"] = payload.computed_digest()
    report_payload: dict[str, object] = {
        "run_status": "COMPLETED",
        "abort_code": None,
        "deterministic_payload": deterministic_payload,
        "run_envelope": {
            "run_id": "4a1ba2ab-cf20-49dd-9066-a4e5b98b3ec1",
            "timestamp": "2026-07-17T10:00:00+08:00",
            "duration_ms": 12,
            "host": "host-a",
        },
    }
    first = EvaluationReport.model_validate_json(json.dumps(report_payload))
    report_payload["run_envelope"] = {
        "run_id": "f11d8a2e-c4bf-462f-ae2c-420765f4bcbb",
        "timestamp": "2026-07-18T11:00:00+08:00",
        "duration_ms": 999,
        "host": "host-b",
    }
    second = EvaluationReport.model_validate_json(json.dumps(report_payload))

    assert first.deterministic_payload is not None
    assert first.computed_digest() == second.computed_digest()
    assert first.computed_digest() == first.deterministic_payload.deterministic_digest
