"""Unit and Gold compatibility controls for deterministic SQL AST analysis."""

from pathlib import Path

import pytest

from insightops.benchmark.contracts import BenchmarkStatus
from insightops.benchmark.registry import load_benchmark_catalog
from insightops.evaluation.contracts import (
    EvaluationFailureCode,
    SqlAnalysisResult,
    SqlStatementType,
)
from insightops.evaluation.sql_analysis import analyze_candidate_sql
from insightops.seed.dataset import load_seed_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BENCHMARK_ROOT = PROJECT_ROOT / "benchmarks" / "m1_2a"
DATASET_ROOT = PROJECT_ROOT / "data" / "seed" / "m1_2a"
ALLOWED_TABLES = ("organization", "subscription", "subscription_invoice")


def _analyze(
    sql: str,
    *,
    required_tables: tuple[str, ...] = ("organization",),
    allowed_binds: tuple[str, ...] = (),
) -> SqlAnalysisResult:
    return analyze_candidate_sql(
        case_id="GQ-SAA-001",
        sql=sql,
        required_tables=required_tables,
        allowed_tables=ALLOWED_TABLES,
        allowed_bind_parameters=allowed_binds,
    )


@pytest.mark.parametrize(
    "sql,statement_type,cte_names",
    [
        ("SELECT organization_id FROM organization", SqlStatementType.SELECT, ()),
        (
            "WITH active_org AS (SELECT organization_id FROM organization) "
            "SELECT organization_id FROM active_org",
            SqlStatementType.SELECT,
            ("active_org",),
        ),
        (
            "WITH a AS (SELECT organization_id FROM organization), "
            "b AS (SELECT organization_id FROM a) SELECT organization_id FROM b",
            SqlStatementType.SELECT,
            ("a", "b"),
        ),
        (
            "WITH outer_cte AS (WITH inner_cte AS "
            "(SELECT organization_id FROM organization) "
            "SELECT organization_id FROM inner_cte) "
            "SELECT organization_id FROM outer_cte",
            SqlStatementType.SELECT,
            ("inner_cte", "outer_cte"),
        ),
        (
            "SELECT nested.organization_id FROM "
            "(SELECT organization_id FROM organization) AS nested",
            SqlStatementType.SELECT,
            (),
        ),
        (
            "SELECT organization_id FROM organization UNION "
            "SELECT organization_id FROM organization",
            SqlStatementType.UNION,
            (),
        ),
        (
            "SELECT organization_id FROM organization UNION ALL "
            "SELECT organization_id FROM organization",
            SqlStatementType.UNION,
            (),
        ),
        (
            "/* candidate */ SeLeCt o.organization_id FROM organization AS o -- end",
            SqlStatementType.SELECT,
            (),
        ),
    ],
)
def test_allowed_query_shapes(
    sql: str,
    statement_type: SqlStatementType,
    cte_names: tuple[str, ...],
) -> None:
    result = _analyze(sql)

    assert result.statement_type is statement_type
    assert result.cte_names == cte_names
    assert result.referenced_tables == ("organization",)
    assert result.violations == ()


def test_cte_names_are_not_physical_tables_and_alias_does_not_replace_table() -> None:
    result = _analyze(
        "WITH subscription AS (SELECT organization_id FROM organization) "
        "SELECT s.organization_id FROM subscription AS s"
    )

    assert result.cte_names == ("subscription",)
    assert result.referenced_tables == ("organization",)


@pytest.mark.parametrize(
    "sql,code",
    [
        ("SELECT organization_id FROM subscription", EvaluationFailureCode.MISSING_REQUIRED_TABLE),
        (
            "SELECT o.organization_id FROM organization o "
            "JOIN subscription s ON s.organization_id = o.organization_id",
            EvaluationFailureCode.EXTRA_TABLE,
        ),
        ("SELECT value FROM unknown_table", EvaluationFailureCode.UNKNOWN_TABLE),
        (
            "SELECT organization_id FROM analytics.organization",
            EvaluationFailureCode.FORBIDDEN_SYSTEM_SCHEMA,
        ),
        (
            "SELECT table_name FROM information_schema.tables",
            EvaluationFailureCode.FORBIDDEN_SYSTEM_SCHEMA,
        ),
    ],
)
def test_table_structure_failures(sql: str, code: EvaluationFailureCode) -> None:
    assert code in _analyze(sql).violations


def test_referenced_tables_are_sorted() -> None:
    result = _analyze(
        "SELECT o.organization_id FROM subscription s "
        "JOIN organization o ON o.organization_id = s.organization_id",
        required_tables=("subscription", "organization"),
    )

    assert result.referenced_tables == ("organization", "subscription")


@pytest.mark.parametrize(
    "sql,is_wildcard",
    [
        ("SELECT * FROM organization", True),
        ("SELECT o.* FROM organization AS o", True),
        ("SELECT COUNT(*) AS row_count FROM organization", False),
    ],
)
def test_projection_wildcard_detection(sql: str, is_wildcard: bool) -> None:
    result = _analyze(sql)

    assert result.has_projection_wildcard is is_wildcard
    assert (EvaluationFailureCode.WILDCARD_SELECT in result.violations) is is_wildcard


def test_named_bind_parameters_allow_known_subset_and_sort_names() -> None:
    result = _analyze(
        "SELECT organization_id FROM organization "
        "WHERE registered_at >= :start_date AND registered_at < :end_date",
        allowed_binds=("unused", "end_date", "start_date"),
    )

    assert result.bind_names == ("end_date", "start_date")
    assert EvaluationFailureCode.UNKNOWN_BIND_PARAMETER not in result.violations


