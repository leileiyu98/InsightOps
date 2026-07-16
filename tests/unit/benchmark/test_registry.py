"""Unit tests for benchmark status, coverage, and oracle-isolation contracts."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from insightops.benchmark.contracts import BenchmarkCase, BenchmarkStatus
from insightops.benchmark.registry import (
    load_baseline_delta_report,
    load_baseline_index,
    load_benchmark_catalog,
    validate_baseline_delta,
    validate_benchmark_bundle,
)
from insightops.seed.dataset import load_seed_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _case(**overrides: object) -> BenchmarkCase:
    values: dict[str, object] = {
        "case_id": "GQ-SAA-001",
        "question": "What is MRR?",
        "difficulty": "L1",
        "status": BenchmarkStatus.EXECUTABLE,
        "domains": ("saas",),
        "metrics": ("mrr",),
        "required_tables": ("subscription",),
        "phenomenon_ids": ("P15",),
        "scenario_ids": ("annual-mrr",),
        "expected_result_shape": "scalar",
        "gold_sql_path": "sql/GQ-SAA-001.sql",
        "expected_result_path": "expected/GQ-SAA-001.json",
        "gold_sql_digest": "0" * 64,
        "expected_result_digest": "1" * 64,
    }
    values.update(overrides)
    return BenchmarkCase.model_validate(values)


def test_public_case_drops_oracle_fields() -> None:
    public = _case().to_public_case()

    assert "gold_sql_path" not in public.model_dump()
    assert "expected_result_path" not in public.model_dump()
    assert "gold_sql_digest" not in public.model_dump()
    assert "expected_result_digest" not in public.model_dump()
    assert "oracle_visibility" not in public.model_dump()


def test_clarification_case_cannot_have_gold_sql() -> None:
    with pytest.raises(ValidationError, match="cannot expose oracle assets"):
        _case(
            status=BenchmarkStatus.CLARIFICATION_REQUIRED,
            clarification_reason="The business definition requires clarification.",
        )


def test_deferred_case_requires_reason() -> None:
    with pytest.raises(ValidationError, match="require deferred_reason"):
        _case(
            status=BenchmarkStatus.DEFERRED,
            gold_sql_path=None,
            expected_result_path=None,
            gold_sql_digest=None,
            expected_result_digest=None,
        )


def test_full_and_partial_phenomenon_coverage_must_be_disjoint() -> None:
    with pytest.raises(ValidationError, match="both full and partial"):
        _case(partial_phenomenon_coverage={"P15": "Only one part is covered."})


def test_m1_2a_benchmark_bundle_has_a_valid_version_and_digest_chain() -> None:
    benchmark_root = PROJECT_ROOT / "benchmarks" / "m1_2a"
    catalog = load_benchmark_catalog(benchmark_root / "cases.json")
    dataset = load_seed_dataset(PROJECT_ROOT / "data" / "seed" / "m1_2a")

    validate_benchmark_bundle(
        benchmark_root,
        catalog,
        dataset.manifest,
        PROJECT_ROOT / "docs" / "business-definitions-v1.md",
    )


def test_baseline_delta_is_ci_self_contained_and_matches_current_assets() -> None:
    benchmark_root = PROJECT_ROOT / "benchmarks" / "m1_2a"
    catalog = load_benchmark_catalog(benchmark_root / "cases.json")
    baseline = load_baseline_index(benchmark_root / "baseline_1.0.0_index.json")
    report = load_baseline_delta_report(benchmark_root / "baseline_delta_1.0.0_to_1.1.0.json")

    validate_baseline_delta(benchmark_root, catalog, baseline, report)


def test_benchmark_bundle_rejects_a_tampered_catalog_binding() -> None:
    benchmark_root = PROJECT_ROOT / "benchmarks" / "m1_2a"
    catalog = load_benchmark_catalog(benchmark_root / "cases.json")
    dataset = load_seed_dataset(PROJECT_ROOT / "data" / "seed" / "m1_2a")
    tampered = catalog.model_copy(update={"dataset_digest": "f" * 64})

    with pytest.raises(ValueError, match="dataset_digest"):
        validate_benchmark_bundle(
            benchmark_root,
            tampered,
            dataset.manifest,
            PROJECT_ROOT / "docs" / "business-definitions-v1.md",
        )
