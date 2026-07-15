"""Real MySQL regression tests for M1.2A benchmark-only Gold SQL."""

import re
from collections.abc import Generator
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from insightops.benchmark.contracts import BenchmarkStatus
from insightops.benchmark.oracle import execute_gold_case
from insightops.benchmark.registry import (
    load_benchmark_catalog,
    load_expected_result,
    validate_benchmark_bundle,
)
from insightops.seed.dataset import load_seed_dataset
from insightops.seed.loader import DatasetLoader

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BENCHMARK_ROOT = PROJECT_ROOT / "benchmarks" / "m1_2a"
DATASET_ROOT = PROJECT_ROOT / "data" / "seed" / "m1_2a"


@pytest.fixture(scope="module")
def seeded_benchmark_database(database_engine: Engine) -> Generator[Engine]:
    """Load the canonical dataset for this module and remove only its owned rows."""
    dataset = load_seed_dataset(DATASET_ROOT)
    loader = DatasetLoader(database_engine, dataset, app_env="test")
    loader.load()
    try:
        yield database_engine
    finally:
        loader.unload()


def test_catalog_has_current_scope_status_partition() -> None:
    catalog = load_benchmark_catalog(BENCHMARK_ROOT / "cases.json")

    counts = {
        status: sum(case.status is status for case in catalog.cases) for status in BenchmarkStatus
    }
    assert len(catalog.cases) == 48
    assert counts == {
        BenchmarkStatus.EXECUTABLE: 16,
        BenchmarkStatus.CLARIFICATION_REQUIRED: 2,
        BenchmarkStatus.DEFERRED: 30,
    }


def test_catalog_assets_have_valid_version_bindings_and_declared_tables() -> None:
    catalog = load_benchmark_catalog(BENCHMARK_ROOT / "cases.json")
    dataset = load_seed_dataset(DATASET_ROOT)
    validate_benchmark_bundle(BENCHMARK_ROOT, catalog, dataset.manifest)
    physical_tables = set(dataset.manifest.table_order)
    table_pattern = re.compile(r"\b(?:FROM|JOIN)\s+([a-z_][a-z0-9_]*)", re.IGNORECASE)

    for case in catalog.cases:
        if case.status is not BenchmarkStatus.EXECUTABLE:
            continue
        assert case.gold_sql_path is not None
        sql = (BENCHMARK_ROOT / case.gold_sql_path).read_text(encoding="utf-8")
        assert re.search(r"\bSELECT\s+(?:[a-z_][a-z0-9_]*\.)?\*", sql, re.IGNORECASE) is None
        assert re.search(r"\b(?:NOW|CURRENT_DATE|CURRENT_TIMESTAMP)\b", sql, re.IGNORECASE) is None
        actual_tables = set(table_pattern.findall(sql)) & physical_tables
        assert set(case.required_tables) == actual_tables, case.case_id


def test_executable_gold_sql_matches_frozen_results(
    seeded_benchmark_database: Engine,
) -> None:
    catalog = load_benchmark_catalog(BENCHMARK_ROOT / "cases.json")
    executable_cases = [case for case in catalog.cases if case.status is BenchmarkStatus.EXECUTABLE]

    with seeded_benchmark_database.connect() as connection:
        for case in executable_cases:
            assert case.expected_result_path is not None
            expected = load_expected_result(BENCHMARK_ROOT / case.expected_result_path)
            columns, rows = execute_gold_case(connection, BENCHMARK_ROOT, case)
            assert expected.dataset_id == catalog.dataset_id
            assert expected.dataset_version == catalog.dataset_version
            assert expected.dataset_digest == catalog.dataset_digest
            assert expected.schema_revision == catalog.schema_revision
            assert expected.business_definition_id == catalog.business_definition_id
            assert expected.business_definition_version == catalog.business_definition_version
            assert expected.catalog_id == catalog.catalog_id
            assert expected.catalog_version == catalog.catalog_version
            assert expected.oracle_assets_digest == catalog.oracle_assets_digest
            assert expected.case_id == case.case_id
            assert columns == expected.columns
            assert rows == expected.rows