def test_unknown_or_positional_bind_is_rejected() -> None:
    unknown = _analyze(
        "SELECT organization_id FROM organization WHERE registered_at >= :unknown",
        allowed_binds=("start_date",),
    )
    positional = _analyze("SELECT ? FROM organization")

    assert unknown.bind_names == ("unknown",)
    assert EvaluationFailureCode.UNKNOWN_BIND_PARAMETER in unknown.violations
    assert EvaluationFailureCode.UNKNOWN_BIND_PARAMETER in positional.violations


@pytest.mark.parametrize(
    "sql,code",
    [
        (
            "INSERT INTO organization (organization_name) VALUES ('x')",
            EvaluationFailureCode.FORBIDDEN_DML,
        ),
        ("UPDATE organization SET organization_name = 'x'", EvaluationFailureCode.FORBIDDEN_DML),
        ("DELETE FROM organization", EvaluationFailureCode.FORBIDDEN_DML),
        ("REPLACE INTO organization VALUES (1)", EvaluationFailureCode.FORBIDDEN_DML),
        ("CREATE TABLE x (id INT)", EvaluationFailureCode.FORBIDDEN_DDL),
        ("ALTER TABLE organization ADD COLUMN x INT", EvaluationFailureCode.FORBIDDEN_DDL),
        ("DROP TABLE organization", EvaluationFailureCode.FORBIDDEN_DDL),
        ("TRUNCATE TABLE organization", EvaluationFailureCode.FORBIDDEN_DDL),
        ("CALL dangerous_proc()", EvaluationFailureCode.FORBIDDEN_COMMAND),
        ("START TRANSACTION", EvaluationFailureCode.FORBIDDEN_COMMAND),
        ("COMMIT", EvaluationFailureCode.FORBIDDEN_COMMAND),
        (
            "SELECT organization_id FROM organization INTO OUTFILE '/tmp/x'",
            EvaluationFailureCode.FORBIDDEN_FILE_OPERATION,
        ),
        (
            "SELECT organization_id INTO DUMPFILE '/tmp/x' FROM organization",
            EvaluationFailureCode.FORBIDDEN_FILE_OPERATION,
        ),
        ("SELECT LOAD_FILE('/tmp/x')", EvaluationFailureCode.FORBIDDEN_FILE_OPERATION),
        (
            "SELECT organization_id FROM organization FOR UPDATE",
            EvaluationFailureCode.FORBIDDEN_LOCKING_CLAUSE,
        ),
        (
            "SELECT organization_id FROM organization LOCK IN SHARE MODE",
            EvaluationFailureCode.FORBIDDEN_LOCKING_CLAUSE,
        ),
        ("SELECT SLEEP(1)", EvaluationFailureCode.FORBIDDEN_FUNCTION),
        ("SELECT BENCHMARK(1, 1 + 1)", EvaluationFailureCode.FORBIDDEN_FUNCTION),
        ("SELECT GET_LOCK('x', 1)", EvaluationFailureCode.FORBIDDEN_FUNCTION),
        ("SELECT RELEASE_LOCK('x')", EvaluationFailureCode.FORBIDDEN_FUNCTION),
        ("SELECT IS_FREE_LOCK('x')", EvaluationFailureCode.FORBIDDEN_FUNCTION),
        ("SELECT @candidate_variable", EvaluationFailureCode.FORBIDDEN_USER_VARIABLE),
    ],
)
def test_dangerous_sql_is_rejected(sql: str, code: EvaluationFailureCode) -> None:
    assert code in _analyze(sql, required_tables=()).violations


def test_empty_multiple_and_malformed_sql_have_stable_parser_codes() -> None:
    empty = _analyze("  -- only a comment")
    multiple = _analyze("SELECT 1; SELECT 2", required_tables=())
    malformed_a = _analyze("SELECT (", required_tables=())
    malformed_b = _analyze("SELECT FROM", required_tables=())

    assert empty.violations == (EvaluationFailureCode.PARSE_ERROR,)
    assert multiple.statement_count == 2
    assert multiple.violations == (EvaluationFailureCode.MULTIPLE_STATEMENTS,)
    assert malformed_a.violations == malformed_b.violations == (EvaluationFailureCode.PARSE_ERROR,)
    assert malformed_a.analysis_digest == malformed_b.analysis_digest


def test_analysis_digest_is_stable_for_equivalent_metadata() -> None:
    first = _analyze("SELECT organization_id FROM organization")
    second = _analyze("SELECT organization_id FROM organization")

    assert first.analysis_digest == second.analysis_digest
    assert first.computed_digest() == first.analysis_digest


def test_all_28_gold_sql_files_are_parser_compatible_controls() -> None:
    catalog = load_benchmark_catalog(BENCHMARK_ROOT / "cases.json")
    dataset = load_seed_dataset(DATASET_ROOT)
    executable = [case for case in catalog.cases if case.status is BenchmarkStatus.EXECUTABLE]

    for case in executable:
        assert case.gold_sql_path is not None
        sql = (BENCHMARK_ROOT / case.gold_sql_path).read_text(encoding="utf-8")
        result = analyze_candidate_sql(
            case_id=case.case_id,
            sql=sql,
            required_tables=case.required_tables,
            allowed_tables=dataset.manifest.table_order,
            allowed_bind_parameters=case.parameters,
        )
        assert result.violations == (), case.case_id
        assert result.referenced_tables == tuple(sorted(case.required_tables)), case.case_id

    assert len(executable) == 28
