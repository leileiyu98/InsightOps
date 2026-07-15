"""Real MySQL lifecycle tests for the deterministic M1.2A dataset."""

from pathlib import Path

from sqlalchemy import Engine, func, select

from insightops.db.models import Base
from insightops.seed.dataset import load_seed_dataset
from insightops.seed.loader import DatasetLoader

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_seed_load_verify_unload_is_repeatable(database_engine: Engine) -> None:
    dataset = load_seed_dataset(PROJECT_ROOT / "data" / "seed" / "m1_2a")
    loader = DatasetLoader(database_engine, dataset, app_env="test")

    first_load = loader.load()
    first_verify = loader.verify()
    first_unload = loader.unload()
    second_load = loader.load()
    second_verify = loader.verify()
    second_unload = loader.unload()

    expected = dataset.manifest.expected_row_counts
    assert first_load == expected
    assert first_verify == expected
    assert first_unload == expected
    assert second_load == expected
    assert second_verify == expected
    assert second_unload == expected

    with database_engine.connect() as connection:
        for table_name in dataset.manifest.table_order:
            table = Base.metadata.tables[table_name]
            assert connection.scalar(select(func.count()).select_from(table)) == 0


def test_seed_second_load_is_idempotent(database_engine: Engine) -> None:
    dataset = load_seed_dataset(PROJECT_ROOT / "data" / "seed" / "m1_2a")
    loader = DatasetLoader(database_engine, dataset, app_env="test")

    try:
        assert loader.load() == dataset.manifest.expected_row_counts
        assert loader.load() == dataset.manifest.expected_row_counts
        assert loader.verify() == dataset.manifest.expected_row_counts
    finally:
        loader.unload()
