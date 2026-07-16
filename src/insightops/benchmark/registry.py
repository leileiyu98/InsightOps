"""Load and validate benchmark metadata while preserving oracle isolation."""

import hashlib
from pathlib import Path

from insightops.benchmark.contracts import (
    BaselineDeltaReport,
    BaselineIndex,
    BenchmarkCatalog,
    BenchmarkStatus,
    ExpectedResult,
    PublicBenchmarkCase,
)
from insightops.canonical import canonical_json_digest, compute_business_definition_digest
from insightops.seed.contracts import DatasetManifest


def load_benchmark_catalog(catalog_path: Path) -> BenchmarkCatalog:
    """Load the full benchmark-only catalog for tests and evaluation tooling."""
    return BenchmarkCatalog.model_validate_json(catalog_path.read_text(encoding="utf-8"))


def public_benchmark_cases(catalog: BenchmarkCatalog) -> tuple[PublicBenchmarkCase, ...]:
    """Return metadata that cannot reveal Gold SQL or expected result locations."""
    return tuple(case.to_public_case() for case in catalog.cases)


def load_expected_result(result_path: Path) -> ExpectedResult:
    """Load one benchmark-only expected result artifact."""
    return ExpectedResult.model_validate_json(result_path.read_text(encoding="utf-8"))


def load_baseline_index(index_path: Path) -> BaselineIndex:
    """Load the compact v1.0.0 index without consulting Git history."""
    return BaselineIndex.model_validate_json(index_path.read_text(encoding="utf-8"))


def load_baseline_delta_report(report_path: Path) -> BaselineDeltaReport:
    """Load the reviewed v1.0.0 to v1.1.0 business-result delta report."""
    return BaselineDeltaReport.model_validate_json(report_path.read_text(encoding="utf-8"))


def compute_sql_digest(sql_path: Path) -> str:
    """Hash exact version-controlled SQL bytes."""
    return hashlib.sha256(sql_path.read_bytes()).hexdigest()


def compute_expected_result_digest(expected: ExpectedResult) -> str:
    """Hash expected-result semantics without the back-reference to oracle digest."""
    return canonical_json_digest(expected.model_dump(mode="json", exclude={"oracle_assets_digest"}))


def compute_business_result_digest(expected: ExpectedResult) -> str:
    """Hash only the case result semantics, excluding all version bindings."""
    return canonical_json_digest(
        {
            "case_id": expected.case_id,
            "columns": expected.columns,
            "ordered_by": expected.ordered_by,
            "rows": expected.rows,
        }
    )


def compute_catalog_digest(catalog: BenchmarkCatalog) -> str:
    """Hash the complete canonical catalog, including its oracle binding."""
    return canonical_json_digest(catalog.model_dump(mode="json"))


def compute_oracle_assets_digest(catalog: BenchmarkCatalog) -> str:
    """Hash catalog metadata plus every declared SQL and expected-result digest."""
    return canonical_json_digest(catalog.model_dump(mode="json", exclude={"oracle_assets_digest"}))


