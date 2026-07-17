"""Generate a review-required M1.2A delta candidate or apply an approved one."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from insightops.benchmark.authoring import (
    input_assets_digest,
    require_clean_worktree,
    reviewed_delta_pair_metadata,
)
from insightops.benchmark.contracts import BaselineDeltaReport, BenchmarkStatus
from insightops.benchmark.registry import (
    compute_business_result_digest,
    load_baseline_delta_report,
    load_baseline_index,
    load_benchmark_catalog,
    load_expected_result,
    validate_baseline_delta,
)

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = ROOT / "benchmarks" / "m1_2a"
REVIEWED_PATH = BENCHMARK_ROOT / "baseline_delta_1.0.0_to_1.1.0.json"
DEFAULT_CANDIDATE_PATH = Path("/tmp/insightops-m1-2a-delta-candidate.json")


def build_candidate() -> dict[str, Any]:
    """Compare exact current digest pairs with the checked-in reviewed report."""
    baseline = load_baseline_index(BENCHMARK_ROOT / "baseline_1.0.0_index.json")
    catalog = load_benchmark_catalog(BENCHMARK_ROOT / "cases.json")
    reviewed = load_baseline_delta_report(REVIEWED_PATH)
    reviewed_by_id = {case.case_id: case for case in reviewed.old_cases}
    current = {
        case.case_id: case for case in catalog.cases if case.status is BenchmarkStatus.EXECUTABLE
    }
    old_cases: list[dict[str, Any]] = []
    unreviewed_case_ids: list[str] = []
    for old in baseline.cases:
        case = current[old.case_id]
        if case.expected_result_path is None or case.expected_result_digest is None:
            raise ValueError(f"missing current expected result: {old.case_id}")
        expected = load_expected_result(BENCHMARK_ROOT / case.expected_result_path)
        new_business_digest = compute_business_result_digest(expected)
        prior = reviewed_by_id[old.case_id]
        change_reason, scenario_ids, pair_review_status = reviewed_delta_pair_metadata(
            prior,
            old_expected_digest=old.expected_result_digest,
            new_expected_digest=case.expected_result_digest,
            old_business_result_digest=old.business_result_digest,
            new_business_result_digest=new_business_digest,
        )
        if pair_review_status == "review_required":
            unreviewed_case_ids.append(old.case_id)
        old_cases.append(
            {
                "case_id": old.case_id,
                "old_expected_digest": old.expected_result_digest,
                "new_expected_digest": case.expected_result_digest,
                "old_business_result_digest": old.business_result_digest,
                "new_business_result_digest": new_business_digest,
                "changed": old.business_result_digest != new_business_digest,
                "change_reason": change_reason,
                "scenario_ids": list(scenario_ids),
                "pair_review_status": pair_review_status,
            }
        )

    new_cases = sorted(set(current) - {case.case_id for case in baseline.cases})
    report = {
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
    top_bindings_match = (
        reviewed.to_dataset_version == catalog.dataset_version
        and reviewed.to_dataset_digest == catalog.dataset_digest
        and reviewed.to_oracle_assets_digest == catalog.oracle_assets_digest
    )
    return {
        "candidate_format": "m1-2a-delta-candidate-v1",
        "review_status": (
            "matches_reviewed"
            if top_bindings_match and not unreviewed_case_ids
            else "review_required"
        ),
        "input_assets_digest": input_assets_digest(ROOT),
        "unreviewed_case_ids": unreviewed_case_ids,
        "report": report,
    }


def apply_reviewed_candidate(candidate_path: Path) -> None:
    """Apply only a manually approved candidate whose exact inputs remain unchanged."""
    require_clean_worktree(ROOT)
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    if candidate.get("candidate_format") != "m1-2a-delta-candidate-v1":
        raise ValueError("unsupported delta candidate format")
    if candidate.get("review_status") != "approved":
        raise ValueError("delta candidate must be explicitly marked approved")
    if candidate.get("input_assets_digest") != input_assets_digest(ROOT):
        raise ValueError("delta candidate input digest no longer matches current assets")
    if candidate.get("unreviewed_case_ids"):
        raise ValueError("delta candidate still contains unreviewed digest pairs")

    report_payload = candidate["report"]
    for case in report_payload["old_cases"]:
        if case.pop("pair_review_status", None) not in {"matches_reviewed", "approved"}:
            raise ValueError(f"delta pair is not reviewed: {case['case_id']}")
    report = BaselineDeltaReport.model_validate(report_payload)
    baseline = load_baseline_index(BENCHMARK_ROOT / "baseline_1.0.0_index.json")
    catalog = load_benchmark_catalog(BENCHMARK_ROOT / "cases.json")
    validate_baseline_delta(BENCHMARK_ROOT, catalog, baseline, report)
    REVIEWED_PATH.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-path", type=Path, default=DEFAULT_CANDIDATE_PATH)
    parser.add_argument("--replace-candidate", action="store_true")
    parser.add_argument("--apply-reviewed", type=Path)
    args = parser.parse_args()
    if args.apply_reviewed is not None:
        apply_reviewed_candidate(args.apply_reviewed.resolve())
        return
    candidate_path = args.candidate_path.resolve()
    if candidate_path.exists() and not args.replace_candidate:
        raise ValueError(f"candidate delta already exists: {candidate_path}")
    candidate = build_candidate()
    candidate_path.write_text(
        json.dumps(candidate, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
