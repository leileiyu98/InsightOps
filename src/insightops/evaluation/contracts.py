"""Immutable contracts for deterministic SQL evaluation artifacts."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from insightops.canonical import canonical_json_digest

SEMANTIC_VERSION_PATTERN = r"^\d+\.\d+\.\d+$"
DIGEST_PATTERN = r"^[0-9a-f]{64}$"
CASE_ID_PATTERN = r"^GQ-[A-Z]{3}-\d{3}$"
CLARIFICATION_CODE_PATTERN = r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$"
MAX_SQL_BYTES_V1 = 65_536

SemanticVersion = Annotated[str, Field(pattern=SEMANTIC_VERSION_PATTERN)]
Sha256Digest = Annotated[str, Field(pattern=DIGEST_PATTERN)]
CaseId = Annotated[str, Field(pattern=CASE_ID_PATTERN)]
ClarificationCode = Annotated[str, Field(pattern=CLARIFICATION_CODE_PATTERN)]


class ContractModel(BaseModel):
    """Strict, immutable base for versioned evaluation contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ExpectedAction(StrEnum):
    """Action assigned to one suite case."""

    EXECUTE_SQL = "execute_sql"
    REQUEST_CLARIFICATION = "request_clarification"
    DEFERRED = "deferred"


class CandidateAction(StrEnum):
    """Actions a candidate may submit for evaluable cases."""

    EXECUTE_SQL = "execute_sql"
    REQUEST_CLARIFICATION = "request_clarification"


class ComparisonMode(StrEnum):
    """Row-order policy selected for one executable case."""

    ORDERED = "ordered"
    UNORDERED = "unordered"


class EvaluationStatus(StrEnum):
    """Frozen top-level deterministic evaluation outcomes."""

    PASS = "PASS"
    FAIL_ACTION = "FAIL_ACTION"
    FAIL_STRUCTURE = "FAIL_STRUCTURE"
    FAIL_EXECUTION = "FAIL_EXECUTION"
    FAIL_RESULT = "FAIL_RESULT"
    NOT_EVALUATED = "NOT_EVALUATED"
    ABORTED = "ABORTED"


class StageStatus(StrEnum):
    """Outcome of an applicable evaluation stage."""

    PASS = "PASS"
    FAIL = "FAIL"


class EvaluationRunStatus(StrEnum):
    """Whether deterministic case evaluation completed or aborted at run level."""

    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"


class EvaluationAbortCode(StrEnum):
    """Frozen run-level abort reasons, never used as ordinary case scores."""

    INVALID_SUITE_MANIFEST = "invalid_suite_manifest"
    SUITE_DIGEST_MISMATCH = "suite_digest_mismatch"
    DATASET_BINDING_MISMATCH = "dataset_binding_mismatch"
    CATALOG_BINDING_MISMATCH = "catalog_binding_mismatch"
    SCHEMA_BINDING_MISMATCH = "schema_binding_mismatch"
    BUSINESS_DEFINITION_BINDING_MISMATCH = "business_definition_binding_mismatch"
    ORACLE_DIGEST_MISMATCH = "oracle_digest_mismatch"
    INVALID_SUBMISSION = "invalid_submission"
    SUBMISSION_SUITE_MISMATCH = "submission_suite_mismatch"
    DUPLICATE_CASE_RESPONSE = "duplicate_case_response"
    MISSING_CASE_RESPONSE = "missing_case_response"
    UNKNOWN_CASE_RESPONSE = "unknown_case_response"
    DEFERRED_CASE_RESPONSE_FORBIDDEN = "deferred_case_response_forbidden"
    EVALUATION_ENVIRONMENT_INVALID = "evaluation_environment_invalid"
    DATASET_VERIFICATION_FAILED = "dataset_verification_failed"
    READONLY_IDENTITY_VERIFICATION_FAILED = "readonly_identity_verification_failed"
    INTERNAL_CONTRACT_VIOLATION = "internal_contract_violation"


