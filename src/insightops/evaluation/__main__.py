"""CLI for the M1.2B deterministic SQL evaluation harness."""

import argparse
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Never

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from insightops.benchmark.contracts import BenchmarkCatalog
from insightops.benchmark.registry import load_benchmark_catalog, validate_benchmark_bundle
from insightops.canonical import compute_business_definition_digest
from insightops.core.config import Settings, load_settings
from insightops.db.session import create_database_engine
from insightops.evaluation.contracts import (
    CandidateSubmission,
    EvaluationAbortCode,
    EvaluationReport,
    EvaluationRunStatus,
    EvaluationSuiteManifest,
)
from insightops.evaluation.execution import (
    ReadonlyDatabaseSettings,
    ReadonlySqlExecutor,
    SqlExecutionError,
    create_readonly_database_engine,
    load_readonly_database_settings,
)
from insightops.evaluation.reporting import build_aborted_report
from insightops.evaluation.runner import EvaluationRunner
from insightops.evaluation.suite import (
    M1_2B_BUSINESS_DEFINITION_DIGEST,
    M1_2B_CATALOG_ID,
    M1_2B_CATALOG_VERSION,
    M1_2B_DATASET_DIGEST,
    M1_2B_DATASET_ID,
    M1_2B_DATASET_VERSION,
    M1_2B_ORACLE_ASSETS_DIGEST,
    M1_2B_SCHEMA_REVISION,
    load_evaluation_suite,
    validate_candidate_submission,
    validate_expected_column_type_bindings,
)
from insightops.seed.contracts import SeedDataset
from insightops.seed.dataset import load_seed_dataset
from insightops.seed.loader import DatasetLoader, SeedDatasetError

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SUITE_PATH = PROJECT_ROOT / "evaluations" / "m1_2b" / "suite.json"
DEFAULT_CATALOG_PATH = PROJECT_ROOT / "benchmarks" / "m1_2a" / "cases.json"
DEFAULT_BENCHMARK_ROOT = PROJECT_ROOT / "benchmarks" / "m1_2a"
DEFAULT_DATASET_ROOT = PROJECT_ROOT / "data" / "seed" / "m1_2a"
DEFAULT_BUSINESS_DEFINITION_PATH = PROJECT_ROOT / "docs" / "business-definitions-v1.md"


class ReportOutputError(ValueError):
    """Raised when a report target is unsafe or cannot be written atomically."""


