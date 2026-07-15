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
    scenario_ids: tuple[str, ...]
    expected_result_shape: str = Field(min_length=1)
    parameters: dict[str, BenchmarkParameter] = Field(default_factory=dict)
    clarification_reason: str | None = None
    deferred_reason: str | None = None


class BenchmarkCase(PublicBenchmarkCase):
    """Full benchmark-only case including oracle paths never exposed to an Agent."""

    oracle_visibility: Literal["benchmark_only"] = "benchmark_only"
    gold_sql_path: str | None = None
    expected_result_path: str | None = None

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
        has_oracle = self.gold_sql_path is not None or self.expected_result_path is not None
        if self.status is BenchmarkStatus.EXECUTABLE:
            if self.gold_sql_path is None or self.expected_result_path is None:
                raise ValueError("executable cases require both Gold SQL and expected result paths")
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
            self.model_dump(exclude={"oracle_visibility", "gold_sql_path", "expected_result_path"})
        )


class BenchmarkCatalog(BaseModel):
    """Versioned collection of question bindings for one deterministic dataset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: str = Field(min_length=1)
    dataset_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    schema_revision: str = Field(pattern=r"^\d{4}$")
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

    dataset_id: str = Field(min_length=1)
    dataset_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
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
