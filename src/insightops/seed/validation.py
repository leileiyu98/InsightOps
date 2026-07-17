"""Deterministic cross-record validation for the M1.2A business dataset."""

import re
from collections import defaultdict
from datetime import datetime, timedelta
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
    "marketing_channel",
    "marketing_campaign",
    "campaign_daily_spend",
    "marketing_touch",
    "attributed_conversion",
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
            f"M1.2A dataset must cover the current 20 tables; got {sorted(table_names)}"
        )

    _validate_scalar_formats(manifest, records)
    _validate_merchant_intervals(records)
    _validate_subscription_history(records)
    _validate_invoice_payments(records)
    _validate_commerce_relationships(records)
    _validate_refund_allocations(records)
    _validate_marketing_campaigns(records)
    _validate_campaign_spend(records)
    _validate_marketing_touches(records)
    _validate_attributed_conversions(manifest, records)
    _validate_attribution_revision_chains(records)
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


def _validate_marketing_campaigns(records: dict[tuple[str, str], SeedRecord]) -> None:
    for (table_name, record_id), campaign in records.items():
        if table_name != "marketing_campaign":
            continue
        channel_ref = _reference_value(
            campaign,
            "primary_channel_id",
            "marketing_channel",
        )
        _record(records, channel_ref)
        organization_ref = _reference_value(campaign, "organization_id", "organization")
        _record(records, organization_ref)
        merchant_value = campaign.values["merchant_assignment_id"]
        scope = _string_value(campaign, "business_scope")
        if scope == "saas":
            if merchant_value is not None:
                raise ValueError(f"marketing campaign {record_id} crosses SaaS into merchant scope")
            continue
        if not isinstance(merchant_value, SeedReference) or merchant_value.table != "merchant":
            raise ValueError(f"commerce campaign {record_id} requires a merchant assignment")
        merchant = _record(records, merchant_value)
        merchant_org = _reference_value(merchant, "organization_id", "organization")
        if merchant_org.record_id != organization_ref.record_id:
            raise ValueError(f"marketing campaign {record_id} disagrees with merchant organization")


def _validate_campaign_spend(records: dict[tuple[str, str], SeedRecord]) -> None:
    groups: dict[tuple[str, str], list[SeedRecord]] = defaultdict(list)
    superseded_ids: set[str] = set()
    for (table_name, record_id), spend in records.items():
        if table_name != "campaign_daily_spend":
            continue
        campaign_ref = _reference_value(
            spend,
            "marketing_campaign_id",
            "marketing_campaign",
        )
        _record(records, campaign_ref)
        business_date = _string_value(spend, "business_date")
        groups[(campaign_ref.record_id, business_date)].append(spend)
        if _datetime_value(spend, "finalized_at") > _datetime_value(spend, "recorded_at"):
            raise ValueError(f"campaign spend {record_id} is visible before finalization")

    for (campaign_id, business_date), revisions in groups.items():
        revisions.sort(key=lambda item: _integer_value(item, "version_number"))
        for expected_version, revision in enumerate(revisions, start=1):
            actual_version = _integer_value(revision, "version_number")
            if actual_version != expected_version:
                raise ValueError(f"campaign spend {campaign_id}/{business_date} has a version gap")
            supersedes = revision.values["supersedes_campaign_daily_spend_id"]
            if expected_version == 1:
                if supersedes is not None:
                    raise ValueError("campaign spend version 1 cannot supersede another revision")
                continue
            if not isinstance(supersedes, SeedReference) or supersedes.table != (
                "campaign_daily_spend"
            ):
                raise ValueError("campaign spend correction must reference its predecessor")
            predecessor = revisions[expected_version - 2]
            if supersedes.record_id != predecessor.record_id:
                raise ValueError("campaign spend correction must supersede the previous version")
            if supersedes.record_id in superseded_ids:
                raise ValueError("campaign spend revision chain cannot fork")
            if _datetime_value(revision, "recorded_at") <= _datetime_value(
                predecessor, "recorded_at"
            ):
                raise ValueError("campaign spend corrections must arrive after their predecessor")
            superseded_ids.add(supersedes.record_id)
        select_visible_spend_revision(revisions, datetime.max)


