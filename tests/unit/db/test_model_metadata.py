"""Metadata-level tests for the implemented M1.1B schema."""

from typing import cast

from sqlalchemy import JSON, Enum, Float
from sqlalchemy.dialects import mysql

from insightops.db.models import Base

TARGET_TABLES = {
    "consumer",
    "invoice_payment_attempt",
    "merchant",
    "organization",
    "organization_member",
    "saas_plan_version",
    "subscription",
    "subscription_invoice",
    "subscription_state_event",
}

INTERNAL_ID_COLUMNS = {
    "organization": {"organization_id"},
    "organization_member": {"organization_member_id", "organization_id"},
    "consumer": {"consumer_id"},
    "merchant": {"merchant_assignment_id", "merchant_id", "organization_id"},
    "saas_plan_version": {"saas_plan_version_id"},
    "subscription": {"subscription_id", "organization_id", "current_plan_version_id"},
    "subscription_state_event": {
        "subscription_state_event_id",
        "subscription_id",
        "plan_version_before_id",
        "plan_version_after_id",
    },
    "subscription_invoice": {"subscription_invoice_id", "subscription_id"},
    "invoice_payment_attempt": {
        "invoice_payment_attempt_id",
        "subscription_invoice_id",
    },
}


def test_model_registry_contains_exactly_the_m1_1b_tables() -> None:
    assert set(Base.metadata.tables) == TARGET_TABLES


def test_internal_primary_and_foreign_keys_are_unsigned_bigint() -> None:
    for table_name, column_names in INTERNAL_ID_COLUMNS.items():
        table = Base.metadata.tables[table_name]
        for column_name in column_names:
            column_type = table.c[column_name].type
            assert isinstance(column_type, mysql.BIGINT)
            assert column_type.unsigned is True


def test_money_columns_are_exact_decimal_19_4() -> None:
    money_columns = [
        column
        for table in Base.metadata.tables.values()
        for column in table.columns
        if column.name.endswith("_amount") or column.name.startswith("normalized_mrr_")
    ]

    assert money_columns
    for column in money_columns:
        assert isinstance(column.type, mysql.DECIMAL)
        assert column.type.precision == 19
        assert column.type.scale == 4
        assert column.type.asdecimal is True


def test_business_timestamps_use_datetime_with_microseconds() -> None:
    datetime_columns = [
        column
        for table in Base.metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, mysql.DATETIME)
    ]

    assert datetime_columns
    assert all(cast(mysql.DATETIME, column.type).fsp == 6 for column in datetime_columns)


def test_external_and_source_ids_are_case_sensitive_ascii() -> None:
    identifier_columns = [
        column
        for table in Base.metadata.tables.values()
        for column in table.columns
        if column.name.startswith("external_")
        or column.name in {"source_event_id", "provider_transaction_id"}
    ]

    assert identifier_columns
    for column in identifier_columns:
        assert isinstance(column.type, mysql.VARCHAR)
        assert column.type.charset == "ascii"
        assert column.type.collation == "ascii_bin"


def test_schema_does_not_use_forbidden_generic_types() -> None:
    forbidden_types = (Enum, Float, JSON, mysql.DOUBLE, mysql.FLOAT, mysql.ENUM, mysql.JSON)

    for table in Base.metadata.tables.values():
        for column in table.columns:
            assert not isinstance(column.type, forbidden_types)
