"""Structural contract tests for constraints, defaults, and indexes."""

from sqlalchemy import CheckConstraint, DefaultClause, ForeignKeyConstraint, UniqueConstraint

from insightops.db.models import Base

EXPECTED_INDEXES = {
    "organization": {"ix_organization__test_registered", "ix_organization__status"},
    "organization_member": {
        "ix_org_member__org_effective",
        "ix_org_member__org_invited",
    },
    "consumer": {"ix_consumer__test_created", "ix_consumer__status"},
    "merchant": {"ix_merchant__identity_range", "ix_merchant__org_range"},
    "saas_plan_version": {
        "ix_saas_plan_ver__tier_effective",
        "ix_saas_plan_ver__status",
    },
    "subscription": {
        "ix_subscription__org_status",
        "ix_subscription__plan_status",
        "ix_subscription__cancel_effective",
    },
    "subscription_state_event": {
        "ix_sub_state_event__type_effective",
        "ix_sub_state_event__before_plan",
        "ix_sub_state_event__after_plan_time",
    },
    "subscription_invoice": {
        "ix_subscription_invoice__sub_issued",
        "ix_subscription_invoice__status_due",
    },
    "invoice_payment_attempt": {
        "ix_invoice_payment__invoice_status",
        "ix_invoice_payment__status_success",
    },
    "product": {"ix_product__merchant_status", "ix_product__category_status"},
    "commerce_order": {
        "ix_commerce_order__paid_status",
        "ix_commerce_order__merchant_paid",
        "ix_commerce_order__consumer_paid",
        "ix_commerce_order__completed",
    },
    "commerce_order_item": {
        "ix_order_item__product",
        "ix_order_item__category_order",
    },
    "commerce_refund": {
        "ix_commerce_refund__status_success",
        "ix_commerce_refund__order",
    },
    "refund_item_allocation": {"ix_refund_alloc__order_item"},
    "platform_fee_charge": {
        "ix_platform_fee__status_success",
        "ix_platform_fee__order",
    },
}


def test_all_check_unique_and_foreign_key_constraints_are_named() -> None:
    named_types = (CheckConstraint, ForeignKeyConstraint, UniqueConstraint)

    for table in Base.metadata.tables.values():
        for constraint in table.constraints:
            if isinstance(constraint, named_types):
                assert isinstance(constraint.name, str)
                assert len(constraint.name) <= 64


def test_foreign_keys_are_explicitly_restrictive() -> None:
    foreign_keys = [
        constraint
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    ]

    assert foreign_keys
    for foreign_key in foreign_keys:
        assert foreign_key.ondelete == "RESTRICT"
        assert foreign_key.onupdate == "RESTRICT"


def test_expected_named_indexes_exist() -> None:
    for table_name, expected_names in EXPECTED_INDEXES.items():
        actual_names = {index.name for index in Base.metadata.tables[table_name].indexes}
        assert actual_names == expected_names
        assert all(name is not None and len(name) <= 64 for name in actual_names)


def test_explicit_indexes_are_not_covered_by_unique_left_prefixes() -> None:
    for table in Base.metadata.tables.values():
        unique_column_sets = [
            tuple(constraint.columns.keys())
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        ]
        for index in table.indexes:
            index_columns = tuple(index.columns.keys())
            assert all(
                unique_columns[: len(index_columns)] != index_columns
                for unique_columns in unique_column_sets
            )

    order_item_indexes = {
        index.name for index in Base.metadata.tables["commerce_order_item"].indexes
    }
    refund_allocation_indexes = {
        index.name for index in Base.metadata.tables["refund_item_allocation"].indexes
    }
    assert "ix_order_item__order" not in order_item_indexes
    assert "ix_refund_alloc__refund" not in refund_allocation_indexes


def test_is_test_defaults_and_constraints_are_explicit() -> None:
    for table in Base.metadata.tables.values():
        column = table.c.is_test
        assert column.nullable is False
        assert isinstance(column.server_default, DefaultClause)
        assert str(column.server_default.arg) == "0"
        check_names = {
            constraint.name
            for constraint in table.constraints
            if isinstance(constraint, CheckConstraint)
        }
        assert f"ck_{_constraint_table_name(table.name)}__is_test" in check_names


def test_updated_at_metadata_marks_server_generated_updates() -> None:
    mutable_tables = {
        "organization",
        "organization_member",
        "consumer",
        "merchant",
        "saas_plan_version",
        "subscription",
        "subscription_invoice",
        "product",
        "commerce_order",
        "commerce_refund",
        "refund_item_allocation",
    }

    for table_name in mutable_tables:
        updated_at = Base.metadata.tables[table_name].c.updated_at
        assert updated_at.nullable is False
        assert isinstance(updated_at.server_default, DefaultClause)
        assert str(updated_at.server_default.arg) == "CURRENT_TIMESTAMP(6)"
        assert isinstance(updated_at.server_onupdate, DefaultClause)
        assert str(updated_at.server_onupdate.arg) == "CURRENT_TIMESTAMP(6)"

    assert "updated_at" not in Base.metadata.tables["subscription_state_event"].c
    assert "updated_at" not in Base.metadata.tables["invoice_payment_attempt"].c
    assert "updated_at" not in Base.metadata.tables["commerce_order_item"].c
    assert "updated_at" not in Base.metadata.tables["platform_fee_charge"].c


def _constraint_table_name(table_name: str) -> str:
    """Return the physical document's shortened constraint prefix."""
    return {
        "organization_member": "org_member",
        "saas_plan_version": "saas_plan_ver",
        "subscription_state_event": "sub_state_event",
        "subscription_invoice": "subscription_invoice",
        "invoice_payment_attempt": "invoice_payment",
        "commerce_order_item": "order_item",
        "refund_item_allocation": "refund_alloc",
        "platform_fee_charge": "platform_fee",
    }.get(table_name, table_name)
