"""Benchmark-only Gold SQL execution helpers, isolated from future Agent runtime code."""

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Connection, text

from insightops.benchmark.contracts import BenchmarkCase, BenchmarkStatus, ExpectedValue


def execute_gold_case(
    connection: Connection,
    benchmark_root: Path,
    case: BenchmarkCase,
) -> tuple[tuple[str, ...], tuple[dict[str, ExpectedValue], ...]]:
    """Execute one trusted, version-controlled Gold SQL file and canonicalize its rows."""
    if case.status is not BenchmarkStatus.EXECUTABLE or case.gold_sql_path is None:
        raise ValueError(f"benchmark case {case.case_id} is not executable")
    sql_path = _safe_oracle_path(benchmark_root, case.gold_sql_path)
    sql = sql_path.read_text(encoding="utf-8").strip()
    if ";" in sql:
        raise ValueError(f"Gold SQL must contain exactly one statement: {case.case_id}")
    if not sql.upper().startswith(("SELECT", "WITH")):
        raise ValueError(f"Gold SQL must be a read-only query: {case.case_id}")

    result = connection.execute(text(sql), case.parameters)
    columns = tuple(result.keys())
    rows = tuple(
        {column_name: canonicalize_result_value(row[column_name]) for column_name in columns}
        for row in result.mappings()
    )
    return columns, rows


def canonicalize_result_value(value: object) -> ExpectedValue:
    """Preserve exact counts, decimals, booleans, nulls, and deterministic timestamps."""
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat(timespec="microseconds")
    raise TypeError(f"unsupported benchmark result type: {type(value).__name__}")


def _safe_oracle_path(benchmark_root: Path, relative_path: str) -> Path:
    root = benchmark_root.resolve()
    path = (root / relative_path).resolve()
    if not path.is_relative_to(root):
        raise ValueError("oracle path escapes benchmark root")
    return path
