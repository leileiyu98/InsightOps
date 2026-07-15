"""Real MySQL regression tests for M1.2A benchmark-only Gold SQL."""

from collections.abc import Generator
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from insightops.benchmark.contracts import BenchmarkStatus
from insightops.benchmark.oracle import execute_gold_case
from insightops.benchmark.registry import load_benchmark_catalog, load_expected_result
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
