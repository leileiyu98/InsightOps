"""Deterministic MySQL AST analysis for candidate SQL without execution."""

from collections.abc import Collection
from typing import cast

import sqlglot
from sqlglot import Dialect, exp
from sqlglot.errors import ParseError
from sqlglot.optimizer.scope import traverse_scope

from insightops.canonical import canonical_json_digest
from insightops.evaluation.contracts import (
    EvaluationFailureCode,
    SqlAnalysisResult,
    SqlStatementType,
)

MYSQL_DIALECT = "mysql"
SYSTEM_SCHEMAS = frozenset({"mysql", "information_schema", "performance_schema", "sys"})
DANGEROUS_FUNCTIONS = frozenset({"SLEEP", "BENCHMARK", "GET_LOCK", "RELEASE_LOCK", "IS_FREE_LOCK"})
FILE_FUNCTIONS = frozenset({"LOAD_FILE"})

_DML_ROOTS = (exp.Insert, exp.Update, exp.Delete, exp.Merge)
_DDL_ROOTS = (exp.Create, exp.Alter, exp.Drop, exp.TruncateTable)
_COMMAND_ROOTS = (exp.Command, exp.Transaction, exp.Commit, exp.Rollback, exp.Set, exp.Use)


def analyze_candidate_sql(
    *,
    case_id: str,
    sql: str,
    required_tables: Collection[str],
    allowed_tables: Collection[str],
    allowed_bind_parameters: Collection[str],
) -> SqlAnalysisResult:
    """Parse and classify candidate SQL using only supplied metadata and AST state."""
    if not sql.strip():
        return _build_result(
            case_id=case_id,
            statement_count=0,
            statement_type=SqlStatementType.EMPTY,
            violations={EvaluationFailureCode.PARSE_ERROR},
        )

    try:
        statements = tuple(
            cast(exp.Expression, statement)
            for statement in sqlglot.parse(sql, read=MYSQL_DIALECT)
            if statement is not None
        )
    except ParseError:
        violation = (
            EvaluationFailureCode.FORBIDDEN_FILE_OPERATION
            if _contains_file_operation_tokens(sql)
            else EvaluationFailureCode.PARSE_ERROR
        )
        return _build_result(
            case_id=case_id,
            statement_count=0,
            statement_type=SqlStatementType.UNKNOWN,
            violations={violation},
        )

    if len(statements) != 1:
        return _build_result(
            case_id=case_id,
            statement_count=len(statements),
            statement_type=SqlStatementType.EMPTY if not statements else SqlStatementType.UNKNOWN,
            violations={
                EvaluationFailureCode.PARSE_ERROR
                if not statements
                else EvaluationFailureCode.MULTIPLE_STATEMENTS
            },
        )

    root = statements[0]
    statement_type = _statement_type(root)
    root_violation = _root_violation(root)
    if root_violation is not None:
        return _build_result(
            case_id=case_id,
            statement_count=1,
            statement_type=statement_type,
            violations={root_violation},
        )

    violations: set[EvaluationFailureCode] = set()
    cte_names = {cte.alias_or_name.lower() for cte in root.find_all(exp.CTE)}
    referenced_tables, has_qualified_table = _physical_tables(root)
    bind_names = {placeholder.name for placeholder in root.find_all(exp.Placeholder)}
    has_projection_wildcard = _has_projection_wildcard(root)

    normalized_allowed_tables = {name.lower() for name in allowed_tables}
    normalized_required_tables = {name.lower() for name in required_tables}
    normalized_allowed_binds = set(allowed_bind_parameters)

    if has_qualified_table:
        violations.add(EvaluationFailureCode.FORBIDDEN_SYSTEM_SCHEMA)

    unknown_tables = referenced_tables - normalized_allowed_tables
    known_tables = referenced_tables & normalized_allowed_tables
    if unknown_tables:
        violations.add(EvaluationFailureCode.UNKNOWN_TABLE)
    if normalized_required_tables - known_tables:
        violations.add(EvaluationFailureCode.MISSING_REQUIRED_TABLE)
    if known_tables - normalized_required_tables:
        violations.add(EvaluationFailureCode.EXTRA_TABLE)

    if has_projection_wildcard:
        violations.add(EvaluationFailureCode.WILDCARD_SELECT)
    if bind_names - normalized_allowed_binds:
        violations.add(EvaluationFailureCode.UNKNOWN_BIND_PARAMETER)
    if any(True for _parameter in root.find_all(exp.Parameter)):
        violations.add(EvaluationFailureCode.FORBIDDEN_USER_VARIABLE)
    if any(True for _lock in root.find_all(exp.Lock)):
        violations.add(EvaluationFailureCode.FORBIDDEN_LOCKING_CLAUSE)
    if any(True for _into in root.find_all(exp.Into)):
        violations.add(EvaluationFailureCode.FORBIDDEN_FILE_OPERATION)

    for function in root.find_all(exp.Func):
        function_name = (
            function.name.upper()
            if isinstance(function, exp.Anonymous)
            else function.sql_name().upper()
        )
        if function_name in FILE_FUNCTIONS:
            violations.add(EvaluationFailureCode.FORBIDDEN_FILE_OPERATION)
        elif function_name in DANGEROUS_FUNCTIONS:
            violations.add(EvaluationFailureCode.FORBIDDEN_FUNCTION)

    return _build_result(
        case_id=case_id,
        statement_count=1,
        statement_type=statement_type,
        cte_names=cte_names,
        referenced_tables=referenced_tables,
        bind_names=bind_names,
        has_projection_wildcard=has_projection_wildcard,
        violations=violations,
    )


