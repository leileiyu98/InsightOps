"""Author the M1.2A v1.1.0 catalog status and oracle bindings."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from insightops.canonical import compute_business_definition_digest
from insightops.seed.contracts import DatasetManifest, SeedSource
from insightops.seed.dataset import compute_dataset_digest, load_seed_dataset

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = ROOT / "benchmarks" / "m1_2a"
CATALOG_PATH = BENCHMARK_ROOT / "cases.json"
SEED_ROOT = ROOT / "data" / "seed" / "m1_2a"
MANIFEST_PATH = SEED_ROOT / "manifest.json"
BUSINESS_DEFINITION_PATH = ROOT / "docs" / "business-definitions-v1.md"
ZERO_DIGEST = "0" * 64

NEW_EXECUTABLE = {
    "GQ-MKT-001",
    "GQ-MKT-002",
    "GQ-MKT-003",
    "GQ-MKT-004",
    "GQ-MKT-005",
    "GQ-MKT-008",
    "GQ-PRD-001",
    "GQ-PRD-006",
    "GQ-PRD-007",
    "GQ-PRD-008",
    "GQ-XDM-002",
    "GQ-XDM-007",
}

CLARIFICATIONS = {
    "GQ-MKT-006": (
        "Attributed ROAS 必须先明确使用 SaaS Revenue 或 Commerce Revenue，不能混合收入类型。"
    ),
    "GQ-MKT-007": "Attributed ROAS 排名必须先明确 SaaS 或 Commerce 收入类型。",
    "GQ-PRD-005": (
        "当前模型没有 organization registration-source attribution；首次付费归因发生在注册之后，"
        "不能用来推断注册来源。"
    ),
    "GQ-XDM-003": "触达到注册的分母和观察窗口未在 Business Definitions 1.0.1 中冻结。",
}

SCENARIOS = {
    "GQ-MKT-001": ["saas-channel-cac", "spend-up-customers-down", "history-boundary-saas"],
    "GQ-MKT-002": ["commerce-channel-cac", "spend-up-customers-down", "history-boundary-commerce"],
    "GQ-MKT-003": ["june-attributed-revenue", "direct-vs-unknown"],
    "GQ-MKT-004": ["q2-same-cohort-touch-to-first-payment"],
    "GQ-MKT-005": ["spend-up-customers-down"],
    "GQ-MKT-008": [
        "direct-vs-unknown",
        "history-boundary-saas",
        "history-boundary-commerce",
        "late-arriving-touch",
        "inactive-channel-history",
    ],
    "GQ-PRD-001": ["q2-activation-cohort", "activation-observation-cutoff"],
    "GQ-PRD-006": ["activation-zero-one-two-conditions"],
    "GQ-PRD-007": ["may-june-registration-activation-divergence"],
    "GQ-PRD-008": ["activation-by-first-payment-channel"],
    "GQ-XDM-002": ["merchant-commerce-attributed-roas", "direct-vs-unknown"],
    "GQ-XDM-007": ["merchant-growth-refund-spend"],
}


def parameters_for(sql: str) -> dict[str, str]:
    values = {
        "snapshot_cutoff_utc": "2026-01-15 08:00:00.000000",
        "marketing_history_started_at": "2025-04-01 07:00:00.000000",
        "activation_observation_as_of_utc": "2025-07-01 07:00:00.000000",
        "jan_start": "2025-01-01 08:00:00.000000",
        "apr_start": "2025-04-01 07:00:00.000000",
        "may_start": "2025-05-01 07:00:00.000000",
        "jun_start": "2025-06-01 07:00:00.000000",
        "jul_start": "2025-07-01 07:00:00.000000",
        "q1_start_date": "2025-01-01",
        "q2_start_date": "2025-04-01",
        "q3_start_date": "2025-07-01",
        "may_start_date": "2025-05-01",
        "jun_start_date": "2025-06-01",
        "jul_start_date": "2025-07-01",
    }
    names = sorted(set(re.findall(r":([a-z][a-z0-9_]*)", sql)))
    missing = set(names) - set(values)
    if missing:
        raise ValueError(f"missing parameter values: {sorted(missing)}")
    return {name: values[name] for name in names}


def required_tables(sql: str) -> list[str]:
    physical_tables = {
        "organization",
        "organization_member",
        "consumer",
        "merchant",
        "saas_plan_version",
        "subscription",
        "subscription_state_event",
        "subscription_invoice",
        "invoice_payment_attempt",
        "product",
        "commerce_order",
        "commerce_order_item",
        "commerce_refund",
        "platform_fee_charge",
        "refund_item_allocation",
        "marketing_channel",
        "marketing_campaign",
        "campaign_daily_spend",
        "marketing_touch",
        "attributed_conversion",
    }
    pattern = re.compile(r"\b(?:FROM|JOIN)\s+([a-z_][a-z0-9_]*)", re.IGNORECASE)
    return sorted(set(pattern.findall(sql)) & physical_tables)


def refresh_manifest_content_digests() -> tuple[str, str]:
    """Compute definition then dataset digests in non-circular dependency order."""
    manifest_payload: dict[str, Any] = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    definition_digest = compute_business_definition_digest(BUSINESS_DEFINITION_PATH)
    manifest_payload["business_definition_digest"] = definition_digest
    manifest = DatasetManifest.model_validate(manifest_payload)
    sources = tuple(
        SeedSource.model_validate_json((SEED_ROOT / filename).read_text(encoding="utf-8"))
        for filename in manifest.source_files
    )
    dataset_digest = compute_dataset_digest(manifest, sources)
    manifest_payload["dataset_digest"] = dataset_digest
    MANIFEST_PATH.write_text(
        json.dumps(manifest_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    load_seed_dataset(SEED_ROOT)
    return definition_digest, dataset_digest


def main() -> None:
    definition_digest, dataset_digest = refresh_manifest_content_digests()
    catalog: dict[str, Any] = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    catalog.update(
        {
            "catalog_version": "1.1.0",
            "dataset_version": "1.1.0",
            "dataset_digest": dataset_digest,
            "schema_revision": "0004",
            "business_definition_version": "1.0.1",
            "business_definition_digest": definition_digest,
            "oracle_assets_digest": ZERO_DIGEST,
        }
    )
    for case in catalog["cases"]:
        case_id = case["case_id"]
        if case_id in NEW_EXECUTABLE:
            sql_relative = f"sql/{case_id}.sql"
            expected_relative = f"expected/{case_id}.json"
            sql = (BENCHMARK_ROOT / sql_relative).read_text(encoding="utf-8")
            case.update(
                {
                    "status": "executable",
                    "required_tables": required_tables(sql),
                    "scenario_ids": SCENARIOS[case_id],
                    "expected_result_shape": "冻结的 typed rows",
                    "parameters": parameters_for(sql),
                    "clarification_reason": None,
                    "deferred_reason": None,
                    "gold_sql_path": sql_relative,
                    "expected_result_path": expected_relative,
                    "gold_sql_digest": ZERO_DIGEST,
                    "expected_result_digest": ZERO_DIGEST,
                }
            )
        elif case_id in CLARIFICATIONS:
            case.update(
                {
                    "status": "clarification_required",
                    "expected_result_shape": "澄清请求",
                    "parameters": {},
                    "clarification_reason": CLARIFICATIONS[case_id],
                    "deferred_reason": None,
                    "gold_sql_path": None,
                    "expected_result_path": None,
                }
            )
            case.pop("gold_sql_digest", None)
            case.pop("expected_result_digest", None)
        elif case["status"] == "deferred":
            case["deferred_reason"] = "依赖尚未实施的 M1.1E 产品使用或客服表。"

        if case_id in {"GQ-MKT-006", "GQ-MKT-007"}:
            case["metrics"] = ["Attributed ROAS"]
            case["question"] = case["question"].replace("ROAS", "Attributed ROAS")
        if case_id == "GQ-XDM-002":
            case["metrics"] = ["Attributed Commerce Revenue", "Commerce Attributed ROAS"]
            case["question"] = case["question"].replace("Commerce ROAS", "Commerce Attributed ROAS")
        if case_id == "GQ-MKT-004":
            case["question"] = (
                "2025 年第二季度从营销触达到新增付费客户的同 cohort 漏斗如何，"
                "SaaS 和 Commerce 分别展示？"
            )
        if case_id == "GQ-MKT-008":
            case["question"] = (
                "给定 2025 年第二季度的转化，direct、unknown/unattributed、晚到触达重归因和"
                "历史渠道失效边界分别是什么？"
            )

    CATALOG_PATH.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