class EvaluationFailureCode(StrEnum):
    """Frozen M1.2B v1 secondary error taxonomy."""

    EXPECTED_EXECUTE_SQL = "expected_execute_sql"
    EXPECTED_REQUEST_CLARIFICATION = "expected_request_clarification"
    CLARIFICATION_CODE_MISMATCH = "clarification_code_mismatch"

    SQL_SIZE_LIMIT_EXCEEDED = "sql_size_limit_exceeded"
    PARSE_ERROR = "parse_error"
    MULTIPLE_STATEMENTS = "multiple_statements"
    NON_QUERY_STATEMENT = "non_query_statement"
    FORBIDDEN_DML = "forbidden_dml"
    FORBIDDEN_DDL = "forbidden_ddl"
    FORBIDDEN_COMMAND = "forbidden_command"
    FORBIDDEN_SYSTEM_SCHEMA = "forbidden_system_schema"
    FORBIDDEN_FILE_OPERATION = "forbidden_file_operation"
    FORBIDDEN_LOCKING_CLAUSE = "forbidden_locking_clause"
    FORBIDDEN_FUNCTION = "forbidden_function"
    FORBIDDEN_USER_VARIABLE = "forbidden_user_variable"
    UNKNOWN_TABLE = "unknown_table"
    MISSING_REQUIRED_TABLE = "missing_required_table"
    EXTRA_TABLE = "extra_table"
    WILDCARD_SELECT = "wildcard_select"
    UNKNOWN_BIND_PARAMETER = "unknown_bind_parameter"

    READONLY_TRANSACTION_FAILED = "readonly_transaction_failed"
    DATABASE_PERMISSION_DENIED = "database_permission_denied"
    QUERY_TIMEOUT = "query_timeout"
    DATABASE_ERROR = "database_error"
    ROW_LIMIT_EXCEEDED = "row_limit_exceeded"
    OUTPUT_LIMIT_EXCEEDED = "output_limit_exceeded"
    UNSUPPORTED_RESULT_TYPE = "unsupported_result_type"
    RESULT_NORMALIZATION_ERROR = "result_normalization_error"

    COLUMN_COUNT_MISMATCH = "column_count_mismatch"
    COLUMN_NAME_MISMATCH = "column_name_mismatch"
    COLUMN_ORDER_MISMATCH = "column_order_mismatch"
    ROW_COUNT_MISMATCH = "row_count_mismatch"
    TYPE_MISMATCH = "type_mismatch"
    NULL_MISMATCH = "null_mismatch"
    VALUE_MISMATCH = "value_mismatch"
    ORDERED_ROWS_MISMATCH = "ordered_rows_mismatch"
    UNORDERED_MULTISET_MISMATCH = "unordered_multiset_mismatch"

    DEFERRED_SCHEMA_DEPENDENCY = "deferred_schema_dependency"


class SqlStatementType(StrEnum):
    """Stable root classifications independent of sqlglot class names."""

    EMPTY = "empty"
    SELECT = "select"
    UNION = "union"
    DML = "dml"
    DDL = "ddl"
    COMMAND = "command"
    UNKNOWN = "unknown"


class NormalizedValueType(StrEnum):
    """Portable result scalar types used by strict comparison."""

    NULL = "null"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    DECIMAL = "decimal"
    DATETIME = "datetime"
    STRING = "string"


class DatasetBinding(ContractModel):
    """Dataset identity and content binding."""

    dataset_id: str = Field(min_length=1)
    dataset_version: SemanticVersion
    dataset_digest: Sha256Digest


class CatalogBinding(ContractModel):
    """Gold catalog identity binding without oracle locations."""

    catalog_id: str = Field(min_length=1)
    catalog_version: SemanticVersion


class BusinessDefinitionBinding(ContractModel):
    """Versioned Business Definitions content binding."""

    business_definition_id: str = Field(min_length=1)
    business_definition_version: SemanticVersion
    business_definition_digest: Sha256Digest


class ComparisonPolicy(ContractModel):
    """Frozen exact result-comparison policy for evaluator v1."""

    columns: Literal["exact"]
    column_order: Literal["exact"]
    types: Literal["exact"]
    nulls: Literal["exact"]
    decimals: Literal["exact"]
    datetimes: Literal["exact_microseconds"]
    ordered_rows: Literal["exact_sequence"]
    unordered_rows: Literal["canonical_multiset"]
    numeric_tolerance: None = None


class ExecutionLimits(ContractModel):
    """Limits bound by the suite and not overridable by submissions."""

    max_sql_bytes: int = Field(gt=0, le=MAX_SQL_BYTES_V1)
    timeout_ms: int = Field(gt=0)
    max_rows: int = Field(gt=0)
    max_output_bytes: int = Field(gt=0)


