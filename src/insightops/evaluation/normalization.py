"""Strict typed result normalization for deterministic evaluation."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal, InvalidOperation

from insightops.benchmark.contracts import ExpectedResult, ExpectedValue
from insightops.canonical import canonical_json_digest
from insightops.evaluation.contracts import (
    NormalizedCell,
    NormalizedResult,
    NormalizedValueType,
)


class ResultNormalizationError(TypeError):
    """Raised when a database value has no exact deterministic representation."""


def normalize_database_result(
    columns: Sequence[str],
    rows: Sequence[Mapping[str, object]],
) -> NormalizedResult:
    """Normalize database-returned values without coercing between scalar types."""
    normalized_columns = tuple(columns)
    normalized_rows = tuple(
        tuple(_normalize_database_value(row[column]) for column in normalized_columns)
        for row in rows
    )
    return _build_result(normalized_columns, normalized_rows)


def normalize_expected_result(
    expected: ExpectedResult,
    column_types: Mapping[str, NormalizedValueType],
) -> NormalizedResult:
    """Decode the M1.2A oracle only through reviewed, digest-bound column types."""
    if set(column_types) != set(expected.columns):
        raise ResultNormalizationError("expected column type metadata does not match columns")
    normalized_rows = tuple(
        tuple(
            _normalize_expected_value(row[column], column_types[column])
            for column in expected.columns
        )
        for row in expected.rows
    )
    return _build_result(expected.columns, normalized_rows)


def _normalize_database_value(value: object) -> NormalizedCell:
    if value is None:
        return NormalizedCell(value_type=NormalizedValueType.NULL, value=None)
    if type(value) is bool:
        return NormalizedCell(value_type=NormalizedValueType.BOOLEAN, value=value)
    if type(value) is int:
        return NormalizedCell(value_type=NormalizedValueType.INTEGER, value=value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ResultNormalizationError("non-finite Decimal is unsupported")
        return NormalizedCell(value_type=NormalizedValueType.DECIMAL, value=format(value, "f"))
    if isinstance(value, datetime):
        return NormalizedCell(
            value_type=NormalizedValueType.DATETIME,
            value=value.isoformat(timespec="microseconds"),
        )
    if isinstance(value, str):
        return NormalizedCell(value_type=NormalizedValueType.STRING, value=value)
    raise ResultNormalizationError(f"unsupported result type: {type(value).__name__}")


def _normalize_expected_value(
    value: ExpectedValue,
    declared_type: NormalizedValueType,
) -> NormalizedCell:
    if value is None:
        return NormalizedCell(value_type=NormalizedValueType.NULL, value=None)
    if declared_type is NormalizedValueType.NULL:
        raise ResultNormalizationError("non-null value declared as null")
    if declared_type is NormalizedValueType.BOOLEAN and type(value) is bool:
        return NormalizedCell(value_type=NormalizedValueType.BOOLEAN, value=value)
    if declared_type is NormalizedValueType.INTEGER and type(value) is int:
        return NormalizedCell(value_type=NormalizedValueType.INTEGER, value=value)
    if declared_type is NormalizedValueType.STRING and isinstance(value, str):
        return NormalizedCell(value_type=NormalizedValueType.STRING, value=value)
    if declared_type is NormalizedValueType.DECIMAL and isinstance(value, str):
        try:
            decimal = Decimal(value)
        except InvalidOperation as error:
            raise ResultNormalizationError("invalid declared decimal value") from error
        if not decimal.is_finite():
            raise ResultNormalizationError("non-finite declared decimal is unsupported")
        return NormalizedCell(value_type=NormalizedValueType.DECIMAL, value=value)
    if declared_type is NormalizedValueType.DATETIME and isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as error:
            raise ResultNormalizationError("invalid declared datetime value") from error
        if parsed.isoformat(timespec="microseconds") != value:
            raise ResultNormalizationError("datetime must use canonical microsecond precision")
        return NormalizedCell(value_type=NormalizedValueType.DATETIME, value=value)
    raise ResultNormalizationError(
        f"expected value does not match declared {declared_type.value} type"
    )


def _build_result(
    columns: tuple[str, ...],
    rows: tuple[tuple[NormalizedCell, ...], ...],
) -> NormalizedResult:
    payload = {"columns": columns, "rows": rows}
    digest_payload = {
        "columns": columns,
        "rows": [[cell.model_dump(mode="json") for cell in row] for row in rows],
    }
    return NormalizedResult.model_validate(
        {**payload, "result_digest": canonical_json_digest(digest_payload)}
    )
