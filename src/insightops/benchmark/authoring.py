"""Safety primitives for reviewed M1.2A benchmark asset authoring."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from sqlalchemy import Connection, Engine, func, select, text

from insightops.benchmark.contracts import BaselineDeltaCase, BenchmarkCatalog
from insightops.benchmark.registry import validate_benchmark_bundle
from insightops.canonical import canonical_json_digest
from insightops.db.models import Base
from insightops.seed.contracts import DatasetManifest, SeedDataset
from insightops.seed.loader import DatasetLoader

CANDIDATE_METADATA_FILENAME = "candidate_metadata.json"


def reviewed_delta_pair_metadata(
    prior: BaselineDeltaCase,
    *,
    old_expected_digest: str,
    new_expected_digest: str,
    old_business_result_digest: str,
    new_business_result_digest: str,
) -> tuple[str | None, tuple[str, ...], str]:
    """Reuse review metadata only when all four frozen digests still match exactly."""
    exact_pair_matches = (
        prior.old_expected_digest == old_expected_digest
        and prior.new_expected_digest == new_expected_digest
        and prior.old_business_result_digest == old_business_result_digest
        and prior.new_business_result_digest == new_business_result_digest
    )
    if exact_pair_matches:
        return prior.change_reason, prior.scenario_ids, "matches_reviewed"
    return None, (), "review_required"


def require_clean_worktree(project_root: Path) -> None:
    """Reject authoring mutations when tracked or untracked workspace state is dirty."""
    completed = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )
    if completed.stdout.strip():
        raise ValueError("reviewed asset apply requires a clean Git worktree")


def input_assets_digest(project_root: Path) -> str:
    """Hash every reviewed input that can influence generated benchmark assets."""
    relative_paths = [
        Path("docs/business-definitions-v1.md"),
        Path("data/seed/m1_2a/manifest.json"),
        Path("data/seed/m1_2a/identity.json"),
        Path("data/seed/m1_2a/saas.json"),
        Path("data/seed/m1_2a/commerce.json"),
        Path("data/seed/m1_2a/marketing.json"),
        Path("benchmarks/m1_2a/cases.json"),
        *(
            path.relative_to(project_root)
            for path in sorted((project_root / "benchmarks/m1_2a/sql").glob("*.sql"))
        ),
        *(
            path.relative_to(project_root)
            for path in sorted((project_root / "benchmarks/m1_2a/expected").glob("*.json"))
        ),
    ]
    payload = {
        str(path): hashlib.sha256((project_root / path).read_bytes()).hexdigest()
        for path in relative_paths
    }
    return canonical_json_digest(payload)


def assert_isolated_database_name(database_name: str, application_database_name: str) -> None:
    """Require an explicitly separate authoring schema with an unmistakable name."""
    if database_name == application_database_name:
        raise ValueError("authoring database must differ from the application database")
    if not database_name.endswith(("_authoring", "_benchmark_authoring")):
        raise ValueError("authoring database name must end with _authoring")


def database_table_names(connection: Connection) -> tuple[str, ...]:
    """Return all base tables in the current MySQL schema."""
    rows = connection.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE' "
            "ORDER BY table_name"
        )
    ).scalars()
    return tuple(str(value) for value in rows)


def assert_database_is_empty(connection: Connection) -> None:
    """Refuse to migrate or load an authoring schema containing any table."""
    table_names = database_table_names(connection)
    if table_names:
        raise ValueError(f"authoring database is not empty: {list(table_names)}")


def remove_empty_alembic_version_table(connection: Connection) -> None:
    """Remove Alembic's empty bookkeeping table after downgrading an isolated schema."""
    table_names = database_table_names(connection)
    if not table_names:
        return
    if table_names != ("alembic_version",):
        raise ValueError(f"authoring cleanup left business tables behind: {list(table_names)}")
    if int(connection.scalar(text("SELECT COUNT(*) FROM alembic_version")) or 0) != 0:
        raise ValueError("authoring cleanup left an Alembic revision behind")
    connection.execute(text("DROP TABLE alembic_version"))


def assert_database_revision(connection: Connection, expected_revision: str) -> None:
    """Require the isolated schema to match the dataset's exact Alembic binding."""
    actual_revision = connection.execute(
        text("SELECT version_num FROM alembic_version")
    ).scalar_one()
    if actual_revision != expected_revision:
        message = (
            f"authoring database revision mismatch: expected {expected_revision}, "
            f"got {actual_revision}"
        )
        raise ValueError(message)