class EvaluationSuiteCase(ContractModel):
    """Public routing metadata for one Gold Question."""

    case_id: CaseId
    expected_action: ExpectedAction
    clarification_code: ClarificationCode | None = None
    comparison_mode: ComparisonMode | None = None
    expected_column_types: dict[str, NormalizedValueType] | None = None

    @model_validator(mode="after")
    def validate_action_metadata(self) -> Self:
        if self.expected_action is ExpectedAction.EXECUTE_SQL:
            if (
                self.comparison_mode is None
                or self.clarification_code is not None
                or not self.expected_column_types
            ):
                raise ValueError(
                    "executable cases require comparison_mode and expected_column_types"
                )
        elif self.expected_action is ExpectedAction.REQUEST_CLARIFICATION:
            if (
                self.clarification_code is None
                or self.comparison_mode is not None
                or self.expected_column_types is not None
            ):
                raise ValueError("clarification cases require only clarification_code")
        elif (
            self.clarification_code is not None
            or self.comparison_mode is not None
            or self.expected_column_types is not None
        ):
            raise ValueError("deferred cases cannot define evaluation metadata")
        return self


class EvaluationSuiteManifest(ContractModel):
    """Versioned deterministic evaluation-suite manifest."""

    suite_id: str = Field(min_length=1)
    suite_version: SemanticVersion
    suite_digest: Sha256Digest
    evaluator_id: str = Field(min_length=1)
    evaluator_version: SemanticVersion
    evaluator_contract_version: SemanticVersion
    digest_algorithm: Literal["sha256-canonical-json-v1"]
    dataset: DatasetBinding
    catalog: CatalogBinding
    schema_revision: str = Field(pattern=r"^\d{4}$")
    business_definition: BusinessDefinitionBinding
    oracle_assets_digest: Sha256Digest
    cases: tuple[EvaluationSuiteCase, ...] = Field(min_length=1)
    comparison_policy: ComparisonPolicy
    execution_limits: ExecutionLimits

    @model_validator(mode="after")
    def validate_case_ids(self) -> Self:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("evaluation suite case_id values must be unique")
        return self

    def computed_digest(self) -> str:
        """Compute the suite digest without its self-referential field."""
        return canonical_json_digest(self.model_dump(mode="json", exclude={"suite_digest"}))


