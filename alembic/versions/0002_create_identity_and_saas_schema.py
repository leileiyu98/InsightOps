"""Create the M1.1B enterprise identity and SaaS schema.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CURRENT_TIMESTAMP_6 = sa.text("CURRENT_TIMESTAMP(6)")
CURRENT_TIMESTAMP_6_ON_UPDATE = sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)")


def upgrade() -> None:
    """Create the nine M1.1B tables in foreign-key dependency order."""
    op.create_table(
        "organization",
        sa.Column(
            "organization_id",
            mysql.BIGINT(unsigned=True),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "external_organization_id",
            mysql.VARCHAR(length=128, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column("organization_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("registered_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("closed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("is_test", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "recorded_at",
            mysql.DATETIME(fsp=6),
            server_default=CURRENT_TIMESTAMP_6,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            server_default=CURRENT_TIMESTAMP_6_ON_UPDATE,
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('registered', 'active', 'suspended', 'closed')",
            name="ck_organization__status",
        ),
        sa.CheckConstraint(
            "closed_at IS NULL OR closed_at >= registered_at",
            name="ck_organization__closed_time",
        ),
        sa.CheckConstraint(
            "status <> 'closed' OR closed_at IS NOT NULL",
            name="ck_organization__closed_status_time",
        ),
        sa.CheckConstraint("is_test IN (0, 1)", name="ck_organization__is_test"),
        sa.PrimaryKeyConstraint("organization_id"),
        sa.UniqueConstraint("external_organization_id", name="uq_organization__external_id"),
    )
    op.create_index(
        "ix_organization__test_registered",
        "organization",
        ["is_test", "registered_at"],
        unique=False,
    )
    op.create_index("ix_organization__status", "organization", ["status"], unique=False)

    op.create_table(
        "consumer",
        sa.Column("consumer_id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column(
            "external_consumer_id",
            mysql.VARCHAR(length=128, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("first_identified_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("closed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("is_test", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "recorded_at",
            mysql.DATETIME(fsp=6),
            server_default=CURRENT_TIMESTAMP_6,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            server_default=CURRENT_TIMESTAMP_6_ON_UPDATE,
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('active', 'blocked', 'closed')",
            name="ck_consumer__status",
        ),
        sa.CheckConstraint(
            "first_identified_at >= created_at AND (closed_at IS NULL OR closed_at >= created_at)",
            name="ck_consumer__time_order",
        ),
        sa.CheckConstraint("is_test IN (0, 1)", name="ck_consumer__is_test"),
        sa.PrimaryKeyConstraint("consumer_id"),
        sa.UniqueConstraint("external_consumer_id", name="uq_consumer__external_id"),
    )
    op.create_index(
        "ix_consumer__test_created",
        "consumer",
        ["is_test", "created_at"],
        unique=False,
    )
    op.create_index("ix_consumer__status", "consumer", ["status"], unique=False)

    op.create_table(
        "saas_plan_version",
        sa.Column(
            "saas_plan_version_id",
            mysql.BIGINT(unsigned=True),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "plan_code",
            mysql.VARCHAR(length=64, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column("version_number", mysql.SMALLINT(unsigned=True), nullable=False),
        sa.Column("plan_name", sa.String(length=255), nullable=False),
        sa.Column(
            "tier_code",
            mysql.VARCHAR(length=64, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column("billing_interval", sa.String(length=32), nullable=False),
        sa.Column("recurring_amount", mysql.DECIMAL(precision=19, scale=4), nullable=False),
        sa.Column(
            "currency_code",
            mysql.CHAR(length=3, charset="ascii", collation="ascii_bin"),
            server_default=sa.text("'USD'"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("effective_from", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("effective_to", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("is_test", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column(
            "recorded_at",
            mysql.DATETIME(fsp=6),
            server_default=CURRENT_TIMESTAMP_6,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            server_default=CURRENT_TIMESTAMP_6_ON_UPDATE,
            nullable=False,
        ),
        sa.CheckConstraint("version_number > 0", name="ck_saas_plan_ver__version_positive"),
        sa.CheckConstraint(
            "billing_interval IN ('monthly', 'annual')",
            name="ck_saas_plan_ver__billing_interval",
        ),
        sa.CheckConstraint("recurring_amount >= 0", name="ck_saas_plan_ver__amount_nonnegative"),
        sa.CheckConstraint("currency_code = 'USD'", name="ck_saas_plan_ver__currency"),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'retired')",
            name="ck_saas_plan_ver__status",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_saas_plan_ver__effective_range",
        ),
        sa.CheckConstraint("is_test IN (0, 1)", name="ck_saas_plan_ver__is_test"),
        sa.PrimaryKeyConstraint("saas_plan_version_id"),
        sa.UniqueConstraint("plan_code", "version_number", name="uq_saas_plan_ver__code_version"),
    )
    op.create_index(
        "ix_saas_plan_ver__tier_effective",
        "saas_plan_version",
        ["tier_code", "effective_from", "effective_to"],
        unique=False,
    )
    op.create_index("ix_saas_plan_ver__status", "saas_plan_version", ["status"], unique=False)

    op.create_table(
        "organization_member",
        sa.Column(
            "organization_member_id",
            mysql.BIGINT(unsigned=True),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "external_membership_id",
            mysql.VARCHAR(length=128, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column("organization_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column(
            "external_account_id",
            mysql.VARCHAR(length=128, charset="ascii", collation="ascii_bin"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("first_invited_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("accepted_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("effective_from", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("effective_to", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("is_test", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "recorded_at",
            mysql.DATETIME(fsp=6),
            server_default=CURRENT_TIMESTAMP_6,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            server_default=CURRENT_TIMESTAMP_6_ON_UPDATE,
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('invited', 'active', 'removed', 'expired')",
            name="ck_org_member__status",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_org_member__effective_range",
        ),
        sa.CheckConstraint(
            "accepted_at IS NULL OR "
            "(first_invited_at IS NOT NULL AND accepted_at >= first_invited_at)",
            name="ck_org_member__invite_order",
        ),
        sa.CheckConstraint("is_test IN (0, 1)", name="ck_org_member__is_test"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.organization_id"],
            name="fk_org_member__organization",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("organization_member_id"),
        sa.UniqueConstraint("external_membership_id", name="uq_org_member__external_id"),
    )
    op.create_index(
        "ix_org_member__org_effective",
        "organization_member",
        ["organization_id", "effective_from", "effective_to"],
        unique=False,
    )
    op.create_index(
        "ix_org_member__org_invited",
        "organization_member",
        ["organization_id", "first_invited_at", "is_test"],
        unique=False,
    )

    op.create_table(
        "merchant",
        sa.Column(
            "merchant_assignment_id",
            mysql.BIGINT(unsigned=True),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("merchant_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column(
            "external_merchant_id",
            mysql.VARCHAR(length=128, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column("organization_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("merchant_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("applied_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("approved_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("activated_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("closed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("assignment_valid_from", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("assignment_valid_to", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("is_test", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "recorded_at",
            mysql.DATETIME(fsp=6),
            server_default=CURRENT_TIMESTAMP_6,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            server_default=CURRENT_TIMESTAMP_6_ON_UPDATE,
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'active', 'suspended', 'closed')",
            name="ck_merchant__status",
        ),
        sa.CheckConstraint(
            "assignment_valid_to IS NULL OR assignment_valid_to > assignment_valid_from",
            name="ck_merchant__assignment_range",
        ),
        sa.CheckConstraint("is_test IN (0, 1)", name="ck_merchant__is_test"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.organization_id"],
            name="fk_merchant__organization",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("merchant_assignment_id"),
        sa.UniqueConstraint(
            "merchant_id", "assignment_valid_from", name="uq_merchant__identity_start"
        ),
        sa.UniqueConstraint(
            "external_merchant_id",
            "assignment_valid_from",
            name="uq_merchant__external_start",
        ),
    )
    op.create_index(
        "ix_merchant__identity_range",
        "merchant",
        ["merchant_id", "assignment_valid_from", "assignment_valid_to"],
        unique=False,
    )
    op.create_index(
        "ix_merchant__org_range",
        "merchant",
        ["organization_id", "assignment_valid_from", "assignment_valid_to"],
        unique=False,
    )

    _create_saas_transaction_tables()


def _create_saas_transaction_tables() -> None:
    """Create the SaaS tables that depend on organization and plan."""
    op.create_table(
        "subscription",
        sa.Column(
            "subscription_id",
            mysql.BIGINT(unsigned=True),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "external_subscription_id",
            mysql.VARCHAR(length=128, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column("organization_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("current_plan_version_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("current_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("first_activated_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("current_period_started_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("current_period_ends_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("cancel_scheduled_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("cancellation_effective_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("is_test", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "recorded_at",
            mysql.DATETIME(fsp=6),
            server_default=CURRENT_TIMESTAMP_6,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            server_default=CURRENT_TIMESTAMP_6_ON_UPDATE,
            nullable=False,
        ),
        sa.CheckConstraint(
            "current_status IN "
            "('pending', 'trialing', 'active', 'paused', "
            "'cancel_scheduled', 'cancelled', 'expired')",
            name="ck_subscription__status",
        ),
        sa.CheckConstraint(
            "current_period_ends_at IS NULL OR "
            "(current_period_started_at IS NOT NULL "
            "AND current_period_ends_at > current_period_started_at)",
            name="ck_subscription__period_order",
        ),
        sa.CheckConstraint(
            "cancellation_effective_at IS NULL OR "
            "(cancel_scheduled_at IS NOT NULL "
            "AND cancellation_effective_at >= cancel_scheduled_at)",
            name="ck_subscription__cancel_order",
        ),
        sa.CheckConstraint(
            "(first_activated_at IS NULL OR first_activated_at >= created_at) AND "
            "(current_period_started_at IS NULL OR current_period_started_at >= created_at) AND "
            "(current_period_ends_at IS NULL OR current_period_ends_at >= created_at) AND "
            "(cancel_scheduled_at IS NULL OR cancel_scheduled_at >= created_at) AND "
            "(cancellation_effective_at IS NULL OR cancellation_effective_at >= created_at) AND "
            "(expires_at IS NULL OR expires_at >= created_at)",
            name="ck_subscription__lifecycle_times",
        ),
        sa.CheckConstraint("is_test IN (0, 1)", name="ck_subscription__is_test"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.organization_id"],
            name="fk_subscription__organization",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["current_plan_version_id"],
            ["saas_plan_version.saas_plan_version_id"],
            name="fk_subscription__current_plan",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("subscription_id"),
        sa.UniqueConstraint("external_subscription_id", name="uq_subscription__external_id"),
    )
    op.create_index(
        "ix_subscription__org_status",
        "subscription",
        ["organization_id", "current_status"],
        unique=False,
    )
    op.create_index(
        "ix_subscription__plan_status",
        "subscription",
        ["current_plan_version_id", "current_status"],
        unique=False,
    )
    op.create_index(
        "ix_subscription__cancel_effective",
        "subscription",
        ["cancellation_effective_at"],
        unique=False,
    )

    _create_subscription_fact_tables()


def _create_subscription_fact_tables() -> None:
    """Create subscription state events, invoices, and payment attempts."""
    op.create_table(
        "subscription_state_event",
        sa.Column(
            "subscription_state_event_id",
            mysql.BIGINT(unsigned=True),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "source_event_id",
            mysql.VARCHAR(length=128, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column("subscription_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("status_before", sa.String(length=32), nullable=True),
        sa.Column("status_after", sa.String(length=32), nullable=True),
        sa.Column("plan_version_before_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("plan_version_after_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("billing_interval_before", sa.String(length=32), nullable=True),
        sa.Column("billing_interval_after", sa.String(length=32), nullable=True),
        sa.Column(
            "recurring_amount_before",
            mysql.DECIMAL(precision=19, scale=4),
            nullable=False,
        ),
        sa.Column(
            "recurring_amount_after",
            mysql.DECIMAL(precision=19, scale=4),
            nullable=False,
        ),
        sa.Column(
            "normalized_mrr_before",
            mysql.DECIMAL(precision=19, scale=4),
            nullable=False,
        ),
        sa.Column(
            "normalized_mrr_after",
            mysql.DECIMAL(precision=19, scale=4),
            nullable=False,
        ),
        sa.Column(
            "currency_code",
            mysql.CHAR(length=3, charset="ascii", collation="ascii_bin"),
            server_default=sa.text("'USD'"),
            nullable=False,
        ),
        sa.Column("effective_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("is_test", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "recorded_at",
            mysql.DATETIME(fsp=6),
            server_default=CURRENT_TIMESTAMP_6,
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type IN "
            "('first_activation', 'expansion', 'contraction', 'pause', 'resume', "
            "'cancellation_effective', 'expiration')",
            name="ck_sub_state_event__event_type",
        ),
        sa.CheckConstraint(
            "(status_before IS NULL OR status_before IN "
            "('pending', 'trialing', 'active', 'paused', "
            "'cancel_scheduled', 'cancelled', 'expired')) AND "
            "(status_after IS NULL OR status_after IN "
            "('pending', 'trialing', 'active', 'paused', "
            "'cancel_scheduled', 'cancelled', 'expired'))",
            name="ck_sub_state_event__statuses",
        ),
        sa.CheckConstraint(
            "(billing_interval_before IS NULL "
            "OR billing_interval_before IN ('monthly', 'annual')) AND "
            "(billing_interval_after IS NULL "
            "OR billing_interval_after IN ('monthly', 'annual'))",
            name="ck_sub_state_event__billing_intervals",
        ),
        sa.CheckConstraint(
            "recurring_amount_before >= 0 AND recurring_amount_after >= 0 AND "
            "normalized_mrr_before >= 0 AND normalized_mrr_after >= 0",
            name="ck_sub_state_event__amounts_nonnegative",
        ),
        sa.CheckConstraint("currency_code = 'USD'", name="ck_sub_state_event__currency"),
        sa.CheckConstraint(
            "event_type <> 'expansion' OR normalized_mrr_after > normalized_mrr_before",
            name="ck_sub_state_event__expansion_mrr",
        ),
        sa.CheckConstraint(
            "event_type <> 'contraction' OR "
            "(normalized_mrr_after < normalized_mrr_before AND normalized_mrr_after > 0)",
            name="ck_sub_state_event__contraction_mrr",
        ),
        sa.CheckConstraint(
            "event_type NOT IN ('cancellation_effective', 'expiration') "
            "OR normalized_mrr_after = 0",
            name="ck_sub_state_event__terminal_mrr",
        ),
        sa.CheckConstraint("is_test IN (0, 1)", name="ck_sub_state_event__is_test"),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["subscription.subscription_id"],
            name="fk_sub_state_event__subscription",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_version_before_id"],
            ["saas_plan_version.saas_plan_version_id"],
            name="fk_sub_state_event__before_plan",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_version_after_id"],
            ["saas_plan_version.saas_plan_version_id"],
            name="fk_sub_state_event__after_plan",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("subscription_state_event_id"),
        sa.UniqueConstraint("source_event_id", name="uq_sub_state_event__source_id"),
        sa.UniqueConstraint(
            "subscription_id", "effective_at", name="uq_sub_state_event__sub_effective"
        ),
    )
    op.create_index(
        "ix_sub_state_event__type_effective",
        "subscription_state_event",
        ["event_type", "effective_at"],
        unique=False,
    )
    op.create_index(
        "ix_sub_state_event__before_plan",
        "subscription_state_event",
        ["plan_version_before_id"],
        unique=False,
    )
    op.create_index(
        "ix_sub_state_event__after_plan_time",
        "subscription_state_event",
        ["plan_version_after_id", "effective_at"],
        unique=False,
    )

    _create_invoice_tables()


def _create_invoice_tables() -> None:
    """Create invoices and their append-only payment attempts."""
    op.create_table(
        "subscription_invoice",
        sa.Column(
            "subscription_invoice_id",
            mysql.BIGINT(unsigned=True),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "external_invoice_id",
            mysql.VARCHAR(length=128, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column("subscription_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "subscription_fee_amount",
            mysql.DECIMAL(precision=19, scale=4),
            nullable=False,
        ),
        sa.Column("tax_amount", mysql.DECIMAL(precision=19, scale=4), nullable=False),
        sa.Column("one_time_amount", mysql.DECIMAL(precision=19, scale=4), nullable=False),
        sa.Column("total_amount", mysql.DECIMAL(precision=19, scale=4), nullable=False),
        sa.Column(
            "currency_code",
            mysql.CHAR(length=3, charset="ascii", collation="ascii_bin"),
            server_default=sa.text("'USD'"),
            nullable=False,
        ),
        sa.Column("issued_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("due_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("voided_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("paid_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("is_test", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "recorded_at",
            mysql.DATETIME(fsp=6),
            server_default=CURRENT_TIMESTAMP_6,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            server_default=CURRENT_TIMESTAMP_6_ON_UPDATE,
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'open', 'paid', 'void', 'uncollectible')",
            name="ck_subscription_invoice__status",
        ),
        sa.CheckConstraint(
            "subscription_fee_amount >= 0 AND tax_amount >= 0 "
            "AND one_time_amount >= 0 AND total_amount >= 0",
            name="ck_subscription_invoice__amounts_nonnegative",
        ),
        sa.CheckConstraint(
            "total_amount = subscription_fee_amount + tax_amount + one_time_amount",
            name="ck_subscription_invoice__amount_total",
        ),
        sa.CheckConstraint("currency_code = 'USD'", name="ck_subscription_invoice__currency"),
        sa.CheckConstraint(
            "due_at IS NULL OR (issued_at IS NOT NULL AND due_at >= issued_at)",
            name="ck_subscription_invoice__due_order",
        ),
        sa.CheckConstraint(
            "(status = 'paid' AND paid_at IS NOT NULL AND voided_at IS NULL) OR "
            "(status = 'void' AND voided_at IS NOT NULL AND paid_at IS NULL) OR "
            "(status NOT IN ('paid', 'void') AND paid_at IS NULL AND voided_at IS NULL)",
            name="ck_subscription_invoice__status_times",
        ),
        sa.CheckConstraint("is_test IN (0, 1)", name="ck_subscription_invoice__is_test"),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["subscription.subscription_id"],
            name="fk_subscription_invoice__subscription",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("subscription_invoice_id"),
        sa.UniqueConstraint("external_invoice_id", name="uq_subscription_invoice__external_id"),
    )
    op.create_index(
        "ix_subscription_invoice__sub_issued",
        "subscription_invoice",
        ["subscription_id", "issued_at"],
        unique=False,
    )
    op.create_index(
        "ix_subscription_invoice__status_due",
        "subscription_invoice",
        ["status", "due_at"],
        unique=False,
    )

    op.create_table(
        "invoice_payment_attempt",
        sa.Column(
            "invoice_payment_attempt_id",
            mysql.BIGINT(unsigned=True),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "external_payment_attempt_id",
            mysql.VARCHAR(length=128, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column(
            "provider_transaction_id",
            mysql.VARCHAR(length=128, charset="ascii", collation="ascii_bin"),
            nullable=True,
        ),
        sa.Column("subscription_invoice_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "subscription_fee_amount",
            mysql.DECIMAL(precision=19, scale=4),
            nullable=False,
        ),
        sa.Column("tax_amount", mysql.DECIMAL(precision=19, scale=4), nullable=False),
        sa.Column("one_time_amount", mysql.DECIMAL(precision=19, scale=4), nullable=False),
        sa.Column("total_amount", mysql.DECIMAL(precision=19, scale=4), nullable=False),
        sa.Column(
            "currency_code",
            mysql.CHAR(length=3, charset="ascii", collation="ascii_bin"),
            server_default=sa.text("'USD'"),
            nullable=False,
        ),
        sa.Column("attempted_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("succeeded_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("failed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("cancelled_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column(
            "failure_code",
            mysql.VARCHAR(length=64, charset="ascii", collation="ascii_bin"),
            nullable=True,
        ),
        sa.Column("is_test", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "recorded_at",
            mysql.DATETIME(fsp=6),
            server_default=CURRENT_TIMESTAMP_6,
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed', 'cancelled')",
            name="ck_invoice_payment__status",
        ),
        sa.CheckConstraint(
            "subscription_fee_amount >= 0 AND tax_amount >= 0 "
            "AND one_time_amount >= 0 AND total_amount >= 0",
            name="ck_invoice_payment__amounts_nonnegative",
        ),
        sa.CheckConstraint(
            "total_amount = subscription_fee_amount + tax_amount + one_time_amount",
            name="ck_invoice_payment__amount_total",
        ),
        sa.CheckConstraint("currency_code = 'USD'", name="ck_invoice_payment__currency"),
        sa.CheckConstraint(
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
        sa.CheckConstraint(
            "(succeeded_at IS NULL OR succeeded_at >= attempted_at) AND "
            "(failed_at IS NULL OR failed_at >= attempted_at) AND "
            "(cancelled_at IS NULL OR cancelled_at >= attempted_at)",
            name="ck_invoice_payment__terminal_order",
        ),
        sa.CheckConstraint("is_test IN (0, 1)", name="ck_invoice_payment__is_test"),
        sa.ForeignKeyConstraint(
            ["subscription_invoice_id"],
            ["subscription_invoice.subscription_invoice_id"],
            name="fk_invoice_payment__invoice",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("invoice_payment_attempt_id"),
        sa.UniqueConstraint("external_payment_attempt_id", name="uq_invoice_payment__external_id"),
        sa.UniqueConstraint(
            "provider_transaction_id", name="uq_invoice_payment__provider_transaction"
        ),
    )
    op.create_index(
        "ix_invoice_payment__invoice_status",
        "invoice_payment_attempt",
        ["subscription_invoice_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_invoice_payment__status_success",
        "invoice_payment_attempt",
        ["status", "succeeded_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the M1.1B tables in reverse foreign-key dependency order."""
    op.drop_table("invoice_payment_attempt")
    op.drop_table("subscription_invoice")
    op.drop_table("subscription_state_event")
    op.drop_table("subscription")
    op.drop_table("saas_plan_version")
    op.drop_table("merchant")
    op.drop_table("organization_member")
    op.drop_table("consumer")
    op.drop_table("organization")
