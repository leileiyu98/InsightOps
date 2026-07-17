"""MySQL checks for isolated benchmark authoring safety gates."""

from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from insightops.benchmark.authoring import (
    assert_database_matches_dataset,
    assert_database_revision,
)
from insightops.seed.dataset import load_seed_dataset
from insightops.seed.loader import DatasetLoader

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATASET_ROOT = PROJECT_ROOT / "data" / "seed" / "m1_2a"


@pytest.fixture(scope="module")
def seeded_authoring_database(database_engine: Engine) -> Generator[Engine]:
    dataset = load_seed_dataset(DATASET_ROOT)
    loader = DatasetLoader(database_engine, dataset, app_env="test")
    loader.load()
    try:
        yield database_engine
    finally:
        loader.unload()


def test_authoring_rejects_wrong_alembic_revision(seeded_authoring_database: Engine) -> None:
    with seeded_authoring_database.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("UPDATE alembic_version SET version_num = '0003'"))
            with pytest.raises(ValueError, match="revision mismatch"):
                assert_database_revision(connection, "0004")
        finally:
            transaction.rollback()


def test_authoring_rejects_an_extra_business_row(seeded_authoring_database: Engine) -> None:
    dataset = load_seed_dataset(DATASET_ROOT)
    with seeded_authoring_database.connect() as connection:
        transaction = connection.begin()
        try:
            assert_database_matches_dataset(connection, dataset)
            connection.execute(
                text(
                    "INSERT INTO organization "
                    "(external_organization_id, organization_name, status, registered_at, "
                    "closed_at, is_test, recorded_at, updated_at) VALUES "
                    "('authoring-extra-org', 'Authoring Extra', 'active', "
                    "'2025-01-01 00:00:00.000000', NULL, 0, "
                    "'2025-01-01 00:00:00.000000', '2025-01-01 00:00:00.000000')"
                )
            )
            with pytest.raises(ValueError, match="non-canonical row counts"):
                assert_database_matches_dataset(connection, dataset)
        finally:
            transaction.rollback()