class ExecuteSqlResponse(ContractModel):
    """Candidate SQL response; syntax and safety are intentionally not inspected here."""

    action: Literal["execute_sql"]
    case_id: CaseId
    sql: str = Field(min_length=1)

    @field_validator("sql")
    @classmethod
    def validate_sql_size(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_SQL_BYTES_V1:
            raise ValueError(f"sql must not exceed {MAX_SQL_BYTES_V1} UTF-8 bytes")
        return value


class RequestClarificationResponse(ContractModel):
    """Candidate request for the suite's frozen clarification reason."""

    action: Literal["request_clarification"]
    case_id: CaseId
    clarification_code: ClarificationCode


CandidateCaseResponse = Annotated[
    ExecuteSqlResponse | RequestClarificationResponse,
    Field(discriminator="action"),
]


class CandidateSubmission(ContractModel):
    """Oracle-free candidate responses bound to one evaluation suite."""

    submission_id: str = Field(min_length=1)
    suite_id: str = Field(min_length=1)
    suite_version: SemanticVersion
    responses: tuple[CandidateCaseResponse, ...]

    @model_validator(mode="after")
    def validate_case_ids(self) -> Self:
        case_ids = [response.case_id for response in self.responses]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("candidate response case_id values must be unique")
        return self

    def computed_digest(self) -> str:
        """Hash the complete oracle-free submission contract."""
        return canonical_json_digest(self.model_dump(mode="json"))


class SqlAnalysisResult(ContractModel):
    """Deterministic AST analysis output without parser exception details."""

    case_id: CaseId
    statement_count: int = Field(ge=0)
    statement_type: SqlStatementType
    cte_names: tuple[str, ...]
    referenced_tables: tuple[str, ...]
    bind_names: tuple[str, ...]
    has_projection_wildcard: bool
    violations: tuple[EvaluationFailureCode, ...]
    analysis_digest: Sha256Digest

    @model_validator(mode="after")
    def validate_deterministic_collections(self) -> Self:
        for name in ("cte_names", "referenced_tables", "bind_names"):
            values = getattr(self, name)
            if len(values) != len(set(values)) or values != tuple(sorted(values)):
                raise ValueError(f"{name} must be sorted and unique")
        violation_values = tuple(code.value for code in self.violations)
        if len(violation_values) != len(set(violation_values)) or violation_values != tuple(
            sorted(violation_values)
        ):
            raise ValueError("violations must be sorted and unique")
        if self.analysis_digest != self.computed_digest():
            raise ValueError("SQL analysis digest mismatch")
        return self

    def computed_digest(self) -> str:
        """Hash analysis semantics while excluding the digest itself."""
        return canonical_json_digest(self.model_dump(mode="json", exclude={"analysis_digest"}))


NormalizedScalar = str | int | bool | None


class NormalizedCell(ContractModel):
    """One strictly typed canonical database or oracle scalar."""

    value_type: NormalizedValueType
    value: NormalizedScalar

    @model_validator(mode="after")
    def validate_value_type(self) -> Self:
        valid = {
            NormalizedValueType.NULL: self.value is None,
            NormalizedValueType.BOOLEAN: type(self.value) is bool,
            NormalizedValueType.INTEGER: type(self.value) is int,
            NormalizedValueType.DECIMAL: isinstance(self.value, str),
            NormalizedValueType.DATETIME: isinstance(self.value, str),
            NormalizedValueType.STRING: isinstance(self.value, str),
        }
        if not valid[self.value_type]:
            raise ValueError(f"value does not match normalized type {self.value_type}")
        return self


class NormalizedResult(ContractModel):
    """Canonical typed rows used by exact ordered or multiset comparison."""

    columns: tuple[str, ...]
    rows: tuple[tuple[NormalizedCell, ...], ...]
    result_digest: Sha256Digest

    @model_validator(mode="after")
    def validate_rows_and_digest(self) -> Self:
        if len(self.columns) != len(set(self.columns)):
            raise ValueError("normalized result columns must be unique")
        if any(len(row) != len(self.columns) for row in self.rows):
            raise ValueError("normalized row width must match columns")
        if self.result_digest != self.computed_digest():
            raise ValueError("normalized result digest mismatch")
        return self

    def computed_digest(self) -> str:
        """Hash normalized columns and typed rows."""
        return canonical_json_digest(self.model_dump(mode="json", exclude={"result_digest"}))


class ResultComparison(ContractModel):
    """Deterministic exact-comparison outcome without row disclosure."""

    matches: bool
    failure_code: EvaluationFailureCode | None = None
    comparison_digest: Sha256Digest

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.matches is (self.failure_code is not None):
            raise ValueError("comparison success and failure_code disagree")
        if self.comparison_digest != self.computed_digest():
            raise ValueError("comparison digest mismatch")
        return self

    def computed_digest(self) -> str:
        """Hash comparison outcome without its self-reference."""
        return canonical_json_digest(self.model_dump(mode="json", exclude={"comparison_digest"}))


class StageEvaluationResult(ContractModel):
    """Minimal deterministic outcome for one applicable pipeline stage."""

    status: StageStatus
    failure_code: EvaluationFailureCode | None = None
    result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def validate_failure_code(self) -> Self:
        if self.status is StageStatus.PASS and self.failure_code is not None:
            raise ValueError("successful stages cannot have failure_code")
        if self.status is StageStatus.FAIL and self.failure_code is None:
            raise ValueError("failed stages require failure_code")
        return self


class CaseDigests(ContractModel):
    """Digests emitted by applicable stages without exposing oracle contents."""

    candidate_sql_digest: Sha256Digest | None = None
    expected_result_digest: Sha256Digest | None = None
    actual_result_digest: Sha256Digest | None = None
    case_evaluation_digest: Sha256Digest


class CaseEvaluationResult(ContractModel):
    """One case outcome with earliest-failure stage constraints."""

    case_id: CaseId
    expected_action: ExpectedAction
    actual_action: CandidateAction | None
    status: EvaluationStatus
    failure_code: EvaluationFailureCode | None = None
    secondary_codes: tuple[EvaluationFailureCode, ...] = ()
    action_result: StageEvaluationResult | None = None
    structure_result: StageEvaluationResult | None = None
    execution_result: StageEvaluationResult | None = None
    comparison_result: StageEvaluationResult | None = None
    digests: CaseDigests

    @model_validator(mode="after")
    def validate_stage_sequence(self) -> Self:
        if self.status is EvaluationStatus.ABORTED:
            raise ValueError("ABORTED is run-level and cannot score a case")
        if len(self.secondary_codes) != len(set(self.secondary_codes)):
            raise ValueError("secondary_codes must be unique")
        if self.failure_code is not None and self.failure_code in self.secondary_codes:
            raise ValueError("failure_code cannot also be a secondary code")

        if self.status is EvaluationStatus.PASS:
            self._require_primary_failure(False)
            self._require_stage(self.action_result, StageStatus.PASS, "action")
            if (
                self.expected_action is ExpectedAction.EXECUTE_SQL
                and self.actual_action is CandidateAction.EXECUTE_SQL
            ):
                self._require_stage(self.structure_result, StageStatus.PASS, "structure")
                self._require_stage(self.execution_result, StageStatus.PASS, "execution")
                self._require_stage(self.comparison_result, StageStatus.PASS, "comparison")
            elif (
                self.expected_action is ExpectedAction.REQUEST_CLARIFICATION
                and self.actual_action is CandidateAction.REQUEST_CLARIFICATION
            ):
                self._require_absent("structure", "execution", "comparison")
            else:
                raise ValueError("PASS requires actual_action to match expected_action")
        elif self.status is EvaluationStatus.FAIL_ACTION:
            self._require_primary_failure(True)
            self._require_stage(self.action_result, StageStatus.FAIL, "action")
            self._require_matching_failure(self.action_result)
            if self.expected_action is ExpectedAction.DEFERRED:
                raise ValueError("deferred cases cannot have FAIL_ACTION")
            self._require_absent("structure", "execution", "comparison")
        elif self.status is EvaluationStatus.FAIL_STRUCTURE:
            self._require_primary_failure(True)
            self._require_sql_action()
            self._require_stage(self.action_result, StageStatus.PASS, "action")
            self._require_stage(self.structure_result, StageStatus.FAIL, "structure")
            self._require_matching_failure(self.structure_result)
            self._require_absent("execution", "comparison")
        elif self.status is EvaluationStatus.FAIL_EXECUTION:
            self._require_primary_failure(True)
            self._require_sql_action()
            self._require_stage(self.action_result, StageStatus.PASS, "action")
            self._require_stage(self.structure_result, StageStatus.PASS, "structure")
            self._require_stage(self.execution_result, StageStatus.FAIL, "execution")
            self._require_matching_failure(self.execution_result)
            self._require_absent("comparison")
        elif self.status is EvaluationStatus.FAIL_RESULT:
            self._require_primary_failure(True)
            self._require_sql_action()
            self._require_stage(self.action_result, StageStatus.PASS, "action")
            self._require_stage(self.structure_result, StageStatus.PASS, "structure")
            self._require_stage(self.execution_result, StageStatus.PASS, "execution")
            self._require_stage(self.comparison_result, StageStatus.FAIL, "comparison")
            self._require_matching_failure(self.comparison_result)
        else:
            self._require_primary_failure(True)
            if (
                self.expected_action is not ExpectedAction.DEFERRED
                or self.actual_action is not None
            ):
                raise ValueError("NOT_EVALUATED is reserved for deferred cases")
            self._require_absent("action", "structure", "execution", "comparison")
        if self.digests.case_evaluation_digest != self.computed_digest():
            raise ValueError("case evaluation digest mismatch")
        return self

    def computed_digest(self) -> str:
        """Hash one case outcome without its self-referential digest."""
        return canonical_json_digest(
            self.model_dump(
                mode="json",
                exclude={"digests": {"case_evaluation_digest"}},
            )
        )

    def _require_primary_failure(self, required: bool) -> None:
        if required and self.failure_code is None:
            raise ValueError(f"{self.status} requires failure_code")
        if not required and self.failure_code is not None:
            raise ValueError(f"{self.status} cannot have failure_code")

    def _require_sql_action(self) -> None:
        if (
            self.expected_action is not ExpectedAction.EXECUTE_SQL
            or self.actual_action is not CandidateAction.EXECUTE_SQL
        ):
            raise ValueError(f"{self.status} requires matching execute_sql actions")

    def _require_matching_failure(self, result: StageEvaluationResult | None) -> None:
        if result is None or result.failure_code is not self.failure_code:
            raise ValueError(f"{self.status} failure_code must match its failed stage")

    def _require_stage(
        self,
        result: StageEvaluationResult | None,
        status: StageStatus,
        name: str,
    ) -> None:
        if result is None or result.status is not status:
            raise ValueError(f"{self.status} requires {name} stage {status}")

    def _require_absent(self, *stage_names: str) -> None:
        for stage_name in stage_names:
            if getattr(self, f"{stage_name}_result") is not None:
                raise ValueError(f"{self.status} cannot have {stage_name} result")


class EvaluationSummary(ContractModel):
    """Deterministic aggregate counts for a suite evaluation."""

    passed: int = Field(ge=0)
    failed_action: int = Field(ge=0)
    failed_structure: int = Field(ge=0)
    failed_execution: int = Field(ge=0)
    failed_result: int = Field(ge=0)
    not_evaluated: int = Field(ge=0)


class DeterministicEvaluationPayload(ContractModel):
    """Portable evaluation result; operational run metadata is excluded."""

    suite_id: str = Field(min_length=1)
    suite_version: SemanticVersion
    suite_digest: Sha256Digest
    submission_id: str = Field(min_length=1)
    submission_digest: Sha256Digest
    evaluator_id: str = Field(min_length=1)
    evaluator_version: SemanticVersion
    evaluator_contract_version: SemanticVersion
    run_status: EvaluationRunStatus
    abort_code: EvaluationAbortCode | None = None
    case_results: tuple[CaseEvaluationResult, ...]
    summary: EvaluationSummary
    deterministic_digest: Sha256Digest

    @model_validator(mode="after")
    def validate_case_results(self) -> Self:
        if self.run_status is not EvaluationRunStatus.COMPLETED or self.abort_code is not None:
            raise ValueError("deterministic evaluation payload is completed-run only")
        case_ids = [result.case_id for result in self.case_results]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("case result IDs must be unique")
        if case_ids != sorted(case_ids):
            raise ValueError("case results must be sorted by case_id")
        counts = {
            EvaluationStatus.PASS: self.summary.passed,
            EvaluationStatus.FAIL_ACTION: self.summary.failed_action,
            EvaluationStatus.FAIL_STRUCTURE: self.summary.failed_structure,
            EvaluationStatus.FAIL_EXECUTION: self.summary.failed_execution,
            EvaluationStatus.FAIL_RESULT: self.summary.failed_result,
            EvaluationStatus.NOT_EVALUATED: self.summary.not_evaluated,
        }
        actual = {status: 0 for status in counts}
        for result in self.case_results:
            actual[result.status] += 1
        if actual != counts:
            raise ValueError("evaluation summary does not match case results")
        return self

    def computed_digest(self) -> str:
        """Hash only deterministic fields and exclude the digest itself."""
        return canonical_json_digest(self.model_dump(mode="json", exclude={"deterministic_digest"}))


class RunEnvelope(ContractModel):
    """Non-deterministic operational metadata excluded from evaluation digests."""

    run_id: UUID
    timestamp: datetime
    duration_ms: int = Field(ge=0)
    host: str = Field(min_length=1)

    @field_validator("timestamp")
    @classmethod
    def validate_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("run timestamp must be timezone-aware")
        return value


class EvaluationReport(ContractModel):
    """Evaluation report separating deterministic content from its run envelope."""

    run_status: EvaluationRunStatus
    abort_code: EvaluationAbortCode | None = None
    deterministic_payload: DeterministicEvaluationPayload | None = None
    run_envelope: RunEnvelope

    @model_validator(mode="after")
    def validate_report_shape(self) -> Self:
        if self.run_status is EvaluationRunStatus.ABORTED:
            if self.abort_code is None or self.deterministic_payload is not None:
                raise ValueError("aborted report requires only abort_code and run_envelope")
            return self
        if self.abort_code is not None or self.deterministic_payload is None:
            raise ValueError("completed report requires deterministic_payload without abort_code")
        if self.deterministic_payload.run_status is not EvaluationRunStatus.COMPLETED:
            raise ValueError("completed report requires completed deterministic payload")
        if self.computed_digest() != self.deterministic_payload.deterministic_digest:
            raise ValueError("deterministic evaluation digest mismatch")
        return self

    def computed_digest(self) -> str | None:
        """Return the completed-run digest, or no digest for an aborted run."""
        if self.deterministic_payload is None:
            return None
        return self.deterministic_payload.computed_digest()
