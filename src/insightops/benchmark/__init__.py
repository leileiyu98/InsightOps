"""Benchmark case contracts isolated from future Agent runtime inputs."""

from insightops.benchmark.contracts import (
    BenchmarkCase,
    BenchmarkCatalog,
    ExpectedResult,
    PublicBenchmarkCase,
)
from insightops.benchmark.registry import load_benchmark_catalog, public_benchmark_cases

__all__ = [
    "BenchmarkCase",
    "BenchmarkCatalog",
    "ExpectedResult",
    "PublicBenchmarkCase",
    "load_benchmark_catalog",
    "public_benchmark_cases",
]