def test_business_metric_acceptance_invariants(
    seeded_benchmark_database: Engine,
) -> None:
    """Prove cutoff, test filtering, and one-to-many aggregation boundaries."""
    catalog = load_benchmark_catalog(BENCHMARK_ROOT / "cases.json")
    cases = {case.case_id: case for case in catalog.cases}

    with seeded_benchmark_database.connect() as connection:
        _columns, commerce_rows = execute_gold_case(
            connection,
            BENCHMARK_ROOT,
            cases["GQ-COM-001"],
        )
        assert commerce_rows == ({"gmv": "720.0000", "order_count": 2, "aov": "360.0000"},)

        candidate_order_count = connection.scalar(
            text(
                "SELECT COUNT(*) FROM commerce_order "
                "WHERE first_paid_at >= :start AND first_paid_at < :end "
                "AND status <> 'cancelled'"
            ),
            {
                "start": cases["GQ-COM-001"].parameters["jun_start"],
                "end": cases["GQ-COM-001"].parameters["jul_start"],
            },
        )
        eligible_item_count = connection.scalar(
            text(
                "SELECT COUNT(*) FROM commerce_order_item AS i "
                "JOIN commerce_order AS o ON o.commerce_order_id = i.commerce_order_id "
                "JOIN consumer AS c ON c.consumer_id = o.consumer_id "
                "JOIN merchant AS m ON m.merchant_assignment_id = o.merchant_assignment_id "
                "JOIN organization AS org ON org.organization_id = m.organization_id "
                "JOIN product AS p ON p.product_id = i.product_id "
                "WHERE o.first_paid_at >= :start AND o.first_paid_at < :end "
                "AND o.status <> 'cancelled' "
                "AND o.is_test = 0 AND c.is_test = 0 AND m.is_test = 0 "
                "AND org.is_test = 0 AND i.is_test = 0 AND p.is_test = 0"
            ),
            {
                "start": cases["GQ-COM-001"].parameters["jun_start"],
                "end": cases["GQ-COM-001"].parameters["jul_start"],
            },
        )
        assert candidate_order_count == 5
        assert eligible_item_count == 3
        assert commerce_rows[0]["order_count"] == 2

        refund_edge = (
            connection.execute(
                text(
                    "SELECT o.status, o.first_paid_at, o.cancelled_at, "
                    "r.succeeded_at AS refund_succeeded_at, "
                    "f.succeeded_at AS fee_succeeded_at "
                    "FROM commerce_order AS o "
                    "JOIN commerce_refund AS r "
                    "ON r.commerce_order_id = o.commerce_order_id "
                    "JOIN platform_fee_charge AS f "
                    "ON f.commerce_order_id = o.commerce_order_id "
                    "WHERE o.external_order_id = :order_id "
                    "AND r.external_refund_id = :refund_id "
                    "AND f.external_fee_charge_id = :fee_id"
                ),
                {
                    "order_id": "seed-order-cancelled-may",
                    "refund_id": "seed-refund-jun-cancelled-order",
                    "fee_id": "seed-fee-cancelled-order-may",
                },
            )
            .mappings()
            .one()
        )
        assert refund_edge["status"] == "cancelled"
        assert refund_edge["first_paid_at"] < refund_edge["refund_succeeded_at"]
        assert refund_edge["fee_succeeded_at"] < refund_edge["cancelled_at"]
        assert refund_edge["refund_succeeded_at"] < refund_edge["cancelled_at"]

        _columns, refund_rows = execute_gold_case(
            connection,
            BENCHMARK_ROOT,
            cases["GQ-COM-002"],
        )
        assert refund_rows == (
            {
                "refund_amount": "390.0000",
                "gmv": "720.0000",
                "refund_rate": "0.5417",
                "prior_month_order_refund_amount": "190.0000",
            },
        )

        _columns, revenue_rows = execute_gold_case(
            connection,
            BENCHMARK_ROOT,
            cases["GQ-XDM-001"],
        )
        assert next(row for row in revenue_rows if row["report_month"] == "2025-05") == {
            "report_month": "2025-05",
            "saas_revenue": "1100.0000",
            "commerce_revenue": "30.0000",
        }

        mrr_case = cases["GQ-SAA-001"]
        early_cutoff_parameters = dict(mrr_case.parameters)
        early_cutoff_parameters["snapshot_cutoff_utc"] = "2025-11-30 23:59:59.999999"
        early_cutoff_case = mrr_case.model_copy(update={"parameters": early_cutoff_parameters})
        _columns, early_cutoff_rows = execute_gold_case(
            connection,
            BENCHMARK_ROOT,
            early_cutoff_case,
        )
        assert early_cutoff_rows == ({"plan_name": "TOTAL", "mrr": "0.0000", "arr": "0.0000"},)

        _columns, bridge_rows = execute_gold_case(
            connection,
            BENCHMARK_ROOT,
            cases["GQ-SAA-005"],
        )
        for row in bridge_rows:
            calculated_closing = (
                Decimal(str(row["opening_mrr"]))
                + Decimal(str(row["new_mrr"]))
                + Decimal(str(row["expansion_mrr"]))
                - Decimal(str(row["contraction_mrr"]))
                - Decimal(str(row["churned_mrr"]))
            )
            assert calculated_closing == Decimal(str(row["closing_mrr"]))
