"""Unit tests for strict normalization and deterministic result comparison."""

from datetime import datetime
from decimal import Decimal

import pytest

from insightops.benchmark.contracts import ExpectedResult
from insightops.evaluation.comparison import compare_normalized_results
from insightops.evaluation.contracts import (
    ComparisonMode,
    EvaluationFailureCode,
    NormalizedValueType,
)
from insightops.evaluation.normalization import (
    ResultNormalizationError,
    normalize_database_result,
    normalize_expected_result,
)


def _expected(*, columns: tuple[str, ...], rows: tuple[dict[str, object], ...]) -> ExpectedResult:
    return ExpectedResult.model_validate(
        {
            "catalog_id": "catalog",
            "catalog_version": "1.0.0",
            "dataset_id": "dataset",
            "dataset_version": "1.0.0",
            "dataset_digest": "a" * 64,
            "schema_revision": "0004",
            "business_definition_id": "definitions",
            "business_definition_version": "1.0.0",
            "business_definition_digest": "b" * 64,
            "oracle_assets_digest": "c" * 64,
            "case_id": "GQ-SAA-001",
            "columns": columns,
            "ordered_by": (),
            "rows": rows,
        }
    )


def test_database_normalization_preserves_exact_scalar_types() -> None:
    result = normalize_database_result(
        ("null_value", "flag", "count", "amount", "occurred_at", "label"),
        [
            {
                "null_value": None,
                "flag": True,
                "count": 2,
                "amount": Decimal("12.3400"),
                "occurred_at": datetime(2025, 1, 2, 3, 4, 5, 6000),
                "label": "12.3400",
            }
        ],
    )

    assert tuple(cell.value_type for cell in result.rows[0]) == (
        NormalizedValueType.NULL,
        NormalizedValueType.BOOLEAN,
        NormalizedValueType.INTEGER,
        NormalizedValueType.DECIMAL,
        NormalizedValueType.DATETIME,
        NormalizedValueType.STRING,
    )
    assert result.rows[0][3].value == "12.3400"
    assert result.rows[0][4].value == "2025-01-02T03:04:05.006000"


def test_expected_normalization_restores_frozen_decimal_and_datetime_types() -> None:
    result = normalize_expected_result(
        _expected(
            columns=("amount", "occurred_at", "label"),
            rows=(
                {
                    "amount": "12.3400",
                    "occurred_at": "2025-01-02T03:04:05.006000",
                    "label": "growth",
                },
            ),
        ),
        {
            "amount": NormalizedValueType.DECIMAL,
            "occurred_at": NormalizedValueType.DATETIME,
            "label": NormalizedValueType.STRING,
        },
    )

    assert tuple(cell.value_type for cell in result.rows[0]) == (
        NormalizedValueType.DECIMAL,
        NormalizedValueType.DATETIME,
        NormalizedValueType.STRING,
    )


def test_ordered_comparison_requires_exact_sequence() -> None:
    expected = normalize_database_result(("id",), [{"id": 1}, {"id": 2}])
    actual = normalize_database_result(("id",), [{"id": 2}, {"id": 1}])

    comparison = compare_normalized_results(actual, expected, ComparisonMode.ORDERED)

    assert not comparison.matches
    assert comparison.failure_code is EvaluationFailureCode.VALUE_MISMATCH


def test_unordered_comparison_uses_multiset_with_duplicate_counts() -> None:
    expected = normalize_database_result(("id",), [{"id": 1}, {"id": 1}, {"id": 2}])
    actual = normalize_database_result(("id",), [{"id": 2}, {"id": 1}, {"id": 1}])

    comparison = compare_normalized_results(actual, expected, ComparisonMode.UNORDERED)

    assert comparison.matches
    assert comparison.failure_code is None


def test_no_type_coercion_between_decimal_encoding_and_candidate_string() -> None:
    expected = normalize_expected_result(
        _expected(columns=("amount",), rows=({"amount": "12.3400"},)),
        {"amount": NormalizedValueType.DECIMAL},
    )
    actual = normalize_database_result(("amount",), [{"amount": "12.3400"}])

    comparison = compare_normalized_results(actual, expected, ComparisonMode.ORDERED)

    assert comparison.failure_code is EvaluationFailureCode.TYPE_MISMATCH


def test_numeric_and_iso_shaped_text_remain_declared_strings() -> None:
    expected = normalize_expected_result(
        _expected(
            columns=("numeric_label", "date_label"),
            rows=(
                {
                    "numeric_label": "1",
                    "date_label": "2025-01-02T03:04:05.006000",
                },
            ),
        ),
        {
            "numeric_label": NormalizedValueType.STRING,
            "date_label": NormalizedValueType.STRING,
        },
    )

    assert all(cell.value_type is NormalizedValueType.STRING for cell in expected.rows[0])


