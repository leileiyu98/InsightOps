"""Author the deterministic M1.2A v1.1.0 seed source additions.

This script is an authoring helper. Runtime seed loading never computes attribution.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
SEED_ROOT = ROOT / "data" / "seed" / "m1_2a"
RECORDED_AT = "2025-12-01 00:00:00.000000"
FINAL_CUTOFF = "2025-12-01 00:00:00.000000"
MODEL_VERSION = "last_non_direct_168h_v1"


def ref(table: str, record_id: str) -> dict[str, str]:
    return {"table": table, "record_id": record_id}


def record(record_id: str, **values: Any) -> dict[str, Any]:
    return {"record_id": record_id, "values": values}


def table(source: dict[str, Any], name: str) -> dict[str, Any]:
    return next(item for item in source["tables"] if item["table_name"] == name)


def append_unique(target: dict[str, Any], records: list[dict[str, Any]]) -> None:
    existing = {item["record_id"] for item in target["records"]}
    target["records"].extend(item for item in records if item["record_id"] not in existing)


def load(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((SEED_ROOT / name).read_text(encoding="utf-8")))


def dump(name: str, payload: dict[str, Any]) -> None:
    (SEED_ROOT / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def dt_string(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S.%f")


def add_identity(identity: dict[str, Any]) -> None:
    organizations = [
        ("org-q2-apr-early", "Q2 April Early", "2025-04-03 15:00:00.000000"),
        ("org-q2-apr-boundary", "Q2 April Boundary", "2025-04-08 06:00:00.000000"),
        ("org-q2-may-a", "Q2 May Activated A", "2025-05-02 15:00:00.000000"),
        ("org-q2-may-b", "Q2 May Activated B", "2025-05-10 15:00:00.000000"),
        ("org-q2-jun-a", "Q2 June Mature A", "2025-06-02 15:00:00.000000"),
        ("org-q2-jun-b", "Q2 June Mature B", "2025-06-10 15:00:00.000000"),
        ("org-q2-jun-late-a", "Q2 June Pending A", "2025-06-20 15:00:00.000000"),
        ("org-q2-jun-late-b", "Q2 June Pending B", "2025-06-25 15:00:00.000000"),
    ]
    append_unique(
        table(identity, "organization"),
        [
            record(
                record_id,
                external_organization_id=f"seed-{record_id}",
                organization_name=name,
                status="active",
                registered_at=registered_at,
                closed_at=None,
                is_test=False,
                recorded_at=RECORDED_AT,
                updated_at=RECORDED_AT,
            )
            for record_id, name, registered_at in organizations
        ],
    )

    member_specs = [
        ("member-q2-apr-early", "org-q2-apr-early", "2025-04-04 15:00:00.000000"),
        ("member-q2-may-a", "org-q2-may-a", "2025-05-03 15:00:00.000000"),
        ("member-q2-may-b", "org-q2-may-b", "2025-05-11 15:00:00.000000"),
        ("member-q2-jun-b", "org-q2-jun-b", "2025-06-11 15:00:00.000000"),
        ("member-q2-jun-late-a", "org-q2-jun-late-a", "2025-06-21 15:00:00.000000"),
    ]
    append_unique(
        table(identity, "organization_member"),
        [
            record(
                record_id,
                external_membership_id=f"seed-{record_id}",
                organization_id=ref("organization", org_id),
                external_account_id=f"seed-account-{record_id}",
                status="active",
                first_invited_at=invited_at,
                accepted_at=dt_string(dt(invited_at) + timedelta(hours=1)),
                effective_from=dt_string(dt(invited_at) + timedelta(hours=1)),
                effective_to=None,
                is_test=False,
                recorded_at=RECORDED_AT,
                updated_at=RECORDED_AT,
            )
            for record_id, org_id, invited_at in member_specs
        ],
    )

    consumers = [
        ("consumer-apr-early", "2025-04-04 15:00:00.000000"),
        ("consumer-may-search", "2025-05-05 15:00:00.000000"),
        ("consumer-may-search-two", "2025-05-24 15:00:00.000000"),
        ("consumer-may-social", "2025-05-19 15:00:00.000000"),
        ("consumer-jun-search", "2025-06-11 15:00:00.000000"),
        ("consumer-jun-direct", "2025-06-16 15:00:00.000000"),
    ]
    append_unique(
        table(identity, "consumer"),
        [
            record(
                record_id,
                external_consumer_id=f"seed-{record_id}",
                status="active",
                first_identified_at=created_at,
                created_at=created_at,
                closed_at=None,
                is_test=False,
                recorded_at=RECORDED_AT,
                updated_at=RECORDED_AT,
            )
            for record_id, created_at in consumers
        ],
    )

    append_unique(
        table(identity, "merchant"),
        [
            record(
                "merchant-q2-may-a",
                merchant_id=1003,
                external_merchant_id="seed-merchant-q2-may-a",
                organization_id=ref("organization", "org-q2-may-a"),
                merchant_name="Q2 May Marketplace",
                status="active",
                applied_at="2025-05-03 10:00:00.000000",
                approved_at="2025-05-03 11:00:00.000000",
                activated_at="2025-05-03 12:00:00.000000",
                closed_at=None,
                assignment_valid_from="2025-05-03 12:00:00.000000",
                assignment_valid_to=None,
                is_test=False,
                recorded_at=RECORDED_AT,
                updated_at=RECORDED_AT,
            )
        ],
    )


def add_saas(saas: dict[str, Any]) -> dict[str, str]:
    specs = [
        (
            "q2-apr-early",
            "org-q2-apr-early",
            "plan-starter-monthly",
            "2025-04-03 15:30:00.000000",
            "2025-04-03 16:00:00.000000",
            "100.0000",
        ),
        (
            "q2-apr-boundary",
            "org-q2-apr-boundary",
            "plan-starter-monthly",
            "2025-04-08 06:30:00.000000",
            "2025-04-08 07:00:00.000000",
            "100.0000",
        ),
        (
            "q2-may-a",
            "org-q2-may-a",
            "plan-growth-monthly",
            "2025-05-05 15:00:00.000000",
            "2025-05-06 16:00:00.000000",
            "200.0000",
        ),
        (
            "q2-may-b",
            "org-q2-may-b",
            "plan-starter-monthly",
            "2025-05-12 15:00:00.000000",
            "2025-05-13 16:00:00.000000",
            "100.0000",
        ),
        (
            "q2-jun-b",
            "org-q2-jun-b",
            "plan-growth-monthly",
            "2025-06-10 16:00:00.000000",
            "2025-06-11 16:00:00.000000",
            "200.0000",
        ),
    ]
    conversions: dict[str, str] = {}
    subscriptions: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    invoices: list[dict[str, Any]] = []
    payments: list[dict[str, Any]] = []
    for key, org_id, plan_id, activated_at, paid_at, amount in specs:
        subscription_id = f"sub-{key}"
        invoice_id = f"invoice-{key}"
        payment_id = f"payment-{key}"
        interval = "monthly"
        subscriptions.append(
            record(
                subscription_id,
                external_subscription_id=f"seed-{subscription_id}",
                organization_id=ref("organization", org_id),
                current_plan_version_id=ref("saas_plan_version", plan_id),
                current_status="active",
                created_at=activated_at,
                first_activated_at=activated_at,
                current_period_started_at="2025-12-01 08:00:00.000000",
                current_period_ends_at="2026-01-01 08:00:00.000000",
                cancel_scheduled_at=None,
                cancellation_effective_at=None,
                expires_at=None,
                is_test=False,
                recorded_at=RECORDED_AT,
                updated_at=RECORDED_AT,
            )
        )
        events.append(
            record(
                f"event-{key}-activate",
                source_event_id=f"seed-event-{key}-activate",
                subscription_id=ref("subscription", subscription_id),
                event_type="first_activation",
                status_before="pending",
                status_after="active",
                plan_version_before_id=None,
                plan_version_after_id=ref("saas_plan_version", plan_id),
                billing_interval_before=None,
                billing_interval_after=interval,
                recurring_amount_before="0.0000",
                recurring_amount_after=amount,
                normalized_mrr_before="0.0000",
                normalized_mrr_after=amount,
                currency_code="USD",
                effective_at=activated_at,
                created_at=activated_at,
                is_test=False,
                recorded_at=RECORDED_AT,
            )
        )
        invoices.append(
            record(
                invoice_id,
                external_invoice_id=f"seed-{invoice_id}",
                subscription_id=ref("subscription", subscription_id),
                status="paid",
                subscription_fee_amount=amount,
                tax_amount="0.0000",
                one_time_amount="0.0000",
                total_amount=amount,
                currency_code="USD",
                issued_at=paid_at,
                due_at=paid_at,
                voided_at=None,
                paid_at=paid_at,
                created_at=paid_at,
                is_test=False,
                recorded_at=RECORDED_AT,
                updated_at=RECORDED_AT,
            )
        )
        payments.append(
            record(
                payment_id,
                external_payment_attempt_id=f"seed-{payment_id}",
                provider_transaction_id=f"seed-provider-{payment_id}",
                subscription_invoice_id=ref("subscription_invoice", invoice_id),
                status="succeeded",
                subscription_fee_amount=amount,
                tax_amount="0.0000",
                one_time_amount="0.0000",
                total_amount=amount,
                currency_code="USD",
                attempted_at=paid_at,
                succeeded_at=paid_at,
                failed_at=None,
                cancelled_at=None,
                failure_code=None,
                is_test=False,
                recorded_at=RECORDED_AT,
            )
        )
        conversions[payment_id] = paid_at
    append_unique(table(saas, "subscription"), subscriptions)
    append_unique(table(saas, "subscription_state_event"), events)
    append_unique(table(saas, "subscription_invoice"), invoices)
    append_unique(table(saas, "invoice_payment_attempt"), payments)
    return conversions


def add_commerce(commerce: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    append_unique(
        table(commerce, "product"),
        [
            record(
                "product-q2-may-a",
                external_product_id="seed-product-q2-may-a",
                merchant_assignment_id=ref("merchant", "merchant-q2-may-a"),
                product_title="Q2 May Service",
                category_code="services",
                status="active",
                created_at="2025-05-03 13:00:00.000000",
                first_published_at="2025-05-03 14:00:00.000000",
                archived_at=None,
                is_test=False,
                recorded_at=RECORDED_AT,
                updated_at=RECORDED_AT,
            )
        ],
    )
    specs = [
        (
            "apr-early",
            "consumer-apr-early",
            "merchant-alpha",
            "product-alpha-hardware",
            "hardware",
            "2025-04-05 16:00:00.000000",
            "50.0000",
            "5.0000",
        ),
        (
            "may-search",
            "consumer-may-search",
            "merchant-q2-may-a",
            "product-q2-may-a",
            "services",
            "2025-05-06 18:00:00.000000",
            "150.0000",
            "15.0000",
        ),
        (
            "may-search-two",
            "consumer-may-search-two",
            "merchant-alpha",
            "product-alpha-hardware",
            "hardware",
            "2025-05-25 18:00:00.000000",
            "120.0000",
            "12.0000",
        ),
        (
            "may-social",
            "consumer-may-social",
            "merchant-beta",
            "product-beta-services",
            "services",
            "2025-05-20 18:00:00.000000",
            "80.0000",
            "8.0000",
        ),
        (
            "jun-search",
            "consumer-jun-search",
            "merchant-alpha",
            "product-alpha-software",
            "software",
            "2025-06-12 18:00:00.000000",
            "200.0000",
            "20.0000",
        ),
        (
            "jun-direct",
            "consumer-jun-direct",
            "merchant-beta",
            "product-beta-services",
            "services",
            "2025-06-18 18:00:00.000000",
            "100.0000",
            "10.0000",
        ),
    ]
    orders: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    fees: list[dict[str, Any]] = []
    order_times: dict[str, str] = {}
    fee_times: dict[str, str] = {}
    for key, consumer_id, merchant_id, product_id, category, paid_at, amount, fee in specs:
        order_id = f"order-{key}"
        fee_id = f"fee-{key}"
        orders.append(
            record(
                order_id,
                external_order_id=f"seed-{order_id}",
                consumer_id=ref("consumer", consumer_id),
                merchant_assignment_id=ref("merchant", merchant_id),
                status="completed",
                currency_code="USD",
                created_at=dt_string(dt(paid_at) - timedelta(hours=1)),
                first_paid_at=paid_at,
                fulfilled_at=paid_at,
                completed_at=paid_at,
                cancelled_at=None,
                is_test=False,
                recorded_at=RECORDED_AT,
                updated_at=RECORDED_AT,
            )
        )
        items.append(
            record(
                f"item-{key}",
                external_order_item_id=f"seed-item-{key}",
                commerce_order_id=ref("commerce_order", order_id),
                product_id=ref("product", product_id),
                product_category_code=category,
                quantity=1,
                discounted_item_amount=amount,
                currency_code="USD",
                created_at=dt_string(dt(paid_at) - timedelta(hours=1)),
                is_test=False,
                recorded_at=RECORDED_AT,
            )
        )
        fees.append(
            record(
                fee_id,
                external_fee_charge_id=f"seed-{fee_id}",
                provider_charge_id=f"seed-provider-{fee_id}",
                commerce_order_id=ref("commerce_order", order_id),
                status="succeeded",
                fee_amount=fee,
                currency_code="USD",
                attempted_at=paid_at,
                succeeded_at=paid_at,
                failed_at=None,
                cancelled_at=None,
                is_test=False,
                recorded_at=RECORDED_AT,
            )
        )
        order_times[order_id] = paid_at
        fee_times[fee_id] = paid_at
    append_unique(table(commerce, "commerce_order"), orders)
    append_unique(table(commerce, "commerce_order_item"), items)
    append_unique(table(commerce, "platform_fee_charge"), fees)
    return order_times, fee_times


def campaign_record(
    record_id: str,
    organization_id: str,
    channel_id: str,
    scope: str,
    created_at: str,
    merchant_id: str | None = None,
    *,
    is_test: bool = False,
) -> dict[str, Any]:
    return record(
        record_id,
        external_campaign_id=f"seed-{record_id}",
        organization_id=ref("organization", organization_id),
        merchant_assignment_id=ref("merchant", merchant_id) if merchant_id else None,
        primary_channel_id=ref("marketing_channel", channel_id),
        business_scope=scope,
        campaign_name=record_id.replace("-", " ").title(),
        status="completed",
        created_at=created_at,
        started_at=created_at,
        ended_at="2025-07-01 07:00:00.000000",
        status_updated_at="2025-07-01 07:00:00.000000",
        is_test=is_test,
        recorded_at=RECORDED_AT,
        updated_at=RECORDED_AT,
    )


def add_marketing(
    payment_times: dict[str, str],
    order_times: dict[str, str],
    fee_times: dict[str, str],
) -> dict[str, Any]:
    channels = [
        record(
            "channel-paid-search",
            channel_code="paid_search",
            channel_name="Paid Search",
            channel_type="paid",
            status="active",
            effective_from="2024-01-01 08:00:00.000000",
            effective_to=None,
            is_test=False,
            created_at="2024-01-01 08:00:00.000000",
            recorded_at=RECORDED_AT,
            updated_at=RECORDED_AT,
        ),
        record(
            "channel-paid-social",
            channel_code="paid_social",
            channel_name="Paid Social",
            channel_type="paid",
            status="inactive",
            effective_from="2024-01-01 08:00:00.000000",
            effective_to="2025-06-15 12:00:00.000000",
            is_test=False,
            created_at="2024-01-01 08:00:00.000000",
            recorded_at=RECORDED_AT,
            updated_at=RECORDED_AT,
        ),
        record(
            "channel-organic",
            channel_code="organic",
            channel_name="Organic",
            channel_type="organic",
            status="active",
            effective_from="2024-01-01 08:00:00.000000",
            effective_to=None,
            is_test=False,
            created_at="2024-01-01 08:00:00.000000",
            recorded_at=RECORDED_AT,
            updated_at=RECORDED_AT,
        ),
        record(
            "channel-direct",
            channel_code="direct",
            channel_name="Direct",
            channel_type="direct",
            status="inactive",
            effective_from="2024-01-01 08:00:00.000000",
            effective_to=None,
            is_test=False,
            created_at="2024-01-01 08:00:00.000000",
            recorded_at=RECORDED_AT,
            updated_at=RECORDED_AT,
        ),
        record(
            "channel-test",
            channel_code="test_paid",
            channel_name="Synthetic Test Channel",
            channel_type="paid",
            status="active",
            effective_from="2024-01-01 08:00:00.000000",
            effective_to=None,
            is_test=True,
            created_at="2024-01-01 08:00:00.000000",
            recorded_at=RECORDED_AT,
            updated_at=RECORDED_AT,
        ),
    ]
    campaigns = [
        campaign_record(
            "campaign-saas-alpha-search",
            "org-alpha",
            "channel-paid-search",
            "saas",
            "2025-04-01 08:00:00.000000",
        ),
        campaign_record(
            "campaign-saas-beta-social",
            "org-beta",
            "channel-paid-social",
            "saas",
            "2025-04-01 08:00:00.000000",
        ),
        campaign_record(
            "campaign-saas-delta-search",
            "org-delta",
            "channel-paid-search",
            "saas",
            "2025-05-01 08:00:00.000000",
        ),
        campaign_record(
            "campaign-saas-apr-early",
            "org-q2-apr-early",
            "channel-paid-search",
            "saas",
            "2025-04-05 15:00:00.000000",
        ),
        campaign_record(
            "campaign-saas-apr-boundary",
            "org-q2-apr-boundary",
            "channel-organic",
            "saas",
            "2025-04-09 15:00:00.000000",
        ),
        campaign_record(
            "campaign-saas-may-a",
            "org-q2-may-a",
            "channel-paid-search",
            "saas",
            "2025-05-04 15:00:00.000000",
        ),
        campaign_record(
            "campaign-saas-may-b",
            "org-q2-may-b",
            "channel-paid-social",
            "saas",
            "2025-05-12 15:00:00.000000",
        ),
        campaign_record(
            "campaign-saas-jun-a",
            "org-q2-jun-a",
            "channel-paid-search",
            "saas",
            "2025-06-03 15:00:00.000000",
        ),
        campaign_record(
            "campaign-saas-jun-b",
            "org-q2-jun-b",
            "channel-paid-social",
            "saas",
            "2025-06-11 15:00:00.000000",
        ),
        campaign_record(
            "campaign-saas-jun-late-b",
            "org-q2-jun-late-b",
            "channel-organic",
            "saas",
            "2025-06-26 15:00:00.000000",
        ),
        campaign_record(
            "campaign-commerce-alpha-search",
            "org-alpha",
            "channel-paid-search",
            "commerce",
            "2024-12-15 16:00:00.000000",
            "merchant-alpha",
        ),
        campaign_record(
            "campaign-commerce-beta-social",
            "org-beta",
            "channel-paid-social",
            "commerce",
            "2024-12-15 16:00:00.000000",
            "merchant-beta",
        ),
        campaign_record(
            "campaign-commerce-q2-search",
            "org-q2-may-a",
            "channel-paid-search",
            "commerce",
            "2025-05-04 15:00:00.000000",
            "merchant-q2-may-a",
        ),
        campaign_record(
            "campaign-test",
            "org-test",
            "channel-test",
            "saas",
            "2025-04-01 08:00:00.000000",
            is_test=True,
        ),
    ]

    spends: list[dict[str, Any]] = []

    def add_spend(
        key: str,
        campaign_id: str,
        business_date: str,
        amount: str,
        *,
        version: int = 1,
        supersedes: str | None = None,
        recorded_at: str = RECORDED_AT,
        is_test: bool = False,
    ) -> None:
        spends.append(
            record(
                key,
                marketing_campaign_id=ref("marketing_campaign", campaign_id),
                business_date=business_date,
                version_number=version,
                supersedes_campaign_daily_spend_id=(
                    ref("campaign_daily_spend", supersedes) if supersedes else None
                ),
                spend_amount=amount,
                currency_code="USD",
                finalized_at=recorded_at,
                is_test=is_test,
                recorded_at=recorded_at,
            )
        )

    for key, campaign_id, day, amount in [
        ("spend-saas-alpha-apr", "campaign-saas-alpha-search", "2025-04-10", "80.0000"),
        ("spend-saas-beta-apr", "campaign-saas-beta-social", "2025-04-15", "60.0000"),
        ("spend-saas-beta-may", "campaign-saas-beta-social", "2025-05-16", "80.0000"),
        ("spend-saas-delta-may", "campaign-saas-delta-search", "2025-05-25", "100.0000"),
        ("spend-saas-delta-jun", "campaign-saas-delta-search", "2025-06-05", "180.0000"),
        ("spend-saas-apr-early", "campaign-saas-apr-early", "2025-04-03", "20.0000"),
        ("spend-saas-may-a", "campaign-saas-may-a", "2025-05-06", "70.0000"),
        ("spend-saas-may-b", "campaign-saas-may-b", "2025-05-13", "60.0000"),
        ("spend-saas-jun-a", "campaign-saas-jun-a", "2025-06-12", "120.0000"),
        ("spend-saas-jun-b", "campaign-saas-jun-b", "2025-06-11", "90.0000"),
        ("spend-com-alpha-jan", "campaign-commerce-alpha-search", "2025-01-15", "20.0000"),
        ("spend-com-alpha-feb", "campaign-commerce-alpha-search", "2025-02-15", "30.0000"),
        ("spend-com-alpha-mar", "campaign-commerce-alpha-search", "2025-03-15", "40.0000"),
        ("spend-com-alpha-apr", "campaign-commerce-alpha-search", "2025-04-15", "60.0000"),
        ("spend-com-alpha-may", "campaign-commerce-alpha-search", "2025-05-15", "100.0000"),
        ("spend-com-alpha-jun-v1", "campaign-commerce-alpha-search", "2025-06-15", "120.0000"),
        ("spend-com-beta-jan", "campaign-commerce-beta-social", "2025-01-16", "25.0000"),
        ("spend-com-beta-feb", "campaign-commerce-beta-social", "2025-02-16", "25.0000"),
        ("spend-com-beta-mar", "campaign-commerce-beta-social", "2025-03-16", "25.0000"),
        ("spend-com-beta-apr", "campaign-commerce-beta-social", "2025-04-16", "30.0000"),
        ("spend-com-beta-may", "campaign-commerce-beta-social", "2025-05-16", "50.0000"),
        ("spend-com-beta-jun", "campaign-commerce-beta-social", "2025-06-16", "80.0000"),
        ("spend-com-q2-may", "campaign-commerce-q2-search", "2025-05-06", "60.0000"),
        ("spend-com-q2-jun", "campaign-commerce-q2-search", "2025-06-06", "90.0000"),
    ]:
        add_spend(key, campaign_id, day, amount, recorded_at="2025-07-01 00:00:00.000000")
    add_spend(
        "spend-com-alpha-jun-v2",
        "campaign-commerce-alpha-search",
        "2025-06-15",
        "140.0000",
        version=2,
        supersedes="spend-com-alpha-jun-v1",
        recorded_at=RECORDED_AT,
    )
    add_spend(
        "spend-test",
        "campaign-test",
        "2025-06-10",
        "9999.0000",
        recorded_at=RECORDED_AT,
        is_test=True,
    )

    touches: list[dict[str, Any]] = []

    def add_touch(
        key: str,
        channel_id: str,
        occurred_at: str,
        *,
        campaign_id: str | None = None,
        organization_id: str | None = None,
        consumer_id: str | None = None,
        touch_type: str = "non_direct",
        quality: str = "accepted",
        processed_at: str | None = None,
        recorded_at: str | None = None,
        is_test: bool = False,
    ) -> None:
        received_at = dt_string(dt(occurred_at) + timedelta(minutes=5))
        processed = processed_at or dt_string(dt(occurred_at) + timedelta(minutes=10))
        recorded = recorded_at or processed
        touches.append(
            record(
                key,
                source_event_id=f"seed-{key}",
                marketing_channel_id=ref("marketing_channel", channel_id),
                marketing_campaign_id=(
                    ref("marketing_campaign", campaign_id) if campaign_id else None
                ),
                organization_id=ref("organization", organization_id) if organization_id else None,
                consumer_id=ref("consumer", consumer_id) if consumer_id else None,
                touch_type=touch_type,
                quality_status=quality,
                occurred_at=occurred_at,
                received_at=received_at,
                processed_at=processed,
                is_test=is_test,
                recorded_at=recorded,
            )
        )

    add_touch(
        "touch-saas-alpha-apr",
        "channel-paid-search",
        "2025-04-09 16:00:00.000000",
        campaign_id="campaign-saas-alpha-search",
        organization_id="org-alpha",
    )
    add_touch(
        "touch-saas-beta-apr",
        "channel-paid-social",
        "2025-04-14 16:00:00.000000",
        campaign_id="campaign-saas-beta-social",
        organization_id="org-beta",
    )
    add_touch(
        "touch-saas-beta-may",
        "channel-paid-social",
        "2025-05-15 16:00:00.000000",
        campaign_id="campaign-saas-beta-social",
        organization_id="org-beta",
    )
    add_touch(
        "touch-saas-delta-may",
        "channel-paid-search",
        "2025-05-24 16:00:00.000000",
        campaign_id="campaign-saas-delta-search",
        organization_id="org-delta",
    )
    add_touch(
        "touch-saas-delta-jun-late",
        "channel-paid-search",
        "2025-06-04 16:00:00.000000",
        campaign_id="campaign-saas-delta-search",
        organization_id="org-delta",
        processed_at="2025-07-10 16:00:00.000000",
        recorded_at="2025-07-10 16:00:00.000000",
    )
    add_touch(
        "touch-saas-apr-early",
        "channel-paid-search",
        "2025-04-02 16:00:00.000000",
        organization_id="org-q2-apr-early",
    )
    add_touch(
        "touch-saas-may-a",
        "channel-paid-search",
        "2025-05-05 16:00:00.000000",
        campaign_id="campaign-saas-may-a",
        organization_id="org-q2-may-a",
    )
    add_touch(
        "touch-saas-may-b",
        "channel-paid-social",
        "2025-05-12 16:00:00.000000",
        campaign_id="campaign-saas-may-b",
        organization_id="org-q2-may-b",
    )
    add_touch(
        "touch-saas-jun-b",
        "channel-paid-social",
        "2025-06-10 16:00:00.000000",
        campaign_id="campaign-saas-jun-b",
        organization_id="org-q2-jun-b",
    )
    add_touch(
        "touch-commerce-apr-early",
        "channel-paid-search",
        "2025-04-04 16:00:00.000000",
        organization_id=None,
        consumer_id="consumer-apr-early",
    )
    add_touch(
        "touch-commerce-may-search",
        "channel-paid-search",
        "2025-05-05 18:00:00.000000",
        campaign_id="campaign-commerce-q2-search",
        consumer_id="consumer-may-search",
    )
    add_touch(
        "touch-commerce-may-search-two-a",
        "channel-organic",
        "2025-05-24 18:00:00.000000",
        consumer_id="consumer-may-search-two",
    )
    add_touch(
        "touch-commerce-may-search-two-z",
        "channel-paid-search",
        "2025-05-24 18:00:00.000000",
        campaign_id="campaign-commerce-alpha-search",
        consumer_id="consumer-may-search-two",
    )
    add_touch(
        "touch-commerce-may-social",
        "channel-paid-social",
        "2025-05-19 18:00:00.000000",
        campaign_id="campaign-commerce-beta-social",
        consumer_id="consumer-may-social",
    )
    add_touch(
        "touch-commerce-jun-search",
        "channel-paid-search",
        "2025-06-11 18:00:00.000000",
        campaign_id="campaign-commerce-alpha-search",
        consumer_id="consumer-jun-search",
    )
    add_touch(
        "touch-commerce-jun-expired-social",
        "channel-paid-social",
        "2025-06-16 18:00:00.000000",
        campaign_id="campaign-commerce-beta-social",
        consumer_id="consumer-jun-direct",
    )
    add_touch(
        "touch-commerce-one-apr",
        "channel-paid-search",
        "2025-04-14 16:00:00.000000",
        campaign_id="campaign-commerce-alpha-search",
        consumer_id="consumer-one",
    )
    add_touch(
        "touch-commerce-one-may",
        "channel-paid-search",
        "2025-05-14 16:00:00.000000",
        campaign_id="campaign-commerce-alpha-search",
        consumer_id="consumer-one",
    )
    add_touch(
        "touch-commerce-one-jun",
        "channel-paid-search",
        "2025-06-14 16:00:00.000000",
        campaign_id="campaign-commerce-alpha-search",
        consumer_id="consumer-one",
    )
    add_touch(
        "touch-commerce-two-apr",
        "channel-paid-social",
        "2025-04-15 16:00:00.000000",
        campaign_id="campaign-commerce-beta-social",
        consumer_id="consumer-two",
    )
    add_touch(
        "touch-commerce-two-may",
        "channel-paid-social",
        "2025-05-15 16:00:00.000000",
        campaign_id="campaign-commerce-beta-social",
        consumer_id="consumer-two",
    )
    add_touch(
        "touch-direct-audit",
        "channel-direct",
        "2025-06-17 12:00:00.000000",
        consumer_id="consumer-jun-direct",
        touch_type="direct",
    )
    add_touch(
        "touch-rejected-audit",
        "channel-paid-search",
        "2025-06-17 13:00:00.000000",
        consumer_id="consumer-jun-direct",
        quality="rejected",
    )
    add_touch(
        "touch-test",
        "channel-test",
        "2025-06-09 16:00:00.000000",
        campaign_id="campaign-test",
        organization_id="org-test",
        is_test=True,
    )

    touch_by_key = {item["record_id"]: item for item in touches}
    attrs: list[dict[str, Any]] = []

    def add_attr(
        key: str,
        conversion_type: str,
        fact_table: str,
        fact_id: str,
        conversion_at: str,
        *,
        organization_id: str | None = None,
        consumer_id: str | None = None,
        result: str,
        touch_id: str | None = None,
        cutoff: str = FINAL_CUTOFF,
        attributed_at: str | None = None,
        recorded_at: str | None = None,
        is_test: bool = False,
    ) -> None:
        touch = touch_by_key[touch_id]["values"] if touch_id else None
        history_complete = dt(conversion_at) - timedelta(hours=168) >= dt(
            "2025-04-01 07:00:00.000000"
        )
        if result == "non_direct":
            reason = "selected_last_non_direct"
            channel = touch["marketing_channel_id"] if touch else None
            campaign = touch["marketing_campaign_id"] if touch else None
        elif result == "direct":
            reason = "no_eligible_non_direct_touch"
            channel = ref("marketing_channel", "channel-direct")
            campaign = None
        else:
            reason = "window_history_incomplete"
            channel = None
            campaign = None
        attributed = attributed_at or cutoff
        recorded = recorded_at or attributed
        attrs.append(
            record(
                key,
                conversion_type=conversion_type,
                organization_id=ref("organization", organization_id) if organization_id else None,
                consumer_id=ref("consumer", consumer_id) if consumer_id else None,
                invoice_payment_attempt_id=(
                    ref(fact_table, fact_id) if fact_table == "invoice_payment_attempt" else None
                ),
                commerce_order_id=(
                    ref(fact_table, fact_id) if fact_table == "commerce_order" else None
                ),
                platform_fee_charge_id=(
                    ref(fact_table, fact_id) if fact_table == "platform_fee_charge" else None
                ),
                selected_marketing_touch_id=ref("marketing_touch", touch_id) if touch_id else None,
                marketing_channel_id=channel,
                marketing_campaign_id=campaign,
                attribution_result=result,
                reason_code=reason,
                model_version=MODEL_VERSION,
                conversion_at=conversion_at,
                window_started_at=dt_string(dt(conversion_at) - timedelta(hours=168)),
                history_complete=history_complete,
                source_data_cutoff_at=cutoff,
                attributed_at=attributed,
                is_test=is_test,
                recorded_at=recorded,
            )
        )

    payment_specs = [
        (
            "payment-apr-alpha",
            "2025-04-10 16:00:00.000000",
            "org-alpha",
            "non_direct",
            "touch-saas-alpha-apr",
            True,
        ),
        (
            "payment-apr-beta",
            "2025-04-15 16:00:00.000000",
            "org-beta",
            "non_direct",
            "touch-saas-beta-apr",
            True,
        ),
        (
            "payment-may-beta",
            "2025-05-16 16:00:00.000000",
            "org-beta",
            "non_direct",
            "touch-saas-beta-may",
            False,
        ),
        (
            "payment-may-delta",
            "2025-05-25 16:00:00.000000",
            "org-delta",
            "non_direct",
            "touch-saas-delta-may",
            True,
        ),
        ("payment-jun-epsilon", "2025-06-08 16:00:00.000000", "org-epsilon", "direct", None, True),
        (
            "payment-q2-apr-early",
            payment_times["payment-q2-apr-early"],
            "org-q2-apr-early",
            "unknown_unattributed",
            None,
            True,
        ),
        (
            "payment-q2-apr-boundary",
            payment_times["payment-q2-apr-boundary"],
            "org-q2-apr-boundary",
            "direct",
            None,
            True,
        ),
        (
            "payment-q2-may-a",
            payment_times["payment-q2-may-a"],
            "org-q2-may-a",
            "non_direct",
            "touch-saas-may-a",
            True,
        ),
        (
            "payment-q2-may-b",
            payment_times["payment-q2-may-b"],
            "org-q2-may-b",
            "non_direct",
            "touch-saas-may-b",
            True,
        ),
        (
            "payment-q2-jun-b",
            payment_times["payment-q2-jun-b"],
            "org-q2-jun-b",
            "non_direct",
            "touch-saas-jun-b",
            True,
        ),
    ]
    for payment_id, conversion_at, org_id, result, touch_id, first in payment_specs:
        if first:
            add_attr(
                f"attr-{payment_id}-first",
                "saas_first_payment",
                "invoice_payment_attempt",
                payment_id,
                conversion_at,
                organization_id=org_id,
                result=result,
                touch_id=touch_id,
            )
        add_attr(
            f"attr-{payment_id}-revenue",
            "saas_revenue",
            "invoice_payment_attempt",
            payment_id,
            conversion_at,
            organization_id=org_id,
            result=result,
            touch_id=touch_id,
        )

    add_attr(
        "attr-payment-jun-delta-revenue-early",
        "saas_revenue",
        "invoice_payment_attempt",
        "payment-jun-delta",
        "2025-06-05 16:00:00.000000",
        organization_id="org-delta",
        result="direct",
        cutoff="2025-06-30 23:59:59.000000",
    )
    add_attr(
        "attr-payment-jun-delta-revenue-final",
        "saas_revenue",
        "invoice_payment_attempt",
        "payment-jun-delta",
        "2025-06-05 16:00:00.000000",
        organization_id="org-delta",
        result="non_direct",
        touch_id="touch-saas-delta-jun-late",
        cutoff=FINAL_CUTOFF,
    )
    add_attr(
        "attr-payment-test",
        "saas_revenue",
        "invoice_payment_attempt",
        "payment-test-fact",
        "2025-06-10 16:00:00.000000",
        organization_id="org-fact-test",
        result="direct",
        is_test=True,
    )

    commerce_new = [
        ("apr-early", "consumer-apr-early", "unknown_unattributed", None),
        ("may-search", "consumer-may-search", "non_direct", "touch-commerce-may-search"),
        (
            "may-search-two",
            "consumer-may-search-two",
            "non_direct",
            "touch-commerce-may-search-two-z",
        ),
        ("may-social", "consumer-may-social", "non_direct", "touch-commerce-may-social"),
        ("jun-search", "consumer-jun-search", "non_direct", "touch-commerce-jun-search"),
        ("jun-direct", "consumer-jun-direct", "direct", None),
    ]
    for key, consumer_id, result, touch_id in commerce_new:
        order_id = f"order-{key}"
        fee_id = f"fee-{key}"
        add_attr(
            f"attr-{order_id}-first",
            "commerce_first_payment",
            "commerce_order",
            order_id,
            order_times[order_id],
            consumer_id=consumer_id,
            result=result,
            touch_id=touch_id,
        )
        add_attr(
            f"attr-{order_id}-gmv",
            "attributed_gmv",
            "commerce_order",
            order_id,
            order_times[order_id],
            consumer_id=consumer_id,
            result=result,
            touch_id=touch_id,
        )
        add_attr(
            f"attr-{fee_id}-revenue",
            "commerce_revenue",
            "platform_fee_charge",
            fee_id,
            fee_times[fee_id],
            consumer_id=consumer_id,
            result=result,
            touch_id=touch_id,
        )

    existing_commerce = [
        ("order-a-apr", "fee-order-a-apr", "consumer-one", "touch-commerce-one-apr"),
        ("order-b-apr", "fee-order-b-apr", "consumer-two", "touch-commerce-two-apr"),
        ("order-a-may", "fee-order-a-may", "consumer-one", "touch-commerce-one-may"),
        ("order-b-may", "fee-order-b-may", "consumer-two", "touch-commerce-two-may"),
        ("order-a-jun", "fee-order-a-jun", "consumer-one", "touch-commerce-one-jun"),
        ("order-b-jun", "fee-order-b-jun", "consumer-two", None),
    ]
    existing_times = {
        "order-a-apr": "2025-04-15 16:00:00.000000",
        "order-b-apr": "2025-04-16 16:00:00.000000",
        "order-a-may": "2025-05-15 16:00:00.000000",
        "order-b-may": "2025-05-16 16:00:00.000000",
        "order-a-jun": "2025-06-15 16:00:00.000000",
        "order-b-jun": "2025-06-16 16:00:00.000000",
    }
    for order_id, fee_id, consumer_id, touch_id in existing_commerce:
        result = "non_direct" if touch_id else "direct"
        conversion_at = existing_times[order_id]
        add_attr(
            f"attr-{order_id}-gmv",
            "attributed_gmv",
            "commerce_order",
            order_id,
            conversion_at,
            consumer_id=consumer_id,
            result=result,
            touch_id=touch_id,
        )
        add_attr(
            f"attr-{fee_id}-revenue",
            "commerce_revenue",
            "platform_fee_charge",
            fee_id,
            conversion_at,
            consumer_id=consumer_id,
            result=result,
            touch_id=touch_id,
        )
    add_attr(
        "attr-fee-cancelled-order-may-revenue",
        "commerce_revenue",
        "platform_fee_charge",
        "fee-cancelled-order-may",
        "2025-05-20 17:05:00.000000",
        consumer_id="consumer-one",
        result="non_direct",
        touch_id="touch-commerce-one-may",
    )
    add_attr(
        "attr-fee-test",
        "commerce_revenue",
        "platform_fee_charge",
        "fee-test",
        "2025-06-20 17:00:00.000000",
        consumer_id="consumer-one",
        result="non_direct",
        touch_id="touch-commerce-one-jun",
        is_test=True,
    )

    return {
        "source_id": "marketing",
        "tables": [
            {
                "table_name": "marketing_channel",
                "match_columns": ["channel_code"],
                "records": channels,
            },
            {
                "table_name": "marketing_campaign",
                "match_columns": ["external_campaign_id"],
                "records": campaigns,
            },
            {
                "table_name": "campaign_daily_spend",
                "match_columns": ["marketing_campaign_id", "business_date", "version_number"],
                "records": spends,
            },
            {
                "table_name": "marketing_touch",
                "match_columns": ["source_event_id"],
                "records": touches,
            },
            {
                "table_name": "attributed_conversion",
                "match_columns": [
                    "conversion_type",
                    "invoice_payment_attempt_id",
                    "commerce_order_id",
                    "platform_fee_charge_id",
                    "model_version",
                    "source_data_cutoff_at",
                ],
                "records": attrs,
            },
        ],
    }


def main() -> None:
    identity = load("identity.json")
    saas = load("saas.json")
    commerce = load("commerce.json")
    add_identity(identity)
    payment_times = add_saas(saas)
    order_times, fee_times = add_commerce(commerce)
    marketing = add_marketing(payment_times, order_times, fee_times)
    dump("identity.json", identity)
    dump("saas.json", saas)
    dump("commerce.json", commerce)
    dump("marketing.json", marketing)


if __name__ == "__main__":
    main()
