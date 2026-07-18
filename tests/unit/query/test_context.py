"""Oracle-isolation tests for the bounded Text2SQL context builder."""

from pathlib import Path

from insightops.benchmark.registry import load_benchmark_catalog, public_benchmark_cases
from insightops.query.context import build_query_context
from insightops.seed.dataset import load_seed_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_context_contains_public_schema_but_no_oracle_assets() -> None:
    catalog = load_benchmark_catalog(PROJECT_ROOT / "benchmarks" / "m1_2a" / "cases.json")
    dataset = load_seed_dataset(PROJECT_ROOT / "data" / "seed" / "m1_2a")
    case = next(case for case in public_benchmark_cases(catalog) if case.case_id == "GQ-SAA-002")

    context = build_query_context(
        question=case.question,
        case=case,
        manifest=dataset.manifest,
    )
    prompt = f"{context.system_prompt}\n{context.user_prompt}".lower()

    assert "subscription_invoice" in prompt
    assert "invoice_payment_attempt" in prompt
    assert "snapshot_cutoff_utc" in prompt
    assert "gold_sql" not in prompt
    assert "expected_result_path" not in prompt
    assert "expected_result_digest" not in prompt
    assert "oracle_visibility" not in prompt
    assert "baseline_delta" not in prompt
    for forbidden_oracle_content in (
        "with periods as (",
        "cast(coalesce(sum(a.subscription_fee_amount), 0) as decimal(19,4))",
        '"saas_revenue": "8000.0000"',
        '"saas_revenue": "1400.0000"',
        '"saas_revenue": "400.0000"',
        "benchmarks/m1_2a/sql/gq-saa-002.sql",
        "benchmarks/m1_2a/expected/gq-saa-002.json",
        "sql/gq-saa-002.sql",
        "expected/gq-saa-002.json",
    ):
        assert forbidden_oracle_content not in prompt


def test_free_query_context_has_all_twenty_bounded_tables() -> None:
    dataset = load_seed_dataset(PROJECT_ROOT / "data" / "seed" / "m1_2a")

    context = build_query_context(
        question="列出一个 organization 名称",
        case=None,
        manifest=dataset.manifest,
    )

    assert all(table_name in context.user_prompt for table_name in dataset.manifest.table_order)
