"""Unit tests for benchmark status and oracle-isolation contracts."""

import pytest
from pydantic import ValidationError

from insightops.benchmark.contracts import BenchmarkCase, BenchmarkStatus


def _case(**overrides: object) -> BenchmarkCase:
    values: dict[str, object] = {
        "case_id": "GQ-SAA-001",
        "question": "What is MRR?",
        "difficulty": "L1",
        "status": BenchmarkStatus.EXECUTABLE,
        "domains": ("saas",),
        "metrics": ("mrr",),
        "required_tables": ("subscription",),
        "phenomenon_ids": ("P15",),
        "scenario_ids": ("annual-mrr",),
        "expected_result_shape": "scalar",
        "gold_sql_path": "sql/GQ-SAA-001.sql",
        "expected_result_path": "expected/GQ-SAA-001.json",
    }
    values.update(overrides)
    return BenchmarkCase.model_validate(values)


def test_public_case_drops_oracle_fields() -> None:
    public = _case().to_public_case()

    assert "gold_sql_path" not in public.model_dump()
    assert "expected_result_path" not in public.model_dump()
    assert "oracle_visibility" not in public.model_dump()


def test_clarification_case_cannot_have_gold_sql() -> None:
    with pytest.raises(ValidationError, match="cannot expose oracle assets"):
        _case(
            status=BenchmarkStatus.CLARIFICATION_REQUIRED,
            clarification_reason="The business definition requires clarification.",
        )


def test_deferred_case_requires_reason() -> None:
    with pytest.raises(ValidationError, match="require deferred_reason"):
        _case(
            status=BenchmarkStatus.DEFERRED,
            gold_sql_path=None,
            expected_result_path=None,
        )