def select_visible_spend_revision(
    revisions: list[SeedRecord] | tuple[SeedRecord, ...],
    snapshot_cutoff: datetime,
) -> SeedRecord:
    """Filter spend revisions by visibility before selecting the greatest version."""
    visible = [
        revision
        for revision in revisions
        if _datetime_value(revision, "recorded_at") <= snapshot_cutoff
    ]
    if not visible:
        raise ValueError("campaign spend has no revision visible at snapshot cutoff")
    return max(visible, key=lambda revision: _integer_value(revision, "version_number"))


def _validate_marketing_touches(records: dict[tuple[str, str], SeedRecord]) -> None:
    for (table_name, record_id), touch in records.items():
        if table_name != "marketing_touch":
            continue
        subject_type, subject_ref = _touch_subject(touch)
        _record(records, subject_ref)
        channel_ref = _reference_value(touch, "marketing_channel_id", "marketing_channel")
        channel = _record(records, channel_ref)
        touch_type = _string_value(touch, "touch_type")
        channel_type = _string_value(channel, "channel_type")
        if (touch_type == "direct") != (channel_type == "direct"):
            raise ValueError(f"marketing touch {record_id} has an incompatible channel type")

        campaign_value = touch.values["marketing_campaign_id"]
        if campaign_value is None:
            continue
        if not isinstance(campaign_value, SeedReference) or campaign_value.table != (
            "marketing_campaign"
        ):
            raise ValueError(f"marketing touch {record_id} has an invalid campaign reference")
        campaign = _record(records, campaign_value)
        campaign_channel = _reference_value(
            campaign,
            "primary_channel_id",
            "marketing_channel",
        )
        if campaign_channel.record_id != channel_ref.record_id:
            raise ValueError(f"marketing touch {record_id} crosses campaign channels")
        scope = _string_value(campaign, "business_scope")
        expected_scope = "saas" if subject_type == "organization" else "commerce"
        if scope != expected_scope:
            raise ValueError(f"marketing touch {record_id} crosses campaign business scope")
        if subject_type == "organization":
            campaign_org = _reference_value(campaign, "organization_id", "organization")
            if campaign_org.record_id != subject_ref.record_id:
                raise ValueError(f"SaaS campaign {campaign_value.record_id} crosses subjects")