def _statement_type(root: exp.Expression) -> SqlStatementType:
    if isinstance(root, exp.Union):
        return SqlStatementType.UNION
    if isinstance(root, exp.Select):
        return SqlStatementType.SELECT
    if isinstance(root, _DML_ROOTS) or (
        isinstance(root, exp.Command) and root.name.upper() == "REPLACE"
    ):
        return SqlStatementType.DML
    if isinstance(root, _DDL_ROOTS):
        return SqlStatementType.DDL
    if isinstance(root, _COMMAND_ROOTS):
        return SqlStatementType.COMMAND
    return SqlStatementType.UNKNOWN


def _root_violation(root: exp.Expression) -> EvaluationFailureCode | None:
    if isinstance(root, (exp.Select, exp.Union)):
        return None
    if isinstance(root, _DML_ROOTS) or (
        isinstance(root, exp.Command) and root.name.upper() == "REPLACE"
    ):
        return EvaluationFailureCode.FORBIDDEN_DML
    if isinstance(root, _DDL_ROOTS):
        return EvaluationFailureCode.FORBIDDEN_DDL
    if isinstance(root, _COMMAND_ROOTS):
        return EvaluationFailureCode.FORBIDDEN_COMMAND
    return EvaluationFailureCode.NON_QUERY_STATEMENT


def _physical_tables(root: exp.Expression) -> tuple[set[str], bool]:
    tables: set[str] = set()
    has_qualified_table = False
    for scope in traverse_scope(root):
        cte_sources = {name.lower() for name in scope.cte_sources}
        for table in scope.tables:
            table_name = table.name.lower()
            qualifier = (table.db or table.catalog).lower()
            if qualifier:
                has_qualified_table = True
            if not qualifier and table_name in cte_sources:
                continue
            tables.add(table_name)
    return tables, has_qualified_table


def _has_projection_wildcard(root: exp.Expression) -> bool:
    for select in root.find_all(exp.Select):
        for projection in select.expressions:
            unwrapped = projection.this if isinstance(projection, exp.Alias) else projection
            if isinstance(unwrapped, exp.Star):
                return True
            if isinstance(unwrapped, exp.Column) and isinstance(unwrapped.this, exp.Star):
                return True
    return False


def _contains_file_operation_tokens(sql: str) -> bool:
    """Classify sqlglot-unsupported MySQL file clauses without regex parsing."""
    try:
        token_text = tuple(
            token.text.upper() for token in Dialect.get_or_raise(MYSQL_DIALECT).tokenize(sql)
        )
    except (ParseError, ValueError):
        return False
    return "OUTFILE" in token_text or "DUMPFILE" in token_text or "LOAD_FILE" in token_text


def _build_result(
    *,
    case_id: str,
    statement_count: int,
    statement_type: SqlStatementType,
    cte_names: Collection[str] = (),
    referenced_tables: Collection[str] = (),
    bind_names: Collection[str] = (),
    has_projection_wildcard: bool = False,
    violations: Collection[EvaluationFailureCode] = (),
) -> SqlAnalysisResult:
    payload = {
        "case_id": case_id,
        "statement_count": statement_count,
        "statement_type": statement_type,
        "cte_names": tuple(sorted(set(cte_names))),
        "referenced_tables": tuple(sorted(set(referenced_tables))),
        "bind_names": tuple(sorted(set(bind_names))),
        "has_projection_wildcard": has_projection_wildcard,
        "violations": tuple(sorted(set(violations), key=lambda code: code.value)),
    }
    return SqlAnalysisResult.model_validate(
        {**payload, "analysis_digest": canonical_json_digest(payload)}
    )
