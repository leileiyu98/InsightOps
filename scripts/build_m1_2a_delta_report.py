"""Build the reviewed M1.2A v1.0.0 to v1.1.0 business-result delta."""

from __future__ import annotations

import json
from pathlib import Path

from insightops.benchmark.contracts import BenchmarkStatus
from insightops.benchmark.registry import (
    compute_business_result_digest,
    load_baseline_index,
    load_benchmark_catalog,
    load_expected_result,
)

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = ROOT / "benchmarks" / "m1_2a"

CHANGES: dict[str, tuple[str, tuple[str, ...]]] = {
    "GQ-COM-001": ("Q2 completed orders extend June GMV and order count.", ("q2-commerce-orders",)),
    "GQ-COM-002": ("Q2 completed orders change the June GMV denominator.", ("q2-commerce-orders",)),
    "GQ-COM-003": ("Q2 merchant orders extend June merchant GMV.", ("q2-commerce-orders",)),
    "GQ-COM-004": ("Q2 first orders add monthly new customers.", ("q2-commerce-first-orders",)),
    "GQ-COM-005": (
        "Q2 orders and fees extend merchant take-rate results.",
        ("q2-commerce-orders",),
    ),
    "GQ-COM-006": ("Q2 order items extend category net sales.", ("q2-commerce-order-items",)),
    "GQ-COM-008": (
        "Q2 orders and fees extend the monthly merchant comparison.",
        ("q2-commerce-orders",),
    ),
    "GQ-SAA-001": ("Q2 subscriptions extend July 1 MRR and ARR.", ("q2-activation-subscriptions",)),
    "GQ-SAA-002": ("Q2 succeeded attempts add monthly SaaS revenue.", ("q2-first-payment-facts",)),
    "GQ-SAA-004": (
        "Q2 activation events extend monthly active subscriptions.",
        ("q2-activation-subscriptions",),
    ),
    "GQ-SAA-005": (
        "Q2 subscription events extend the monthly MRR bridge.",
        ("q2-activation-subscriptions",),
    ),
    "GQ-SAA-007": (
        "Q2 payment revenue and subscription events extend ARPA.",
        ("q2-first-payment-facts",),
    ),
    "GQ-XDM-001": (
        "Q2 SaaS payments and Commerce fees extend revenue by business line.",
        ("q2-first-payment-facts", "q2-commerce-orders"),
    ),
}


def main() -> None:
    baseline = load_baseline_index(BENCHMARK_ROOT / "baseline_1.0.0_index.json")
    catalog = load_benchmark_catalog(BENCHMARK_ROOT / "cases.json")
    current = {
        case.case_id: case for case in catalog.cases if case.status is BenchmarkStatus.EXECUTABLE
    }
    old_cases: list[dict[str, object]] = []
    for old in baseline.cases:
        case = current[old.case_id]
        if case.expected_result_path is None or case.expected_result_digest is None:
            raise ValueError(f"missing current expected result: {old.case_id}")
        expected = load_expected_result(BENCHMARK_ROOT / case.expected_result_path)
        new_business_digest = compute_business_result_digest(expected)
        changed = old.business_result_digest != new_business_digest
        if changed:
            reason, scenarios = CHANGES[old.case_id]
        else:
            reason, scenarios = "unchanged", ()
        old_cases.append(
            {
                "case_id": old.case_id,
                "old_expected_digest": old.expected_result_digest,
                "new_expected_digest": case.expected_result_digest,
                "old_business_result_digest": old.business_result_digest,
                "new_business_result_digest": new_business_digest,
                "changed": changed,
                "change_reason": reason,
                "scenario_ids": scenarios,
            }
        )
    new_cases = sorted(set(current) - {case.case_id for case in baseline.cases})
    payload = {
        "from_dataset_version": baseline.dataset_version,
        "from_dataset_digest": baseline.dataset_digest,
        "from_catalog_digest": baseline.catalog_digest,
        "from_oracle_assets_digest": baseline.oracle_assets_digest,
        "from_git_commit": baseline.baseline_git_commit,
        "to_dataset_version": catalog.dataset_version,
        "to_dataset_digest": catalog.dataset_digest,
        "to_oracle_assets_digest": catalog.oracle_assets_digest,
        "old_cases": old_cases,
        "new_cases": new_cases,
    }
    output = BENCHMARK_ROOT / "baseline_delta_1.0.0_to_1.1.0.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
