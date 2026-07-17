"""Compare the immutable M1.2A v1.0.0 baseline index with its merge commit."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any, cast

from insightops.benchmark.authoring import require_clean_worktree
from insightops.canonical import canonical_json_digest

ROOT = Path(__file__).resolve().parents[1]
BASELINE_COMMIT = "70680bc087a739583bcd5242907f9f0c6d9b2e0b"
OUTPUT = ROOT / "benchmarks" / "m1_2a" / "baseline_1.0.0_index.json"


def git_json(path: str) -> dict[str, Any]:
    completed = subprocess.run(
        ["git", "show", f"{BASELINE_COMMIT}:{path}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return cast(dict[str, Any], json.loads(completed.stdout))


def business_result_digest(expected: dict[str, Any]) -> str:
    return canonical_json_digest(
        {
            "case_id": expected["case_id"],
            "columns": expected["columns"],
            "ordered_by": expected["ordered_by"],
            "rows": expected["rows"],
        }
    )


def build_payload() -> dict[str, Any]:
    manifest = git_json("data/seed/m1_2a/manifest.json")
    catalog = git_json("benchmarks/m1_2a/cases.json")
    cases: list[dict[str, str]] = []
    for case in catalog["cases"]:
        if case["status"] != "executable":
            continue
        expected = git_json(f"benchmarks/m1_2a/{case['expected_result_path']}")
        cases.append(
            {
                "case_id": case["case_id"],
                "expected_result_digest": case["expected_result_digest"],
                "business_result_digest": business_result_digest(expected),
            }
        )
    payload = {
        "dataset_id": manifest["dataset_id"],
        "dataset_version": manifest["dataset_version"],
        "dataset_digest": manifest["dataset_digest"],
        "baseline_git_commit": BASELINE_COMMIT,
        "catalog_id": catalog["catalog_id"],
        "catalog_version": catalog["catalog_version"],
        "catalog_digest": canonical_json_digest(catalog),
        "oracle_assets_digest": catalog["oracle_assets_digest"],
        "cases": sorted(cases, key=lambda item: item["case_id"]),
    }
    if len(cases) != 16:
        raise ValueError(f"baseline must contain 16 executable cases, got {len(cases)}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-reviewed", action="store_true")
    args = parser.parse_args()
    payload = build_payload()
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.write_reviewed:
        require_clean_worktree(ROOT)
        OUTPUT.write_text(rendered, encoding="utf-8")
        return
    if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != rendered:
        raise ValueError(
            "reviewed baseline index differs from its fixed commit; "
            "inspect before using --write-reviewed"
        )


if __name__ == "__main__":
    main()
