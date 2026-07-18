"""Load and validate M1.2B suite and candidate contract bindings."""

from pathlib import Path

from insightops.benchmark.contracts import BenchmarkCatalog, BenchmarkStatus
from insightops.benchmark.registry import load_benchmark_catalog, load_expected_result
from insightops.canonical import canonical_json_digest
from insightops.evaluation.contracts import (
    CandidateSubmission,
    EvaluationSuiteManifest,
    ExpectedAction,
    RequestClarificationResponse,
)

M1_2B_SUITE_ID = "insightcloud-m1-2b-sql-evaluation"
M1_2B_SUITE_VERSION = "1.0.0"
M1_2B_EVALUATOR_ID = "insightops-deterministic-sql-evaluator"
M1_2B_EVALUATOR_VERSION = "1.0.0"
M1_2B_CONTRACT_VERSION = "1.0.0"
M1_2B_DIGEST_ALGORITHM = "sha256-canonical-json-v1"
M1_2B_DATASET_ID = "insightcloud-m1-2a-benchmark"
M1_2B_DATASET_VERSION = "1.1.0"
M1_2B_DATASET_DIGEST = "bf3efd9079bd434fe8f400fac161735e012548565fce9277e3bcf30ace44c18c"
M1_2B_SCHEMA_REVISION = "0004"
M1_2B_BUSINESS_DEFINITION_ID = "insightcloud-business-definitions"
M1_2B_BUSINESS_DEFINITION_VERSION = "1.0.1"
M1_2B_BUSINESS_DEFINITION_DIGEST = (
    "eb759951171f377c5c33a199d06d98dd4ebf0529b66d4e950ea8f622a778500d"
)
M1_2B_CATALOG_ID = "insightcloud-m1-2a-gold-catalog"
M1_2B_CATALOG_VERSION = "1.1.0"
M1_2B_ORACLE_ASSETS_DIGEST = "356369ee2c6664e87c818082f3d73f8c41be3323a8b5224b107cd5b95fafc4d0"
M1_2B_EXPECTED_COLUMN_TYPES_DIGEST = (
    "f7a4423d0c23634e363bd68c424ec2c5bcdfbb3980de39e7013f671392800250"
)

M1_2B_CLARIFICATION_CODES = {
    "GQ-SAA-009": "observable_churn_scope_required",
    "GQ-COM-007": "order_lifecycle_funnel_definition_required",
    "GQ-MKT-006": "attributed_revenue_type_required",
    "GQ-MKT-007": "attributed_revenue_type_required",
    "GQ-PRD-005": "registration_source_attribution_unavailable",
    "GQ-XDM-003": "touch_to_registration_funnel_definition_required",
}

_EXPECTED_PARTITION = {
    BenchmarkStatus.EXECUTABLE: 28,
    BenchmarkStatus.CLARIFICATION_REQUIRED: 6,
    BenchmarkStatus.DEFERRED: 14,
}

_EXPECTED_ACTION_BY_STATUS = {
    BenchmarkStatus.EXECUTABLE: ExpectedAction.EXECUTE_SQL,
    BenchmarkStatus.CLARIFICATION_REQUIRED: ExpectedAction.REQUEST_CLARIFICATION,
    BenchmarkStatus.DEFERRED: ExpectedAction.DEFERRED,
}


def load_evaluation_suite(suite_path: Path, catalog_path: Path) -> EvaluationSuiteManifest:
    """Load one suite and validate its frozen M1.2B and catalog bindings."""
    suite = EvaluationSuiteManifest.model_validate_json(suite_path.read_text(encoding="utf-8"))
    if suite.computed_digest() != suite.suite_digest:
        raise ValueError("evaluation suite digest mismatch")
    catalog = load_benchmark_catalog(catalog_path)
    _validate_frozen_bindings(suite)
    _validate_catalog_bindings(suite, catalog)
    _validate_case_partition(suite, catalog)
    return suite