def _validate_attributed_conversions(
    manifest: DatasetManifest,
    records: dict[tuple[str, str], SeedRecord],
) -> None:
    history_started_at = manifest.marketing_history_started_at.replace(tzinfo=None)
    for (table_name, record_id), conversion in records.items():
        if table_name != "attributed_conversion":
            continue
        conversion_type = _string_value(conversion, "conversion_type")
        subject_type, subject_ref = _conversion_subject(conversion)
        subject = _record(records, subject_ref)
        fact_ref, fact, expected_subject_ref, expected_conversion_at = _conversion_fact(
            records,
            conversion,
            conversion_type,
        )
        if expected_subject_ref.record_id != subject_ref.record_id:
            raise ValueError(f"attributed conversion {record_id} disagrees with fact subject")
        conversion_at = _datetime_value(conversion, "conversion_at")
        if conversion_at != expected_conversion_at:
            raise ValueError(f"attributed conversion {record_id} uses a non-authoritative time")
        window_started_at = _datetime_value(conversion, "window_started_at")
        if window_started_at != conversion_at - timedelta(hours=168):
            raise ValueError(f"attributed conversion {record_id} has the wrong window start")
        computed_history_complete = window_started_at >= history_started_at
        if _boolean_value(conversion, "history_complete") is not computed_history_complete:
            raise ValueError(f"attributed conversion {record_id} has an unproven history flag")

        conversion_is_test = _boolean_value(conversion, "is_test")
        fact_is_test = _boolean_value(fact, "is_test")
        subject_is_test = _boolean_value(subject, "is_test")
        if (fact_is_test or subject_is_test) and not conversion_is_test:
            raise ValueError(f"attributed conversion {record_id} leaks a test lineage")

        result = _string_value(conversion, "attribution_result")
        reason = _string_value(conversion, "reason_code")
        cutoff = _datetime_value(conversion, "source_data_cutoff_at")
        if cutoff < conversion_at:
            raise ValueError(f"attributed conversion {record_id} cutoff precedes conversion")
        if _datetime_value(conversion, "recorded_at") < cutoff:
            raise ValueError(f"attributed conversion {record_id} was recorded before its cutoff")
        if cutoff > manifest.snapshot_cutoff.replace(tzinfo=None):
            raise ValueError(f"attributed conversion {record_id} cutoff exceeds dataset snapshot")
        if not computed_history_complete:
            if result != "unknown_unattributed" or reason != "window_history_incomplete":
                raise ValueError(
                    f"attributed conversion {record_id} misclassifies incomplete history"
                )
            _validate_empty_attribution_links(conversion)
            continue

        candidates = _eligible_touches(
            records,
            subject_type,
            subject_ref,
            conversion_at,
            window_started_at,
            cutoff,
        )
        if not candidates:
            if result != "direct" or reason != "no_eligible_non_direct_touch":
                raise ValueError(f"attributed conversion {record_id} must be direct")
            _validate_direct_attribution(records, conversion, conversion_at)
            continue

        selected = max(
            candidates,
            key=lambda item: (
                _datetime_value(item, "occurred_at"),
                _string_value(item, "source_event_id").encode("ascii"),
            ),
        )
        if result != "non_direct" or reason != "selected_last_non_direct":
            raise ValueError(f"attributed conversion {record_id} ignores an eligible touch")
        selected_ref = _reference_value(
            conversion,
            "selected_marketing_touch_id",
            "marketing_touch",
        )
        if selected_ref.record_id != selected.record_id:
            raise ValueError(f"attributed conversion {record_id} selects the wrong touch")
        _validate_selected_touch_links(
            records,
            conversion,
            selected,
            subject_type,
            subject_ref,
            fact_ref,
        )


def _validate_attribution_revision_chains(
    records: dict[tuple[str, str], SeedRecord],
) -> None:
    revisions: dict[tuple[str, str], list[SeedRecord]] = defaultdict(list)
    for (table_name, _record_id), conversion in records.items():
        if table_name != "attributed_conversion":
            continue
        if _string_value(conversion, "model_version") != "last_non_direct_168h_v1":
            raise ValueError("attributed conversion uses an unsupported model version")
        fact_values = (
            conversion.values["invoice_payment_attempt_id"],
            conversion.values["commerce_order_id"],
            conversion.values["platform_fee_charge_id"],
        )
        fact_ref = next(value for value in fact_values if isinstance(value, SeedReference))
        key = (_string_value(conversion, "conversion_type"), fact_ref.record_id)
        revisions[key].append(conversion)

    for key, chain in revisions.items():
        chain.sort(key=lambda item: _datetime_value(item, "source_data_cutoff_at"))
        cutoffs = [_datetime_value(item, "source_data_cutoff_at") for item in chain]
        if len(cutoffs) != len(set(cutoffs)):
            raise ValueError(f"attribution revision chain has a duplicate cutoff: {key}")
        for previous, current in zip(chain, chain[1:], strict=False):
            if _datetime_value(current, "recorded_at") <= _datetime_value(previous, "recorded_at"):
                raise ValueError("attribution re-materialization must append a later record")


