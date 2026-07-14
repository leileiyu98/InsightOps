"""Real MySQL tests for UTC sessions and server-maintained timestamps."""

from datetime import datetime

from sqlalchemy import Engine, text


def test_every_new_physical_connection_uses_utc(database_engine: Engine) -> None:
    database_engine.dispose()
    with database_engine.connect() as first_connection:
        assert first_connection.execute(text("SELECT @@session.time_zone")).scalar_one() == "+00:00"

    database_engine.dispose()
    with database_engine.connect() as second_connection:
        assert (
            second_connection.execute(text("SELECT @@session.time_zone")).scalar_one() == "+00:00"
        )


def test_mysql_automatically_updates_updated_at(database_engine: Engine) -> None:
    with database_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO organization "
                "(external_organization_id, organization_name, status, registered_at, updated_at) "
                "VALUES (:external_id, 'Timestamp Test', 'active', :registered_at, :old_updated_at)"
            ),
            {
                "external_id": "org-updated-at-behavior",
                "registered_at": datetime(2025, 1, 1),
                "old_updated_at": datetime(2000, 1, 1),
            },
        )
        connection.execute(
            text(
                "UPDATE organization SET organization_name = 'Timestamp Test Updated' "
                "WHERE external_organization_id = :external_id"
            ),
            {"external_id": "org-updated-at-behavior"},
        )
        updated_at = connection.execute(
            text(
                "SELECT updated_at FROM organization WHERE external_organization_id = :external_id"
            ),
            {"external_id": "org-updated-at-behavior"},
        ).scalar_one()

        assert isinstance(updated_at, datetime)
        assert updated_at > datetime(2000, 1, 1)

        connection.rollback()