def validate_candidate_submission(
    submission: CandidateSubmission,
    suite: EvaluationSuiteManifest,
    *,
    validate_actions: bool = True,
) -> None:
    """Validate response completeness and action routing without inspecting SQL."""
    if submission.suite_id != suite.suite_id or submission.suite_version != suite.suite_version:
        raise ValueError("candidate submission suite binding mismatch")

    suite_cases = {case.case_id: case for case in suite.cases}
    responses = {response.case_id: response for response in submission.responses}
    unknown = sorted(set(responses) - set(suite_cases))
    if unknown:
        raise ValueError(f"unknown candidate response case IDs: {unknown}")

    deferred = sorted(
        case_id
        for case_id, case in suite_cases.items()
        if case.expected_action is ExpectedAction.DEFERRED and case_id in responses
    )
    if deferred:
        raise ValueError(f"deferred cases cannot have candidate responses: {deferred}")

    expected_response_ids = {
        case_id
        for case_id, case in suite_cases.items()
        if case.expected_action is not ExpectedAction.DEFERRED
    }
    missing = sorted(expected_response_ids - set(responses))
    if missing:
        raise ValueError(f"missing candidate responses: {missing}")

    for case_id in sorted(expected_response_ids):
        case = suite_cases[case_id]
        response = responses[case_id]
        if not validate_actions:
            continue
        if case.expected_action is ExpectedAction.EXECUTE_SQL and response.action != "execute_sql":
            raise ValueError(f"{case_id} requires execute_sql")
        if (
            case.expected_action is ExpectedAction.REQUEST_CLARIFICATION
            and response.action != "request_clarification"
        ):
            raise ValueError(f"{case_id} requires request_clarification")
        if isinstance(response, RequestClarificationResponse):
            expected_code = case.clarification_code
            if response.clarification_code != expected_code:
                raise ValueError(f"{case_id} clarification_code mismatch")


def validate_expected_column_type_bindings(
    suite: EvaluationSuiteManifest,
    catalog: BenchmarkCatalog,
    benchmark_root: Path,
) -> None:
    """Validate reviewed type metadata against oracle columns without exposing rows."""
    root = benchmark_root.resolve()
    suite_cases = {case.case_id: case for case in suite.cases}
    for catalog_case in catalog.cases:
        if catalog_case.expected_result_path is None:
            continue
        suite_case = suite_cases[catalog_case.case_id]
        if suite_case.expected_column_types is None:
            raise ValueError("executable case lacks expected column type metadata")
        expected_path = (root / catalog_case.expected_result_path).resolve()
        if not expected_path.is_relative_to(root):
            raise ValueError("expected result path escapes benchmark root")
        expected = load_expected_result(expected_path)
        if set(expected.columns) != set(suite_case.expected_column_types):
            raise ValueError("expected column type metadata does not match oracle columns")


def _validate_frozen_bindings(suite: EvaluationSuiteManifest) -> None:
    bindings = {
        "suite_id": suite.suite_id == M1_2B_SUITE_ID,
        "suite_version": suite.suite_version == M1_2B_SUITE_VERSION,
        "evaluator_id": suite.evaluator_id == M1_2B_EVALUATOR_ID,
        "evaluator_version": suite.evaluator_version == M1_2B_EVALUATOR_VERSION,
        "evaluator_contract_version": (suite.evaluator_contract_version == M1_2B_CONTRACT_VERSION),
        "digest_algorithm": suite.digest_algorithm == M1_2B_DIGEST_ALGORITHM,
        "dataset_id": suite.dataset.dataset_id == M1_2B_DATASET_ID,
        "dataset_version": suite.dataset.dataset_version == M1_2B_DATASET_VERSION,
        "dataset_digest": suite.dataset.dataset_digest == M1_2B_DATASET_DIGEST,
        "schema_revision": suite.schema_revision == M1_2B_SCHEMA_REVISION,
        "business_definition_id": (
            suite.business_definition.business_definition_id == M1_2B_BUSINESS_DEFINITION_ID
        ),
        "business_definition_version": (
            suite.business_definition.business_definition_version
            == M1_2B_BUSINESS_DEFINITION_VERSION
        ),
        "business_definition_digest": (
            suite.business_definition.business_definition_digest == M1_2B_BUSINESS_DEFINITION_DIGEST
        ),
        "catalog_id": suite.catalog.catalog_id == M1_2B_CATALOG_ID,
        "catalog_version": suite.catalog.catalog_version == M1_2B_CATALOG_VERSION,
        "oracle_assets_digest": suite.oracle_assets_digest == M1_2B_ORACLE_ASSETS_DIGEST,
        "expected_column_types": _expected_column_types_digest(suite)
        == M1_2B_EXPECTED_COLUMN_TYPES_DIGEST,
        "comparison_policy": suite.comparison_policy.model_dump(mode="json")
        == {
            "columns": "exact",
            "column_order": "exact",
            "types": "exact",
            "nulls": "exact",
            "decimals": "exact",
            "datetimes": "exact_microseconds",
            "ordered_rows": "exact_sequence",
            "unordered_rows": "canonical_multiset",
            "numeric_tolerance": None,
        },
        "execution_limits": suite.execution_limits.model_dump(mode="json")
        == {
            "max_sql_bytes": 65_536,
            "timeout_ms": 5_000,
            "max_rows": 1_000,
            "max_output_bytes": 1_048_576,
        },
    }
    invalid = [name for name, valid in bindings.items() if not valid]
    if invalid:
        raise ValueError(f"evaluation suite frozen binding mismatch: {invalid}")


