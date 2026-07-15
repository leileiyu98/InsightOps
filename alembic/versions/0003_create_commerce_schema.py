"""Create the M1.1C commerce schema.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CURRENT_TIMESTAMP_6 = sa.text("CURRENT_TIMESTAMP(6)")
CURRENT_TIMESTAMP_6_ON_UPDATE = sa.text("CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)")


def upgrade() -> None:
    """Create the six M1.1C tables in foreign-key dependency order."""
    _create_product_table()
    _create_order_tables()
    _create_refund_and_fee_tables()
    _create_refund_allocation_table()


def _create_product_table() -> None:
    """Create the current product entity table."""
    op.create_table(
        "product",
        sa.Column("product_id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column(
            "external_product_id",
            mysql.VARCHAR(length=128, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column("merchant_assignment_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("product_title", sa.String(length=255), nullable=False),
        sa.Column(
            "category_code",
            mysql.VARCHAR(length=64, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("first_published_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("archived_at", mysql.DATETIME(fsp=6), nullable=True),
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
            "status IN ('draft', 'active', 'inactive', 'archived')",
            name="ck_product__status",
        ),
        sa.CheckConstraint("category_code <> ''", name="ck_product__category_nonempty"),
        sa.CheckConstraint(
            "(first_published_at IS NULL OR first_published_at >= created_at) AND "
            "(archived_at IS NULL OR archived_at >= created_at)",
            name="ck_product__lifecycle_times",
        ),
        sa.CheckConstraint(
            "status <> 'archived' OR archived_at IS NOT NULL",
            name="ck_product__archived_status_time",
        ),
        sa.CheckConstraint("is_test IN (0, 1)", name="ck_product__is_test"),
        sa.ForeignKeyConstraint(
            ["merchant_assignment_id"],
            ["merchant.merchant_assignment_id"],
            name="fk_product__merchant_assignment",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("product_id"),
        sa.UniqueConstraint("external_product_id", name="uq_product__external_id"),
    )
    op.create_index(
        "ix_product__merchant_status",
        "product",
        ["merchant_assignment_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_product__category_status",
        "product",
        ["category_code", "status"],
        unique=False,
    )


def _create_order_tables() -> None:
    """Create commerce orders and their authoritative GMV detail facts."""
    op.create_table(
        "commerce_order",
        sa.Column(
            "commerce_order_id",
            mysql.BIGINT(unsigned=True),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "external_order_id",
            mysql.VARCHAR(length=128, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column("consumer_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("merchant_assignment_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "currency_code",
            mysql.CHAR(length=3, charset="ascii", collation="ascii_bin"),
            server_default=sa.text("'USD'"),
            nullable=False,
        ),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("first_paid_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("fulfilled_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("completed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("cancelled_at", mysql.DATETIME(fsp=6), nullable=True),
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
            "status IN "
            "('created', 'payment_pending', 'paid', 'fulfilled', 'completed', 'cancelled')",
            name="ck_commerce_order__status",
        ),
        sa.CheckConstraint("currency_code = 'USD'", name="ck_commerce_order__currency"),
        sa.CheckConstraint(
            "(first_paid_at IS NULL OR first_paid_at >= created_at) AND "
            "(fulfilled_at IS NULL OR fulfilled_at >= created_at) AND "
            "(completed_at IS NULL OR completed_at >= created_at) AND "
            "(cancelled_at IS NULL OR cancelled_at >= created_at)",
            name="ck_commerce_order__lifecycle_times",
        ),
        sa.CheckConstraint(
            "(status NOT IN ('paid', 'fulfilled', 'completed') OR first_paid_at IS NOT NULL) "
            "AND (status <> 'fulfilled' OR fulfilled_at IS NOT NULL) "
            "AND (status <> 'completed' OR completed_at IS NOT NULL) "
            "AND (status <> 'cancelled' OR cancelled_at IS NOT NULL)",
            name="ck_commerce_order__status_times",
        ),
        sa.CheckConstraint(
            "fulfilled_at IS NULL OR (first_paid_at IS NOT NULL AND fulfilled_at >= first_paid_at)",
            name="ck_commerce_order__fulfillment_order",
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR "
            "(first_paid_at IS NOT NULL AND completed_at >= first_paid_at "
            "AND (fulfilled_at IS NULL OR completed_at >= fulfilled_at))",
            name="ck_commerce_order__completion_order",
        ),
        sa.CheckConstraint("is_test IN (0, 1)", name="ck_commerce_order__is_test"),
        sa.ForeignKeyConstraint(
            ["consumer_id"],
            ["consumer.consumer_id"],
            name="fk_commerce_order__consumer",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["merchant_assignment_id"],
            ["merchant.merchant_assignment_id"],
            name="fk_commerce_order__merchant_assignment",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("commerce_order_id"),
        sa.UniqueConstraint("external_order_id", name="uq_commerce_order__external_id"),
    )
    op.create_index(
        "ix_commerce_order__paid_status",
        "commerce_order",
        ["first_paid_at", "status", "is_test"],
        unique=False,
    )
    op.create_index(
        "ix_commerce_order__merchant_paid",
        "commerce_order",
        ["merchant_assignment_id", "first_paid_at"],
        unique=False,
    )
    op.create_index(
        "ix_commerce_order__consumer_paid",
        "commerce_order",
        ["consumer_id", "first_paid_at"],
        unique=False,
    )
    op.create_index(
        "ix_commerce_order__completed",
        "commerce_order",
        ["completed_at", "status"],
        unique=False,
    )

    op.create_table(
        "commerce_order_item",
        sa.Column(
            "commerce_order_item_id",
            mysql.BIGINT(unsigned=True),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "external_order_item_id",
            mysql.VARCHAR(length=128, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column("commerce_order_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("product_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column(
            "product_category_code",
            mysql.VARCHAR(length=64, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column("quantity", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column(
            "discounted_item_amount",
            mysql.DECIMAL(precision=19, scale=4),
            nullable=False,
        ),
        sa.Column(
            "currency_code",
            mysql.CHAR(length=3, charset="ascii", collation="ascii_bin"),
            server_default=sa.text("'USD'"),
            nullable=False,
        ),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("is_test", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "recorded_at",
            mysql.DATETIME(fsp=6),
            server_default=CURRENT_TIMESTAMP_6,
            nullable=False,
        ),
        sa.CheckConstraint(
            "product_category_code <> ''",
            name="ck_order_item__category_nonempty",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_order_item__quantity_positive"),
        sa.CheckConstraint(
            "discounted_item_amount >= 0",
            name="ck_order_item__amount_nonnegative",
        ),
        sa.CheckConstraint("currency_code = 'USD'", name="ck_order_item__currency"),
        sa.CheckConstraint("is_test IN (0, 1)", name="ck_order_item__is_test"),
        sa.ForeignKeyConstraint(
            ["commerce_order_id"],
            ["commerce_order.commerce_order_id"],
            name="fk_order_item__order",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["product.product_id"],
            name="fk_order_item__product",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("commerce_order_item_id"),
        sa.UniqueConstraint(
            "commerce_order_id",
            "external_order_item_id",
            name="uq_order_item__order_external",
        ),
    )
    op.create_index(
        "ix_order_item__product",
        "commerce_order_item",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        "ix_order_item__category_order",
        "commerce_order_item",
        ["product_category_code", "commerce_order_id"],
        unique=False,
    )


def _create_refund_and_fee_tables() -> None:
    """Create refund lifecycles and append-only platform fee attempts."""
    op.create_table(
        "commerce_refund",
        sa.Column(
            "commerce_refund_id",
            mysql.BIGINT(unsigned=True),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "external_refund_id",
            mysql.VARCHAR(length=128, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column("commerce_order_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("item_refund_amount", mysql.DECIMAL(precision=19, scale=4), nullable=False),
        sa.Column("tax_refund_amount", mysql.DECIMAL(precision=19, scale=4), nullable=False),
        sa.Column("shipping_refund_amount", mysql.DECIMAL(precision=19, scale=4), nullable=False),
        sa.Column("total_refund_amount", mysql.DECIMAL(precision=19, scale=4), nullable=False),
        sa.Column(
            "currency_code",
            mysql.CHAR(length=3, charset="ascii", collation="ascii_bin"),
            server_default=sa.text("'USD'"),
            nullable=False,
        ),
        sa.Column(
            "reason_code",
            mysql.VARCHAR(length=64, charset="ascii", collation="ascii_bin"),
            nullable=True,
        ),
        sa.Column("requested_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("processed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("succeeded_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("failed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("cancelled_at", mysql.DATETIME(fsp=6), nullable=True),
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
            "status IN ('requested', 'pending', 'succeeded', 'failed', 'cancelled')",
            name="ck_commerce_refund__status",
        ),
        sa.CheckConstraint(
            "item_refund_amount >= 0 AND tax_refund_amount >= 0 "
            "AND shipping_refund_amount >= 0 AND total_refund_amount >= 0",
            name="ck_commerce_refund__amounts_nonnegative",
        ),
        sa.CheckConstraint(
            "total_refund_amount = item_refund_amount + tax_refund_amount + shipping_refund_amount",
            name="ck_commerce_refund__amount_total",
        ),
        sa.CheckConstraint("currency_code = 'USD'", name="ck_commerce_refund__currency"),
        sa.CheckConstraint(
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
        sa.CheckConstraint(
            "(processed_at IS NULL OR processed_at >= requested_at) AND "
            "(succeeded_at IS NULL OR succeeded_at >= requested_at) AND "
            "(failed_at IS NULL OR failed_at >= requested_at) AND "
            "(cancelled_at IS NULL OR cancelled_at >= requested_at)",
            name="ck_commerce_refund__time_order",
        ),
        sa.CheckConstraint("is_test IN (0, 1)", name="ck_commerce_refund__is_test"),
        sa.ForeignKeyConstraint(
            ["commerce_order_id"],
            ["commerce_order.commerce_order_id"],
            name="fk_commerce_refund__order",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("commerce_refund_id"),
        sa.UniqueConstraint("external_refund_id", name="uq_commerce_refund__external_id"),
    )
    op.create_index(
        "ix_commerce_refund__status_success",
        "commerce_refund",
        ["status", "succeeded_at"],
        unique=False,
    )
    op.create_index(
        "ix_commerce_refund__order",
        "commerce_refund",
        ["commerce_order_id"],
        unique=False,
    )

    op.create_table(
        "platform_fee_charge",
        sa.Column(
            "platform_fee_charge_id",
            mysql.BIGINT(unsigned=True),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "external_fee_charge_id",
            mysql.VARCHAR(length=128, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column(
            "provider_charge_id",
            mysql.VARCHAR(length=128, charset="ascii", collation="ascii_bin"),
            nullable=True,
        ),
        sa.Column("commerce_order_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("fee_amount", mysql.DECIMAL(precision=19, scale=4), nullable=False),
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
        sa.Column("is_test", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "recorded_at",
            mysql.DATETIME(fsp=6),
            server_default=CURRENT_TIMESTAMP_6,
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed', 'cancelled')",
            name="ck_platform_fee__status",
        ),
        sa.CheckConstraint("fee_amount >= 0", name="ck_platform_fee__amount_nonnegative"),
        sa.CheckConstraint("currency_code = 'USD'", name="ck_platform_fee__currency"),
        sa.CheckConstraint(
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
        sa.CheckConstraint(
            "(succeeded_at IS NULL OR succeeded_at >= attempted_at) AND "
            "(failed_at IS NULL OR failed_at >= attempted_at) AND "
            "(cancelled_at IS NULL OR cancelled_at >= attempted_at)",
            name="ck_platform_fee__terminal_order",
        ),
        sa.CheckConstraint("is_test IN (0, 1)", name="ck_platform_fee__is_test"),
        sa.ForeignKeyConstraint(
            ["commerce_order_id"],
            ["commerce_order.commerce_order_id"],
            name="fk_platform_fee__order",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("platform_fee_charge_id"),
        sa.UniqueConstraint("external_fee_charge_id", name="uq_platform_fee__external_id"),
        sa.UniqueConstraint("provider_charge_id", name="uq_platform_fee__provider_charge"),
    )
    op.create_index(
        "ix_platform_fee__status_success",
        "platform_fee_charge",
        ["status", "succeeded_at"],
        unique=False,
    )
    op.create_index(
        "ix_platform_fee__order",
        "platform_fee_charge",
        ["commerce_order_id"],
        unique=False,
    )


def _create_refund_allocation_table() -> None:
    """Create correctable item-level refund allocations."""
    op.create_table(
        "refund_item_allocation",
        sa.Column(
            "refund_item_allocation_id",
            mysql.BIGINT(unsigned=True),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "external_refund_allocation_id",
            mysql.VARCHAR(length=128, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column("commerce_refund_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("commerce_order_item_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column(
            "allocated_item_amount",
            mysql.DECIMAL(precision=19, scale=4),
            nullable=False,
        ),
        sa.Column(
            "currency_code",
            mysql.CHAR(length=3, charset="ascii", collation="ascii_bin"),
            server_default=sa.text("'USD'"),
            nullable=False,
        ),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("corrected_at", mysql.DATETIME(fsp=6), nullable=True),
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
            "allocated_item_amount >= 0",
            name="ck_refund_alloc__amount_nonnegative",
        ),
        sa.CheckConstraint("currency_code = 'USD'", name="ck_refund_alloc__currency"),
        sa.CheckConstraint(
            "corrected_at IS NULL OR corrected_at >= created_at",
            name="ck_refund_alloc__corrected_time",
        ),
        sa.CheckConstraint("is_test IN (0, 1)", name="ck_refund_alloc__is_test"),
        sa.ForeignKeyConstraint(
            ["commerce_refund_id"],
            ["commerce_refund.commerce_refund_id"],
            name="fk_refund_alloc__refund",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["commerce_order_item_id"],
            ["commerce_order_item.commerce_order_item_id"],
            name="fk_refund_alloc__order_item",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("refund_item_allocation_id"),
        sa.UniqueConstraint(
            "external_refund_allocation_id",
            name="uq_refund_alloc__external_id",
        ),
        sa.UniqueConstraint(
            "commerce_refund_id",
            "commerce_order_item_id",
            name="uq_refund_alloc__refund_item",
        ),
    )
    op.create_index(
        "ix_refund_alloc__order_item",
        "refund_item_allocation",
        ["commerce_order_item_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the M1.1C tables in reverse foreign-key dependency order."""
    op.drop_table("refund_item_allocation")
    op.drop_table("platform_fee_charge")
    op.drop_table("commerce_refund")
    op.drop_table("commerce_order_item")
    op.drop_table("commerce_order")
    op.drop_table("product")
