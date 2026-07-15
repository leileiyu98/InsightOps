"""Load and validate benchmark metadata while preserving oracle isolation."""

import hashlib
import json
from pathlib import Path
from typing import Any

from insightops.benchmark.contracts import (
    BenchmarkCatalog,
    BenchmarkStatus,
    ExpectedResult,
    PublicBenchmarkCase,
)
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


def compute_sql_digest(sql_path: Path) -> str:
    """Hash exact version-controlled SQL bytes."""
    return hashlib.sha256(sql_path.read_bytes()).hexdigest()


def compute_expected_result_digest(expected: ExpectedResult) -> str:
    """Hash expected-result semantics without the back-reference to oracle digest."""
    return _canonical_digest(expected.model_dump(mode="json", exclude={"oracle_assets_digest"}))


def compute_oracle_assets_digest(catalog: BenchmarkCatalog) -> str:
    """Hash catalog metadata plus every declared SQL and expected-result digest."""
    return _canonical_digest(catalog.model_dump(mode="json", exclude={"oracle_assets_digest"}))


def validate_benchmark_bundle(
    benchmark_root: Path,
    catalog: BenchmarkCatalog,
    dataset_manifest: DatasetManifest,
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
        "oracle_assets_digest": (
            catalog.oracle_assets_digest,
            dataset_manifest.oracle_assets_digest,
        ),
    }
    mismatches = [name for name, values in bindings.items() if values[0] != values[1]]
    if mismatches:
        raise ValueError(f"benchmark manifest binding mismatch: {mismatches}")

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
            "oracle_assets_digest": (expected.oracle_assets_digest == catalog.oracle_assets_digest),
            "case_id": expected.case_id == case.case_id,
        }
        invalid = [name for name, valid in expected_bindings.items() if not valid]
        if invalid:
            raise ValueError(f"expected result binding mismatch {case.case_id}: {invalid}")

    if compute_oracle_assets_digest(catalog) != catalog.oracle_assets_digest:
        raise ValueError("oracle assets digest mismatch")


def _safe_asset_path(benchmark_root: Path, relative_path: str) -> Path:
    root = benchmark_root.resolve()
    path = (root / relative_path).resolve()
    if not path.is_relative_to(root):
        raise ValueError("benchmark asset path escapes benchmark root")
    return path


def _canonical_digest(payload: Any) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
