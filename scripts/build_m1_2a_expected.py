"""Execute all M1.2A Gold SQL and bind deterministic expected/oracle digests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from insightops.benchmark.contracts import BenchmarkCatalog, BenchmarkStatus, ExpectedResult
from insightops.benchmark.oracle import execute_gold_case
from insightops.benchmark.registry import (
    compute_expected_result_digest,
    compute_oracle_assets_digest,
    compute_sql_digest,
)
from insightops.core.config import load_settings
from insightops.db.session import create_database_engine

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = ROOT / "benchmarks" / "m1_2a"
CATALOG_PATH = BENCHMARK_ROOT / "cases.json"
MANIFEST_PATH = ROOT / "data" / "seed" / "m1_2a" / "manifest.json"
ZERO_DIGEST = "0" * 64
ORDERED_BY: dict[str, tuple[str, ...]] = {
    "GQ-SAA-001": ("plan_name",),
    "GQ-SAA-002": ("report_month",),
    "GQ-SAA-003": ("report_month",),
    "GQ-SAA-004": ("report_month", "plan_name"),
    "GQ-SAA-005": ("report_month",),
    "GQ-SAA-006": ("plan_name",),
    "GQ-SAA-007": ("report_month",),
    "GQ-SAA-008": ("comparison_period",),
    "GQ-COM-001": (),
    "GQ-COM-002": (),
    "GQ-COM-003": ("merchant_id",),
    "GQ-COM-004": ("report_month",),
    "GQ-COM-005": ("merchant_id",),
    "GQ-COM-006": ("report_month", "category_code"),
    "GQ-COM-008": ("gmv_change", "merchant_id"),
    "GQ-XDM-001": ("report_month",),
    "GQ-MKT-001": ("channel_code",),
    "GQ-MKT-002": ("channel_code",),
    "GQ-MKT-003": ("business_scope", "attribution_result", "channel_code"),
    "GQ-MKT-004": ("business_scope",),
    "GQ-MKT-005": ("business_scope", "channel_code"),
    "GQ-MKT-008": ("business_scope", "conversion_type", "authoritative_external_id"),
    "GQ-PRD-001": (),
    "GQ-PRD-006": ("condition_stage",),
    "GQ-PRD-007": ("cohort_month",),
    "GQ-PRD-008": ("channel_code",),
    "GQ-XDM-002": ("merchant_id",),
    "GQ-XDM-007": ("gmv_change", "merchant_id"),
}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    catalog_payload: dict[str, Any] = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    catalog = BenchmarkCatalog.model_validate(catalog_payload)
    expected_payloads: dict[str, dict[str, Any]] = {}
    engine = create_database_engine(load_settings())
    try:
        with engine.connect() as connection:
            for case in catalog.cases:
                if case.status is not BenchmarkStatus.EXECUTABLE:
                    continue
                columns, rows = execute_gold_case(connection, BENCHMARK_ROOT, case)
                expected = ExpectedResult(
                    catalog_id=catalog.catalog_id,
                    catalog_version=catalog.catalog_version,
                    dataset_id=catalog.dataset_id,
                    dataset_version=catalog.dataset_version,
                    dataset_digest=catalog.dataset_digest,
                    schema_revision=catalog.schema_revision,
                    business_definition_id=catalog.business_definition_id,
                    business_definition_version=catalog.business_definition_version,
                    business_definition_digest=catalog.business_definition_digest,
                    oracle_assets_digest=ZERO_DIGEST,
                    case_id=case.case_id,
                    columns=columns,
                    ordered_by=ORDERED_BY[case.case_id],
                    rows=rows,
                )
                expected_payloads[case.case_id] = expected.model_dump(mode="json")
    finally:
        engine.dispose()

    cases_by_id = {case["case_id"]: case for case in catalog_payload["cases"]}
    for case_id, expected_payload in expected_payloads.items():
        expected = ExpectedResult.model_validate(expected_payload)
        case_payload = cases_by_id[case_id]
        sql_path = BENCHMARK_ROOT / case_payload["gold_sql_path"]
        case_payload["gold_sql_digest"] = compute_sql_digest(sql_path)
        case_payload["expected_result_digest"] = compute_expected_result_digest(expected)

    catalog_payload["oracle_assets_digest"] = ZERO_DIGEST
    rebound_catalog = BenchmarkCatalog.model_validate(catalog_payload)
    oracle_digest = compute_oracle_assets_digest(rebound_catalog)
    catalog_payload["oracle_assets_digest"] = oracle_digest
    write_json(CATALOG_PATH, catalog_payload)

    manifest_payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_payload["oracle_assets_digest"] = oracle_digest
    write_json(MANIFEST_PATH, manifest_payload)

    for case_id, expected_payload in expected_payloads.items():
        expected_payload["oracle_assets_digest"] = oracle_digest
        write_json(BENCHMARK_ROOT / "expected" / f"{case_id}.json", expected_payload)


if __name__ == "__main__":
    main()