@pytest.mark.parametrize("candidate", [1, True, Decimal("1")])
def test_numeric_text_is_not_equal_to_integer_boolean_or_decimal(candidate: object) -> None:
    expected = normalize_expected_result(
        _expected(columns=("value",), rows=({"value": "1"},)),
        {"value": NormalizedValueType.STRING},
    )
    actual = normalize_database_result(("value",), [{"value": candidate}])

    comparison = compare_normalized_results(actual, expected, ComparisonMode.ORDERED)

    assert comparison.failure_code is EvaluationFailureCode.TYPE_MISMATCH


def test_integer_is_not_equal_to_boolean() -> None:
    expected = normalize_expected_result(
        _expected(columns=("value",), rows=({"value": 1},)),
        {"value": NormalizedValueType.INTEGER},
    )
    actual = normalize_database_result(("value",), [{"value": True}])

    comparison = compare_normalized_results(actual, expected, ComparisonMode.ORDERED)

    assert comparison.failure_code is EvaluationFailureCode.TYPE_MISMATCH


def test_declared_integer_boolean_decimal_and_datetime_are_strict() -> None:
    expected = normalize_expected_result(
        _expected(
            columns=("count", "flag", "amount", "occurred_at"),
            rows=(
                {
                    "count": 1,
                    "flag": True,
                    "amount": "1.00",
                    "occurred_at": "2025-01-02T03:04:05.006000",
                },
            ),
        ),
        {
            "count": NormalizedValueType.INTEGER,
            "flag": NormalizedValueType.BOOLEAN,
            "amount": NormalizedValueType.DECIMAL,
            "occurred_at": NormalizedValueType.DATETIME,
        },
    )

    assert tuple(cell.value_type for cell in expected.rows[0]) == (
        NormalizedValueType.INTEGER,
        NormalizedValueType.BOOLEAN,
        NormalizedValueType.DECIMAL,
        NormalizedValueType.DATETIME,
    )


def test_decimal_scale_is_part_of_strict_value_comparison() -> None:
    expected = normalize_expected_result(
        _expected(columns=("amount",), rows=({"amount": "1.00"},)),
        {"amount": NormalizedValueType.DECIMAL},
    )
    actual = normalize_database_result(("amount",), [{"amount": Decimal("1.0")}])

    comparison = compare_normalized_results(actual, expected, ComparisonMode.ORDERED)

    assert comparison.failure_code is EvaluationFailureCode.VALUE_MISMATCH


@pytest.mark.parametrize(
    "value,declared_type",
    [
        (True, NormalizedValueType.INTEGER),
        (1, NormalizedValueType.BOOLEAN),
        ("not-a-decimal", NormalizedValueType.DECIMAL),
        ("2025-01-02", NormalizedValueType.DATETIME),
    ],
)
def test_expected_value_must_match_declared_type(
    value: object,
    declared_type: NormalizedValueType,
) -> None:
    with pytest.raises(ResultNormalizationError):
        normalize_expected_result(
            _expected(columns=("value",), rows=({"value": value},)),
            {"value": declared_type},
        )


def test_expected_type_metadata_must_match_columns() -> None:
    with pytest.raises(ResultNormalizationError, match="metadata does not match"):
        normalize_expected_result(
            _expected(columns=("value",), rows=({"value": "text"},)),
            {"other": NormalizedValueType.STRING},
        )


def test_null_and_column_order_mismatches_are_distinct() -> None:
    expected = normalize_database_result(("a", "b"), [{"a": None, "b": 1}])
    null_actual = normalize_database_result(("a", "b"), [{"a": "", "b": 1}])
    columns_actual = normalize_database_result(("b", "a"), [{"b": 1, "a": None}])

    assert (
        compare_normalized_results(null_actual, expected, ComparisonMode.ORDERED).failure_code
        is EvaluationFailureCode.NULL_MISMATCH
    )
    assert (
        compare_normalized_results(columns_actual, expected, ComparisonMode.ORDERED).failure_code
        is EvaluationFailureCode.COLUMN_ORDER_MISMATCH
    )


def test_float_is_rejected_instead_of_applying_tolerance() -> None:
    with pytest.raises(ResultNormalizationError, match="unsupported result type"):
        normalize_database_result(("value",), [{"value": 1.5}])


def test_normalization_and_comparison_digests_are_stable() -> None:
    first = normalize_database_result(("id",), [{"id": 1}])
    second = normalize_database_result(("id",), [{"id": 1}])
    first_comparison = compare_normalized_results(first, second, ComparisonMode.ORDERED)
    second_comparison = compare_normalized_results(first, second, ComparisonMode.ORDERED)

    assert first.result_digest == second.result_digest
    assert first_comparison.comparison_digest == second_comparison.comparison_digest
