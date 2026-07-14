"""Real MySQL migration lifecycle and reflected schema tests."""

from collections.abc import Mapping
from typing import Any

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import (
    CheckConstraint,
    Engine,
    ForeignKeyConstraint,
    UniqueConstraint,
    inspect,
    text,
)

from alembic import command
from insightops.db.models import Base

TARGET_TABLES = set(Base.metadata.tables)
UPDATED_AT_TABLES = {
    "organization",
    "organization_member",
    "consumer",
    "merchant",
    "saas_plan_version",
    "subscription",
    "subscription_invoice",
}


def test_migration_round_trip_restores_0002_head(
    alembic_config: Config,
    database_engine: Engine,
) -> None:
    database_engine.dispose()
    try:
        command.downgrade(alembic_config, "base")
        _assert_m1_1b_schema_absent(database_engine)

        command.upgrade(alembic_config, "head")
        _assert_m1_1b_schema_matches_metadata(database_engine)

        command.downgrade(alembic_config, "base")
        _assert_m1_1b_schema_absent(database_engine)

        command.upgrade(alembic_config, "head")
        _assert_m1_1b_schema_matches_metadata(database_engine)
    finally:
        database_engine.dispose()
        command.upgrade(alembic_config, "head")

    assert _current_revision(database_engine) == "0002"


def _assert_m1_1b_schema_absent(engine: Engine) -> None:
    inspector = inspect(engine)
    assert TARGET_TABLES.isdisjoint(inspector.get_table_names())

    with engine.connect() as connection:
        residual_foreign_keys = connection.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS "
                "WHERE CONSTRAINT_SCHEMA = DATABASE() "
                "AND TABLE_NAME IN "
                "('organization', 'organization_member', 'consumer', 'merchant', "
                "'saas_plan_version', 'subscription', 'subscription_state_event', "
                "'subscription_invoice', 'invoice_payment_attempt')"
            )
        ).scalar_one()
    assert residual_foreign_keys == 0


def _assert_m1_1b_schema_matches_metadata(engine: Engine) -> None:
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) - {"alembic_version"} == TARGET_TABLES

    for table_name, metadata_table in Base.metadata.tables.items():
        reflected_columns = {column["name"]: column for column in inspector.get_columns(table_name)}
        assert set(reflected_columns) == set(metadata_table.c.keys())

        expected_checks = {
            constraint.name
            for constraint in metadata_table.constraints
            if isinstance(constraint, CheckConstraint)
        }
        actual_checks = {
            constraint["name"] for constraint in inspector.get_check_constraints(table_name)
        }
        assert actual_checks == expected_checks

        expected_uniques = {
            constraint.name
            for constraint in metadata_table.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        actual_uniques = {
            constraint["name"] for constraint in inspector.get_unique_constraints(table_name)
        }
        assert actual_uniques == expected_uniques

        expected_indexes = {index.name for index in metadata_table.indexes}
        actual_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
        assert expected_indexes <= actual_indexes

        expected_foreign_keys = {
            constraint.name
            for constraint in metadata_table.constraints
            if isinstance(constraint, ForeignKeyConstraint)
        }
        actual_foreign_keys = {
            foreign_key["name"] for foreign_key in inspector.get_foreign_keys(table_name)
        }
        assert actual_foreign_keys == expected_foreign_keys

    _assert_physical_mysql_types_and_collations(engine)
    _assert_foreign_key_restrict_rules(engine)
    _assert_subscription_effective_unique_index(engine)
    _assert_updated_at_on_update_ddl(engine)
    assert _current_revision(engine) == "0002"


def _assert_physical_mysql_types_and_collations(engine: Engine) -> None:
    rows = _information_schema_columns(engine)
    row_by_column = {(row["TABLE_NAME"], row["COLUMN_NAME"]): row for row in rows}

    for table_name, metadata_table in Base.metadata.tables.items():
        for column in metadata_table.columns:
            row = row_by_column[(table_name, column.name)]
            column_type = str(row["COLUMN_TYPE"]).lower()
            if column.primary_key or any(foreign_key for foreign_key in column.foreign_keys):
                assert column_type == "bigint unsigned"
            if column.name == "merchant_id":
                assert column_type == "bigint unsigned"
            if column.name.endswith("_amount") or column.name.startswith("normalized_mrr_"):
                assert column_type == "decimal(19,4)"
            if column.name.endswith("_at") or column.name in {
                "effective_from",
                "effective_to",
                "assignment_valid_from",
                "assignment_valid_to",
            }:
                assert column_type == "datetime(6)"
            if column.name.startswith("external_") or column.name in {
                "source_event_id",
                "provider_transaction_id",
            }:
                assert row["CHARACTER_SET_NAME"] == "ascii"
                assert row["COLLATION_NAME"] == "ascii_bin"


def _assert_foreign_key_restrict_rules(engine: Engine) -> None:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT CONSTRAINT_NAME, UPDATE_RULE, DELETE_RULE "
                "FROM information_schema.REFERENTIAL_CONSTRAINTS "
                "WHERE CONSTRAINT_SCHEMA = DATABASE()"
            )
        ).mappings()
        rules = list(rows)

    expected_names = {
        constraint.name
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }
    assert {row["CONSTRAINT_NAME"] for row in rules} == expected_names
    assert all(row["UPDATE_RULE"] == "RESTRICT" for row in rules)
    assert all(row["DELETE_RULE"] == "RESTRICT" for row in rules)


def _assert_updated_at_on_update_ddl(engine: Engine) -> None:
    rows = _information_schema_columns(engine)
    updated_at_rows = {row["TABLE_NAME"]: row for row in rows if row["COLUMN_NAME"] == "updated_at"}

    assert set(updated_at_rows) == UPDATED_AT_TABLES
    for row in updated_at_rows.values():
        assert str(row["COLUMN_TYPE"]).lower() == "datetime(6)"
        assert str(row["COLUMN_DEFAULT"]).lower() == "current_timestamp(6)"
        assert "on update current_timestamp(6)" in str(row["EXTRA"]).lower()


def _assert_subscription_effective_unique_index(engine: Engine) -> None:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME "
                "FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'subscription_state_event' "
                "ORDER BY INDEX_NAME, SEQ_IN_INDEX"
            )
        ).mappings()
        statistics = list(rows)

    index_columns: dict[str, list[str]] = {}
    index_non_unique: dict[str, int] = {}
    for row in statistics:
        index_name = str(row["INDEX_NAME"])
        index_columns.setdefault(index_name, []).append(str(row["COLUMN_NAME"]))
        index_non_unique[index_name] = int(row["NON_UNIQUE"])

    expected_columns = ("subscription_id", "effective_at")
    unique_index_name = "uq_sub_state_event__sub_effective"
    assert tuple(index_columns[unique_index_name]) == expected_columns
    assert index_non_unique[unique_index_name] == 0
    assert {
        index_name
        for index_name, columns in index_columns.items()
        if tuple(columns) == expected_columns
    } == {unique_index_name}


def _information_schema_columns(engine: Engine) -> list[Mapping[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, CHARACTER_SET_NAME, "
                "COLLATION_NAME, COLUMN_DEFAULT, EXTRA "
                "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE()"
            )
        ).mappings()
        return [dict(row) for row in rows]


def _current_revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()
