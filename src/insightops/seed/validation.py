"""Deterministic cross-record validation for the M1.2A business dataset."""

import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation

from insightops.seed.contracts import (
    DatasetManifest,
    SeedRecord,
    SeedReference,
    SeedSource,
)

EXPECTED_TABLES = {
    "organization",
    "organization_member",
    "consumer",
    "merchant",
    "saas_plan_version",
    "subscription",
    "subscription_state_event",
    "subscription_invoice",
    "invoice_payment_attempt",
    "product",
    "commerce_order",
    "commerce_order_item",
    "commerce_refund",
    "platform_fee_charge",
    "refund_item_allocation",
}
MONEY_PATTERN = re.compile(r"^\d+\.\d{4}$")
UTC_DATETIME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{6}$")


def validate_business_dataset(
    manifest: DatasetManifest,
    sources: tuple[SeedSource, ...],
) -> None:
    """Validate business invariants that are not expressible as row-level checks."""
    if not sources:
        return

    records = {
        (table.table_name, record.record_id): record
        for source in sources
        for table in source.tables
        for record in table.records
    }
    table_names = {table_name for table_name, _record_id in records}
    if table_names != EXPECTED_TABLES:
        raise ValueError(
            f"M1.2A dataset must cover the current 15 tables; got {sorted(table_names)}"
        )

    _validate_scalar_formats(manifest, records)
    _validate_merchant_intervals(records)
    _validate_subscription_history(records)
    _validate_invoice_payments(records)
    _validate_commerce_relationships(records)
    _validate_refund_allocations(records)
    _validate_test_coverage(records)


def _validate_scalar_formats(
    manifest: DatasetManifest,
    records: dict[tuple[str, str], SeedRecord],
) -> None:
    cutoff = manifest.snapshot_cutoff.replace(tzinfo=None)
    for (table_name, record_id), record in records.items():
        for column_name, value in record.values.items():
            if value is None or isinstance(value, (SeedReference, bool, int)):
                continue
            if _is_datetime_column(column_name):
                if not UTC_DATETIME_PATTERN.fullmatch(value):
                    raise ValueError(
                        f"{table_name}:{record_id}.{column_name} must be fixed UTC DATETIME(6)"
                    )
                parsed = datetime.fromisoformat(value)
                if column_name == "recorded_at" and parsed > cutoff:
                    raise ValueError(f"{table_name}:{record_id} is recorded after snapshot cutoff")
            if _is_money_column(column_name):
                if not MONEY_PATTERN.fullmatch(value):
                    raise ValueError(
                        f"{table_name}:{record_id}.{column_name} must have four decimals"
                    )
                try:
                    amount = Decimal(value)
                except InvalidOperation as error:
                    raise ValueError(
                        f"{table_name}:{record_id}.{column_name} is not decimal"
                    ) from error
                if amount < 0:
                    raise ValueError(f"{table_name}:{record_id}.{column_name} cannot be negative")


def _validate_merchant_intervals(records: dict[tuple[str, str], SeedRecord]) -> None:
    by_merchant: dict[int, list[tuple[datetime, datetime | None, str]]] = defaultdict(list)
    for (table_name, record_id), record in records.items():
        if table_name != "merchant":
            continue
        merchant_id = record.values["merchant_id"]
        if not isinstance(merchant_id, int):
            raise ValueError(f"merchant:{record_id}.merchant_id must be an integer")
        start = _datetime_value(record, "assignment_valid_from")
        end = _optional_datetime_value(record, "assignment_valid_to")
        by_merchant[merchant_id].append((start, end, record_id))

    for merchant_id, intervals in by_merchant.items():
        intervals.sort(key=lambda interval: interval[0])
        for previous, current in zip(intervals, intervals[1:], strict=False):
            previous_end = previous[1]
            if previous_end is None or current[0] < previous_end:
                raise ValueError(
                    f"merchant {merchant_id} has overlapping assignments: "
                    f"{previous[2]}, {current[2]}"
                )


def _validate_subscription_history(records: dict[tuple[str, str], SeedRecord]) -> None:
    events_by_subscription: dict[str, list[SeedRecord]] = defaultdict(list)
    for (table_name, _record_id), record in records.items():
        if table_name != "subscription_state_event":
            continue
        subscription_ref = _reference_value(record, "subscription_id", "subscription")
        events_by_subscription[subscription_ref.record_id].append(record)
        before = _decimal_value(record, "normalized_mrr_before")
        after = _decimal_value(record, "normalized_mrr_after")
        event_type = _string_value(record, "event_type")
        if event_type == "expansion" and after <= before:
            raise ValueError("expansion event must increase normalized MRR")
        if event_type == "contraction" and not (Decimal("0") < after < before):
            raise ValueError("contraction event must retain positive, lower normalized MRR")
        if event_type in {"cancellation_effective", "expiration"} and after != 0:
            raise ValueError("terminal subscription events must set normalized MRR to zero")
        _validate_normalization(record, "before")
        _validate_normalization(record, "after")

    for (table_name, record_id), subscription in records.items():
        if table_name != "subscription":
            continue
        events = events_by_subscription.get(record_id, [])
        if not events:
            raise ValueError(f"subscription:{record_id} has no state event")
        latest = max(events, key=lambda event: _datetime_value(event, "effective_at"))
        if subscription.values["current_status"] != latest.values["status_after"]:
            raise ValueError(f"subscription:{record_id} current status disagrees with history")
        current_plan = _reference_value(
            subscription,
            "current_plan_version_id",
            "saas_plan_version",
        )
        latest_plan = _reference_value(
            latest,
            "plan_version_after_id",
            "saas_plan_version",
        )
        if current_plan.record_id != latest_plan.record_id:
            raise ValueError(f"subscription:{record_id} current plan disagrees with history")


