"""Commerce SQLAlchemy mappings for M1.1C."""

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
    unsigned_integer,
)

CURRENT_TIMESTAMP_6 = text("CURRENT_TIMESTAMP(6)")


class Product(Base):
    """One merchant's current product entity."""

    __tablename__ = "product"
    __table_args__ = (
        ForeignKeyConstraint(
            ["merchant_assignment_id"],
            ["merchant.merchant_assignment_id"],
            name="fk_product__merchant_assignment",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        UniqueConstraint("external_product_id", name="uq_product__external_id"),
        CheckConstraint(
            "status IN ('draft', 'active', 'inactive', 'archived')",
            name="ck_product__status",
        ),
        CheckConstraint("category_code <> ''", name="ck_product__category_nonempty"),
        CheckConstraint(
            "(first_published_at IS NULL OR first_published_at >= created_at) AND "
            "(archived_at IS NULL OR archived_at >= created_at)",
            name="ck_product__lifecycle_times",
        ),
        CheckConstraint(
            "status <> 'archived' OR archived_at IS NOT NULL",
            name="ck_product__archived_status_time",
        ),
        CheckConstraint("is_test IN (0, 1)", name="ck_product__is_test"),
        Index("ix_product__merchant_status", "merchant_assignment_id", "status"),
        Index("ix_product__category_status", "category_code", "status"),
    )

    product_id: Mapped[int] = mapped_column(unsigned_bigint(), primary_key=True, autoincrement=True)
    external_product_id: Mapped[str] = mapped_column(ascii_binary_varchar(128), nullable=False)
    merchant_assignment_id: Mapped[int] = mapped_column(unsigned_bigint(), nullable=False)
    product_title: Mapped[str] = mapped_column(String(255), nullable=False)
    category_code: Mapped[str] = mapped_column(ascii_binary_varchar(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(datetime_6(), nullable=False)
    first_published_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
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


class CommerceOrder(Base):
    """One commerce order with current status and durable milestone times."""

    __tablename__ = "commerce_order"
    __table_args__ = (
        ForeignKeyConstraint(
            ["consumer_id"],
            ["consumer.consumer_id"],
            name="fk_commerce_order__consumer",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["merchant_assignment_id"],
            ["merchant.merchant_assignment_id"],
            name="fk_commerce_order__merchant_assignment",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        UniqueConstraint("external_order_id", name="uq_commerce_order__external_id"),
        CheckConstraint(
            "status IN "
            "('created', 'payment_pending', 'paid', 'fulfilled', 'completed', 'cancelled')",
            name="ck_commerce_order__status",
        ),
        CheckConstraint("currency_code = 'USD'", name="ck_commerce_order__currency"),
        CheckConstraint(
            "(first_paid_at IS NULL OR first_paid_at >= created_at) AND "
            "(fulfilled_at IS NULL OR fulfilled_at >= created_at) AND "
            "(completed_at IS NULL OR completed_at >= created_at) AND "
            "(cancelled_at IS NULL OR cancelled_at >= created_at)",
            name="ck_commerce_order__lifecycle_times",
        ),
        CheckConstraint(
            "(status NOT IN ('paid', 'fulfilled', 'completed') OR first_paid_at IS NOT NULL) "
            "AND (status <> 'fulfilled' OR fulfilled_at IS NOT NULL) "
            "AND (status <> 'completed' OR completed_at IS NOT NULL) "
            "AND (status <> 'cancelled' OR cancelled_at IS NOT NULL)",
            name="ck_commerce_order__status_times",
        ),
        CheckConstraint(
            "fulfilled_at IS NULL OR (first_paid_at IS NOT NULL AND fulfilled_at >= first_paid_at)",
            name="ck_commerce_order__fulfillment_order",
        ),
        CheckConstraint(
            "completed_at IS NULL OR "
            "(first_paid_at IS NOT NULL AND completed_at >= first_paid_at "
            "AND (fulfilled_at IS NULL OR completed_at >= fulfilled_at))",
            name="ck_commerce_order__completion_order",
        ),
        CheckConstraint("is_test IN (0, 1)", name="ck_commerce_order__is_test"),
        Index("ix_commerce_order__paid_status", "first_paid_at", "status", "is_test"),
        Index("ix_commerce_order__merchant_paid", "merchant_assignment_id", "first_paid_at"),
        Index("ix_commerce_order__consumer_paid", "consumer_id", "first_paid_at"),
        Index("ix_commerce_order__completed", "completed_at", "status"),
    )

    commerce_order_id: Mapped[int] = mapped_column(
        unsigned_bigint(), primary_key=True, autoincrement=True
    )
    external_order_id: Mapped[str] = mapped_column(ascii_binary_varchar(128), nullable=False)
    consumer_id: Mapped[int] = mapped_column(unsigned_bigint(), nullable=False)
    merchant_assignment_id: Mapped[int] = mapped_column(unsigned_bigint(), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    currency_code: Mapped[str] = mapped_column(
        currency_code_type(), nullable=False, server_default=text("'USD'")
    )
    created_at: Mapped[datetime] = mapped_column(datetime_6(), nullable=False)
    first_paid_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    fulfilled_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
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


class CommerceOrderItem(Base):
    """One immutable product line and its purchase-time category snapshot."""

    __tablename__ = "commerce_order_item"
    __table_args__ = (
        ForeignKeyConstraint(
            ["commerce_order_id"],
            ["commerce_order.commerce_order_id"],
            name="fk_order_item__order",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["product_id"],
            ["product.product_id"],
            name="fk_order_item__product",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        UniqueConstraint(
            "commerce_order_id",
            "external_order_item_id",
            name="uq_order_item__order_external",
        ),
        CheckConstraint(
            "product_category_code <> ''",
            name="ck_order_item__category_nonempty",
        ),
        CheckConstraint("quantity > 0", name="ck_order_item__quantity_positive"),
        CheckConstraint(
            "discounted_item_amount >= 0",
            name="ck_order_item__amount_nonnegative",
        ),
        CheckConstraint("currency_code = 'USD'", name="ck_order_item__currency"),
        CheckConstraint("is_test IN (0, 1)", name="ck_order_item__is_test"),
        Index("ix_order_item__product", "product_id"),
        Index("ix_order_item__category_order", "product_category_code", "commerce_order_id"),
    )

    commerce_order_item_id: Mapped[int] = mapped_column(
        unsigned_bigint(), primary_key=True, autoincrement=True
    )
    external_order_item_id: Mapped[str] = mapped_column(ascii_binary_varchar(128), nullable=False)
    commerce_order_id: Mapped[int] = mapped_column(unsigned_bigint(), nullable=False)
    product_id: Mapped[int] = mapped_column(unsigned_bigint(), nullable=False)
    product_category_code: Mapped[str] = mapped_column(ascii_binary_varchar(64), nullable=False)
    quantity: Mapped[int] = mapped_column(unsigned_integer(), nullable=False)
    discounted_item_amount: Mapped[Decimal] = mapped_column(money_decimal(), nullable=False)
    currency_code: Mapped[str] = mapped_column(
        currency_code_type(), nullable=False, server_default=text("'USD'")
    )
    created_at: Mapped[datetime] = mapped_column(datetime_6(), nullable=False)
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    recorded_at: Mapped[datetime] = mapped_column(
        datetime_6(), nullable=False, server_default=CURRENT_TIMESTAMP_6
    )


class CommerceRefund(Base):
    """One commerce refund lifecycle and its authoritative item amount."""

    __tablename__ = "commerce_refund"
    __table_args__ = (
        ForeignKeyConstraint(
            ["commerce_order_id"],
            ["commerce_order.commerce_order_id"],
            name="fk_commerce_refund__order",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        UniqueConstraint("external_refund_id", name="uq_commerce_refund__external_id"),
        CheckConstraint(
            "status IN ('requested', 'pending', 'succeeded', 'failed', 'cancelled')",
            name="ck_commerce_refund__status",
        ),
        CheckConstraint(
            "item_refund_amount >= 0 AND tax_refund_amount >= 0 "
            "AND shipping_refund_amount >= 0 AND total_refund_amount >= 0",
            name="ck_commerce_refund__amounts_nonnegative",
        ),
        CheckConstraint(
            "total_refund_amount = item_refund_amount + tax_refund_amount + shipping_refund_amount",
            name="ck_commerce_refund__amount_total",
        ),
        CheckConstraint("currency_code = 'USD'", name="ck_commerce_refund__currency"),
        CheckConstraint(
            "(status IN ('requested', 'pending') AND succeeded_at IS NULL "
            "AND failed_at IS NULL AND cancelled_at IS NULL) OR "
            "(status = 'succeeded' AND succeeded_at IS NOT NULL "
            "AND failed_at IS NULL AND cancelled_at IS NULL) OR "
            "(status = 'failed' AND failed_at IS NOT NULL "
            "AND succeeded_at IS NULL AND cancelled_at IS NULL) OR "
            "(status = 'cancelled' AND cancelled_at IS NOT NULL "
            "AND succeeded_at IS NULL AND failed_at IS NULL)",
            name="ck_commerce_refund__status_times",
        ),
        CheckConstraint(
            "(processed_at IS NULL OR processed_at >= requested_at) AND "
            "(succeeded_at IS NULL OR succeeded_at >= requested_at) AND "
            "(failed_at IS NULL OR failed_at >= requested_at) AND "
            "(cancelled_at IS NULL OR cancelled_at >= requested_at)",
            name="ck_commerce_refund__time_order",
        ),
        CheckConstraint("is_test IN (0, 1)", name="ck_commerce_refund__is_test"),
        Index("ix_commerce_refund__status_success", "status", "succeeded_at"),
        Index("ix_commerce_refund__order", "commerce_order_id"),
    )

    commerce_refund_id: Mapped[int] = mapped_column(
        unsigned_bigint(), primary_key=True, autoincrement=True
    )
    external_refund_id: Mapped[str] = mapped_column(ascii_binary_varchar(128), nullable=False)
    commerce_order_id: Mapped[int] = mapped_column(unsigned_bigint(), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    item_refund_amount: Mapped[Decimal] = mapped_column(money_decimal(), nullable=False)
    tax_refund_amount: Mapped[Decimal] = mapped_column(money_decimal(), nullable=False)
    shipping_refund_amount: Mapped[Decimal] = mapped_column(money_decimal(), nullable=False)
    total_refund_amount: Mapped[Decimal] = mapped_column(money_decimal(), nullable=False)
    currency_code: Mapped[str] = mapped_column(
        currency_code_type(), nullable=False, server_default=text("'USD'")
    )
    reason_code: Mapped[str | None] = mapped_column(ascii_binary_varchar(64), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(datetime_6(), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    succeeded_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
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


class RefundItemAllocation(Base):
    """One correctable allocation of refund item amount to an order line."""

    __tablename__ = "refund_item_allocation"
    __table_args__ = (
        ForeignKeyConstraint(
            ["commerce_refund_id"],
            ["commerce_refund.commerce_refund_id"],
            name="fk_refund_alloc__refund",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["commerce_order_item_id"],
            ["commerce_order_item.commerce_order_item_id"],
            name="fk_refund_alloc__order_item",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        UniqueConstraint(
            "external_refund_allocation_id",
            name="uq_refund_alloc__external_id",
        ),
        UniqueConstraint(
            "commerce_refund_id",
            "commerce_order_item_id",
            name="uq_refund_alloc__refund_item",
        ),
        CheckConstraint(
            "allocated_item_amount >= 0",
            name="ck_refund_alloc__amount_nonnegative",
        ),
        CheckConstraint("currency_code = 'USD'", name="ck_refund_alloc__currency"),
        CheckConstraint(
            "corrected_at IS NULL OR corrected_at >= created_at",
            name="ck_refund_alloc__corrected_time",
        ),
        CheckConstraint("is_test IN (0, 1)", name="ck_refund_alloc__is_test"),
        Index("ix_refund_alloc__order_item", "commerce_order_item_id"),
    )

    refund_item_allocation_id: Mapped[int] = mapped_column(
        unsigned_bigint(), primary_key=True, autoincrement=True
    )
    external_refund_allocation_id: Mapped[str] = mapped_column(
        ascii_binary_varchar(128), nullable=False
    )
    commerce_refund_id: Mapped[int] = mapped_column(unsigned_bigint(), nullable=False)
    commerce_order_item_id: Mapped[int] = mapped_column(unsigned_bigint(), nullable=False)
    allocated_item_amount: Mapped[Decimal] = mapped_column(money_decimal(), nullable=False)
    currency_code: Mapped[str] = mapped_column(
        currency_code_type(), nullable=False, server_default=text("'USD'")
    )
    created_at: Mapped[datetime] = mapped_column(datetime_6(), nullable=False)
    corrected_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
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


class PlatformFeeCharge(Base):
    """One append-only attempt to charge an order's platform transaction fee."""

    __tablename__ = "platform_fee_charge"
    __table_args__ = (
        ForeignKeyConstraint(
            ["commerce_order_id"],
            ["commerce_order.commerce_order_id"],
            name="fk_platform_fee__order",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        UniqueConstraint("external_fee_charge_id", name="uq_platform_fee__external_id"),
        UniqueConstraint("provider_charge_id", name="uq_platform_fee__provider_charge"),
        CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed', 'cancelled')",
            name="ck_platform_fee__status",
        ),
        CheckConstraint("fee_amount >= 0", name="ck_platform_fee__amount_nonnegative"),
        CheckConstraint("currency_code = 'USD'", name="ck_platform_fee__currency"),
        CheckConstraint(
            "(status = 'pending' AND succeeded_at IS NULL "
            "AND failed_at IS NULL AND cancelled_at IS NULL) OR "
            "(status = 'succeeded' AND succeeded_at IS NOT NULL "
            "AND failed_at IS NULL AND cancelled_at IS NULL) OR "
            "(status = 'failed' AND failed_at IS NOT NULL "
            "AND succeeded_at IS NULL AND cancelled_at IS NULL) OR "
            "(status = 'cancelled' AND cancelled_at IS NOT NULL "
            "AND succeeded_at IS NULL AND failed_at IS NULL)",
            name="ck_platform_fee__status_times",
        ),
        CheckConstraint(
            "(succeeded_at IS NULL OR succeeded_at >= attempted_at) AND "
            "(failed_at IS NULL OR failed_at >= attempted_at) AND "
            "(cancelled_at IS NULL OR cancelled_at >= attempted_at)",
            name="ck_platform_fee__terminal_order",
        ),
        CheckConstraint("is_test IN (0, 1)", name="ck_platform_fee__is_test"),
        Index("ix_platform_fee__status_success", "status", "succeeded_at"),
        Index("ix_platform_fee__order", "commerce_order_id"),
    )

    platform_fee_charge_id: Mapped[int] = mapped_column(
        unsigned_bigint(), primary_key=True, autoincrement=True
    )
    external_fee_charge_id: Mapped[str] = mapped_column(ascii_binary_varchar(128), nullable=False)
    provider_charge_id: Mapped[str | None] = mapped_column(ascii_binary_varchar(128), nullable=True)
    commerce_order_id: Mapped[int] = mapped_column(unsigned_bigint(), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    fee_amount: Mapped[Decimal] = mapped_column(money_decimal(), nullable=False)
    currency_code: Mapped[str] = mapped_column(
        currency_code_type(), nullable=False, server_default=text("'USD'")
    )
    attempted_at: Mapped[datetime] = mapped_column(datetime_6(), nullable=False)
    succeeded_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(datetime_6(), nullable=True)
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    recorded_at: Mapped[datetime] = mapped_column(
        datetime_6(), nullable=False, server_default=CURRENT_TIMESTAMP_6
    )
