"""Marketing SQLAlchemy mappings for M1.1D."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
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


class MarketingChannel(Base):
    """One governed marketing channel definition."""

    __tablename__ = "marketing_channel"
    __table_args__ = (
        UniqueConstraint("channel_code", name="uq_marketing_channel__code"),
        CheckConstraint("channel_code <> ''", name="ck_marketing_channel__code_nonempty"),
        CheckConstraint(
            "channel_type IN ('paid', 'organic', 'referral', 'direct')",
            name="ck_marketing_channel__type",
        ),
        CheckConstraint(
            "status IN ('active', 'inactive')",
            name="ck_marketing_channel__status",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_marketing_channel__effective_range",
        ),
        CheckConstraint(
            "(channel_type = 'direct' AND channel_code = 'direct') OR "
            "(channel_type <> 'direct' AND channel_code <> 'direct')",
            name="ck_marketing_channel__direct_code",
        ),
        CheckConstraint("is_test IN (0, 1)", name="ck_marketing_channel__is_test"),
        Index("ix_marketing_channel__type_status", "channel_type", "status"),
        Index("ix_marketing_channel__effective", "effective_from", "effective_to"),
    )

    marketing_channel_id: Mapped[int] = mapped_column(
        unsigned_bigint(), primary_key=True, autoincrement=True
    )
    channel_code: Mapped[str] = mapped_column(ascii_binary_varchar(64), nullable=False)
    channel_name: Mapped[str] = mapped_column(String(255), nullable=False)
    channel_type: Mapped[str] = mapped_column(String(32), nullable=False)
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


class MarketingCampaign(Base):
    """One marketing campaign with a single SaaS or commerce scope."""

    __tablename__ = "marketing_campaign"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id"],
            ["organization.organization_id"],
            name="fk_marketing_campaign__organization",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["merchant_assignment_id"],
            ["merchant.merchant_assignment_id"],
            name="fk_marketing_campaign__merchant_assignment",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["primary_channel_id"],
            ["marketing_channel.marketing_channel_id"],
            name="fk_marketing_campaign__primary_channel",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        UniqueConstraint(
            "external_campaign_id",
            name="uq_marketing_campaign__external_id",
        ),
        CheckConstraint(
            "business_scope IN ('saas', 'commerce')",
            name="ck_marketing_campaign__business_scope",
        ),
        CheckConstraint(
            "status IN ('draft', 'active', 'paused', 'completed', 'cancelled')",
            name="ck_marketing_campaign__status",
        ),
        CheckConstraint(
            "(started_at IS NULL OR started_at >= created_at) AND "
            "(ended_at IS NULL OR (started_at IS NOT NULL AND ended_at >= started_at)) AND "
            "status_updated_at >= created_at",
            name="ck_marketing_campaign__lifecycle_times",
        ),
        CheckConstraint(
            "business_scope = 'commerce' OR merchant_assignment_id IS NULL",
            name="ck_marketing_campaign__saas_no_merchant",
        ),
        CheckConstraint("is_test IN (0, 1)", name="ck_marketing_campaign__is_test"),
        Index(
            "ix_marketing_campaign__channel_created",
            "primary_channel_id",
            "created_at",
        ),
        Index(
            "ix_marketing_campaign__org_created",
            "organization_id",
            "created_at",
            "is_test",
        ),
        Index(
            "ix_marketing_campaign__merchant_created",
            "merchant_assignment_id",
            "created_at",
        ),
        Index("ix_marketing_campaign__scope_status", "business_scope", "status"),
    )

    marketing_campaign_id: Mapped[int] = mapped_column(
        unsigned_bigint(), primary_key=True, autoincrement=True
    )
    external_campaign_id: Mapped[str] = mapped_column(ascii_binary_varchar(128), nullable=False)
    organization_id: Mapped[int] = mapped_column(unsigned_bigint(), nullable=False)
    merchant_assignment_id: Mapped[int | None] = mapped_column(unsigned_bigint(), nullable=True)
    primary_channel_id: Mapped[int] = mapped_column(unsigned_bigint(), nullable=False)
    business_scope: Mapped[str] = mapped_column(ascii_binary_varchar(32), nullable=False)
    campaign_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(datetime_6(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    status_updated_at: Mapped[datetime] = mapped_column(datetime_6(), nullable=False)
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


class CampaignDailySpend(Base):
    """One immutable final revision of a campaign's daily actual spend."""

    __tablename__ = "campaign_daily_spend"
    __table_args__ = (
        ForeignKeyConstraint(
            ["marketing_campaign_id"],
            ["marketing_campaign.marketing_campaign_id"],
            name="fk_campaign_spend__campaign",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["supersedes_campaign_daily_spend_id"],
            ["campaign_daily_spend.campaign_daily_spend_id"],
            name="fk_campaign_spend__supersedes",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        UniqueConstraint(
            "marketing_campaign_id",
            "business_date",
            "version_number",
            name="uq_campaign_spend__campaign_date_version",
        ),
        UniqueConstraint(
            "supersedes_campaign_daily_spend_id",
            name="uq_campaign_spend__supersedes",
        ),
        CheckConstraint("version_number > 0", name="ck_campaign_spend__version_positive"),
        CheckConstraint(
            "(version_number = 1 AND supersedes_campaign_daily_spend_id IS NULL) OR "
            "(version_number > 1 AND supersedes_campaign_daily_spend_id IS NOT NULL)",
            name="ck_campaign_spend__version_lineage",
        ),
        CheckConstraint("spend_amount >= 0", name="ck_campaign_spend__amount_nonnegative"),
        CheckConstraint("currency_code = 'USD'", name="ck_campaign_spend__currency"),
        CheckConstraint(
            "recorded_at >= finalized_at",
            name="ck_campaign_spend__visibility_time",
        ),
        CheckConstraint("is_test IN (0, 1)", name="ck_campaign_spend__is_test"),
        Index(
            "ix_campaign_spend__date_recorded",
            "business_date",
            "recorded_at",
            "is_test",
        ),
    )

    campaign_daily_spend_id: Mapped[int] = mapped_column(
        unsigned_bigint(), primary_key=True, autoincrement=True
    )
    marketing_campaign_id: Mapped[int] = mapped_column(unsigned_bigint(), nullable=False)
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    version_number: Mapped[int] = mapped_column(unsigned_smallint(), nullable=False)
    supersedes_campaign_daily_spend_id: Mapped[int | None] = mapped_column(
        unsigned_bigint(), nullable=True
    )
    spend_amount: Mapped[Decimal] = mapped_column(money_decimal(), nullable=False)
    currency_code: Mapped[str] = mapped_column(
        currency_code_type(), nullable=False, server_default=text("'USD'")
    )
    finalized_at: Mapped[datetime] = mapped_column(datetime_6(), nullable=False)
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    recorded_at: Mapped[datetime] = mapped_column(
        datetime_6(), nullable=False, server_default=CURRENT_TIMESTAMP_6
    )


class MarketingTouch(Base):
    """One append-only marketing touch resolved to exactly one business subject."""

    __tablename__ = "marketing_touch"
    __table_args__ = (
        ForeignKeyConstraint(
            ["marketing_channel_id"],
            ["marketing_channel.marketing_channel_id"],
            name="fk_marketing_touch__channel",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["marketing_campaign_id"],
            ["marketing_campaign.marketing_campaign_id"],
            name="fk_marketing_touch__campaign",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id"],
            ["organization.organization_id"],
            name="fk_marketing_touch__organization",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["consumer_id"],
            ["consumer.consumer_id"],
            name="fk_marketing_touch__consumer",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        UniqueConstraint("source_event_id", name="uq_marketing_touch__source_id"),
        CheckConstraint(
            "(organization_id IS NOT NULL AND consumer_id IS NULL) OR "
            "(organization_id IS NULL AND consumer_id IS NOT NULL)",
            name="ck_marketing_touch__subject_xor",
        ),
        CheckConstraint(
            "touch_type IN ('non_direct', 'direct')",
            name="ck_marketing_touch__type",
        ),
        CheckConstraint(
            "quality_status IN ('accepted', 'rejected')",
            name="ck_marketing_touch__quality",
        ),
        CheckConstraint(
            "received_at >= occurred_at AND "
            "(processed_at IS NULL OR processed_at >= received_at) AND "
            "recorded_at >= received_at AND "
            "(processed_at IS NULL OR recorded_at >= processed_at)",
            name="ck_marketing_touch__visibility_times",
        ),
        CheckConstraint("is_test IN (0, 1)", name="ck_marketing_touch__is_test"),
        Index(
            "ix_marketing_touch__org_time",
            "organization_id",
            "occurred_at",
            "source_event_id",
        ),
        Index(
            "ix_marketing_touch__consumer_time",
            "consumer_id",
            "occurred_at",
            "source_event_id",
        ),
        Index("ix_marketing_touch__channel_time", "marketing_channel_id", "occurred_at"),
        Index("ix_marketing_touch__campaign_time", "marketing_campaign_id", "occurred_at"),
        Index("ix_marketing_touch__visibility", "recorded_at", "quality_status"),
    )

    marketing_touch_id: Mapped[int] = mapped_column(
        unsigned_bigint(), primary_key=True, autoincrement=True
    )
    source_event_id: Mapped[str] = mapped_column(ascii_binary_varchar(128), nullable=False)
    marketing_channel_id: Mapped[int] = mapped_column(unsigned_bigint(), nullable=False)
    marketing_campaign_id: Mapped[int | None] = mapped_column(unsigned_bigint(), nullable=True)
    organization_id: Mapped[int | None] = mapped_column(unsigned_bigint(), nullable=True)
    consumer_id: Mapped[int | None] = mapped_column(unsigned_bigint(), nullable=True)
    touch_type: Mapped[str] = mapped_column(String(32), nullable=False)
    quality_status: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(datetime_6(), nullable=False)
    received_at: Mapped[datetime] = mapped_column(datetime_6(), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    recorded_at: Mapped[datetime] = mapped_column(
        datetime_6(), nullable=False, server_default=CURRENT_TIMESTAMP_6
    )


class AttributedConversion(Base):
    """One immutable attribution result for a fact, model, and source-data cutoff."""

    __tablename__ = "attributed_conversion"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id"],
            ["organization.organization_id"],
            name="fk_attr_conversion__organization",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["consumer_id"],
            ["consumer.consumer_id"],
            name="fk_attr_conversion__consumer",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["invoice_payment_attempt_id"],
            ["invoice_payment_attempt.invoice_payment_attempt_id"],
            name="fk_attr_conversion__payment_attempt",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["commerce_order_id"],
            ["commerce_order.commerce_order_id"],
            name="fk_attr_conversion__order",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["platform_fee_charge_id"],
            ["platform_fee_charge.platform_fee_charge_id"],
            name="fk_attr_conversion__fee_charge",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["selected_marketing_touch_id"],
            ["marketing_touch.marketing_touch_id"],
            name="fk_attr_conversion__selected_touch",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["marketing_channel_id"],
            ["marketing_channel.marketing_channel_id"],
            name="fk_attr_conversion__channel",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["marketing_campaign_id"],
            ["marketing_campaign.marketing_campaign_id"],
            name="fk_attr_conversion__campaign",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        UniqueConstraint(
            "conversion_type",
            "invoice_payment_attempt_id",
            "model_version",
            "source_data_cutoff_at",
            name="uq_attr_conversion__payment_model_cutoff",
        ),
        UniqueConstraint(
            "conversion_type",
            "commerce_order_id",
            "model_version",
            "source_data_cutoff_at",
            name="uq_attr_conversion__order_model_cutoff",
        ),
        UniqueConstraint(
            "conversion_type",
            "platform_fee_charge_id",
            "model_version",
            "source_data_cutoff_at",
            name="uq_attr_conversion__fee_model_cutoff",
        ),
        CheckConstraint(
            "conversion_type IN "
            "('saas_first_payment', 'saas_revenue', 'commerce_first_payment', "
            "'commerce_revenue', 'attributed_gmv')",
            name="ck_attr_conversion__type",
        ),
        CheckConstraint(
            "(invoice_payment_attempt_id IS NOT NULL AND commerce_order_id IS NULL "
            "AND platform_fee_charge_id IS NULL) OR "
            "(invoice_payment_attempt_id IS NULL AND commerce_order_id IS NOT NULL "
            "AND platform_fee_charge_id IS NULL) OR "
            "(invoice_payment_attempt_id IS NULL AND commerce_order_id IS NULL "
            "AND platform_fee_charge_id IS NOT NULL)",
            name="ck_attr_conversion__fact_xor",
        ),
        CheckConstraint(
            "(organization_id IS NOT NULL AND consumer_id IS NULL) OR "
            "(organization_id IS NULL AND consumer_id IS NOT NULL)",
            name="ck_attr_conversion__subject_xor",
        ),
        CheckConstraint(
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
        CheckConstraint(
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
        CheckConstraint(
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
        CheckConstraint(
            "(reason_code = 'window_history_incomplete' "
            "AND history_complete = 0) OR "
            "(reason_code <> 'window_history_incomplete' "
            "AND history_complete = 1)",
            name="ck_attr_conversion__history_reason",
        ),
        CheckConstraint(
            "model_version = 'last_non_direct_168h_v1'",
            name="ck_attr_conversion__model_version",
        ),
        CheckConstraint(
            "window_started_at = conversion_at - INTERVAL 168 HOUR",
            name="ck_attr_conversion__window",
        ),
        CheckConstraint(
            "conversion_at <= source_data_cutoff_at AND "
            "source_data_cutoff_at <= attributed_at AND "
            "attributed_at <= recorded_at",
            name="ck_attr_conversion__visibility_times",
        ),
        CheckConstraint("is_test IN (0, 1)", name="ck_attr_conversion__is_test"),
        Index("ix_attr_conversion__type_time", "conversion_type", "conversion_at"),
        Index("ix_attr_conversion__channel_time", "marketing_channel_id", "conversion_at"),
        Index("ix_attr_conversion__result_time", "attribution_result", "conversion_at"),
        Index(
            "ix_attr_conversion__org_type_time",
            "organization_id",
            "conversion_type",
            "conversion_at",
        ),
        Index(
            "ix_attr_conversion__consumer_type_time",
            "consumer_id",
            "conversion_type",
            "conversion_at",
        ),
        Index("ix_attr_conversion__payment", "invoice_payment_attempt_id"),
        Index("ix_attr_conversion__order", "commerce_order_id"),
        Index("ix_attr_conversion__fee", "platform_fee_charge_id"),
        Index("ix_attr_conversion__selected_touch", "selected_marketing_touch_id"),
        Index("ix_attr_conversion__campaign", "marketing_campaign_id"),
        Index("ix_attr_conversion__source_cutoff", "source_data_cutoff_at", "recorded_at"),
    )

    attributed_conversion_id: Mapped[int] = mapped_column(
        unsigned_bigint(), primary_key=True, autoincrement=True
    )
    conversion_type: Mapped[str] = mapped_column(String(32), nullable=False)
    organization_id: Mapped[int | None] = mapped_column(unsigned_bigint(), nullable=True)
    consumer_id: Mapped[int | None] = mapped_column(unsigned_bigint(), nullable=True)
    invoice_payment_attempt_id: Mapped[int | None] = mapped_column(unsigned_bigint(), nullable=True)
    commerce_order_id: Mapped[int | None] = mapped_column(unsigned_bigint(), nullable=True)
    platform_fee_charge_id: Mapped[int | None] = mapped_column(unsigned_bigint(), nullable=True)
    selected_marketing_touch_id: Mapped[int | None] = mapped_column(
        unsigned_bigint(), nullable=True
    )
    marketing_channel_id: Mapped[int | None] = mapped_column(unsigned_bigint(), nullable=True)
    marketing_campaign_id: Mapped[int | None] = mapped_column(unsigned_bigint(), nullable=True)
    attribution_result: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str] = mapped_column(ascii_binary_varchar(64), nullable=False)
    model_version: Mapped[str] = mapped_column(
        ascii_binary_varchar(64),
        nullable=False,
        server_default=text("'last_non_direct_168h_v1'"),
    )
    conversion_at: Mapped[datetime] = mapped_column(datetime_6(), nullable=False)
    window_started_at: Mapped[datetime] = mapped_column(datetime_6(), nullable=False)
    history_complete: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source_data_cutoff_at: Mapped[datetime] = mapped_column(datetime_6(), nullable=False)
    attributed_at: Mapped[datetime] = mapped_column(datetime_6(), nullable=False)
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    recorded_at: Mapped[datetime] = mapped_column(
        datetime_6(), nullable=False, server_default=CURRENT_TIMESTAMP_6
    )