def _validate_normalization(record: SeedRecord, suffix: str) -> None:
    interval = record.values[f"billing_interval_{suffix}"]
    if interval is None:
        return
    if not isinstance(interval, str):
        raise ValueError("billing interval must be a string")
    recurring = _decimal_value(record, f"recurring_amount_{suffix}")
    normalized = _decimal_value(record, f"normalized_mrr_{suffix}")
    expected = recurring if interval == "monthly" else recurring / Decimal("12")
    if normalized != expected:
        raise ValueError(
            f"subscription event {record.record_id} has invalid {suffix} MRR normalization"
        )


def _validate_invoice_payments(records: dict[tuple[str, str], SeedRecord]) -> None:
    succeeded_invoice_ids = {
        _reference_value(record, "subscription_invoice_id", "subscription_invoice").record_id
        for (table_name, _record_id), record in records.items()
        if table_name == "invoice_payment_attempt" and record.values["status"] == "succeeded"
    }
    for (table_name, record_id), invoice in records.items():
        if table_name == "subscription_invoice" and invoice.values["status"] == "paid":
            if record_id not in succeeded_invoice_ids:
                raise ValueError(f"paid invoice {record_id} has no succeeded payment attempt")


def _validate_commerce_relationships(records: dict[tuple[str, str], SeedRecord]) -> None:
    for (table_name, record_id), order_item in records.items():
        if table_name != "commerce_order_item":
            continue
        order_ref = _reference_value(order_item, "commerce_order_id", "commerce_order")
        product_ref = _reference_value(order_item, "product_id", "product")
        order = records[("commerce_order", order_ref.record_id)]
        product = records[("product", product_ref.record_id)]
        if order.values["merchant_assignment_id"] != product.values["merchant_assignment_id"]:
            raise ValueError(f"commerce item {record_id} crosses merchant ownership")


def _validate_refund_allocations(records: dict[tuple[str, str], SeedRecord]) -> None:
    allocated: dict[str, Decimal] = defaultdict(Decimal)
    for (table_name, record_id), allocation in records.items():
        if table_name != "refund_item_allocation":
            continue
        refund_ref = _reference_value(allocation, "commerce_refund_id", "commerce_refund")
        item_ref = _reference_value(
            allocation,
            "commerce_order_item_id",
            "commerce_order_item",
        )
        refund = records[("commerce_refund", refund_ref.record_id)]
        item = records[("commerce_order_item", item_ref.record_id)]
        refund_order = _reference_value(refund, "commerce_order_id", "commerce_order")
        item_order = _reference_value(item, "commerce_order_id", "commerce_order")
        if refund_order.record_id != item_order.record_id:
            raise ValueError(f"refund allocation {record_id} crosses orders")
        allocated[refund_ref.record_id] += _decimal_value(allocation, "allocated_item_amount")

    for (table_name, record_id), refund in records.items():
        if table_name != "commerce_refund":
            continue
        if allocated[record_id] != _decimal_value(refund, "item_refund_amount"):
            raise ValueError(f"refund {record_id} allocation sum does not match item amount")


def _validate_test_coverage(records: dict[tuple[str, str], SeedRecord]) -> None:
    covered = {
        table_name
        for (table_name, _record_id), record in records.items()
        if record.values.get("is_test") is True
    }
    missing = EXPECTED_TABLES - covered
    if missing:
        raise ValueError(f"seed dataset lacks explicit test coverage for: {sorted(missing)}")


def _reference_value(record: SeedRecord, column_name: str, table_name: str) -> SeedReference:
    value = record.values[column_name]
    if not isinstance(value, SeedReference) or value.table != table_name:
        raise ValueError(f"{record.record_id}.{column_name} must reference {table_name}")
    return value


def _string_value(record: SeedRecord, column_name: str) -> str:
    value = record.values[column_name]
    if not isinstance(value, str):
        raise ValueError(f"{record.record_id}.{column_name} must be a string")
    return value


def _decimal_value(record: SeedRecord, column_name: str) -> Decimal:
    return Decimal(_string_value(record, column_name))


def _datetime_value(record: SeedRecord, column_name: str) -> datetime:
    return datetime.fromisoformat(_string_value(record, column_name))


def _optional_datetime_value(record: SeedRecord, column_name: str) -> datetime | None:
    value = record.values[column_name]
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{record.record_id}.{column_name} must be datetime or null")
    return datetime.fromisoformat(value)


def _is_datetime_column(column_name: str) -> bool:
    return column_name.endswith("_at") or column_name in {
        "effective_from",
        "effective_to",
        "assignment_valid_from",
        "assignment_valid_to",
    }


def _is_money_column(column_name: str) -> bool:
    return column_name.endswith("_amount") or column_name.startswith("normalized_mrr_")
