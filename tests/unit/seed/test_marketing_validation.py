"""Unit tests for M1.2A marketing materialization validation."""

from datetime import datetime
from pathlib import Path

import pytest

from insightops.seed.contracts import SeedRecord, SeedReference, SeedSource
from insightops.seed.dataset import load_seed_dataset
from insightops.seed.validation import (
    select_visible_spend_revision,
    validate_business_dataset,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATASET_ROOT = PROJECT_ROOT / "data" / "seed" / "m1_2a"


def _records(sources: tuple[SeedSource, ...]) -> dict[tuple[str, str], SeedRecord]:
    return {
        (table.table_name, record.record_id): record
        for source in sources
        for table in source.tables
        for record in table.records
    }


def _string_value(record: SeedRecord, column_name: str) -> str:
    value = record.values[column_name]
    assert isinstance(value, str)
    return value


def _replace_values(
    sources: tuple[SeedSource, ...],
    table_name: str,
    record_id: str,
    **updates: object,
) -> tuple[SeedSource, ...]:
    replaced_sources: list[SeedSource] = []
    for source in sources:
        replaced_tables = []
        for table in source.tables:
            records = []
            for record in table.records:
                if table.table_name == table_name and record.record_id == record_id:
                    records.append(
                        record.model_copy(update={"values": {**record.values, **updates}})
                    )
                else:
                    records.append(record)
            replaced_tables.append(table.model_copy(update={"records": tuple(records)}))
        replaced_sources.append(source.model_copy(update={"tables": tuple(replaced_tables)}))
    return tuple(replaced_sources)


def test_historical_channel_eligibility_ignores_current_status() -> None:
    dataset = load_seed_dataset(DATASET_ROOT)
    records = _records(dataset.sources)
    channel = records[("marketing_channel", "channel-paid-social")]
    eligible_touch = records[("marketing_touch", "touch-saas-jun-b")]
    expired_touch = records[("marketing_touch", "touch-commerce-jun-expired-social")]

    assert channel.values["status"] == "inactive"
    assert _string_value(eligible_touch, "occurred_at") < _string_value(channel, "effective_to")
    assert _string_value(expired_touch, "occurred_at") > _string_value(channel, "effective_to")
    validate_business_dataset(dataset.manifest, dataset.sources)
    selected = records[("attributed_conversion", "attr-payment-q2-jun-b-first")].values[
        "selected_marketing_touch_id"
    ]
    assert isinstance(selected, SeedReference)
    assert selected.model_dump() == {
        "table": "marketing_touch",
        "record_id": "touch-saas-jun-b",
    }
    assert (
        records[("attributed_conversion", "attr-order-jun-direct-first")].values[
            "attribution_result"
        ]
        == "direct"
    )


def test_touch_outside_channel_effective_interval_is_rejected_as_a_selection() -> None:
    dataset = load_seed_dataset(DATASET_ROOT)
    invalid_sources = _replace_values(
        dataset.sources,
        "marketing_channel",
        "channel-paid-social",
        effective_to="2025-04-14 15:00:00.000000",
    )

    with pytest.raises(ValueError, match="must be direct"):
        validate_business_dataset(dataset.manifest, invalid_sources)


def test_selected_touch_must_be_processed_and_visible_at_attribution_cutoff() -> None:
    dataset = load_seed_dataset(DATASET_ROOT)
    invalid_sources = _replace_values(
        dataset.sources,
        "marketing_touch",
        "touch-saas-beta-apr",
        processed_at=None,
    )

    with pytest.raises(ValueError, match="must be direct"):
        validate_business_dataset(dataset.manifest, invalid_sources)


def test_late_touch_re_attribution_is_an_append_only_materialization() -> None:
    dataset = load_seed_dataset(DATASET_ROOT)
    records = _records(dataset.sources)
    early = records[("attributed_conversion", "attr-payment-jun-delta-revenue-early")]
    final = records[("attributed_conversion", "attr-payment-jun-delta-revenue-final")]

    assert early.values["attribution_result"] == "direct"
    assert final.values["attribution_result"] == "non_direct"
    assert _string_value(early, "source_data_cutoff_at") < _string_value(
        final, "source_data_cutoff_at"
    )

    invalid_sources = _replace_values(
        dataset.sources,
        "attributed_conversion",
        early.record_id,
        recorded_at=_string_value(final, "recorded_at"),
    )
    with pytest.raises(ValueError, match="append a later record"):
        validate_business_dataset(dataset.manifest, invalid_sources)


def test_spend_snapshot_filters_visibility_before_selecting_version() -> None:
    dataset = load_seed_dataset(DATASET_ROOT)
    records = _records(dataset.sources)
    revisions = [
        records[("campaign_daily_spend", "spend-com-alpha-jun-v1")],
        records[("campaign_daily_spend", "spend-com-alpha-jun-v2")],
    ]

    early = select_visible_spend_revision(revisions, datetime(2025, 7, 2))
    late = select_visible_spend_revision(revisions, datetime(2025, 12, 2))

    assert early.record_id == "spend-com-alpha-jun-v1"
    assert late.record_id == "spend-com-alpha-jun-v2"


def test_history_boundary_is_recomputed_from_manifest_coverage() -> None:
    dataset = load_seed_dataset(DATASET_ROOT)
    records = _records(dataset.sources)
    incomplete = records[("attributed_conversion", "attr-payment-q2-apr-early-first")]
    complete = records[("attributed_conversion", "attr-payment-q2-apr-boundary-first")]

    assert _string_value(incomplete, "window_started_at") < "2025-04-01 07:00:00.000000"
    assert incomplete.values["reason_code"] == "window_history_incomplete"
    assert complete.values["window_started_at"] == "2025-04-01 07:00:00.000000"
    assert complete.values["history_complete"] is True
