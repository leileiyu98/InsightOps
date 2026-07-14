"""SaaS SQLAlchemy mappings for M1.1B."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import text

from insightops.db.base import Base
from insightops.db.models.sql_types import (
    ascii_binary_varchar,
    currency_code_type,
    datetime_6,
    money_decimal,
    unsigned_bigint,
    unsigned_smallint,
)

CURRENT_TIMESTAMP_6 = text("CURRENT_TIMESTAMP(6)")
SUBSCRIPTION_STATUSES = (
    "'pending', 'trialing', 'active', 'paused', 'cancel_scheduled', 'cancelled', 'expired'"
)


class SaasPlanVersion(Base):
    """One version of a SaaS plan and its governed price."""

    __tablename__ = "saas_plan_version"
    __table_args__ = (
        UniqueConstraint("plan_code", "version_number", name="uq_saas_plan_ver__code_version"),
        CheckConstraint("version_number > 0", name="ck_saas_plan_ver__version_positive"),
        CheckConstraint(
            "billing_interval IN ('monthly', 'annual')",
            name="ck_saas_plan_ver__billing_interval",
        ),
        CheckConstraint("recurring_amount >= 0", name="ck_saas_plan_ver__amount_nonnegative"),
        CheckConstraint("currency_code = 'USD'", name="ck_saas_plan_ver__currency"),
        CheckConstraint(
            "status IN ('draft', 'active', 'retired')",
            name="ck_saas_plan_ver__status",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_saas_plan_ver__effective_range",
        ),
        CheckConstraint("is_test IN (0, 1)", name="ck_saas_plan_ver__is_test"),
        Index("ix_saas_plan_ver__tier_effective", "tier_code", "effective_from", "effective_to"),
        Index("ix_saas_plan_ver__status", "status"),
    )

    saas_plan_version_id: Mapped[int] = mapped_column(
        unsigned_bigint(), primary_key=True, autoincrement=True
    )
    plan_code: Mapped[str] = mapped_column(ascii_binary_varchar(64), nullable=False)
    version_number: Mapped[int] = mapped_column(unsigned_smallint(), nullable=False)
    plan_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tier_code: Mapped[str] = mapped_column(ascii_binary_varchar(64), nullable=False)
    billing_interval: Mapped[str] = mapped_column(String(32), nullable=False)
    recurring_amount: Mapped[Decimal] = mapped_column(money_decimal(), nullable=False)
    currency_code: Mapped[str] = mapped_column(
        currency_code_type(), nullable=False, server_default=text("'USD'")
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(datetime_6(), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(datetime_6(), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        datetime_6(), nullable=False, server_default=CURRENT_TIMESTAMP_6
    )
    updated_at: Mapped[datetime] = mapped_column(
        datetime_6(),
        nullable=False,
        server_default=CURRENT_TIMESTAMP_6,
        server_onupdate=CURRENT_TIMESTAMP_6,
    )


class Subscription(Base):
    """One organization subscription lifecycle with current convenience fields."""

    __tablename__ = "subscription"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id"],
            ["organization.organization_id"],
            name="fk_subscription__organization",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["current_plan_version_id"],
            ["saas_plan_version.saas_plan_version_id"],
            name="fk_subscription__current_plan",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        UniqueConstraint("external_subscription_id", name="uq_subscription__external_id"),
        CheckConstraint(
            f"current_status IN ({SUBSCRIPTION_STATUSES})",
            name="ck_subscription__status",
        ),
        CheckConstraint(
            "current_period_ends_at IS NULL OR "
            "(current_period_started_at IS NOT NULL "
            "AND current_period_ends_at > current_period_started_at)",
            name="ck_subscription__period_order",
        ),
        CheckConstraint(
            "cancellation_effective_at IS NULL OR "
            "(cancel_scheduled_at IS NOT NULL "
            "AND cancellation_effective_at >= cancel_scheduled_at)",
            name="ck_subscription__cancel_order",
        ),
        CheckConstraint(
            "(first_activated_at IS NULL OR first_activated_at >= created_at) AND "
            "(current_period_started_at IS NULL OR current_period_started_at >= created_at) AND "
            "(current_period_ends_at IS NULL OR current_period_ends_at >= created_at) AND "
            "(cancel_scheduled_at IS NULL OR cancel_scheduled_at >= created_at) AND "
            "(cancellation_effective_at IS NULL OR cancellation_effective_at >= created_at) AND "
            "(expires_at IS NULL OR expires_at >= created_at)",
            name="ck_subscription__lifecycle_times",
        ),
        CheckConstraint("is_test IN (0, 1)", name="ck_subscription__is_test"),
        Index("ix_subscription__org_status", "organization_id", "current_status"),
        Index("ix_subscription__plan_status", "current_plan_version_id", "current_status"),
        Index("ix_subscription__cancel_effective", "cancellation_effective_at"),
    )

    subscription_id: Mapped[int] = mapped_column(
        unsigned_bigint(), primary_key=True, autoincrement=True
    )
    external_subscription_id: Mapped[str] = mapped_column(ascii_binary_varchar(128), nullable=False)
    organization_id: Mapped[int] = mapped_column(unsigned_bigint(), nullable=False)
    current_plan_version_id: Mapped[int | None] = mapped_column(unsigned_bigint(), nullable=True)
    current_status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(datetime_6(), nullable=False)
    first_activated_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    current_period_started_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    current_period_ends_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    cancel_scheduled_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    cancellation_effective_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    recorded_at: Mapped[datetime] = mapped_column(
        datetime_6(), nullable=False, server_default=CURRENT_TIMESTAMP_6
    )
    updated_at: Mapped[datetime] = mapped_column(
        datetime_6(),
        nullable=False,
        server_default=CURRENT_TIMESTAMP_6,
        server_onupdate=CURRENT_TIMESTAMP_6,
    )


class SubscriptionStateEvent(Base):
    """A net subscription state and MRR change at one effective instant."""

    __tablename__ = "subscription_state_event"
    __table_args__ = (
        ForeignKeyConstraint(
            ["subscription_id"],
            ["subscription.subscription_id"],
            name="fk_sub_state_event__subscription",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["plan_version_before_id"],
            ["saas_plan_version.saas_plan_version_id"],
            name="fk_sub_state_event__before_plan",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["plan_version_after_id"],
            ["saas_plan_version.saas_plan_version_id"],
            name="fk_sub_state_event__after_plan",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        UniqueConstraint("source_event_id", name="uq_sub_state_event__source_id"),
        UniqueConstraint(
            "subscription_id", "effective_at", name="uq_sub_state_event__sub_effective"
        ),
        CheckConstraint(
            "event_type IN "
            "('first_activation', 'expansion', 'contraction', 'pause', 'resume', "
            "'cancellation_effective', 'expiration')",
            name="ck_sub_state_event__event_type",
        ),
        CheckConstraint(
            f"(status_before IS NULL OR status_before IN ({SUBSCRIPTION_STATUSES})) AND "
            f"(status_after IS NULL OR status_after IN ({SUBSCRIPTION_STATUSES}))",
            name="ck_sub_state_event__statuses",
        ),
        CheckConstraint(
            "(billing_interval_before IS NULL "
            "OR billing_interval_before IN ('monthly', 'annual')) AND "
            "(billing_interval_after IS NULL "
            "OR billing_interval_after IN ('monthly', 'annual'))",
            name="ck_sub_state_event__billing_intervals",
        ),
        CheckConstraint(
            "recurring_amount_before >= 0 AND recurring_amount_after >= 0 AND "
            "normalized_mrr_before >= 0 AND normalized_mrr_after >= 0",
            name="ck_sub_state_event__amounts_nonnegative",
        ),
        CheckConstraint("currency_code = 'USD'", name="ck_sub_state_event__currency"),
        CheckConstraint(
            "event_type <> 'expansion' OR normalized_mrr_after > normalized_mrr_before",
            name="ck_sub_state_event__expansion_mrr",
        ),
        CheckConstraint(
            "event_type <> 'contraction' OR "
            "(normalized_mrr_after < normalized_mrr_before AND normalized_mrr_after > 0)",
            name="ck_sub_state_event__contraction_mrr",
        ),
        CheckConstraint(
            "event_type NOT IN ('cancellation_effective', 'expiration') "
            "OR normalized_mrr_after = 0",
            name="ck_sub_state_event__terminal_mrr",
        ),
        CheckConstraint("is_test IN (0, 1)", name="ck_sub_state_event__is_test"),
        Index("ix_sub_state_event__type_effective", "event_type", "effective_at"),
        Index("ix_sub_state_event__before_plan", "plan_version_before_id"),
        Index("ix_sub_state_event__after_plan_time", "plan_version_after_id", "effective_at"),
    )

    subscription_state_event_id: Mapped[int] = mapped_column(
        unsigned_bigint(), primary_key=True, autoincrement=True
    )
    source_event_id: Mapped[str] = mapped_column(ascii_binary_varchar(128), nullable=False)
    subscription_id: Mapped[int] = mapped_column(unsigned_bigint(), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status_before: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status_after: Mapped[str | None] = mapped_column(String(32), nullable=True)
    plan_version_before_id: Mapped[int | None] = mapped_column(unsigned_bigint(), nullable=True)
    plan_version_after_id: Mapped[int | None] = mapped_column(unsigned_bigint(), nullable=True)
    billing_interval_before: Mapped[str | None] = mapped_column(String(32), nullable=True)
    billing_interval_after: Mapped[str | None] = mapped_column(String(32), nullable=True)
    recurring_amount_before: Mapped[Decimal] = mapped_column(money_decimal(), nullable=False)
    recurring_amount_after: Mapped[Decimal] = mapped_column(money_decimal(), nullable=False)
    normalized_mrr_before: Mapped[Decimal] = mapped_column(money_decimal(), nullable=False)
    normalized_mrr_after: Mapped[Decimal] = mapped_column(money_decimal(), nullable=False)
    currency_code: Mapped[str] = mapped_column(
        currency_code_type(), nullable=False, server_default=text("'USD'")
    )
    effective_at: Mapped[datetime] = mapped_column(datetime_6(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(datetime_6(), nullable=False)
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    recorded_at: Mapped[datetime] = mapped_column(
        datetime_6(), nullable=False, server_default=CURRENT_TIMESTAMP_6
    )


class SubscriptionInvoice(Base):
    """A subscription invoice whose creation is not itself SaaS revenue."""

    __tablename__ = "subscription_invoice"
    __table_args__ = (
        ForeignKeyConstraint(
            ["subscription_id"],
            ["subscription.subscription_id"],
            name="fk_subscription_invoice__subscription",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        UniqueConstraint("external_invoice_id", name="uq_subscription_invoice__external_id"),
        CheckConstraint(
            "status IN ('draft', 'open', 'paid', 'void', 'uncollectible')",
            name="ck_subscription_invoice__status",
        ),
        CheckConstraint(
            "subscription_fee_amount >= 0 AND tax_amount >= 0 "
            "AND one_time_amount >= 0 AND total_amount >= 0",
            name="ck_subscription_invoice__amounts_nonnegative",
        ),
        CheckConstraint(
            "total_amount = subscription_fee_amount + tax_amount + one_time_amount",
            name="ck_subscription_invoice__amount_total",
        ),
        CheckConstraint("currency_code = 'USD'", name="ck_subscription_invoice__currency"),
        CheckConstraint(
            "due_at IS NULL OR (issued_at IS NOT NULL AND due_at >= issued_at)",
            name="ck_subscription_invoice__due_order",
        ),
        CheckConstraint(
            "(status = 'paid' AND paid_at IS NOT NULL AND voided_at IS NULL) OR "
            "(status = 'void' AND voided_at IS NOT NULL AND paid_at IS NULL) OR "
            "(status NOT IN ('paid', 'void') AND paid_at IS NULL AND voided_at IS NULL)",
            name="ck_subscription_invoice__status_times",
        ),
        CheckConstraint("is_test IN (0, 1)", name="ck_subscription_invoice__is_test"),
        Index("ix_subscription_invoice__sub_issued", "subscription_id", "issued_at"),
        Index("ix_subscription_invoice__status_due", "status", "due_at"),
    )

    subscription_invoice_id: Mapped[int] = mapped_column(
        unsigned_bigint(), primary_key=True, autoincrement=True
    )
    external_invoice_id: Mapped[str] = mapped_column(ascii_binary_varchar(128), nullable=False)
    subscription_id: Mapped[int] = mapped_column(unsigned_bigint(), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    subscription_fee_amount: Mapped[Decimal] = mapped_column(money_decimal(), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(money_decimal(), nullable=False)
    one_time_amount: Mapped[Decimal] = mapped_column(money_decimal(), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(money_decimal(), nullable=False)
    currency_code: Mapped[str] = mapped_column(
        currency_code_type(), nullable=False, server_default=text("'USD'")
    )
    issued_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(datetime_6(), nullable=False)
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    recorded_at: Mapped[datetime] = mapped_column(
        datetime_6(), nullable=False, server_default=CURRENT_TIMESTAMP_6
    )
    updated_at: Mapped[datetime] = mapped_column(
        datetime_6(),
        nullable=False,
        server_default=CURRENT_TIMESTAMP_6,
        server_onupdate=CURRENT_TIMESTAMP_6,
    )


class InvoicePaymentAttempt(Base):
    """One append-only attempt to pay a subscription invoice."""

    __tablename__ = "invoice_payment_attempt"
    __table_args__ = (
        ForeignKeyConstraint(
            ["subscription_invoice_id"],
            ["subscription_invoice.subscription_invoice_id"],
            name="fk_invoice_payment__invoice",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        UniqueConstraint("external_payment_attempt_id", name="uq_invoice_payment__external_id"),
        UniqueConstraint(
            "provider_transaction_id", name="uq_invoice_payment__provider_transaction"
        ),
        CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed', 'cancelled')",
            name="ck_invoice_payment__status",
        ),
        CheckConstraint(
            "subscription_fee_amount >= 0 AND tax_amount >= 0 "
            "AND one_time_amount >= 0 AND total_amount >= 0",
            name="ck_invoice_payment__amounts_nonnegative",
        ),
        CheckConstraint(
            "total_amount = subscription_fee_amount + tax_amount + one_time_amount",
            name="ck_invoice_payment__amount_total",
        ),
        CheckConstraint("currency_code = 'USD'", name="ck_invoice_payment__currency"),
        CheckConstraint(
            "(status = 'pending' AND succeeded_at IS NULL "
            "AND failed_at IS NULL AND cancelled_at IS NULL) OR "
            "(status = 'succeeded' AND succeeded_at IS NOT NULL "
            "AND failed_at IS NULL AND cancelled_at IS NULL) OR "
            "(status = 'failed' AND failed_at IS NOT NULL "
            "AND succeeded_at IS NULL AND cancelled_at IS NULL) OR "
            "(status = 'cancelled' AND cancelled_at IS NOT NULL "
            "AND succeeded_at IS NULL AND failed_at IS NULL)",
            name="ck_invoice_payment__status_times",
        ),
        CheckConstraint(
            "(succeeded_at IS NULL OR succeeded_at >= attempted_at) AND "
            "(failed_at IS NULL OR failed_at >= attempted_at) AND "
            "(cancelled_at IS NULL OR cancelled_at >= attempted_at)",
            name="ck_invoice_payment__terminal_order",
        ),
        CheckConstraint("is_test IN (0, 1)", name="ck_invoice_payment__is_test"),
        Index("ix_invoice_payment__invoice_status", "subscription_invoice_id", "status"),
        Index("ix_invoice_payment__status_success", "status", "succeeded_at"),
    )

    invoice_payment_attempt_id: Mapped[int] = mapped_column(
        unsigned_bigint(), primary_key=True, autoincrement=True
    )
    external_payment_attempt_id: Mapped[str] = mapped_column(
        ascii_binary_varchar(128), nullable=False
    )
    provider_transaction_id: Mapped[str | None] = mapped_column(
        ascii_binary_varchar(128), nullable=True
    )
    subscription_invoice_id: Mapped[int] = mapped_column(unsigned_bigint(), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    subscription_fee_amount: Mapped[Decimal] = mapped_column(money_decimal(), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(money_decimal(), nullable=False)
    one_time_amount: Mapped[Decimal] = mapped_column(money_decimal(), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(money_decimal(), nullable=False)
    currency_code: Mapped[str] = mapped_column(
        currency_code_type(), nullable=False, server_default=text("'USD'")
    )
    attempted_at: Mapped[datetime] = mapped_column(datetime_6(), nullable=False)
    succeeded_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(ascii_binary_varchar(64), nullable=True)
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    recorded_at: Mapped[datetime] = mapped_column(
        datetime_6(), nullable=False, server_default=CURRENT_TIMESTAMP_6
    )
