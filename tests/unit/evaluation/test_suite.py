"""Unit tests for the checked-in M1.2B evaluation suite."""

import json
from collections import Counter
from pathlib import Path

import pytest

from insightops.canonical import canonical_json_bytes
from insightops.evaluation.contracts import EvaluationSuiteManifest, ExpectedAction
from insightops.evaluation.suite import (
    M1_2B_CLARIFICATION_CODES,
    load_evaluation_suite,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SUITE_PATH = PROJECT_ROOT / "evaluations" / "m1_2b" / "suite.json"
CATALOG_PATH = PROJECT_ROOT / "benchmarks" / "m1_2a" / "cases.json"


def test_checked_in_suite_loads_with_frozen_bindings() -> None:
    suite = load_evaluation_suite(SUITE_PATH, CATALOG_PATH)

    assert suite.suite_id == "insightcloud-m1-2b-sql-evaluation"
    assert suite.suite_version == "1.0.0"
    assert suite.schema_revision == "0004"
    assert suite.suite_digest == "d2f5a80f06651707d78b73856dc68b35f769a86bd392071b890fa2f369622cea"


def test_checked_in_suite_has_28_6_14_partition() -> None:
    suite = load_evaluation_suite(SUITE_PATH, CATALOG_PATH)
    counts = Counter(case.expected_action for case in suite.cases)

    assert counts == {
        ExpectedAction.EXECUTE_SQL: 28,
        ExpectedAction.REQUEST_CLARIFICATION: 6,
        ExpectedAction.DEFERRED: 14,
    }


def test_checked_in_suite_has_frozen_clarification_codes() -> None:
    suite = load_evaluation_suite(SUITE_PATH, CATALOG_PATH)
    actual = {
        case.case_id: case.clarification_code
        for case in suite.cases
        if case.expected_action is ExpectedAction.REQUEST_CLARIFICATION
    }

    assert actual == M1_2B_CLARIFICATION_CODES


def test_suite_serialization_and_digest_are_deterministic() -> None:
    suite = load_evaluation_suite(SUITE_PATH, CATALOG_PATH)
    first = canonical_json_bytes(suite.model_dump(mode="json"))
    second = canonical_json_bytes(
        type(suite)
        .model_validate_json(SUITE_PATH.read_text(encoding="utf-8"))
        .model_dump(mode="json")
    )

    assert first == second
    assert suite.computed_digest() == suite.suite_digest


def test_suite_loader_rejects_digest_tampering(tmp_path: Path) -> None:
    payload = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    payload["execution_limits"]["max_rows"] = 999
    tampered = tmp_path / "suite.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="suite digest mismatch"):
        load_evaluation_suite(tampered, CATALOG_PATH)


def test_suite_loader_rejects_rehashed_limit_changes(tmp_path: Path) -> None:
    payload = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    payload["execution_limits"]["max_rows"] = 999
    changed = EvaluationSuiteManifest.model_validate_json(json.dumps(payload))
    payload["suite_digest"] = changed.computed_digest()
    tampered = tmp_path / "suite.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="execution_limits"):
        load_evaluation_suite(tampered, CATALOG_PATH)


def test_suite_loader_rejects_rehashed_expected_type_changes(tmp_path: Path) -> None:
    payload = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    payload["cases"][0]["expected_column_types"]["plan_name"] = "decimal"
    changed = EvaluationSuiteManifest.model_validate_json(json.dumps(payload))
    payload["suite_digest"] = changed.computed_digest()
    tampered = tmp_path / "suite.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="expected_column_types"):
        load_evaluation_suite(tampered, CATALOG_PATH)
