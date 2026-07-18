"""Strict public and provider contracts for the Text2SQL demo."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from insightops.evaluation.contracts import CASE_ID_PATTERN, CLARIFICATION_CODE_PATTERN

QueryScalar = str | int | bool | None
_MAX_CLARIFICATION_LENGTH = 500


class QueryContract(BaseModel):
    """Forbid accidental expansion of model and API boundaries."""

    model_config = ConfigDict(extra="forbid", strict=True)


class StructuredCandidate(QueryContract):
    """Provider output with mutually exclusive SQL and clarification branches."""

    action: Literal["execute_sql", "request_clarification"]
    sql: str | None = Field(default=None, min_length=1)
    clarification_code: str | None = Field(
        default=None,
        pattern=CLARIFICATION_CODE_PATTERN,
    )
    clarification_question: str | None = Field(
        default=None,
        min_length=1,
        max_length=_MAX_CLARIFICATION_LENGTH,
    )

    @field_validator("clarification_question")
    @classmethod
    def validate_clarification_question(cls, value: str | None) -> str | None:
        return _safe_clarification_question(value)

    @model_validator(mode="after")
    def validate_action_fields(self) -> Self:
        if self.action == "execute_sql":
            if self.sql is None:
                raise ValueError("execute_sql requires sql")
            if self.clarification_code is not None or self.clarification_question is not None:
                raise ValueError("execute_sql cannot include clarification fields")
        elif (
            self.sql is not None
            or self.clarification_code is None
            or self.clarification_question is None
        ):
            raise ValueError("request_clarification requires only clarification fields")
        return self


class ProviderUsage(QueryContract):
    """Small, provider-neutral token accounting envelope."""

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class ProviderOutput(QueryContract):
    """Validated generation plus safe provider metadata."""

    candidate: StructuredCandidate
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    usage: ProviderUsage = Field(default_factory=ProviderUsage)


class QueryRequest(QueryContract):
    """Public query request."""

    question: str = Field(min_length=1, max_length=4_000)
    case_id: str | None = Field(default=None, pattern=CASE_ID_PATTERN)

    @field_validator("question")
    @classmethod
    def reject_blank_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must contain non-whitespace characters")
        return value


class QueryResponse(QueryContract):
    """Oracle-free API and CLI response for SQL or clarification."""

    request_id: str = Field(min_length=1)
    question: str
    action: Literal["execute_sql", "request_clarification"]
    generated_sql: str | None = None
    clarification_code: str | None = None
    clarification_question: str | None = Field(
        default=None,
        max_length=_MAX_CLARIFICATION_LENGTH,
    )
    evaluation_status: str = Field(min_length=1)
    failure_code: str | None = None
    columns: tuple[str, ...] = ()
    rows: tuple[dict[str, QueryScalar], ...] = ()
    business_summary: str | None = None
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)

    @field_validator("clarification_question")
    @classmethod
    def validate_clarification_question(cls, value: str | None) -> str | None:
        return _safe_clarification_question(value)

    @model_validator(mode="after")
    def validate_response_branch(self) -> Self:
        if self.action == "execute_sql":
            if self.generated_sql is None:
                raise ValueError("SQL responses require generated_sql")
            if self.clarification_code is not None or self.clarification_question is not None:
                raise ValueError("SQL responses cannot contain clarification fields")
        elif (
            self.generated_sql is not None
            or self.clarification_code is None
            or self.clarification_question is None
            or self.columns
            or self.rows
            or self.business_summary is not None
        ):
            raise ValueError("clarification responses require only clarification fields")
        return self


class QueryErrorBody(QueryContract):
    """Stable error body without raw provider or database details."""

    request_id: str
    code: str
    message: str


def _safe_clarification_question(value: str | None) -> str | None:
    if value is None:
        return None
    if not value.strip():
        raise ValueError("clarification_question must contain visible text")
    if "<" in value or ">" in value:
        raise ValueError("clarification_question cannot contain HTML markup")
    return value
