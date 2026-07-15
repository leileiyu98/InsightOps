"""Load and hash deterministic seed dataset assets."""

import hashlib
import json
from pathlib import Path
from typing import Any

from insightops.seed.contracts import DatasetManifest, SeedDataset, SeedReference, SeedSource
from insightops.seed.validation import validate_business_dataset

MANIFEST_FILENAME = "manifest.json"


def load_seed_dataset(dataset_root: Path) -> SeedDataset:
    """Load a dataset directory, validate its sources, and verify its digest."""
    root = dataset_root.resolve()
    manifest = DatasetManifest.model_validate_json(
        (root / MANIFEST_FILENAME).read_text(encoding="utf-8")
    )
    sources = tuple(_load_source(root, source_file) for source_file in manifest.source_files)
    _validate_dataset_structure(manifest, sources)
    validate_business_dataset(manifest, sources)
    computed_digest = compute_dataset_digest(manifest, sources)
    if computed_digest != manifest.dataset_digest:
        raise ValueError(
            f"dataset digest mismatch: expected {manifest.dataset_digest}, got {computed_digest}"
        )
    return SeedDataset(
        manifest=manifest,
        sources=sources,
        computed_digest=computed_digest,
    )


def compute_dataset_digest(
    manifest: DatasetManifest,
    sources: tuple[SeedSource, ...],
) -> str:
    """Return a stable SHA-256 over compatibility metadata and canonical source content."""
    payload = {
        "manifest": manifest.model_dump(
            mode="json",
            exclude={
                "benchmark_catalog_id",
                "benchmark_catalog_version",
                "dataset_digest",
                "oracle_assets_digest",
            },
        ),
        "sources": [source.model_dump(mode="json") for source in sources],
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def canonicalize_seed_value(value: Any) -> str | int | bool | None:
    """Canonicalize database-returned scalar values for deterministic comparisons."""
    if value is None or isinstance(value, (str, int, bool)):
        return value
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    return str(value)


def _load_source(root: Path, source_file: str) -> SeedSource:
    source_path = (root / source_file).resolve()
    if not source_path.is_relative_to(root):
        raise ValueError(f"source file escapes dataset root: {source_file}")
    return SeedSource.model_validate_json(source_path.read_text(encoding="utf-8"))


def _validate_dataset_structure(
    manifest: DatasetManifest,
    sources: tuple[SeedSource, ...],
) -> None:
    source_ids = [source.source_id for source in sources]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("dataset source_id values must be unique")

    table_names: list[str] = []
    record_keys: set[tuple[str, str]] = set()
    row_counts: dict[str, int] = {}
    for source in sources:
        for table in source.tables:
            table_names.append(table.table_name)
            row_counts[table.table_name] = row_counts.get(table.table_name, 0) + len(table.records)
            for record in table.records:
                key = (table.table_name, record.record_id)
                if key in record_keys:
                    raise ValueError(f"duplicate logical seed record: {key}")
                record_keys.add(key)

    if tuple(table_names) != manifest.table_order:
        raise ValueError("source table order does not match manifest table_order")
    if row_counts != manifest.expected_row_counts:
        raise ValueError(
            f"row counts do not match manifest: expected {manifest.expected_row_counts}, "
            f"got {row_counts}"
        )

    for source in sources:
        for table in source.tables:
            for record in table.records:
                for value in record.values.values():
                    if isinstance(value, SeedReference):
                        reference_key = (value.table, value.record_id)
                        if reference_key not in record_keys:
                            raise ValueError(f"unresolved seed reference: {reference_key}")