def _conversion_subject(conversion: SeedRecord) -> tuple[str, SeedReference]:
    organization = conversion.values["organization_id"]
    consumer = conversion.values["consumer_id"]
    if isinstance(organization, SeedReference) and organization.table == "organization":
        if consumer is not None:
            raise ValueError(f"attributed conversion {conversion.record_id} violates subject XOR")
        return "organization", organization
    if isinstance(consumer, SeedReference) and consumer.table == "consumer":
        if organization is not None:
            raise ValueError(f"attributed conversion {conversion.record_id} violates subject XOR")
        return "consumer", consumer
    raise ValueError(f"attributed conversion {conversion.record_id} has no valid subject")


def _conversion_fact(
    records: dict[tuple[str, str], SeedRecord],
    conversion: SeedRecord,
    conversion_type: str,
) -> tuple[SeedReference, SeedRecord, SeedReference, datetime]:
    payment = conversion.values["invoice_payment_attempt_id"]
    order = conversion.values["commerce_order_id"]
    fee = conversion.values["platform_fee_charge_id"]
    present = [value for value in (payment, order, fee) if value is not None]
    if len(present) != 1 or not isinstance(present[0], SeedReference):
        raise ValueError(f"attributed conversion {conversion.record_id} violates fact XOR")
    fact_ref = present[0]
    fact = _record(records, fact_ref)
    if conversion_type in {"saas_first_payment", "saas_revenue"}:
        if fact_ref.table != "invoice_payment_attempt" or fact.values["status"] != "succeeded":
            raise ValueError("SaaS attribution requires a succeeded payment attempt")
        invoice_ref = _reference_value(
            fact,
            "subscription_invoice_id",
            "subscription_invoice",
        )
        invoice = _record(records, invoice_ref)
        subscription_ref = _reference_value(invoice, "subscription_id", "subscription")
        subscription = _record(records, subscription_ref)
        subject_ref = _reference_value(subscription, "organization_id", "organization")
        conversion_at = _datetime_value(fact, "succeeded_at")
        if conversion_type == "saas_first_payment":
            earliest = min(
                _datetime_value(candidate, "succeeded_at")
                for (table_name, _record_id), candidate in records.items()
                if table_name == "invoice_payment_attempt"
                and candidate.values["status"] == "succeeded"
                and _payment_organization(records, candidate).record_id == subject_ref.record_id
            )
            if conversion_at != earliest:
                raise ValueError("SaaS first-payment attribution must use the earliest payment")
    elif conversion_type in {"commerce_first_payment", "attributed_gmv"}:
        if fact_ref.table != "commerce_order" or fact.values["status"] != "completed":
            raise ValueError("Commerce order attribution requires a completed order")
        subject_ref = _reference_value(fact, "consumer_id", "consumer")
        conversion_at = _datetime_value(fact, "first_paid_at")
        if conversion_type == "commerce_first_payment":
            earliest = min(
                _datetime_value(candidate, "first_paid_at")
                for (table_name, _record_id), candidate in records.items()
                if table_name == "commerce_order"
                and candidate.values["status"] == "completed"
                and _reference_value(candidate, "consumer_id", "consumer").record_id
                == subject_ref.record_id
            )
            if conversion_at != earliest:
                raise ValueError("Commerce first-payment attribution must use the earliest order")
    elif conversion_type == "commerce_revenue":
        if fact_ref.table != "platform_fee_charge" or fact.values["status"] != "succeeded":
            raise ValueError("Commerce revenue attribution requires a succeeded fee charge")
        order_ref = _reference_value(fact, "commerce_order_id", "commerce_order")
        order_record = _record(records, order_ref)
        subject_ref = _reference_value(order_record, "consumer_id", "consumer")
        conversion_at = _datetime_value(fact, "succeeded_at")
    else:
        raise ValueError(f"unsupported conversion type: {conversion_type}")
    return fact_ref, fact, subject_ref, conversion_at


