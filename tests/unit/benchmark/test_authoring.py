"""Unit tests for candidate-only benchmark authoring."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from insightops.benchmark.authoring import reviewed_delta_pair_metadata, write_candidate_bundle
from insightops.benchmark.registry import load_baseline_delta_report

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BENCHMARK_ROOT = PROJECT_ROOT / "benchmarks" / "m1_2a"
MANIFEST_PATH = PROJECT_ROOT / "data" / "seed" / "m1_2a" / "manifest.json"


def _load_payloads() -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    catalog = json.loads((BENCHMARK_ROOT / "cases.json").read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    expected = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((BENCHMARK_ROOT / "expected").glob("*.json"))
    }
    return catalog, manifest, expected


def _reviewed_asset_hashes() -> dict[Path, str]:
    paths = [
        BENCHMARK_ROOT / "cases.json",
        MANIFEST_PATH,
        *sorted((BENCHMARK_ROOT / "expected").glob("*.json")),
    ]
    return {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def test_default_candidate_write_does_not_overwrite_reviewed_assets(tmp_path: Path) -> None:
    catalog, manifest, expected = _load_payloads()
    before = _reviewed_asset_hashes()

    candidate_root = tmp_path / "candidate"
    write_candidate_bundle(
        candidate_root,
        project_root=PROJECT_ROOT,
        catalog_payload=catalog,
        manifest_payload=manifest,
        expected_payloads=expected,
    )

    assert (candidate_root / "candidate_metadata.json").is_file()
    assert (candidate_root / "expected" / "GQ-MKT-008.json").is_file()
    assert _reviewed_asset_hashes() == before


def test_validator_failure_does_not_write_reviewed_assets(tmp_path: Path) -> None:
    catalog, manifest, expected = _load_payloads()
    before = _reviewed_asset_hashes()
    expected["GQ-MKT-004"]["rows"][0]["touched_subject_count"] = 999

    with pytest.raises(ValueError, match="expected result digest mismatch"):
        write_candidate_bundle(
            tmp_path / "invalid-candidate",
            project_root=PROJECT_ROOT,
            catalog_payload=catalog,
            manifest_payload=manifest,
            expected_payloads=expected,
        )

    assert _reviewed_asset_hashes() == before


def test_unreviewed_delta_pair_does_not_inherit_an_old_reason() -> None:
    report = load_baseline_delta_report(BENCHMARK_ROOT / "baseline_delta_1.0.0_to_1.1.0.json")
    prior = next(case for case in report.old_cases if case.case_id == "GQ-COM-001")
    assert prior.changed

    reason, scenarios, status = reviewed_delta_pair_metadata(
        prior,
        old_expected_digest=prior.old_expected_digest,
        new_expected_digest="f" * 64,
        old_business_result_digest=prior.old_business_result_digest,
        new_business_result_digest="e" * 64,
    )

    assert status == "review_required"
    assert reason is None
    assert scenarios == ()
