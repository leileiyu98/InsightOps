"""Exact ordered and unordered comparison for normalized evaluation results."""

from collections import Counter

from insightops.canonical import canonical_json_bytes, canonical_json_digest
from insightops.evaluation.contracts import (
    ComparisonMode,
    EvaluationFailureCode,
    NormalizedCell,
    NormalizedResult,
    NormalizedValueType,
    ResultComparison,
)


def compare_normalized_results(
    actual: NormalizedResult,
    expected: NormalizedResult,
    mode: ComparisonMode,
) -> ResultComparison:
    """Compare columns and typed rows without tolerance or type coercion."""
    failure_code: EvaluationFailureCode | None = None
    if len(actual.columns) != len(expected.columns):
        failure_code = EvaluationFailureCode.COLUMN_COUNT_MISMATCH
    elif actual.columns != expected.columns:
        failure_code = _column_failure(actual.columns, expected.columns)
    elif len(actual.rows) != len(expected.rows):
        failure_code = EvaluationFailureCode.ROW_COUNT_MISMATCH
    elif mode is ComparisonMode.ORDERED:
        failure_code = _ordered_failure(actual, expected)
    else:
        failure_code = _unordered_failure(actual, expected)

    payload = {
        "matches": failure_code is None,
        "failure_code": failure_code,
    }
    return ResultComparison.model_validate(
        {**payload, "comparison_digest": canonical_json_digest(payload)}
    )


def _column_failure(
    actual: tuple[str, ...],
    expected: tuple[str, ...],
) -> EvaluationFailureCode:
    if set(actual) == set(expected):
        return EvaluationFailureCode.COLUMN_ORDER_MISMATCH
    return EvaluationFailureCode.COLUMN_NAME_MISMATCH


def _ordered_failure(
    actual: NormalizedResult,
    expected: NormalizedResult,
) -> EvaluationFailureCode | None:
    for actual_row, expected_row in zip(actual.rows, expected.rows, strict=True):
        cell_failure = _row_failure(actual_row, expected_row)
        if cell_failure is not None:
            return cell_failure
    return None


def _unordered_failure(
    actual: NormalizedResult,
    expected: NormalizedResult,
) -> EvaluationFailureCode | None:
    actual_rows = Counter(_row_bytes(row) for row in actual.rows)
    expected_rows = Counter(_row_bytes(row) for row in expected.rows)
    if actual_rows == expected_rows:
        return None

    actual_types = Counter(_row_type_bytes(row) for row in actual.rows)
    expected_types = Counter(_row_type_bytes(row) for row in expected.rows)
    if actual_types != expected_types:
        if _contains_null_type_difference(actual.rows, expected.rows):
            return EvaluationFailureCode.NULL_MISMATCH
        return EvaluationFailureCode.TYPE_MISMATCH
    return EvaluationFailureCode.UNORDERED_MULTISET_MISMATCH


def _row_failure(
    actual: tuple[NormalizedCell, ...],
    expected: tuple[NormalizedCell, ...],
) -> EvaluationFailureCode | None:
    for actual_cell, expected_cell in zip(actual, expected, strict=True):
        if actual_cell.value_type is not expected_cell.value_type:
            if (
                actual_cell.value_type is NormalizedValueType.NULL
                or expected_cell.value_type is NormalizedValueType.NULL
            ):
                return EvaluationFailureCode.NULL_MISMATCH
            return EvaluationFailureCode.TYPE_MISMATCH
        if actual_cell.value != expected_cell.value:
            return EvaluationFailureCode.VALUE_MISMATCH
    return None


def _contains_null_type_difference(
    actual_rows: tuple[tuple[NormalizedCell, ...], ...],
    expected_rows: tuple[tuple[NormalizedCell, ...], ...],
) -> bool:
    actual_null_counts = Counter(
        sum(cell.value_type is NormalizedValueType.NULL for cell in row) for row in actual_rows
    )
    expected_null_counts = Counter(
        sum(cell.value_type is NormalizedValueType.NULL for cell in row) for row in expected_rows
    )
    return actual_null_counts != expected_null_counts


def _row_bytes(row: tuple[NormalizedCell, ...]) -> bytes:
    return canonical_json_bytes([cell.model_dump(mode="json") for cell in row])


def _row_type_bytes(row: tuple[NormalizedCell, ...]) -> bytes:
    return canonical_json_bytes([cell.value_type.value for cell in row])