def _payment_organization(
    records: dict[tuple[str, str], SeedRecord],
    payment: SeedRecord,
) -> SeedReference:
    invoice = _record(
        records,
        _reference_value(payment, "subscription_invoice_id", "subscription_invoice"),
    )
    subscription = _record(
        records,
        _reference_value(invoice, "subscription_id", "subscription"),
    )
    return _reference_value(subscription, "organization_id", "organization")


def _eligible_touches(
    records: dict[tuple[str, str], SeedRecord],
    subject_type: str,
    subject_ref: SeedReference,
    conversion_at: datetime,
    window_started_at: datetime,
    cutoff: datetime,
) -> list[SeedRecord]:
    candidates: list[SeedRecord] = []
    for (table_name, _record_id), touch in records.items():
        if table_name != "marketing_touch":
            continue
        try:
            touch_subject_type, touch_subject_ref = _touch_subject(touch)
        except ValueError:
            continue
        if (
            touch_subject_type != subject_type
            or touch_subject_ref.record_id != subject_ref.record_id
        ):
            continue
        if _string_value(touch, "quality_status") != "accepted":
            continue
        if _string_value(touch, "touch_type") != "non_direct":
            continue
        if _boolean_value(touch, "is_test"):
            continue
        processed_at = _optional_datetime_value(touch, "processed_at")
        if processed_at is None or processed_at > cutoff:
            continue
        if _datetime_value(touch, "recorded_at") > cutoff:
            continue
        occurred_at = _datetime_value(touch, "occurred_at")
        if not window_started_at <= occurred_at <= conversion_at:
            continue
        channel_ref = _reference_value(touch, "marketing_channel_id", "marketing_channel")
        channel = _record(records, channel_ref)
        if _boolean_value(channel, "is_test"):
            continue
        if _string_value(channel, "channel_type") == "direct":
            continue
        if not _channel_effective_at(channel, occurred_at):
            continue
        campaign_value = touch.values["marketing_campaign_id"]
        if campaign_value is not None:
            if not isinstance(campaign_value, SeedReference):
                continue
            campaign = _record(records, campaign_value)
            if _boolean_value(campaign, "is_test"):
                continue
            campaign_channel = _reference_value(
                campaign,
                "primary_channel_id",
                "marketing_channel",
            )
            if campaign_channel.record_id != channel_ref.record_id:
                continue
            expected_scope = "saas" if subject_type == "organization" else "commerce"
            if _string_value(campaign, "business_scope") != expected_scope:
                continue
            if subject_type == "organization":
                campaign_org = _reference_value(campaign, "organization_id", "organization")
                if campaign_org.record_id != subject_ref.record_id:
                    continue
        candidates.append(touch)
    return candidates


def _validate_selected_touch_links(
    records: dict[tuple[str, str], SeedRecord],
    conversion: SeedRecord,
    selected: SeedRecord,
    subject_type: str,
    subject_ref: SeedReference,
    fact_ref: SeedReference,
) -> None:
    selected_subject_type, selected_subject_ref = _touch_subject(selected)
    if (
        selected_subject_type != subject_type
        or selected_subject_ref.record_id != subject_ref.record_id
    ):
        raise ValueError("selected touch crosses attribution subjects")
    selected_channel = _reference_value(selected, "marketing_channel_id", "marketing_channel")
    conversion_channel = _reference_value(
        conversion,
        "marketing_channel_id",
        "marketing_channel",
    )
    if conversion_channel.record_id != selected_channel.record_id:
        raise ValueError("selected attribution channel disagrees with touch")
    selected_campaign = selected.values["marketing_campaign_id"]
    conversion_campaign = conversion.values["marketing_campaign_id"]
    if selected_campaign != conversion_campaign:
        raise ValueError("selected attribution campaign disagrees with touch")
    if selected_campaign is None or subject_type != "consumer":
        return
    if not isinstance(selected_campaign, SeedReference):
        raise ValueError("selected attribution campaign reference is invalid")
    campaign = _record(records, selected_campaign)
    merchant_ref = _reference_value(campaign, "merchant_assignment_id", "merchant")
    if fact_ref.table == "platform_fee_charge":
        fee = _record(records, fact_ref)
        order_ref = _reference_value(fee, "commerce_order_id", "commerce_order")
        order = _record(records, order_ref)
    else:
        order = _record(records, fact_ref)
    order_merchant = _reference_value(order, "merchant_assignment_id", "merchant")
    if merchant_ref.record_id != order_merchant.record_id:
        raise ValueError("selected Commerce campaign disagrees with authoritative merchant")


