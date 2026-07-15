"""Real MySQL constraint tests for M1.1D marketing tables."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError, IntegrityError, OperationalError
from sqlalchemy.orm import Session

from insightops.db.models import (
    AttributedConversion,
    CampaignDailySpend,
    CommerceOrder,
    Consumer,
    InvoicePaymentAttempt,
    MarketingCampaign,
    MarketingChannel,
    MarketingTouch,
    Organization,
    PlatformFeeCharge,
    SubscriptionInvoice,
)

START = datetime(2025, 1, 1)
TOUCH_TIME = datetime(2025, 1, 2)
RECEIVED_TIME = datetime(2025, 1, 2, 1)
PROCESSED_TIME = datetime(2025, 1, 2, 2)
CONVERSION_TIME = datetime(2025, 1, 4)
WINDOW_START = CONVERSION_TIME - timedelta(hours=168)
SOURCE_CUTOFF = datetime(2025, 1, 5)
ATTRIBUTED_TIME = datetime(2025, 1, 6)
RECORDED_TIME = datetime(2025, 1, 7)
ONE_HUNDRED = Decimal("100.0000")


@pytest.fixture
def paid_channel(db_session: Session) -> MarketingChannel:
    """Insert a governed paid channel."""
    channel = _channel("paid-search", "paid")
    db_session.add(channel)
    db_session.flush()
    return channel


@pytest.fixture
def direct_channel(db_session: Session) -> MarketingChannel:
    """Insert the one governed direct channel."""
    channel = _channel("direct", "direct")
    db_session.add(channel)
    db_session.flush()
    return channel


@pytest.fixture
def campaign(
    db_session: Session,
    organization: Organization,
    paid_channel: MarketingChannel,
) -> MarketingCampaign:
    """Insert a SaaS-scoped campaign."""
    campaign = _campaign(organization, paid_channel)
    db_session.add(campaign)
    db_session.flush()
    return campaign


@pytest.fixture
def organization_touch(
    db_session: Session,
    organization: Organization,
    paid_channel: MarketingChannel,
    campaign: MarketingCampaign,
) -> MarketingTouch:
    """Insert an accepted organization touch."""
    touch = _organization_touch(organization, paid_channel, campaign)
    db_session.add(touch)
    db_session.flush()
    return touch


@pytest.fixture
def payment_attempt(
    db_session: Session,
    invoice: SubscriptionInvoice,
) -> InvoicePaymentAttempt:
    """Insert a successful SaaS payment attempt."""
    attempt = InvoicePaymentAttempt(
        external_payment_attempt_id="payment-marketing-fixture",
        provider_transaction_id="provider-marketing-fixture",
        subscription_invoice_id=invoice.subscription_invoice_id,
        status="succeeded",
        subscription_fee_amount="100.0000",
        tax_amount="10.0000",
        one_time_amount="0.0000",
        total_amount="110.0000",
        currency_code="USD",
        attempted_at=CONVERSION_TIME - timedelta(hours=1),
        succeeded_at=CONVERSION_TIME,
    )
    db_session.add(attempt)
    db_session.flush()
    return attempt


@pytest.fixture
def fee_charge(
    db_session: Session,
    commerce_order: CommerceOrder,
) -> PlatformFeeCharge:
    """Insert a successful commerce platform-fee charge."""
    charge = PlatformFeeCharge(
        external_fee_charge_id="fee-marketing-fixture",
        provider_charge_id="provider-fee-marketing-fixture",
        commerce_order_id=commerce_order.commerce_order_id,
        status="succeeded",
        fee_amount="5.0000",
        currency_code="USD",
        attempted_at=CONVERSION_TIME - timedelta(hours=1),
        succeeded_at=CONVERSION_TIME,
    )
    db_session.add(charge)
    db_session.flush()
    return charge


def test_channel_accepts_case_distinct_codes(db_session: Session) -> None:
    db_session.add_all([_channel("Paid-Search", "paid"), _channel("paid-search", "paid")])
    db_session.flush()


def test_channel_rejects_invalid_direct_code_type_and_range(db_session: Session) -> None:
    invalid = _channel("direct", "paid")
    invalid.effective_to = START
    db_session.add(invalid)
    _assert_constraint_rejection_and_rollback(db_session)


def test_campaign_requires_valid_scope_parent_and_lifecycle(
    db_session: Session,
    organization: Organization,
    paid_channel: MarketingChannel,
) -> None:
    invalid = _campaign(organization, paid_channel)
    invalid.business_scope = "mixed"
    invalid.ended_at = START - timedelta(days=1)
    db_session.add(invalid)
    _assert_constraint_rejection_and_rollback(db_session)


def test_saas_campaign_rejects_merchant_assignment(
    db_session: Session,
    organization: Organization,
    paid_channel: MarketingChannel,
) -> None:
    invalid = _campaign(organization, paid_channel)
    invalid.merchant_assignment_id = 18_446_744_073_709_551_614
    db_session.add(invalid)
    _assert_constraint_rejection_and_rollback(db_session)


def test_spend_accepts_append_only_correction_revisions(
    db_session: Session,
    campaign: MarketingCampaign,
) -> None:
    first = _spend(campaign, version=1, amount="100.0000", recorded_at=datetime(2025, 1, 3))
    db_session.add(first)
    db_session.flush()
    second = _spend(
        campaign,
        version=2,
        amount="120.0000",
        recorded_at=datetime(2025, 1, 5),
        supersedes=first.campaign_daily_spend_id,
    )
    db_session.add(second)
    db_session.flush()


@pytest.mark.parametrize(
    ("version", "supersedes"),
    [(1, 1), (2, None), (0, None)],
)
def test_spend_rejects_invalid_version_lineage(
    db_session: Session,
    campaign: MarketingCampaign,
    version: int,
    supersedes: int | None,
) -> None:
    db_session.add(_spend(campaign, version=version, supersedes=supersedes))
    _assert_constraint_rejection_and_rollback(db_session)


def test_spend_rejects_duplicate_version_and_revision_branch(
    db_session: Session,
    campaign: MarketingCampaign,
) -> None:
    first = _spend(campaign, version=1)
    db_session.add(first)
    db_session.flush()
    db_session.add_all(
        [
            _spend(campaign, version=2, supersedes=first.campaign_daily_spend_id),
            _spend(campaign, version=2, supersedes=first.campaign_daily_spend_id),
        ]
    )
    _assert_constraint_rejection_and_rollback(db_session)


def test_spend_rejects_invalid_amount_currency_and_visibility(
    db_session: Session,
    campaign: MarketingCampaign,
) -> None:
    invalid = _spend(campaign, version=1, amount="-0.0001")
    invalid.currency_code = "EUR"
    invalid.recorded_at = START - timedelta(seconds=1)
    db_session.add(invalid)
    _assert_constraint_rejection_and_rollback(db_session)


def test_spend_snapshot_filters_visibility_before_selecting_max_version(
    db_session: Session,
    campaign: MarketingCampaign,
) -> None:
    first = _spend(campaign, version=1, amount="100.0000", recorded_at=datetime(2025, 1, 3))
    db_session.add(first)
    db_session.flush()
    second = _spend(
        campaign,
        version=2,
        amount="120.0000",
        recorded_at=datetime(2025, 1, 5),
        supersedes=first.campaign_daily_spend_id,
    )
    db_session.add(second)
    db_session.flush()

    query = text(
        "WITH visible AS ("
        "SELECT spend_amount, ROW_NUMBER() OVER ("
        "PARTITION BY marketing_campaign_id, business_date "
        "ORDER BY version_number DESC) AS revision_rank "
        "FROM campaign_daily_spend "
        "WHERE marketing_campaign_id = :campaign_id AND recorded_at <= :cutoff"
        ") SELECT spend_amount FROM visible WHERE revision_rank = 1"
    )
    early = db_session.scalar(
        query,
        {"campaign_id": campaign.marketing_campaign_id, "cutoff": datetime(2025, 1, 4)},
    )
    late = db_session.scalar(
        query,
        {"campaign_id": campaign.marketing_campaign_id, "cutoff": datetime(2025, 1, 6)},
    )
    assert early == ONE_HUNDRED
    assert late == Decimal("120.0000")


def test_touch_accepts_exactly_one_subject(
    db_session: Session,
    organization: Organization,
    consumer: Consumer,
    paid_channel: MarketingChannel,
) -> None:
    organization_touch = _organization_touch(organization, paid_channel)
    consumer_touch = _consumer_touch(consumer, paid_channel)
    db_session.add_all([organization_touch, consumer_touch])
    db_session.flush()


@pytest.mark.parametrize("both_subjects", [False, True])
def test_touch_rejects_missing_or_multiple_subjects(
    db_session: Session,
    organization: Organization,
    consumer: Consumer,
    paid_channel: MarketingChannel,
    both_subjects: bool,
) -> None:
    touch = _organization_touch(organization, paid_channel)
    touch.organization_id = organization.organization_id if both_subjects else None
    touch.consumer_id = consumer.consumer_id if both_subjects else None
    db_session.add(touch)
    _assert_constraint_rejection_and_rollback(db_session)


def test_touch_rejects_invalid_visibility_order(
    db_session: Session,
    organization: Organization,
    paid_channel: MarketingChannel,
) -> None:
    touch = _organization_touch(organization, paid_channel)
    touch.processed_at = touch.received_at - timedelta(seconds=1)
    db_session.add(touch)
    _assert_constraint_rejection_and_rollback(db_session)


def test_touch_source_event_is_unique(
    db_session: Session,
    organization: Organization,
    paid_channel: MarketingChannel,
) -> None:
    db_session.add_all(
        [
            _organization_touch(organization, paid_channel),
            _organization_touch(organization, paid_channel),
        ]
    )
    _assert_constraint_rejection_and_rollback(db_session)


def test_all_conversion_types_accept_their_authoritative_fact_and_subject(
    db_session: Session,
    organization: Organization,
    consumer: Consumer,
    paid_channel: MarketingChannel,
    campaign: MarketingCampaign,
    organization_touch: MarketingTouch,
    payment_attempt: InvoicePaymentAttempt,
    commerce_order: CommerceOrder,
    fee_charge: PlatformFeeCharge,
) -> None:
    conversions = [
        _saas_conversion(
            organization,
            payment_attempt,
            paid_channel,
            campaign,
            organization_touch,
            conversion_type="saas_first_payment",
        ),
        _saas_conversion(
            organization,
            payment_attempt,
            paid_channel,
            campaign,
            organization_touch,
            conversion_type="saas_revenue",
        ),
        _commerce_conversion(consumer, commerce_order, conversion_type="commerce_first_payment"),
        _commerce_conversion(consumer, commerce_order, conversion_type="attributed_gmv"),
        _commerce_revenue_conversion(consumer, fee_charge),
    ]
    db_session.add_all(conversions)
    db_session.flush()


@pytest.mark.parametrize("fact_mode", ["none", "multiple", "wrong_type"])
def test_conversion_rejects_invalid_authoritative_fact_combination(
    db_session: Session,
    organization: Organization,
    paid_channel: MarketingChannel,
    campaign: MarketingCampaign,
    organization_touch: MarketingTouch,
    payment_attempt: InvoicePaymentAttempt,
    commerce_order: CommerceOrder,
    fact_mode: str,
) -> None:
    conversion = _saas_conversion(
        organization,
        payment_attempt,
        paid_channel,
        campaign,
        organization_touch,
    )
    if fact_mode == "none":
        conversion.invoice_payment_attempt_id = None
    elif fact_mode == "multiple":
        conversion.commerce_order_id = commerce_order.commerce_order_id
    else:
        conversion.conversion_type = "commerce_first_payment"
    db_session.add(conversion)
    _assert_constraint_rejection_and_rollback(db_session)


@pytest.mark.parametrize("subject_mode", ["none", "multiple", "wrong_domain"])
def test_conversion_rejects_invalid_subject_combination(
    db_session: Session,
    organization: Organization,
    consumer: Consumer,
    paid_channel: MarketingChannel,
    campaign: MarketingCampaign,
    organization_touch: MarketingTouch,
    payment_attempt: InvoicePaymentAttempt,
    subject_mode: str,
) -> None:
    conversion = _saas_conversion(
        organization,
        payment_attempt,
        paid_channel,
        campaign,
        organization_touch,
    )
    if subject_mode == "none":
        conversion.organization_id = None
    elif subject_mode == "multiple":
        conversion.consumer_id = consumer.consumer_id
    else:
        conversion.organization_id = None
        conversion.consumer_id = consumer.consumer_id
    db_session.add(conversion)
    _assert_constraint_rejection_and_rollback(db_session)


def test_conversion_rejects_missing_selected_touch_for_non_direct(
    db_session: Session,
    organization: Organization,
    paid_channel: MarketingChannel,
    campaign: MarketingCampaign,
    organization_touch: MarketingTouch,
    payment_attempt: InvoicePaymentAttempt,
) -> None:
    conversion = _saas_conversion(
        organization,
        payment_attempt,
        paid_channel,
        campaign,
        organization_touch,
    )
    conversion.selected_marketing_touch_id = None
    db_session.add(conversion)
    _assert_constraint_rejection_and_rollback(db_session)


def test_direct_and_unknown_require_empty_selected_touch(
    db_session: Session,
    organization: Organization,
    direct_channel: MarketingChannel,
    organization_touch: MarketingTouch,
    payment_attempt: InvoicePaymentAttempt,
) -> None:
    direct = _direct_saas_conversion(organization, payment_attempt, direct_channel)
    direct.selected_marketing_touch_id = organization_touch.marketing_touch_id
    unknown = _unknown_saas_conversion(organization, payment_attempt)
    unknown.selected_marketing_touch_id = organization_touch.marketing_touch_id
    db_session.add_all([direct, unknown])
    _assert_constraint_rejection_and_rollback(db_session)


def test_conversion_rejects_inconsistent_reason_history_model_window_and_visibility(
    db_session: Session,
    organization: Organization,
    paid_channel: MarketingChannel,
    campaign: MarketingCampaign,
    organization_touch: MarketingTouch,
    payment_attempt: InvoicePaymentAttempt,
) -> None:
    conversion = _saas_conversion(
        organization,
        payment_attempt,
        paid_channel,
        campaign,
        organization_touch,
    )
    conversion.reason_code = "window_history_incomplete"
    conversion.model_version = "first_touch_v1"
    conversion.window_started_at = WINDOW_START + timedelta(seconds=1)
    conversion.source_data_cutoff_at = ATTRIBUTED_TIME + timedelta(seconds=1)
    db_session.add(conversion)
    _assert_constraint_rejection_and_rollback(db_session)


def test_conversion_is_unique_per_fact_model_and_source_cutoff(
    db_session: Session,
    organization: Organization,
    paid_channel: MarketingChannel,
    campaign: MarketingCampaign,
    organization_touch: MarketingTouch,
    payment_attempt: InvoicePaymentAttempt,
) -> None:
    first = _saas_conversion(
        organization,
        payment_attempt,
        paid_channel,
        campaign,
        organization_touch,
    )
    duplicate = _saas_conversion(
        organization,
        payment_attempt,
        paid_channel,
        campaign,
        organization_touch,
    )
    db_session.add_all([first, duplicate])
    _assert_constraint_rejection_and_rollback(db_session)


def test_later_source_cutoff_can_append_a_new_attribution_result(
    db_session: Session,
    organization: Organization,
    paid_channel: MarketingChannel,
    campaign: MarketingCampaign,
    organization_touch: MarketingTouch,
    payment_attempt: InvoicePaymentAttempt,
) -> None:
    first = _saas_conversion(
        organization,
        payment_attempt,
        paid_channel,
        campaign,
        organization_touch,
    )
    second = _saas_conversion(
        organization,
        payment_attempt,
        paid_channel,
        campaign,
        organization_touch,
    )
    second.source_data_cutoff_at = SOURCE_CUTOFF + timedelta(days=1)
    second.attributed_at = ATTRIBUTED_TIME + timedelta(days=1)
    second.recorded_at = RECORDED_TIME + timedelta(days=1)
    db_session.add_all([first, second])
    db_session.flush()


def test_unknown_history_reason_requires_incomplete_history(
    db_session: Session,
    organization: Organization,
    payment_attempt: InvoicePaymentAttempt,
) -> None:
    valid = _unknown_saas_conversion(organization, payment_attempt)
    db_session.add(valid)
    db_session.flush()
    invalid = _unknown_saas_conversion(organization, payment_attempt)
    invalid.source_data_cutoff_at += timedelta(days=1)
    invalid.attributed_at += timedelta(days=1)
    invalid.recorded_at += timedelta(days=1)
    invalid.history_complete = True
    db_session.add(invalid)
    _assert_constraint_rejection_and_rollback(db_session)


def _channel(code: str, channel_type: str) -> MarketingChannel:
    return MarketingChannel(
        channel_code=code,
        channel_name=code,
        channel_type=channel_type,
        status="active",
        effective_from=START,
        created_at=START,
    )


def _campaign(
    organization: Organization,
    channel: MarketingChannel,
) -> MarketingCampaign:
    return MarketingCampaign(
        external_campaign_id="campaign-test",
        organization_id=organization.organization_id,
        primary_channel_id=channel.marketing_channel_id,
        business_scope="saas",
        campaign_name="Test Campaign",
        status="active",
        created_at=START,
        started_at=START,
        status_updated_at=START,
    )


def _spend(
    campaign: MarketingCampaign,
    *,
    version: int,
    amount: str = "100.0000",
    recorded_at: datetime = datetime(2025, 1, 3),
    supersedes: int | None = None,
) -> CampaignDailySpend:
    return CampaignDailySpend(
        marketing_campaign_id=campaign.marketing_campaign_id,
        business_date=date(2025, 1, 1),
        version_number=version,
        supersedes_campaign_daily_spend_id=supersedes,
        spend_amount=amount,
        currency_code="USD",
        finalized_at=datetime(2025, 1, 2),
        recorded_at=recorded_at,
    )


def _organization_touch(
    organization: Organization,
    channel: MarketingChannel,
    campaign: MarketingCampaign | None = None,
) -> MarketingTouch:
    return MarketingTouch(
        source_event_id="touch-organization-test",
        marketing_channel_id=channel.marketing_channel_id,
        marketing_campaign_id=(campaign.marketing_campaign_id if campaign is not None else None),
        organization_id=organization.organization_id,
        touch_type="non_direct",
        quality_status="accepted",
        occurred_at=TOUCH_TIME,
        received_at=RECEIVED_TIME,
        processed_at=PROCESSED_TIME,
        recorded_at=PROCESSED_TIME,
    )


def _consumer_touch(consumer: Consumer, channel: MarketingChannel) -> MarketingTouch:
    return MarketingTouch(
        source_event_id="touch-consumer-test",
        marketing_channel_id=channel.marketing_channel_id,
        consumer_id=consumer.consumer_id,
        touch_type="non_direct",
        quality_status="accepted",
        occurred_at=TOUCH_TIME,
        received_at=RECEIVED_TIME,
        processed_at=PROCESSED_TIME,
        recorded_at=PROCESSED_TIME,
    )


def _saas_conversion(
    organization: Organization,
    payment: InvoicePaymentAttempt,
    channel: MarketingChannel,
    campaign: MarketingCampaign,
    touch: MarketingTouch,
    *,
    conversion_type: str = "saas_revenue",
) -> AttributedConversion:
    return AttributedConversion(
        conversion_type=conversion_type,
        organization_id=organization.organization_id,
        invoice_payment_attempt_id=payment.invoice_payment_attempt_id,
        selected_marketing_touch_id=touch.marketing_touch_id,
        marketing_channel_id=channel.marketing_channel_id,
        marketing_campaign_id=campaign.marketing_campaign_id,
        attribution_result="non_direct",
        reason_code="selected_last_non_direct",
        model_version="last_non_direct_168h_v1",
        conversion_at=CONVERSION_TIME,
        window_started_at=WINDOW_START,
        history_complete=True,
        source_data_cutoff_at=SOURCE_CUTOFF,
        attributed_at=ATTRIBUTED_TIME,
        recorded_at=RECORDED_TIME,
    )


def _direct_saas_conversion(
    organization: Organization,
    payment: InvoicePaymentAttempt,
    direct_channel: MarketingChannel,
) -> AttributedConversion:
    return AttributedConversion(
        conversion_type="saas_revenue",
        organization_id=organization.organization_id,
        invoice_payment_attempt_id=payment.invoice_payment_attempt_id,
        marketing_channel_id=direct_channel.marketing_channel_id,
        attribution_result="direct",
        reason_code="no_eligible_non_direct_touch",
        model_version="last_non_direct_168h_v1",
        conversion_at=CONVERSION_TIME,
        window_started_at=WINDOW_START,
        history_complete=True,
        source_data_cutoff_at=SOURCE_CUTOFF,
        attributed_at=ATTRIBUTED_TIME,
        recorded_at=RECORDED_TIME,
    )


def _unknown_saas_conversion(
    organization: Organization,
    payment: InvoicePaymentAttempt,
) -> AttributedConversion:
    return AttributedConversion(
        conversion_type="saas_revenue",
        organization_id=organization.organization_id,
        invoice_payment_attempt_id=payment.invoice_payment_attempt_id,
        attribution_result="unknown_unattributed",
        reason_code="window_history_incomplete",
        model_version="last_non_direct_168h_v1",
        conversion_at=CONVERSION_TIME,
        window_started_at=WINDOW_START,
        history_complete=False,
        source_data_cutoff_at=SOURCE_CUTOFF,
        attributed_at=ATTRIBUTED_TIME,
        recorded_at=RECORDED_TIME,
    )


def _commerce_conversion(
    consumer: Consumer,
    order: CommerceOrder,
    *,
    conversion_type: str,
) -> AttributedConversion:
    return AttributedConversion(
        conversion_type=conversion_type,
        consumer_id=consumer.consumer_id,
        commerce_order_id=order.commerce_order_id,
        attribution_result="unknown_unattributed",
        reason_code="identity_unresolved",
        model_version="last_non_direct_168h_v1",
        conversion_at=CONVERSION_TIME,
        window_started_at=WINDOW_START,
        history_complete=True,
        source_data_cutoff_at=SOURCE_CUTOFF,
        attributed_at=ATTRIBUTED_TIME,
        recorded_at=RECORDED_TIME,
    )


def _commerce_revenue_conversion(
    consumer: Consumer,
    fee: PlatformFeeCharge,
) -> AttributedConversion:
    return AttributedConversion(
        conversion_type="commerce_revenue",
        consumer_id=consumer.consumer_id,
        platform_fee_charge_id=fee.platform_fee_charge_id,
        attribution_result="unknown_unattributed",
        reason_code="channel_unmapped",
        model_version="last_non_direct_168h_v1",
        conversion_at=CONVERSION_TIME,
        window_started_at=WINDOW_START,
        history_complete=True,
        source_data_cutoff_at=SOURCE_CUTOFF,
        attributed_at=ATTRIBUTED_TIME,
        recorded_at=RECORDED_TIME,
    )


def _assert_constraint_rejection_and_rollback(db_session: Session) -> None:
    with pytest.raises((IntegrityError, OperationalError)) as error_info:
        db_session.flush()
    db_session.rollback()
    _assert_expected_constraint_exception(error_info.value)


def _assert_expected_constraint_exception(error: DatabaseError) -> None:
    """Accept integrity errors or MySQL's narrowly identified CHECK violation."""
    assert isinstance(error, (IntegrityError, OperationalError))
    if isinstance(error, OperationalError):
        assert error.orig is not None
        assert error.orig.args[0] == 3819