def _expected_column_types_digest(suite: EvaluationSuiteManifest) -> str:
    payload = {
        case.case_id: case.expected_column_types
        for case in suite.cases
        if case.expected_column_types is not None
    }
    return canonical_json_digest(payload)


def _validate_catalog_bindings(
    suite: EvaluationSuiteManifest,
    catalog: BenchmarkCatalog,
) -> None:
    bindings = {
        "dataset_id": suite.dataset.dataset_id == catalog.dataset_id,
        "dataset_version": suite.dataset.dataset_version == catalog.dataset_version,
        "dataset_digest": suite.dataset.dataset_digest == catalog.dataset_digest,
        "schema_revision": suite.schema_revision == catalog.schema_revision,
        "business_definition_id": (
            suite.business_definition.business_definition_id == catalog.business_definition_id
        ),
        "business_definition_version": (
            suite.business_definition.business_definition_version
            == catalog.business_definition_version
        ),
        "business_definition_digest": (
            suite.business_definition.business_definition_digest
            == catalog.business_definition_digest
        ),
        "catalog_id": suite.catalog.catalog_id == catalog.catalog_id,
        "catalog_version": suite.catalog.catalog_version == catalog.catalog_version,
        "oracle_assets_digest": suite.oracle_assets_digest == catalog.oracle_assets_digest,
    }
    invalid = [name for name, valid in bindings.items() if not valid]
    if invalid:
        raise ValueError(f"evaluation suite catalog binding mismatch: {invalid}")


def _validate_case_partition(
    suite: EvaluationSuiteManifest,
    catalog: BenchmarkCatalog,
) -> None:
    if [case.case_id for case in suite.cases] != [case.case_id for case in catalog.cases]:
        raise ValueError("evaluation suite case order or partition differs from Gold catalog")

    counts = {status: 0 for status in _EXPECTED_PARTITION}
    suite_by_id = {case.case_id: case for case in suite.cases}
    for catalog_case in catalog.cases:
        counts[catalog_case.status] += 1
        suite_case = suite_by_id[catalog_case.case_id]
        expected_action = _EXPECTED_ACTION_BY_STATUS[catalog_case.status]
        if suite_case.expected_action is not expected_action:
            raise ValueError(f"evaluation action mismatch: {catalog_case.case_id}")

    if counts != _EXPECTED_PARTITION:
        raise ValueError(f"evaluation suite case partition mismatch: {counts}")

    actual_codes = {
        case.case_id: case.clarification_code
        for case in suite.cases
        if case.expected_action is ExpectedAction.REQUEST_CLARIFICATION
    }
    if actual_codes != M1_2B_CLARIFICATION_CODES:
        raise ValueError("evaluation suite clarification code mapping mismatch")