def _validate_direct_attribution(
    records: dict[tuple[str, str], SeedRecord],
    conversion: SeedRecord,
    conversion_at: datetime,
) -> None:
    if conversion.values["selected_marketing_touch_id"] is not None:
        raise ValueError("direct attribution cannot select a touch")
    if conversion.values["marketing_campaign_id"] is not None:
        raise ValueError("direct attribution cannot select a campaign")
    channel_ref = _reference_value(conversion, "marketing_channel_id", "marketing_channel")
    channel = _record(records, channel_ref)
    if _string_value(channel, "channel_code") != "direct":
        raise ValueError("direct attribution must use the governed direct channel")
    if _string_value(channel, "channel_type") != "direct":
        raise ValueError("direct attribution must use a direct channel type")
    if _boolean_value(channel, "is_test"):
        raise ValueError("direct attribution cannot use a test channel")
    if not _channel_effective_at(channel, conversion_at):
        raise ValueError("direct attribution channel was not effective at conversion time")


def _validate_empty_attribution_links(conversion: SeedRecord) -> None:
    link_names = (
        "selected_marketing_touch_id",
        "marketing_channel_id",
        "marketing_campaign_id",
    )
    if any(conversion.values[name] is not None for name in link_names):
        raise ValueError("unknown attribution cannot retain selected links")


def _touch_subject(touch: SeedRecord) -> tuple[str, SeedReference]:
    organization = touch.values["organization_id"]
    consumer = touch.values["consumer_id"]
    if isinstance(organization, SeedReference) and organization.table == "organization":
        if consumer is not None:
            raise ValueError(f"marketing touch {touch.record_id} violates subject XOR")
        return "organization", organization
    if isinstance(consumer, SeedReference) and consumer.table == "consumer":
        if organization is not None:
            raise ValueError(f"marketing touch {touch.record_id} violates subject XOR")
        return "consumer", consumer
    raise ValueError(f"marketing touch {touch.record_id} has no valid subject")


def _channel_effective_at(channel: SeedRecord, at: datetime) -> bool:
    effective_from = _datetime_value(channel, "effective_from")
    effective_to = _optional_datetime_value(channel, "effective_to")
    return effective_from <= at and (effective_to is None or at < effective_to)


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


def _record(
    records: dict[tuple[str, str], SeedRecord],
    reference: SeedReference,
) -> SeedRecord:
    try:
        return records[(reference.table, reference.record_id)]
    except KeyError as error:
        raise ValueError(
            f"unresolved business reference: {reference.table}:{reference.record_id}"
        ) from error


def _string_value(record: SeedRecord, column_name: str) -> str:
    value = record.values[column_name]
    if not isinstance(value, str):
        raise ValueError(f"{record.record_id}.{column_name} must be a string")
    return value


def _decimal_value(record: SeedRecord, column_name: str) -> Decimal:
    return Decimal(_string_value(record, column_name))


def _integer_value(record: SeedRecord, column_name: str) -> int:
    value = record.values[column_name]
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{record.record_id}.{column_name} must be an integer")
    return value


def _boolean_value(record: SeedRecord, column_name: str) -> bool:
    value = record.values[column_name]
    if not isinstance(value, bool):
        raise ValueError(f"{record.record_id}.{column_name} must be a boolean")
    return value


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
