"""Create the M1.1D marketing schema.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CURRENT_TIMESTAMP_6 = sa.text("CURRENT_TIMESTAMP(6)")
CURRENT_TIMESTAMP_6_ON_UPDATE = sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)")


def upgrade() -> None:
    """Create the five M1.1D tables in foreign-key dependency order."""
    _create_marketing_channel_table()
    _create_marketing_campaign_table()
    _create_campaign_daily_spend_table()
    _create_marketing_touch_table()
    _create_attributed_conversion_table()


def _create_marketing_channel_table() -> None:
    """Create governed marketing channel definitions."""
    op.create_table(
        "marketing_channel",
        sa.Column(
            "marketing_channel_id",
            mysql.BIGINT(unsigned=True),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "channel_code",
            mysql.VARCHAR(length=64, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column("channel_name", sa.String(length=255), nullable=False),
        sa.Column("channel_type", sa.String(length=32), nullable=False),
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
        sa.CheckConstraint("channel_code <> ''", name="ck_marketing_channel__code_nonempty"),
        sa.CheckConstraint(
            "channel_type IN ('paid', 'organic', 'referral', 'direct')",
            name="ck_marketing_channel__type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'inactive')",
            name="ck_marketing_channel__status",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_marketing_channel__effective_range",
        ),
        sa.CheckConstraint(
            "(channel_type = 'direct' AND channel_code = 'direct') OR "
            "(channel_type <> 'direct' AND channel_code <> 'direct')",
            name="ck_marketing_channel__direct_code",
        ),
        sa.CheckConstraint("is_test IN (0, 1)", name="ck_marketing_channel__is_test"),
        sa.PrimaryKeyConstraint("marketing_channel_id"),
        sa.UniqueConstraint("channel_code", name="uq_marketing_channel__code"),
    )
    op.create_index(
        "ix_marketing_channel__type_status",
        "marketing_channel",
        ["channel_type", "status"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_channel__effective",
        "marketing_channel",
        ["effective_from", "effective_to"],
        unique=False,
    )


def _create_marketing_campaign_table() -> None:
    """Create scoped marketing campaign entities."""
    op.create_table(
        "marketing_campaign",
        sa.Column(
            "marketing_campaign_id",
            mysql.BIGINT(unsigned=True),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "external_campaign_id",
            mysql.VARCHAR(length=128, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column("organization_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("merchant_assignment_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("primary_channel_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column(
            "business_scope",
            mysql.VARCHAR(length=32, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column("campaign_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("started_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("ended_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("status_updated_at", mysql.DATETIME(fsp=6), nullable=False),
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
            "business_scope IN ('saas', 'commerce')",
            name="ck_marketing_campaign__business_scope",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'paused', 'completed', 'cancelled')",
            name="ck_marketing_campaign__status",
        ),
        sa.CheckConstraint(
            "(started_at IS NULL OR started_at >= created_at) AND "
            "(ended_at IS NULL OR (started_at IS NOT NULL AND ended_at >= started_at)) AND "
            "status_updated_at >= created_at",
            name="ck_marketing_campaign__lifecycle_times",
        ),
        sa.CheckConstraint(
            "business_scope = 'commerce' OR merchant_assignment_id IS NULL",
            name="ck_marketing_campaign__saas_no_merchant",
        ),
        sa.CheckConstraint("is_test IN (0, 1)", name="ck_marketing_campaign__is_test"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.organization_id"],
            name="fk_marketing_campaign__organization",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["merchant_assignment_id"],
            ["merchant.merchant_assignment_id"],
            name="fk_marketing_campaign__merchant_assignment",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["primary_channel_id"],
            ["marketing_channel.marketing_channel_id"],
            name="fk_marketing_campaign__primary_channel",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("marketing_campaign_id"),
        sa.UniqueConstraint(
            "external_campaign_id",
            name="uq_marketing_campaign__external_id",
        ),
    )
    op.create_index(
        "ix_marketing_campaign__channel_created",
        "marketing_campaign",
        ["primary_channel_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_campaign__org_created",
        "marketing_campaign",
        ["organization_id", "created_at", "is_test"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_campaign__merchant_created",
        "marketing_campaign",
        ["merchant_assignment_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_campaign__scope_status",
        "marketing_campaign",
        ["business_scope", "status"],
        unique=False,
    )


def _create_campaign_daily_spend_table() -> None:
    """Create immutable final daily-spend revisions."""
    op.create_table(
        "campaign_daily_spend",
        sa.Column(
            "campaign_daily_spend_id",
            mysql.BIGINT(unsigned=True),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("marketing_campaign_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("version_number", mysql.SMALLINT(unsigned=True), nullable=False),
        sa.Column(
            "supersedes_campaign_daily_spend_id",
            mysql.BIGINT(unsigned=True),
            nullable=True,
        ),
        sa.Column("spend_amount", mysql.DECIMAL(precision=19, scale=4), nullable=False),
        sa.Column(
            "currency_code",
            mysql.CHAR(length=3, charset="ascii", collation="ascii_bin"),
            server_default=sa.text("'USD'"),
            nullable=False,
        ),
        sa.Column("finalized_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("is_test", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "recorded_at",
            mysql.DATETIME(fsp=6),
            server_default=CURRENT_TIMESTAMP_6,
            nullable=False,
        ),
        sa.CheckConstraint(
            "version_number > 0",
            name="ck_campaign_spend__version_positive",
        ),
        sa.CheckConstraint(
            "(version_number = 1 AND supersedes_campaign_daily_spend_id IS NULL) OR "
            "(version_number > 1 AND supersedes_campaign_daily_spend_id IS NOT NULL)",
            name="ck_campaign_spend__version_lineage",
        ),
        sa.CheckConstraint(
            "spend_amount >= 0",
            name="ck_campaign_spend__amount_nonnegative",
        ),
        sa.CheckConstraint("currency_code = 'USD'", name="ck_campaign_spend__currency"),
        sa.CheckConstraint(
            "recorded_at >= finalized_at",
            name="ck_campaign_spend__visibility_time",
        ),
        sa.CheckConstraint("is_test IN (0, 1)", name="ck_campaign_spend__is_test"),
        sa.ForeignKeyConstraint(
            ["marketing_campaign_id"],
            ["marketing_campaign.marketing_campaign_id"],
            name="fk_campaign_spend__campaign",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_campaign_daily_spend_id"],
            ["campaign_daily_spend.campaign_daily_spend_id"],
            name="fk_campaign_spend__supersedes",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("campaign_daily_spend_id"),
        sa.UniqueConstraint(
            "marketing_campaign_id",
            "business_date",
            "version_number",
            name="uq_campaign_spend__campaign_date_version",
        ),
        sa.UniqueConstraint(
            "supersedes_campaign_daily_spend_id",
            name="uq_campaign_spend__supersedes",
        ),
    )
    op.create_index(
        "ix_campaign_spend__date_recorded",
        "campaign_daily_spend",
        ["business_date", "recorded_at", "is_test"],
        unique=False,
    )


def _create_marketing_touch_table() -> None:
    """Create append-only marketing touch facts."""
    op.create_table(
        "marketing_touch",
        sa.Column(
            "marketing_touch_id",
            mysql.BIGINT(unsigned=True),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "source_event_id",
            mysql.VARCHAR(length=128, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column("marketing_channel_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("marketing_campaign_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("organization_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("consumer_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("touch_type", sa.String(length=32), nullable=False),
        sa.Column("quality_status", sa.String(length=32), nullable=False),
        sa.Column("occurred_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("received_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("processed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("is_test", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "recorded_at",
            mysql.DATETIME(fsp=6),
            server_default=CURRENT_TIMESTAMP_6,
            nullable=False,
        ),
        sa.CheckConstraint(
            "(organization_id IS NOT NULL AND consumer_id IS NULL) OR "
            "(organization_id IS NULL AND consumer_id IS NOT NULL)",
            name="ck_marketing_touch__subject_xor",
        ),
        sa.CheckConstraint(
            "touch_type IN ('non_direct', 'direct')",
            name="ck_marketing_touch__type",
        ),
        sa.CheckConstraint(
            "quality_status IN ('accepted', 'rejected')",
            name="ck_marketing_touch__quality",
        ),
        sa.CheckConstraint(
            "received_at >= occurred_at AND "
            "(processed_at IS NULL OR processed_at >= received_at) AND "
            "recorded_at >= received_at AND "
            "(processed_at IS NULL OR recorded_at >= processed_at)",
            name="ck_marketing_touch__visibility_times",
        ),
        sa.CheckConstraint("is_test IN (0, 1)", name="ck_marketing_touch__is_test"),
        sa.ForeignKeyConstraint(
            ["marketing_channel_id"],
            ["marketing_channel.marketing_channel_id"],
            name="fk_marketing_touch__channel",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["marketing_campaign_id"],
            ["marketing_campaign.marketing_campaign_id"],
            name="fk_marketing_touch__campaign",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.organization_id"],
            name="fk_marketing_touch__organization",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["consumer_id"],
            ["consumer.consumer_id"],
            name="fk_marketing_touch__consumer",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("marketing_touch_id"),
        sa.UniqueConstraint("source_event_id", name="uq_marketing_touch__source_id"),
    )
    op.create_index(
        "ix_marketing_touch__org_time",
        "marketing_touch",
        ["organization_id", "occurred_at", "source_event_id"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_touch__consumer_time",
        "marketing_touch",
        ["consumer_id", "occurred_at", "source_event_id"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_touch__channel_time",
        "marketing_touch",
        ["marketing_channel_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_touch__campaign_time",
        "marketing_touch",
        ["marketing_campaign_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_marketing_touch__visibility",
        "marketing_touch",
        ["recorded_at", "quality_status"],
        unique=False,
    )


def _create_attributed_conversion_table() -> None:
    """Create versioned final attribution results."""
    op.create_table(
        "attributed_conversion",
        sa.Column(
            "attributed_conversion_id",
            mysql.BIGINT(unsigned=True),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("conversion_type", sa.String(length=32), nullable=False),
        sa.Column("organization_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("consumer_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("invoice_payment_attempt_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("commerce_order_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("platform_fee_charge_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("selected_marketing_touch_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("marketing_channel_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("marketing_campaign_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("attribution_result", sa.String(length=32), nullable=False),
        sa.Column(
            "reason_code",
            mysql.VARCHAR(length=64, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column(
            "model_version",
            mysql.VARCHAR(length=64, charset="ascii", collation="ascii_bin"),
            server_default=sa.text("'last_non_direct_168h_v1'"),
            nullable=False,
        ),
        sa.Column("conversion_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("window_started_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("history_complete", sa.Boolean(), nullable=False),
        sa.Column("source_data_cutoff_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("attributed_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("is_test", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "recorded_at",
            mysql.DATETIME(fsp=6),
            server_default=CURRENT_TIMESTAMP_6,
            nullable=False,
        ),
        sa.CheckConstraint(
            "conversion_type IN "
            "('saas_first_payment', 'saas_revenue', 'commerce_first_payment', "
            "'commerce_revenue', 'attributed_gmv')",
            name="ck_attr_conversion__type",
        ),
        sa.CheckConstraint(
            "(invoice_payment_attempt_id IS NOT NULL AND commerce_order_id IS NULL "
            "AND platform_fee_charge_id IS NULL) OR "
            "(invoice_payment_attempt_id IS NULL AND commerce_order_id IS NOT NULL "
            "AND platform_fee_charge_id IS NULL) OR "
            "(invoice_payment_attempt_id IS NULL AND commerce_order_id IS NULL "
            "AND platform_fee_charge_id IS NOT NULL)",
            name="ck_attr_conversion__fact_xor",
        ),
        sa.CheckConstraint(
            "(organization_id IS NOT NULL AND consumer_id IS NULL) OR "
            "(organization_id IS NULL AND consumer_id IS NOT NULL)",
            name="ck_attr_conversion__subject_xor",
        ),
        sa.CheckConstraint(
            "(conversion_type IN ('saas_first_payment', 'saas_revenue') "
            "AND invoice_payment_attempt_id IS NOT NULL "
            "AND organization_id IS NOT NULL AND consumer_id IS NULL) OR "
            "(conversion_type IN ('commerce_first_payment', 'attributed_gmv') "
            "AND commerce_order_id IS NOT NULL "
            "AND consumer_id IS NOT NULL AND organization_id IS NULL) OR "
            "(conversion_type = 'commerce_revenue' "
            "AND platform_fee_charge_id IS NOT NULL "
            "AND consumer_id IS NOT NULL AND organization_id IS NULL)",
            name="ck_attr_conversion__type_fact_subject",
        ),
        sa.CheckConstraint(
            "(attribution_result = 'non_direct' "
            "AND selected_marketing_touch_id IS NOT NULL "
            "AND marketing_channel_id IS NOT NULL) OR "
            "(attribution_result = 'direct' "
            "AND selected_marketing_touch_id IS NULL "
            "AND marketing_channel_id IS NOT NULL "
            "AND marketing_campaign_id IS NULL) OR "
            "(attribution_result = 'unknown_unattributed' "
            "AND selected_marketing_touch_id IS NULL "
            "AND marketing_channel_id IS NULL "
            "AND marketing_campaign_id IS NULL)",
            name="ck_attr_conversion__result_links",
        ),
        sa.CheckConstraint(
            "(attribution_result = 'non_direct' "
            "AND reason_code = 'selected_last_non_direct') OR "
            "(attribution_result = 'direct' "
            "AND reason_code = 'no_eligible_non_direct_touch') OR "
            "(attribution_result = 'unknown_unattributed' "
            "AND reason_code IN "
            "('window_history_incomplete', 'identity_unresolved', "
            "'touch_time_missing', 'channel_unmapped'))",
            name="ck_attr_conversion__result_reason",
        ),
        sa.CheckConstraint(
            "(reason_code = 'window_history_incomplete' "
            "AND history_complete = 0) OR "
            "(reason_code <> 'window_history_incomplete' "
            "AND history_complete = 1)",
            name="ck_attr_conversion__history_reason",
        ),
        sa.CheckConstraint(
            "model_version = 'last_non_direct_168h_v1'",
            name="ck_attr_conversion__model_version",
        ),
        sa.CheckConstraint(
            "window_started_at = conversion_at - INTERVAL 168 HOUR",
            name="ck_attr_conversion__window",
        ),
        sa.CheckConstraint(
            "conversion_at <= source_data_cutoff_at AND "
            "source_data_cutoff_at <= attributed_at AND "
            "attributed_at <= recorded_at",
            name="ck_attr_conversion__visibility_times",
        ),
        sa.CheckConstraint("is_test IN (0, 1)", name="ck_attr_conversion__is_test"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.organization_id"],
            name="fk_attr_conversion__organization",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["consumer_id"],
            ["consumer.consumer_id"],
            name="fk_attr_conversion__consumer",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["invoice_payment_attempt_id"],
            ["invoice_payment_attempt.invoice_payment_attempt_id"],
            name="fk_attr_conversion__payment_attempt",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["commerce_order_id"],
            ["commerce_order.commerce_order_id"],
            name="fk_attr_conversion__order",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["platform_fee_charge_id"],
            ["platform_fee_charge.platform_fee_charge_id"],
            name="fk_attr_conversion__fee_charge",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["selected_marketing_touch_id"],
            ["marketing_touch.marketing_touch_id"],
            name="fk_attr_conversion__selected_touch",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["marketing_channel_id"],
            ["marketing_channel.marketing_channel_id"],
            name="fk_attr_conversion__channel",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["marketing_campaign_id"],
            ["marketing_campaign.marketing_campaign_id"],
            name="fk_attr_conversion__campaign",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("attributed_conversion_id"),
        sa.UniqueConstraint(
            "conversion_type",
            "invoice_payment_attempt_id",
            "model_version",
            "source_data_cutoff_at",
            name="uq_attr_conversion__payment_model_cutoff",
        ),
        sa.UniqueConstraint(
            "conversion_type",
            "commerce_order_id",
            "model_version",
            "source_data_cutoff_at",
            name="uq_attr_conversion__order_model_cutoff",
        ),
        sa.UniqueConstraint(
            "conversion_type",
            "platform_fee_charge_id",
            "model_version",
            "source_data_cutoff_at",
            name="uq_attr_conversion__fee_model_cutoff",
        ),
    )
    indexes = {
        "ix_attr_conversion__type_time": ["conversion_type", "conversion_at"],
        "ix_attr_conversion__channel_time": ["marketing_channel_id", "conversion_at"],
        "ix_attr_conversion__result_time": ["attribution_result", "conversion_at"],
        "ix_attr_conversion__org_type_time": [
            "organization_id",
            "conversion_type",
            "conversion_at",
        ],
        "ix_attr_conversion__consumer_type_time": [
            "consumer_id",
            "conversion_type",
            "conversion_at",
        ],
        "ix_attr_conversion__payment": ["invoice_payment_attempt_id"],
        "ix_attr_conversion__order": ["commerce_order_id"],
        "ix_attr_conversion__fee": ["platform_fee_charge_id"],
        "ix_attr_conversion__selected_touch": ["selected_marketing_touch_id"],
        "ix_attr_conversion__campaign": ["marketing_campaign_id"],
        "ix_attr_conversion__source_cutoff": ["source_data_cutoff_at", "recorded_at"],
    }
    for index_name, columns in indexes.items():
        op.create_index(index_name, "attributed_conversion", columns, unique=False)


def downgrade() -> None:
    """Drop M1.1D tables in reverse foreign-key dependency order."""
    op.drop_table("attributed_conversion")
    op.drop_table("marketing_touch")
    op.drop_table("campaign_daily_spend")
    op.drop_table("marketing_campaign")
    op.drop_table("marketing_channel")
