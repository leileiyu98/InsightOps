"""Real MySQL constraint tests for SaaS tables."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from insightops.db.models import (
    InvoicePaymentAttempt,
    Organization,
    SaasPlanVersion,
    Subscription,
    SubscriptionInvoice,
    SubscriptionStateEvent,
)

START = datetime(2025, 1, 1)
LATER = datetime(2025, 2, 1)
ZERO = Decimal("0.0000")
TEN = Decimal("10.0000")
ONE_HUNDRED = Decimal("100.0000")


def test_duplicate_plan_code_and_version_is_rejected(db_session: Session) -> None:
    db_session.add_all([_plan(), _plan()])
    _assert_constraint_rejection_and_rollback(db_session)


def test_plan_version_must_be_positive(db_session: Session) -> None:
    plan = _plan()
    plan.version_number = 0
    db_session.add(plan)
    _assert_constraint_rejection_and_rollback(db_session)


def test_plan_billing_interval_is_restricted(db_session: Session) -> None:
    plan = _plan()
    plan.billing_interval = "weekly"
    db_session.add(plan)
    _assert_constraint_rejection_and_rollback(db_session)


def test_plan_currency_is_usd_only(db_session: Session) -> None:
    plan = _plan()
    plan.currency_code = "EUR"
    db_session.add(plan)
    _assert_constraint_rejection_and_rollback(db_session)


def test_plan_amount_cannot_be_negative(db_session: Session) -> None:
    plan = _plan()
    plan.recurring_amount = Decimal("-0.0001")
    db_session.add(plan)
    _assert_constraint_rejection_and_rollback(db_session)


def test_plan_effective_range_requires_strictly_later_end(db_session: Session) -> None:
    plan = _plan()
    plan.effective_to = plan.effective_from
    db_session.add(plan)
    _assert_constraint_rejection_and_rollback(db_session)


def test_subscription_requires_existing_organization(
    db_session: Session,
    plan: SaasPlanVersion,
) -> None:
    db_session.add(_subscription(18_446_744_073_709_551_614, plan.saas_plan_version_id))
    _assert_constraint_rejection_and_rollback(db_session)


def test_subscription_requires_existing_current_plan(
    db_session: Session,
    organization: Organization,
) -> None:
    db_session.add(_subscription(organization.organization_id, 18_446_744_073_709_551_614))
    _assert_constraint_rejection_and_rollback(db_session)


def test_duplicate_subscription_external_id_is_rejected(
    db_session: Session,
    organization: Organization,
    plan: SaasPlanVersion,
) -> None:
    db_session.add_all(
        [
            _subscription(organization.organization_id, plan.saas_plan_version_id),
            _subscription(organization.organization_id, plan.saas_plan_version_id),
        ]
    )
    _assert_constraint_rejection_and_rollback(db_session)


def test_subscription_status_is_restricted(
    db_session: Session,
    organization: Organization,
    plan: SaasPlanVersion,
) -> None:
    subscription = _subscription(
        organization.organization_id,
        plan.saas_plan_version_id,
    )
    subscription.current_status = "unknown"
    db_session.add(subscription)
    _assert_constraint_rejection_and_rollback(db_session)


def test_subscription_period_end_must_be_after_start(
    db_session: Session,
    organization: Organization,
    plan: SaasPlanVersion,
) -> None:
    subscription = _subscription(
        organization.organization_id,
        plan.saas_plan_version_id,
    )
    subscription.current_period_started_at = LATER
    subscription.current_period_ends_at = START
    db_session.add(subscription)
    _assert_constraint_rejection_and_rollback(db_session)


def test_subscription_cancellation_cannot_precede_schedule(
    db_session: Session,
    organization: Organization,
    plan: SaasPlanVersion,
) -> None:
    subscription = _subscription(
        organization.organization_id,
        plan.saas_plan_version_id,
    )
    subscription.cancel_scheduled_at = LATER
    subscription.cancellation_effective_at = START
    db_session.add(subscription)
    _assert_constraint_rejection_and_rollback(db_session)


def test_duplicate_state_event_source_id_is_rejected(
    db_session: Session,
    subscription: Subscription,
    plan: SaasPlanVersion,
) -> None:
    first = _state_event(subscription, plan, source_id="event-duplicate", effective_at=START)
    second = _state_event(
        subscription,
        plan,
        source_id="event-duplicate",
        effective_at=START + timedelta(days=1),
    )
    db_session.add_all([first, second])
    _assert_constraint_rejection_and_rollback(db_session)


def test_state_event_is_unique_per_subscription_effective_time(
    db_session: Session,
    subscription: Subscription,
    plan: SaasPlanVersion,
) -> None:
    first = _state_event(subscription, plan, source_id="event-one", effective_at=START)
    second = _state_event(subscription, plan, source_id="event-two", effective_at=START)
    db_session.add_all([first, second])
    _assert_constraint_rejection_and_rollback(db_session)


def test_expansion_requires_mrr_increase(
    db_session: Session,
    subscription: Subscription,
    plan: SaasPlanVersion,
) -> None:
    event = _state_event(subscription, plan, event_type="expansion")
    event.normalized_mrr_before = ONE_HUNDRED
    event.normalized_mrr_after = ONE_HUNDRED
    db_session.add(event)
    _assert_constraint_rejection_and_rollback(db_session)


def test_contraction_requires_positive_lower_after_mrr(
    db_session: Session,
    subscription: Subscription,
    plan: SaasPlanVersion,
) -> None:
    event = _state_event(subscription, plan, event_type="contraction")
    event.normalized_mrr_before = ONE_HUNDRED
    event.normalized_mrr_after = ZERO
    db_session.add(event)
    _assert_constraint_rejection_and_rollback(db_session)


def test_cancellation_requires_zero_after_mrr(
    db_session: Session,
    subscription: Subscription,
    plan: SaasPlanVersion,
) -> None:
    event = _state_event(subscription, plan, event_type="cancellation_effective")
    event.normalized_mrr_before = ONE_HUNDRED
    event.normalized_mrr_after = TEN
    db_session.add(event)
    _assert_constraint_rejection_and_rollback(db_session)


def test_state_event_rejects_negative_amount(
    db_session: Session,
    subscription: Subscription,
    plan: SaasPlanVersion,
) -> None:
    event = _state_event(subscription, plan)
    event.recurring_amount_before = Decimal("-0.0001")
    db_session.add(event)
    _assert_constraint_rejection_and_rollback(db_session)


def test_state_event_currency_is_usd_only(
    db_session: Session,
    subscription: Subscription,
    plan: SaasPlanVersion,
) -> None:
    event = _state_event(subscription, plan)
    event.currency_code = "EUR"
    db_session.add(event)
    _assert_constraint_rejection_and_rollback(db_session)


def test_state_event_type_is_restricted(
    db_session: Session,
    subscription: Subscription,
    plan: SaasPlanVersion,
) -> None:
    event = _state_event(subscription, plan)
    event.event_type = "unknown"
    db_session.add(event)
    _assert_constraint_rejection_and_rollback(db_session)


def test_duplicate_invoice_external_id_is_rejected(
    db_session: Session,
    subscription: Subscription,
) -> None:
    db_session.add_all([_invoice(subscription), _invoice(subscription)])
    _assert_constraint_rejection_and_rollback(db_session)


def test_invoice_amount_total_must_match_components(
    db_session: Session,
    subscription: Subscription,
) -> None:
    invoice = _invoice(subscription)
    invoice.total_amount = Decimal("99.0000")
    db_session.add(invoice)
    _assert_constraint_rejection_and_rollback(db_session)


def test_invoice_rejects_negative_amount(
    db_session: Session,
    subscription: Subscription,
) -> None:
    invoice = _invoice(subscription)
    invoice.tax_amount = Decimal("-1.0000")
    invoice.total_amount = Decimal("99.0000")
    db_session.add(invoice)
    _assert_constraint_rejection_and_rollback(db_session)


def test_invoice_currency_is_usd_only(
    db_session: Session,
    subscription: Subscription,
) -> None:
    invoice = _invoice(subscription)
    invoice.currency_code = "EUR"
    db_session.add(invoice)
    _assert_constraint_rejection_and_rollback(db_session)


def test_invoice_due_time_cannot_precede_issue_time(
    db_session: Session,
    subscription: Subscription,
) -> None:
    invoice = _invoice(subscription)
    invoice.due_at = datetime(2024, 12, 31)
    db_session.add(invoice)
    _assert_constraint_rejection_and_rollback(db_session)


def test_paid_invoice_requires_paid_time(
    db_session: Session,
    subscription: Subscription,
) -> None:
    invoice = _invoice(subscription)
    invoice.status = "paid"
    db_session.add(invoice)
    _assert_constraint_rejection_and_rollback(db_session)


def test_payment_attempt_status_requires_matching_terminal_time(
    db_session: Session,
    invoice: SubscriptionInvoice,
) -> None:
    attempt = _payment_attempt(invoice, status="succeeded")
    db_session.add(attempt)
    _assert_constraint_rejection_and_rollback(db_session)


def test_failed_payment_attempt_requires_failed_time(
    db_session: Session,
    invoice: SubscriptionInvoice,
) -> None:
    attempt = _payment_attempt(invoice, status="failed")
    db_session.add(attempt)
    _assert_constraint_rejection_and_rollback(db_session)


def test_cancelled_payment_attempt_requires_cancelled_time(
    db_session: Session,
    invoice: SubscriptionInvoice,
) -> None:
    attempt = _payment_attempt(invoice, status="cancelled")
    db_session.add(attempt)
    _assert_constraint_rejection_and_rollback(db_session)


def test_pending_payment_attempt_cannot_have_terminal_time(
    db_session: Session,
    invoice: SubscriptionInvoice,
) -> None:
    attempt = _payment_attempt(invoice)
    attempt.failed_at = LATER
    db_session.add(attempt)
    _assert_constraint_rejection_and_rollback(db_session)


def test_payment_attempt_rejects_conflicting_terminal_times(
    db_session: Session,
    invoice: SubscriptionInvoice,
) -> None:
    attempt = _payment_attempt(invoice, status="failed")
    attempt.failed_at = LATER
    attempt.succeeded_at = LATER
    db_session.add(attempt)
    _assert_constraint_rejection_and_rollback(db_session)


def test_payment_attempt_terminal_time_cannot_precede_attempt(
    db_session: Session,
    invoice: SubscriptionInvoice,
) -> None:
    attempt = _payment_attempt(invoice, status="succeeded")
    attempt.succeeded_at = datetime(2024, 12, 31)
    db_session.add(attempt)
    _assert_constraint_rejection_and_rollback(db_session)


def test_payment_attempt_amount_total_must_match_components(
    db_session: Session,
    invoice: SubscriptionInvoice,
) -> None:
    attempt = _payment_attempt(invoice)
    attempt.total_amount = Decimal("109.0000")
    db_session.add(attempt)
    _assert_constraint_rejection_and_rollback(db_session)


def test_duplicate_payment_attempt_external_id_is_rejected(
    db_session: Session,
    invoice: SubscriptionInvoice,
) -> None:
    db_session.add_all([_payment_attempt(invoice), _payment_attempt(invoice)])
    _assert_constraint_rejection_and_rollback(db_session)


def test_payment_attempt_currency_is_usd_only(
    db_session: Session,
    invoice: SubscriptionInvoice,
) -> None:
    attempt = _payment_attempt(invoice)
    attempt.currency_code = "EUR"
    db_session.add(attempt)
    _assert_constraint_rejection_and_rollback(db_session)


def test_valid_payment_attempt_terminal_states_are_accepted(
    db_session: Session,
    invoice: SubscriptionInvoice,
) -> None:
    pending = _payment_attempt(invoice, external_id="attempt-pending")
    succeeded = _payment_attempt(
        invoice,
        external_id="attempt-succeeded",
        status="succeeded",
    )
    succeeded.succeeded_at = LATER
    failed = _payment_attempt(invoice, external_id="attempt-failed", status="failed")
    failed.failed_at = LATER
    failed.failure_code = "card_declined"
    cancelled = _payment_attempt(
        invoice,
        external_id="attempt-cancelled",
        status="cancelled",
    )
    cancelled.cancelled_at = LATER

    db_session.add_all([pending, succeeded, failed, cancelled])
    db_session.flush()


def test_payment_attempt_provider_transaction_id_is_unique_when_present(
    db_session: Session,
    invoice: SubscriptionInvoice,
) -> None:
    first = _payment_attempt(invoice, external_id="attempt-one")
    first.provider_transaction_id = "provider-transaction"
    second = _payment_attempt(invoice, external_id="attempt-two")
    second.provider_transaction_id = "provider-transaction"
    db_session.add_all([first, second])
    _assert_constraint_rejection_and_rollback(db_session)


def _plan() -> SaasPlanVersion:
    return SaasPlanVersion(
        plan_code="test-plan",
        version_number=1,
        plan_name="Test Plan",
        tier_code="test",
        billing_interval="monthly",
        recurring_amount=ONE_HUNDRED,
        currency_code="USD",
        status="active",
        effective_from=START,
        created_at=START,
    )


def _subscription(organization_id: int, plan_id: int) -> Subscription:
    return Subscription(
        external_subscription_id="subscription-test",
        organization_id=organization_id,
        current_plan_version_id=plan_id,
        current_status="active",
        created_at=START,
        first_activated_at=START,
        current_period_started_at=START,
        current_period_ends_at=LATER,
    )


def _state_event(
    subscription: Subscription,
    plan: SaasPlanVersion,
    *,
    source_id: str = "state-event-test",
    effective_at: datetime = START,
    event_type: str = "first_activation",
) -> SubscriptionStateEvent:
    return SubscriptionStateEvent(
        source_event_id=source_id,
        subscription_id=subscription.subscription_id,
        event_type=event_type,
        status_before="pending",
        status_after="active",
        plan_version_before_id=None,
        plan_version_after_id=plan.saas_plan_version_id,
        billing_interval_before=None,
        billing_interval_after="monthly",
        recurring_amount_before=ZERO,
        recurring_amount_after=ONE_HUNDRED,
        normalized_mrr_before=ZERO,
        normalized_mrr_after=ONE_HUNDRED,
        currency_code="USD",
        effective_at=effective_at,
        created_at=effective_at,
    )


def _invoice(subscription: Subscription) -> SubscriptionInvoice:
    return SubscriptionInvoice(
        external_invoice_id="invoice-test",
        subscription_id=subscription.subscription_id,
        status="open",
        subscription_fee_amount=ONE_HUNDRED,
        tax_amount=TEN,
        one_time_amount=ZERO,
        total_amount=Decimal("110.0000"),
        currency_code="USD",
        issued_at=START,
        due_at=LATER,
        created_at=START,
    )


def _payment_attempt(
    invoice: SubscriptionInvoice,
    *,
    external_id: str = "payment-attempt-test",
    status: str = "pending",
) -> InvoicePaymentAttempt:
    return InvoicePaymentAttempt(
        external_payment_attempt_id=external_id,
        subscription_invoice_id=invoice.subscription_invoice_id,
        status=status,
        subscription_fee_amount=ONE_HUNDRED,
        tax_amount=TEN,
        one_time_amount=ZERO,
        total_amount=Decimal("110.0000"),
        currency_code="USD",
        attempted_at=START,
    )


def _assert_constraint_rejection_and_rollback(db_session: Session) -> None:
    with pytest.raises((IntegrityError, OperationalError)) as error_info:
        db_session.flush()
    db_session.rollback()
    if isinstance(error_info.value, OperationalError):
        assert error_info.value.orig is not None
        assert error_info.value.orig.args[0] == 3819
