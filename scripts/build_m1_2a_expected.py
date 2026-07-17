"""Generate or explicitly apply reviewed M1.2A expected-result candidates."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from alembic.config import Config

from alembic import command
from insightops.benchmark.authoring import (
    apply_reviewed_candidate,
    assert_database_is_empty,
    assert_isolated_database_name,
    remove_empty_alembic_version_table,
    require_clean_worktree,
    validate_loaded_authoring_database,
    write_candidate_bundle,
)
from insightops.benchmark.contracts import BenchmarkCatalog, BenchmarkStatus, ExpectedResult
from insightops.benchmark.oracle import execute_gold_case
from insightops.benchmark.registry import (
    compute_expected_result_digest,
    compute_oracle_assets_digest,
    compute_sql_digest,
)
from insightops.core.config import load_settings
from insightops.db.session import create_database_engine
from insightops.seed.dataset import load_seed_dataset
from insightops.seed.loader import DatasetLoader

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = ROOT / "benchmarks" / "m1_2a"
CATALOG_PATH = BENCHMARK_ROOT / "cases.json"
MANIFEST_PATH = ROOT / "data" / "seed" / "m1_2a" / "manifest.json"
ZERO_DIGEST = "0" * 64
DEFAULT_CANDIDATE_ROOT = Path("/tmp/insightops-m1-2a-expected-candidate")
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
    "GQ-MKT-008": (
        "boundary_case",
        "business_scope",
        "conversion_type",
        "authoritative_external_id",
        "source_data_cutoff_at",
    ),
    "GQ-PRD-001": (),
    "GQ-PRD-006": ("condition_stage",),
    "GQ-PRD-007": ("cohort_month",),
    "GQ-PRD-008": ("channel_code",),
    "GQ-XDM-002": ("merchant_id",),
    "GQ-XDM-007": ("gmv_change", "merchant_id"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-dir", type=Path, default=DEFAULT_CANDIDATE_ROOT)
    parser.add_argument("--replace-candidate", action="store_true")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--apply-reviewed", type=Path)
    return parser.parse_args()


def build_candidate_payloads() -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    """Build candidates only from a clean isolated schema loaded with canonical seed data."""
    catalog_payload: dict[str, Any] = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    catalog = BenchmarkCatalog.model_validate(catalog_payload)
    expected_payloads: dict[str, dict[str, Any]] = {}
    dataset = load_seed_dataset(ROOT / "data/seed/m1_2a")
    base_settings = load_settings()
    authoring_database_name = os.environ.get("M1_2A_AUTHORING_DATABASE_NAME")
    if authoring_database_name is None:
        raise ValueError("M1_2A_AUTHORING_DATABASE_NAME is required for isolated authoring")
    assert_isolated_database_name(authoring_database_name, base_settings.database_name)
    authoring_settings = base_settings.model_copy(update={"database_name": authoring_database_name})
    alembic_config = Config(str(ROOT / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(ROOT / "alembic"))
    migration_attempted = False
    engine = create_database_engine(authoring_settings)
    try:
        with engine.connect() as connection:
            assert_database_is_empty(connection)
        engine.dispose()
        migration_attempted = True
        with _database_name_override(authoring_database_name):
            command.upgrade(alembic_config, dataset.manifest.schema_revision)
        engine = create_database_engine(authoring_settings)
        loader = DatasetLoader(engine, dataset, app_env="test")
        loaded_counts = loader.load()
        if loaded_counts != dataset.manifest.expected_row_counts:
            raise ValueError("canonical dataset load returned unexpected row counts")
        validate_loaded_authoring_database(engine, dataset)
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
        if migration_attempted:
            with _database_name_override(authoring_database_name):
                command.downgrade(alembic_config, "base")
            cleanup_engine = create_database_engine(authoring_settings)
            try:
                with cleanup_engine.begin() as connection:
                    remove_empty_alembic_version_table(connection)
                    assert_database_is_empty(connection)
            finally:
                cleanup_engine.dispose()

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

    manifest_payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_payload["oracle_assets_digest"] = oracle_digest
    for expected_payload in expected_payloads.values():
        expected_payload["oracle_assets_digest"] = oracle_digest
    return catalog_payload, manifest_payload, expected_payloads


@contextmanager
def _database_name_override(database_name: str) -> Iterator[None]:
    previous = os.environ.get("DATABASE_NAME")
    os.environ["DATABASE_NAME"] = database_name
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("DATABASE_NAME", None)
        else:
            os.environ["DATABASE_NAME"] = previous


def main() -> None:
    args = parse_args()
    if args.apply_reviewed is not None:
        if args.allow_dirty:
            raise ValueError("dirty-worktree override can only generate a candidate")
        apply_reviewed_candidate(ROOT, args.apply_reviewed.resolve())
        return
    if not args.allow_dirty:
        require_clean_worktree(ROOT)
    catalog_payload, manifest_payload, expected_payloads = build_candidate_payloads()
    write_candidate_bundle(
        args.candidate_dir.resolve(),
        project_root=ROOT,
        catalog_payload=catalog_payload,
        manifest_payload=manifest_payload,
        expected_payloads=expected_payloads,
        replace=args.replace_candidate,
    )


if __name__ == "__main__":
    main()
