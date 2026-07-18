"""Unit tests for safe, atomic evaluation report output."""

import os
import sys
from pathlib import Path

import pytest

from insightops.evaluation.__main__ import (
    DEFAULT_BUSINESS_DEFINITION_PATH,
    DEFAULT_SUITE_PATH,
    PROJECT_ROOT,
    ReportOutputError,
    _write_report,
    main,
    resolve_report_output_path,
)
from insightops.evaluation.contracts import EvaluationAbortCode, EvaluationReport
from insightops.evaluation.execution import ReadonlySqlExecutor
from insightops.evaluation.reporting import build_aborted_report


def test_report_output_rejects_suite_and_submission(tmp_path: Path) -> None:
    submission = tmp_path / "submission.json"
    submission.write_text("{}", encoding="utf-8")

    with pytest.raises(ReportOutputError):
        resolve_report_output_path(DEFAULT_SUITE_PATH, DEFAULT_SUITE_PATH, submission)
    with pytest.raises(ReportOutputError):
        resolve_report_output_path(submission, DEFAULT_SUITE_PATH, submission)
    with pytest.raises(ReportOutputError):
        resolve_report_output_path(
            DEFAULT_BUSINESS_DEFINITION_PATH,
            DEFAULT_SUITE_PATH,
            submission,
        )


@pytest.mark.parametrize(
    "protected_target",
    [
        PROJECT_ROOT / "benchmarks" / "report.json",
        PROJECT_ROOT / "data" / "seed" / "report.json",
    ],
)
def test_report_output_rejects_protected_directories(
    protected_target: Path,
    tmp_path: Path,
) -> None:
    submission = tmp_path / "submission.json"

    with pytest.raises(ReportOutputError):
        resolve_report_output_path(protected_target, DEFAULT_SUITE_PATH, submission)


def test_report_output_rejects_symlink_to_protected_asset(tmp_path: Path) -> None:
    submission = tmp_path / "submission.json"
    output_link = tmp_path / "report.json"
    output_link.symlink_to(DEFAULT_SUITE_PATH)

    with pytest.raises(ReportOutputError):
        resolve_report_output_path(output_link, DEFAULT_SUITE_PATH, submission)


def test_atomic_report_write_preserves_existing_file_on_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "report.json"
    output.write_text("original\n", encoding="utf-8")
    report = build_aborted_report(EvaluationAbortCode.INVALID_SUBMISSION)

    def fail_replace(_source: Path, _destination: Path) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(ReportOutputError, match="atomically"):
        _write_report(output, report)

    assert output.read_text(encoding="utf-8") == "original\n"
    assert tuple(tmp_path.glob(".report.json.*.tmp")) == ()


def test_atomic_report_write_creates_parent_and_complete_json(tmp_path: Path) -> None:
    output = tmp_path / "new" / "report.json"
    report = build_aborted_report(EvaluationAbortCode.INVALID_SUBMISSION)

    _write_report(output, report)

    written = EvaluationReport.model_validate_json(output.read_text(encoding="utf-8"))
    assert written == report
    assert output.read_text(encoding="utf-8").endswith(
        "\n"
    ) and '"deterministic_payload"' not in output.read_text(encoding="utf-8")
    assert tuple(output.parent.glob(".report.json.*.tmp")) == ()


def test_preflight_failure_never_calls_candidate_executor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_submission = tmp_path / "submission.json"
    invalid_submission.write_text("{", encoding="utf-8")
    output = tmp_path / "report.json"
    calls = 0

    def count_execute(
        _executor: ReadonlySqlExecutor,
        _sql: str,
        _parameters: object,
    ) -> object:
        nonlocal calls
        calls += 1
        raise AssertionError("candidate executor must not run during failed preflight")

    monkeypatch.setattr(ReadonlySqlExecutor, "execute", count_execute)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "insightops.evaluation",
            "--suite",
            str(DEFAULT_SUITE_PATH),
            "--submission",
            str(invalid_submission),
            "--output",
            str(output),
        ],
    )

    with pytest.raises(SystemExit) as captured:
        main()

    assert captured.value.code == 2
    assert calls == 0
