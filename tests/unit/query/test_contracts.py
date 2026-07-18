"""Unit tests for strict Text2SQL provider and API contracts."""

import pytest
from pydantic import ValidationError

from insightops.query.contracts import QueryRequest, QueryResponse, StructuredCandidate


def test_structured_candidate_enforces_action_specific_fields() -> None:
    sql = StructuredCandidate(action="execute_sql", sql="SELECT 1 AS value")
    clarification = StructuredCandidate(
        action="request_clarification",
        clarification_code="metric_scope_required",
        clarification_question="Which metric scope should be used?",
    )

    assert sql.sql == "SELECT 1 AS value"
    assert clarification.clarification_code == "metric_scope_required"

    with pytest.raises(ValidationError, match="execute_sql requires sql"):
        StructuredCandidate(action="execute_sql")
    with pytest.raises(ValidationError, match="requires only clarification fields"):
        StructuredCandidate(
            action="request_clarification",
            sql="SELECT 1",
            clarification_code="metric_scope_required",
            clarification_question="Which metric scope should be used?",
        )


def test_query_response_rejects_cross_branch_fields() -> None:
    with pytest.raises(ValidationError, match="SQL responses cannot contain clarification"):
        QueryResponse(
            request_id="request-1",
            question="question",
            action="execute_sql",
            generated_sql="SELECT 1 AS value",
            clarification_code="metric_scope_required",
            evaluation_status="PASS",
            provider="fake",
            model="deterministic-v1",
        )


@pytest.mark.parametrize("question", ["", "   ", "\n\t"])
def test_query_request_rejects_empty_or_blank_questions(question: str) -> None:
    with pytest.raises(ValidationError):
        QueryRequest(question=question)


def test_query_request_rejects_extra_fields_and_oversized_question() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        QueryRequest.model_validate({"question": "valid", "api_key": "forbidden"})
    with pytest.raises(ValidationError):
        QueryRequest(question="x" * 4_001)


@pytest.mark.parametrize(
    "question",
    [
        "<script>alert(1)</script>",
        "请确认 <b>指标</b>",
        "x" * 501,
    ],
)
def test_clarification_question_rejects_html_and_excessive_length(question: str) -> None:
    with pytest.raises(ValidationError):
        StructuredCandidate(
            action="request_clarification",
            clarification_code="metric_scope_required",
            clarification_question=question,
        )