def validate_benchmark_bundle(
    benchmark_root: Path,
    catalog: BenchmarkCatalog,
    dataset_manifest: DatasetManifest,
    business_definition_path: Path,
) -> None:
    """Validate the complete dataset/schema/definition/catalog/oracle version chain."""
    bindings = {
        "catalog_id": (catalog.catalog_id, dataset_manifest.benchmark_catalog_id),
        "catalog_version": (
            catalog.catalog_version,
            dataset_manifest.benchmark_catalog_version,
        ),
        "dataset_id": (catalog.dataset_id, dataset_manifest.dataset_id),
        "dataset_version": (catalog.dataset_version, dataset_manifest.dataset_version),
        "dataset_digest": (catalog.dataset_digest, dataset_manifest.dataset_digest),
        "schema_revision": (catalog.schema_revision, dataset_manifest.schema_revision),
        "business_definition_id": (
            catalog.business_definition_id,
            dataset_manifest.business_definition_id,
        ),
        "business_definition_version": (
            catalog.business_definition_version,
            dataset_manifest.business_definition_version,
        ),
        "business_definition_digest": (
            catalog.business_definition_digest,
            dataset_manifest.business_definition_digest,
        ),
        "oracle_assets_digest": (
            catalog.oracle_assets_digest,
            dataset_manifest.oracle_assets_digest,
        ),
    }
    mismatches = [name for name, values in bindings.items() if values[0] != values[1]]
    if mismatches:
        raise ValueError(f"benchmark manifest binding mismatch: {mismatches}")

    computed_definition_digest = compute_business_definition_digest(business_definition_path)
    if computed_definition_digest != catalog.business_definition_digest:
        raise ValueError("Business Definitions content digest mismatch")

    for case in catalog.cases:
        if case.status is not BenchmarkStatus.EXECUTABLE:
            continue
        if (
            case.gold_sql_path is None
            or case.expected_result_path is None
            or case.gold_sql_digest is None
            or case.expected_result_digest is None
        ):
            raise ValueError(f"executable case has incomplete oracle binding: {case.case_id}")
        sql_path = _safe_asset_path(benchmark_root, case.gold_sql_path)
        expected_path = _safe_asset_path(benchmark_root, case.expected_result_path)
        if compute_sql_digest(sql_path) != case.gold_sql_digest:
            raise ValueError(f"Gold SQL digest mismatch: {case.case_id}")
        expected = load_expected_result(expected_path)
        if compute_expected_result_digest(expected) != case.expected_result_digest:
            raise ValueError(f"expected result digest mismatch: {case.case_id}")
        expected_bindings = {
            "catalog_id": expected.catalog_id == catalog.catalog_id,
            "catalog_version": expected.catalog_version == catalog.catalog_version,
            "dataset_id": expected.dataset_id == catalog.dataset_id,
            "dataset_version": expected.dataset_version == catalog.dataset_version,
            "dataset_digest": expected.dataset_digest == catalog.dataset_digest,
            "schema_revision": expected.schema_revision == catalog.schema_revision,
            "business_definition_id": (
                expected.business_definition_id == catalog.business_definition_id
            ),
            "business_definition_version": (
                expected.business_definition_version == catalog.business_definition_version
            ),
            "business_definition_digest": (
                expected.business_definition_digest == catalog.business_definition_digest
            ),
            "oracle_assets_digest": (expected.oracle_assets_digest == catalog.oracle_assets_digest),
            "case_id": expected.case_id == case.case_id,
        }
        invalid = [name for name, valid in expected_bindings.items() if not valid]
        if invalid:
            raise ValueError(f"expected result binding mismatch {case.case_id}: {invalid}")

    if compute_oracle_assets_digest(catalog) != catalog.oracle_assets_digest:
        raise ValueError("oracle assets digest mismatch")


def validate_baseline_delta(
    benchmark_root: Path,
    catalog: BenchmarkCatalog,
    baseline: BaselineIndex,
    report: BaselineDeltaReport,
) -> None:
    """Validate the checked-in baseline/report/current-assets chain without Git."""
    report_bindings = {
        "from_dataset_version": report.from_dataset_version == baseline.dataset_version,
        "from_dataset_digest": report.from_dataset_digest == baseline.dataset_digest,
        "from_catalog_digest": report.from_catalog_digest == baseline.catalog_digest,
        "from_oracle_assets_digest": (
            report.from_oracle_assets_digest == baseline.oracle_assets_digest
        ),
        "from_git_commit": report.from_git_commit == baseline.baseline_git_commit,
        "to_dataset_version": report.to_dataset_version == catalog.dataset_version,
        "to_dataset_digest": report.to_dataset_digest == catalog.dataset_digest,
        "to_oracle_assets_digest": (report.to_oracle_assets_digest == catalog.oracle_assets_digest),
    }
    invalid_bindings = [name for name, valid in report_bindings.items() if not valid]
    if invalid_bindings:
        raise ValueError(f"baseline delta binding mismatch: {invalid_bindings}")

    baseline_by_id = {case.case_id: case for case in baseline.cases}
    current_by_id = {
        case.case_id: case for case in catalog.cases if case.status is BenchmarkStatus.EXECUTABLE
    }
    report_by_id = {case.case_id: case for case in report.old_cases}
    if set(report_by_id) != set(baseline_by_id):
        raise ValueError("baseline delta old-case set mismatch")
    if set(current_by_id) != set(baseline_by_id) | set(report.new_cases):
        raise ValueError("baseline delta executable case partition mismatch")

    for case_id, delta in report_by_id.items():
        baseline_case = baseline_by_id[case_id]
        current_case = current_by_id[case_id]
        if current_case.expected_result_path is None:
            raise ValueError(f"current executable case lacks expected result: {case_id}")
        expected = load_expected_result(
            _safe_asset_path(benchmark_root, current_case.expected_result_path)
        )
        case_bindings = {
            "old_expected_digest": (
                delta.old_expected_digest == baseline_case.expected_result_digest
            ),
            "old_business_result_digest": (
                delta.old_business_result_digest == baseline_case.business_result_digest
            ),
            "new_expected_digest": (
                delta.new_expected_digest == current_case.expected_result_digest
            ),
            "new_business_result_digest": (
                delta.new_business_result_digest == compute_business_result_digest(expected)
            ),
        }
        invalid = [name for name, valid in case_bindings.items() if not valid]
        if invalid:
            raise ValueError(f"baseline delta case mismatch {case_id}: {invalid}")


def _safe_asset_path(benchmark_root: Path, relative_path: str) -> Path:
    root = benchmark_root.resolve()
    path = (root / relative_path).resolve()
    if not path.is_relative_to(root):
        raise ValueError("benchmark asset path escapes benchmark root")
    return path
