"""Validated benchmark metadata with explicit oracle isolation."""

from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

BenchmarkParameter = str | int | bool | None
ExpectedValue = str | int | bool | None


class BenchmarkStatus(StrEnum):
    """Permitted behavior for one catalog question at the current schema revision."""

    EXECUTABLE = "executable"
    CLARIFICATION_REQUIRED = "clarification_required"
    DEFERRED = "deferred"


class PublicBenchmarkCase(BaseModel):
    """Question metadata safe for future runtime schema retrieval or prompting."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^GQ-[A-Z]{3}-\d{3}$")
    question: str = Field(min_length=1)
    difficulty: Literal["L1", "L2", "L3"]
    status: BenchmarkStatus
    domains: tuple[str, ...] = Field(min_length=1)
    metrics: tuple[str, ...]
    required_tables: tuple[str, ...]
    phenomenon_ids: tuple[str, ...]
    partial_phenomenon_coverage: dict[str, str] = Field(default_factory=dict)
    scenario_ids: tuple[str, ...]
    expected_result_shape: str = Field(min_length=1)
    parameters: dict[str, BenchmarkParameter] = Field(default_factory=dict)
    clarification_reason: str | None = None
    deferred_reason: str | None = None

    @model_validator(mode="after")
    def validate_phenomenon_coverage(self) -> Self:
        """Keep full and explicitly partial phenomenon claims disjoint."""
        overlap = set(self.phenomenon_ids) & set(self.partial_phenomenon_coverage)
        if overlap:
            raise ValueError(f"phenomena cannot be both full and partial: {sorted(overlap)}")
        if any(not reason.strip() for reason in self.partial_phenomenon_coverage.values()):
            raise ValueError("partial phenomenon coverage requires a non-empty reason")
        return self


class BenchmarkCase(PublicBenchmarkCase):
    """Full benchmark-only case including oracle paths never exposed to an Agent."""

    oracle_visibility: Literal["benchmark_only"] = "benchmark_only"
    gold_sql_path: str | None = None
    expected_result_path: str | None = None
    gold_sql_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    expected_result_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("gold_sql_path", "expected_result_path")
    @classmethod
    def validate_oracle_path(cls, value: str | None) -> str | None:
        """Keep oracle assets inside the version-controlled benchmark directory."""
        if value is not None and (value.startswith("/") or ".." in value.split("/")):
            raise ValueError("oracle paths must be safe relative paths")
        return value

    @model_validator(mode="after")
    def validate_status_contract(self) -> Self:
        """Prevent deferred or clarification cases from accidentally gaining an oracle."""
        oracle_values = (
            self.gold_sql_path,
            self.expected_result_path,
            self.gold_sql_digest,
            self.expected_result_digest,
        )
        has_oracle = any(value is not None for value in oracle_values)
        if self.status is BenchmarkStatus.EXECUTABLE:
            if any(value is None for value in oracle_values):
                raise ValueError("executable cases require oracle paths and digests")
            if self.clarification_reason is not None or self.deferred_reason is not None:
                raise ValueError("executable cases cannot have clarification/deferred reasons")
        elif self.status is BenchmarkStatus.CLARIFICATION_REQUIRED:
            if self.clarification_reason is None:
                raise ValueError("clarification cases require clarification_reason")
            if has_oracle or self.deferred_reason is not None:
                raise ValueError("clarification cases cannot expose oracle assets")
        else:
            if self.deferred_reason is None:
                raise ValueError("deferred cases require deferred_reason")
            if has_oracle or self.clarification_reason is not None:
                raise ValueError("deferred cases cannot expose oracle assets")
        return self

    def to_public_case(self) -> PublicBenchmarkCase:
        """Drop all oracle-only fields before runtime consumption."""
        return PublicBenchmarkCase.model_validate(
            self.model_dump(
                exclude={
                    "expected_result_digest",
                    "expected_result_path",
                    "gold_sql_digest",
                    "gold_sql_path",
                    "oracle_visibility",
                }
            )
        )


class BenchmarkCatalog(BaseModel):
    """Versioned collection of question bindings for one deterministic dataset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    catalog_id: str = Field(min_length=1)
    catalog_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    dataset_id: str = Field(min_length=1)
    dataset_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    dataset_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_revision: str = Field(pattern=r"^\d{4}$")
    business_definition_id: str = Field(min_length=1)
    business_definition_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    business_definition_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    oracle_assets_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    cases: tuple[BenchmarkCase, ...]

    @model_validator(mode="after")
    def validate_case_ids(self) -> Self:
        """Require one binding per Gold Question ID."""
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("benchmark case_id values must be unique")
        return self


