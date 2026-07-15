"""Load benchmark metadata while preserving the Agent/oracle isolation boundary."""

from pathlib import Path

from insightops.benchmark.contracts import (
    BenchmarkCatalog,
    ExpectedResult,
    PublicBenchmarkCase,
)


def load_benchmark_catalog(catalog_path: Path) -> BenchmarkCatalog:
    """Load the full benchmark-only catalog for tests and evaluation tooling."""
    return BenchmarkCatalog.model_validate_json(catalog_path.read_text(encoding="utf-8"))


def public_benchmark_cases(catalog: BenchmarkCatalog) -> tuple[PublicBenchmarkCase, ...]:
    """Return metadata that cannot reveal Gold SQL or expected result locations."""
    return tuple(case.to_public_case() for case in catalog.cases)


def load_expected_result(result_path: Path) -> ExpectedResult:
    """Load one benchmark-only expected result artifact."""
    return ExpectedResult.model_validate_json(result_path.read_text(encoding="utf-8"))
