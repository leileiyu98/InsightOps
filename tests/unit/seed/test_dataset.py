"""Unit tests for deterministic dataset contracts and digest generation."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from insightops.seed.contracts import (
    DatasetManifest,
    SeedRecord,
    SeedReference,
    SeedSource,
    SeedTable,
)
from insightops.seed.dataset import compute_dataset_digest, load_seed_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _manifest() -> DatasetManifest:
    return DatasetManifest(
        dataset_id="test-dataset",
        dataset_version="1.0.0",
        dataset_digest="0" * 64,
        schema_revision="0003",
        business_definition_id="test-definitions",
        business_definition_version="1.0.0",
        business_timezone="America/Los_Angeles",
        snapshot_cutoff=datetime(2026, 1, 15, 8, tzinfo=UTC),
        source_files=("identity.json",),
        table_order=("organization",),
        expected_row_counts={"organization": 1},
    )


def _source(name: str = "Acme") -> SeedSource:
    return SeedSource(
        source_id="identity",
        tables=(
            SeedTable(
                table_name="organization",
                match_columns=("external_organization_id",),
                records=(
                    SeedRecord(
                        record_id="org-acme",
                        values={
                            "external_organization_id": "seed-org-acme",
                            "organization_name": name,
                        },
                    ),
                ),
            ),
        ),
    )


def test_dataset_digest_is_stable_and_content_sensitive() -> None:
    manifest = _manifest()
    first = compute_dataset_digest(manifest, (_source(),))
    second = compute_dataset_digest(manifest, (_source(),))
    changed = compute_dataset_digest(manifest, (_source("Changed"),))

    assert first == second
    assert first != changed
    assert len(first) == 64


def test_manifest_rejects_naive_snapshot_cutoff() -> None:
    values = _manifest().model_dump()
    values["snapshot_cutoff"] = datetime(2026, 1, 15, 8)
    with pytest.raises(ValidationError, match="timezone-aware"):
        DatasetManifest.model_validate(values)


def test_seed_table_requires_match_columns_in_every_record() -> None:
    with pytest.raises(ValidationError, match="missing match columns"):
        SeedTable(
            table_name="organization",
            match_columns=("external_organization_id",),
            records=(SeedRecord(record_id="org", values={"organization_name": "Missing"}),),
        )


def test_seed_reference_is_structured() -> None:
    reference = SeedReference(table="organization", record_id="org-acme")

    assert reference.model_dump() == {"table": "organization", "record_id": "org-acme"}


def test_m1_2a_dataset_manifest_and_digest_are_stable() -> None:
    dataset = load_seed_dataset(PROJECT_ROOT / "data" / "seed" / "m1_2a")

    assert dataset.computed_digest == dataset.manifest.dataset_digest
    assert dataset.computed_digest == (
        "97edd25bff257b0eb7cf803c125a761a7d485e5c51efd96725bfef7283aa987a"
    )
    assert sum(dataset.manifest.expected_row_counts.values()) == 149
    assert len(dataset.manifest.table_order) == 15