def assert_database_matches_dataset(connection: Connection, dataset: SeedDataset) -> None:
    """Prove the database contains exactly the canonical rows and no extras."""
    actual_counts: dict[str, int] = {}
    for table_name in dataset.manifest.table_order:
        table = Base.metadata.tables[table_name]
        actual_counts[table_name] = int(
            connection.scalar(select(func.count()).select_from(table)) or 0
        )
    if actual_counts != dataset.manifest.expected_row_counts:
        raise ValueError(
            "authoring database contains non-canonical row counts: "
            f"expected {dataset.manifest.expected_row_counts}, got {actual_counts}"
        )


def validate_loaded_authoring_database(engine: Engine, dataset: SeedDataset) -> None:
    """Run loader verification plus revision and exact-count checks."""
    loader = DatasetLoader(engine, dataset, app_env="test")
    loader.verify()
    with engine.connect() as connection:
        assert_database_revision(connection, dataset.manifest.schema_revision)
        assert_database_matches_dataset(connection, dataset)


def write_candidate_bundle(
    candidate_root: Path,
    *,
    project_root: Path,
    catalog_payload: Mapping[str, Any],
    manifest_payload: Mapping[str, Any],
    expected_payloads: Mapping[str, Mapping[str, Any]],
    replace: bool = False,
) -> None:
    """Write and validate an isolated candidate without touching reviewed assets."""
    if candidate_root.exists():
        if not replace:
            raise ValueError(f"candidate directory already exists: {candidate_root}")
        shutil.rmtree(candidate_root)
    (candidate_root / "expected").mkdir(parents=True)
    (candidate_root / "sql").mkdir()
    _write_json(candidate_root / "cases.json", catalog_payload)
    _write_json(candidate_root / "manifest.json", manifest_payload)
    for case_id, payload in expected_payloads.items():
        _write_json(candidate_root / "expected" / f"{case_id}.json", payload)
    for sql_path in sorted((project_root / "benchmarks/m1_2a/sql").glob("*.sql")):
        shutil.copyfile(sql_path, candidate_root / "sql" / sql_path.name)

    catalog = BenchmarkCatalog.model_validate(catalog_payload)
    manifest = DatasetManifest.model_validate(manifest_payload)
    validate_benchmark_bundle(
        candidate_root,
        catalog,
        manifest,
        project_root / "docs/business-definitions-v1.md",
    )
    metadata = {
        "format_version": "m1-2a-candidate-v1",
        "input_assets_digest": input_assets_digest(project_root),
        "dataset_digest": manifest.dataset_digest,
        "oracle_assets_digest": catalog.oracle_assets_digest,
    }
    _write_json(candidate_root / CANDIDATE_METADATA_FILENAME, metadata)


def apply_reviewed_candidate(project_root: Path, candidate_root: Path) -> None:
    """Apply a validated candidate only from a clean, unchanged reviewed input state."""
    require_clean_worktree(project_root)
    metadata = _load_json(candidate_root / CANDIDATE_METADATA_FILENAME)
    if metadata.get("format_version") != "m1-2a-candidate-v1":
        raise ValueError("unsupported benchmark candidate format")
    if metadata.get("input_assets_digest") != input_assets_digest(project_root):
        raise ValueError("candidate input digest no longer matches reviewed repository assets")

    catalog_payload = _load_json(candidate_root / "cases.json")
    manifest_payload = _load_json(candidate_root / "manifest.json")
    catalog = BenchmarkCatalog.model_validate(catalog_payload)
    manifest = DatasetManifest.model_validate(manifest_payload)
    validate_benchmark_bundle(
        candidate_root,
        catalog,
        manifest,
        project_root / "docs/business-definitions-v1.md",
    )
    if metadata.get("dataset_digest") != manifest.dataset_digest:
        raise ValueError("candidate dataset digest metadata mismatch")
    if metadata.get("oracle_assets_digest") != catalog.oracle_assets_digest:
        raise ValueError("candidate oracle digest metadata mismatch")

    benchmark_root = project_root / "benchmarks/m1_2a"
    shutil.copyfile(candidate_root / "cases.json", benchmark_root / "cases.json")
    shutil.copyfile(
        candidate_root / "manifest.json",
        project_root / "data/seed/m1_2a/manifest.json",
    )
    for case in catalog.cases:
        if case.expected_result_path is None:
            continue
        source = candidate_root / case.expected_result_path
        destination = benchmark_root / case.expected_result_path
        shutil.copyfile(source, destination)


def _load_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