class ExpectedResult(BaseModel):
    """Canonical typed rows produced by one benchmark-only Gold SQL oracle."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    catalog_id: str = Field(min_length=1)
    catalog_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    dataset_id: str = Field(min_length=1)
    dataset_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    dataset_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_revision: str = Field(pattern=r"^\d{4}$")
    business_definition_id: str = Field(min_length=1)
    business_definition_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    business_definition_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    oracle_assets_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_id: str = Field(pattern=r"^GQ-[A-Z]{3}-\d{3}$")
    columns: tuple[str, ...] = Field(min_length=1)
    ordered_by: tuple[str, ...]
    rows: tuple[dict[str, ExpectedValue], ...]

    @model_validator(mode="after")
    def validate_rows(self) -> Self:
        """Require each result row to exactly match the declared columns."""
        column_set = set(self.columns)
        if not set(self.ordered_by) <= column_set:
            raise ValueError("ordered_by must reference declared columns")
        for row in self.rows:
            if set(row) != column_set:
                raise ValueError("expected result row columns do not match declaration")
        return self


class BaselineCaseIndex(BaseModel):
    """Compact immutable digest record for one baseline executable case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^GQ-[A-Z]{3}-\d{3}$")
    expected_result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    business_result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class BaselineIndex(BaseModel):
    """Compact v1.0.0 benchmark baseline independent of CI Git history."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: str = Field(min_length=1)
    dataset_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    dataset_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    baseline_git_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    catalog_id: str = Field(min_length=1)
    catalog_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    catalog_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    oracle_assets_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    cases: tuple[BaselineCaseIndex, ...]

    @model_validator(mode="after")
    def validate_cases(self) -> Self:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != 16 or len(case_ids) != len(set(case_ids)):
            raise ValueError("baseline index requires 16 unique executable cases")
        return self


class BaselineDeltaCase(BaseModel):
    """Reviewed business-result delta for one prior executable case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^GQ-[A-Z]{3}-\d{3}$")
    old_expected_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    new_expected_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    old_business_result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    new_business_result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    changed: bool
    change_reason: str = Field(min_length=1)
    scenario_ids: tuple[str, ...]

    @model_validator(mode="after")
    def validate_change_contract(self) -> Self:
        computed_changed = self.old_business_result_digest != self.new_business_result_digest
        if self.changed is not computed_changed:
            raise ValueError("delta changed flag disagrees with business-result digests")
        if self.changed:
            if self.change_reason == "unchanged" or not self.scenario_ids:
                raise ValueError("changed delta requires a reviewed reason and scenarios")
        elif self.change_reason != "unchanged" or self.scenario_ids:
            raise ValueError("unchanged delta cannot claim a reason or scenario")
        return self


class BaselineDeltaReport(BaseModel):
    """Reviewed v1.0.0 to v1.1.0 benchmark delta contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    from_dataset_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    from_dataset_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    from_catalog_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    from_oracle_assets_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    from_git_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    to_dataset_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    to_dataset_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    to_oracle_assets_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    old_cases: tuple[BaselineDeltaCase, ...]
    new_cases: tuple[str, ...]

    @model_validator(mode="after")
    def validate_case_partition(self) -> Self:
        old_ids = [case.case_id for case in self.old_cases]
        if len(old_ids) != 16 or len(old_ids) != len(set(old_ids)):
            raise ValueError("delta report requires 16 unique baseline cases")
        if len(self.new_cases) != 12 or len(self.new_cases) != len(set(self.new_cases)):
            raise ValueError("delta report requires 12 unique new executable cases")
        if set(old_ids) & set(self.new_cases):
            raise ValueError("old and new delta case sets must be disjoint")
        return self