def main() -> None:
    """Validate inputs, execute the suite, and write one versioned JSON report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE_PATH)
    parser.add_argument("--submission", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG_PATH)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    args = parser.parse_args()
    started = time.monotonic()

    try:
        output_path = resolve_report_output_path(args.output, args.suite, args.submission)
    except ReportOutputError as error:
        parser.error(str(error))

    try:
        claimed_suite = EvaluationSuiteManifest.model_validate_json(
            args.suite.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, ValidationError):
        _abort(output_path, EvaluationAbortCode.INVALID_SUITE_MANIFEST, started)
    if claimed_suite.computed_digest() != claimed_suite.suite_digest:
        _abort(output_path, EvaluationAbortCode.SUITE_DIGEST_MISMATCH, started)

    try:
        submission = CandidateSubmission.model_validate_json(
            args.submission.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, ValidationError):
        _abort(output_path, EvaluationAbortCode.INVALID_SUBMISSION, started)

    try:
        catalog = load_benchmark_catalog(args.catalog)
    except (OSError, UnicodeError, ValidationError, ValueError):
        _abort(output_path, EvaluationAbortCode.CATALOG_BINDING_MISMATCH, started)

    try:
        suite = load_evaluation_suite(args.suite, args.catalog)
    except (OSError, UnicodeError, ValidationError, ValueError):
        _abort(output_path, _suite_abort_code(claimed_suite, catalog), started)
    try:
        validate_candidate_submission(submission, suite, validate_actions=False)
    except ValueError:
        _abort(output_path, EvaluationAbortCode.INVALID_SUBMISSION, started)

    try:
        dataset = load_seed_dataset(args.dataset_root)
    except (OSError, UnicodeError, ValidationError, ValueError):
        _abort(output_path, EvaluationAbortCode.DATASET_BINDING_MISMATCH, started)

    binding_error = _binding_abort_code(suite, catalog, dataset)
    if binding_error is not None:
        _abort(output_path, binding_error, started)

    try:
        definition_digest = compute_business_definition_digest(DEFAULT_BUSINESS_DEFINITION_PATH)
    except OSError:
        _abort(
            output_path,
            EvaluationAbortCode.BUSINESS_DEFINITION_BINDING_MISMATCH,
            started,
        )
    if definition_digest != suite.business_definition.business_definition_digest:
        _abort(output_path, EvaluationAbortCode.BUSINESS_DEFINITION_BINDING_MISMATCH, started)
    try:
        validate_benchmark_bundle(
            DEFAULT_BENCHMARK_ROOT,
            catalog,
            dataset.manifest,
            DEFAULT_BUSINESS_DEFINITION_PATH,
        )
        validate_expected_column_type_bindings(suite, catalog, DEFAULT_BENCHMARK_ROOT)
    except (OSError, UnicodeError, ValidationError, ValueError):
        _abort(output_path, EvaluationAbortCode.ORACLE_DIGEST_MISMATCH, started)

    try:
        writer_settings = load_settings()
        readonly_settings = load_readonly_database_settings()
    except ValidationError:
        _abort(output_path, EvaluationAbortCode.EVALUATION_ENVIRONMENT_INVALID, started)
    if not _readonly_environment_matches(readonly_settings, writer_settings):
        _abort(output_path, EvaluationAbortCode.EVALUATION_ENVIRONMENT_INVALID, started)

    writer_engine = create_database_engine(writer_settings)
    readonly_engine = None
    try:
        try:
            with writer_engine.connect() as connection:
                revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        except DBAPIError:
            _abort(output_path, EvaluationAbortCode.EVALUATION_ENVIRONMENT_INVALID, started)
        if revision != suite.schema_revision:
            _abort(output_path, EvaluationAbortCode.SCHEMA_BINDING_MISMATCH, started)
        try:
            DatasetLoader(writer_engine, dataset, app_env=writer_settings.app_env).verify()
        except SeedDatasetError:
            _abort(output_path, EvaluationAbortCode.DATASET_VERIFICATION_FAILED, started)

        readonly_engine = create_readonly_database_engine(
            readonly_settings,
            timeout_ms=suite.execution_limits.timeout_ms,
        )
        readonly_executor = ReadonlySqlExecutor(
            readonly_engine,
            readonly_settings,
            suite.execution_limits,
        )
        try:
            readonly_executor.verify_identity()
        except SqlExecutionError:
            _abort(
                output_path,
                EvaluationAbortCode.READONLY_IDENTITY_VERIFICATION_FAILED,
                started,
            )

        runner = EvaluationRunner(
            suite=suite,
            catalog=catalog,
            dataset=dataset,
            writer_engine=writer_engine,
            readonly_executor=readonly_executor,
            benchmark_root=DEFAULT_BENCHMARK_ROOT,
            business_definition_path=DEFAULT_BUSINESS_DEFINITION_PATH,
            app_env=writer_settings.app_env,
        )
        report = runner.run(submission)
    finally:
        if readonly_engine is not None:
            readonly_engine.dispose()
        writer_engine.dispose()

    try:
        _write_report(output_path, report)
    except ReportOutputError as error:
        raise SystemExit(str(error)) from None
    if report.run_status is EvaluationRunStatus.ABORTED:
        raise SystemExit(2)


def resolve_report_output_path(
    output_path: Path,
    suite_path: Path,
    submission_path: Path,
) -> Path:
    """Resolve and reject any report target that overlaps protected input assets."""
    resolved = output_path.resolve(strict=False)
    protected_directories = (
        (PROJECT_ROOT / "data" / "seed").resolve(),
        (PROJECT_ROOT / "benchmarks").resolve(),
    )
    if any(resolved.is_relative_to(directory) for directory in protected_directories):
        raise ReportOutputError("report output cannot be inside protected benchmark assets")
    protected_files = {
        DEFAULT_SUITE_PATH.resolve(),
        DEFAULT_BUSINESS_DEFINITION_PATH.resolve(),
        suite_path.resolve(strict=False),
        submission_path.resolve(strict=False),
    }
    if resolved in protected_files:
        raise ReportOutputError("report output cannot overwrite an evaluation input asset")
    return resolved


def _write_report(output_path: Path, report: EvaluationReport) -> None:
    """Atomically replace a report after a complete UTF-8 write and fsync."""
    temporary_path: Path | None = None
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output_file:
            output_file.write(_serialize_report(report) + "\n")
            output_file.flush()
            os.fsync(output_file.fileno())
        os.replace(temporary_path, output_path)
        temporary_path = None
    except OSError as error:
        raise ReportOutputError("failed to write evaluation report atomically") from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _abort(output_path: Path, code: EvaluationAbortCode, started: float) -> Never:
    report = build_aborted_report(code, duration_ms=_duration_ms(started))
    try:
        _write_report(output_path, report)
    except ReportOutputError as error:
        raise SystemExit(str(error)) from None
    raise SystemExit(2)


def _serialize_report(report: EvaluationReport) -> str:
    payload = report.model_dump(mode="json")
    if report.run_status is EvaluationRunStatus.ABORTED:
        payload.pop("deterministic_payload")
    else:
        payload.pop("abort_code")
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _suite_abort_code(
    suite: EvaluationSuiteManifest,
    catalog: BenchmarkCatalog,
) -> EvaluationAbortCode:
    if (
        suite.schema_revision != M1_2B_SCHEMA_REVISION
        or suite.schema_revision != catalog.schema_revision
    ):
        return EvaluationAbortCode.SCHEMA_BINDING_MISMATCH
    if (
        suite.dataset.dataset_id != M1_2B_DATASET_ID
        or suite.dataset.dataset_version != M1_2B_DATASET_VERSION
        or suite.dataset.dataset_digest != M1_2B_DATASET_DIGEST
    ):
        return EvaluationAbortCode.DATASET_BINDING_MISMATCH
    if (
        suite.catalog.catalog_id != M1_2B_CATALOG_ID
        or suite.catalog.catalog_version != M1_2B_CATALOG_VERSION
    ):
        return EvaluationAbortCode.CATALOG_BINDING_MISMATCH
    if suite.business_definition.business_definition_digest != M1_2B_BUSINESS_DEFINITION_DIGEST:
        return EvaluationAbortCode.BUSINESS_DEFINITION_BINDING_MISMATCH
    if suite.oracle_assets_digest != M1_2B_ORACLE_ASSETS_DIGEST:
        return EvaluationAbortCode.ORACLE_DIGEST_MISMATCH
    return EvaluationAbortCode.INVALID_SUITE_MANIFEST


def _binding_abort_code(
    suite: EvaluationSuiteManifest,
    catalog: BenchmarkCatalog,
    dataset: SeedDataset,
) -> EvaluationAbortCode | None:
    manifest = dataset.manifest
    if (
        manifest.dataset_id != suite.dataset.dataset_id
        or manifest.dataset_version != suite.dataset.dataset_version
        or manifest.dataset_digest != suite.dataset.dataset_digest
        or dataset.computed_digest != suite.dataset.dataset_digest
    ):
        return EvaluationAbortCode.DATASET_BINDING_MISMATCH
    if (
        manifest.schema_revision != suite.schema_revision
        or catalog.schema_revision != suite.schema_revision
    ):
        return EvaluationAbortCode.SCHEMA_BINDING_MISMATCH
    if (
        manifest.benchmark_catalog_id != suite.catalog.catalog_id
        or manifest.benchmark_catalog_version != suite.catalog.catalog_version
        or catalog.catalog_id != suite.catalog.catalog_id
        or catalog.catalog_version != suite.catalog.catalog_version
    ):
        return EvaluationAbortCode.CATALOG_BINDING_MISMATCH
    if (
        manifest.business_definition_digest != suite.business_definition.business_definition_digest
        or catalog.business_definition_digest
        != suite.business_definition.business_definition_digest
    ):
        return EvaluationAbortCode.BUSINESS_DEFINITION_BINDING_MISMATCH
    if (
        manifest.oracle_assets_digest != suite.oracle_assets_digest
        or catalog.oracle_assets_digest != suite.oracle_assets_digest
    ):
        return EvaluationAbortCode.ORACLE_DIGEST_MISMATCH
    return None


def _readonly_environment_matches(
    readonly: ReadonlyDatabaseSettings,
    writer: Settings,
) -> bool:
    return (
        readonly.user != writer.database_user
        and readonly.host == writer.database_host
        and readonly.port == writer.database_port
        and readonly.name == writer.database_name
    )


def _duration_ms(started: float) -> int:
    return max(int((time.monotonic() - started) * 1_000), 0)


if __name__ == "__main__":
    main()
