"""Validated contracts for version-controlled deterministic seed datasets."""

from dataclasses import dataclass
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SeedReference(BaseModel):
    """Reference another logical seed record without hard-coding a database ID."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    table: str = Field(min_length=1)
    record_id: str = Field(min_length=1)


SeedValue = str | int | bool | None | SeedReference


class SeedRecord(BaseModel):
    """One logical seed row with stable identity and optionally referenced foreign keys."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str = Field(min_length=1)
    values: dict[str, SeedValue]


class SeedTable(BaseModel):
    """Ordered records for one physical table and their database match key."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    table_name: str = Field(min_length=1)
    match_columns: tuple[str, ...] = Field(min_length=1)
    records: tuple[SeedRecord, ...]

    @model_validator(mode="after")
    def validate_records(self) -> Self:
        """Require unique logical IDs and match columns in every record."""
        record_ids = [record.record_id for record in self.records]
        if len(record_ids) != len(set(record_ids)):
            raise ValueError(f"duplicate record_id in {self.table_name}")
        for record in self.records:
            missing = set(self.match_columns) - set(record.values)
            if missing:
                raise ValueError(
                    f"record {record.record_id} is missing match columns: {sorted(missing)}"
                )
        return self


class SeedSource(BaseModel):
    """One version-controlled source file containing ordered table data."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1)
    tables: tuple[SeedTable, ...]


class DatasetManifest(BaseModel):
    """Immutable identity, compatibility, and integrity metadata for a dataset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: str = Field(min_length=1)
    dataset_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    dataset_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_revision: str = Field(pattern=r"^\d{4}$")
    business_definition_id: str = Field(min_length=1)
    business_definition_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    business_timezone: str = Field(min_length=1)
    snapshot_cutoff: datetime
    source_files: tuple[str, ...]
    table_order: tuple[str, ...]
    expected_row_counts: dict[str, int]

    @field_validator("snapshot_cutoff")
    @classmethod
    def validate_snapshot_cutoff(cls, value: datetime) -> datetime:
        """Require an explicit UTC cutoff rather than a naive wall-clock value."""
        utc_offset = value.utcoffset()
        if value.tzinfo is None or utc_offset is None:
            raise ValueError("snapshot_cutoff must be timezone-aware")
        if utc_offset.total_seconds() != 0:
            raise ValueError("snapshot_cutoff must be expressed in UTC")
        return value

    @field_validator("source_files")
    @classmethod
    def validate_source_files(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Keep dataset sources relative to their dataset directory."""
        if len(values) != len(set(values)):
            raise ValueError("source_files must be unique")
        for value in values:
            if value.startswith("/") or ".." in value.split("/"):
                raise ValueError("source_files must be safe relative paths")
        return values

    @model_validator(mode="after")
    def validate_tables(self) -> Self:
        """Keep table order and expected row-count keys aligned."""
        if len(self.table_order) != len(set(self.table_order)):
            raise ValueError("table_order must be unique")
        if set(self.table_order) != set(self.expected_row_counts):
            raise ValueError("table_order and expected_row_counts must contain the same tables")
        if any(count < 0 for count in self.expected_row_counts.values()):
            raise ValueError("expected row counts cannot be negative")
        return self


@dataclass(frozen=True)
class SeedDataset:
    """Fully loaded manifest and ordered source files."""

    manifest: DatasetManifest
    sources: tuple[SeedSource, ...]
    computed_digest: str
