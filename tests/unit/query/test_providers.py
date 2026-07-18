"""Unit tests for deterministic and real-provider adapter boundaries."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from openai import (
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)

from insightops.benchmark.registry import load_benchmark_catalog, public_benchmark_cases
from insightops.query.context import QueryContext, build_query_context
from insightops.query.contracts import StructuredCandidate
from insightops.query.providers.base import ProviderError
from insightops.query.providers.fake import FakeQueryProvider
from insightops.query.providers.openai import OpenAIQueryProvider
from insightops.seed.dataset import load_seed_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _context() -> QueryContext:
    catalog = load_benchmark_catalog(PROJECT_ROOT / "benchmarks" / "m1_2a" / "cases.json")
    dataset = load_seed_dataset(PROJECT_ROOT / "data" / "seed" / "m1_2a")
    case = next(case for case in public_benchmark_cases(catalog) if case.case_id == "GQ-SAA-002")
    return build_query_context(question=case.question, case=case, manifest=dataset.manifest)


def _provider(client: MagicMock) -> OpenAIQueryProvider:
    return OpenAIQueryProvider(
        api_key="test-key",
        model="gpt-5.6-sol",
        timeout_seconds=1,
        client=client,
    )


def _parsed_response(
    candidate: object | None,
    *,
    status: str = "completed",
    refusal: bool = False,
    include_usage: bool = True,
) -> SimpleNamespace:
    content = (
        SimpleNamespace(type="refusal", refusal="upstream refusal detail")
        if refusal
        else SimpleNamespace(type="output_text", parsed=candidate)
    )
    usage = (
        SimpleNamespace(input_tokens=17, output_tokens=9, total_tokens=26)
        if include_usage
        else None
    )
    return SimpleNamespace(
        status=status,
        output=[SimpleNamespace(type="message", content=[content])],
        output_parsed=candidate,
        usage=usage,
        model="untrusted-upstream-model-value",
    )


def test_fake_provider_is_deterministic() -> None:
    provider = FakeQueryProvider()
    context = _context()

    first = provider.generate(context)
    second = provider.generate(context)

    assert first == second
    assert first.provider == "fake"
    assert first.candidate.action == "execute_sql"
    provider.close()


def test_fake_provider_maps_failure_to_stable_code() -> None:
    provider = FakeQueryProvider(fail=True)

    with pytest.raises(ProviderError) as captured:
        provider.generate(_context())

    assert captured.value.code == "provider_unavailable"


def test_openai_provider_parses_structured_sql_and_usage() -> None:
    client = MagicMock(spec=OpenAI)
    candidate = StructuredCandidate(action="execute_sql", sql="SELECT 1 AS value")
    client.responses.parse.return_value = _parsed_response(candidate)

    result = _provider(client).generate(_context())

    assert result.candidate == candidate
    assert result.provider == "openai"
    assert result.model == "gpt-5.6-sol"
    assert result.usage.model_dump() == {
        "input_tokens": 17,
        "output_tokens": 9,
        "total_tokens": 26,
    }
    call = client.responses.parse.call_args
    assert call.kwargs["model"] == "gpt-5.6-sol"
    assert call.kwargs["text_format"] is StructuredCandidate
    assert call.kwargs["reasoning"] == {"effort": "low"}
    assert call.kwargs["store"] is False
    assert "temperature" not in call.kwargs


def test_openai_provider_parses_structured_clarification() -> None:
    client = MagicMock(spec=OpenAI)
    candidate = StructuredCandidate(
        action="request_clarification",
        clarification_code="metric_scope_required",
        clarification_question="请明确需要使用哪个指标口径？",
    )
    client.responses.parse.return_value = _parsed_response(candidate)

    result = _provider(client).generate(_context())

    assert result.candidate == candidate


@pytest.mark.parametrize(
    ("response", "expected_code"),
    [
        (_parsed_response(None, refusal=True), "provider_refusal"),
        (_parsed_response(None, status="incomplete"), "provider_incomplete_response"),
        (_parsed_response(None, status="failed"), "provider_failed_response"),
        (_parsed_response(None), "provider_invalid_response"),
        (_parsed_response({"action": "execute_sql"}), "provider_invalid_response"),
    ],
)
def test_openai_provider_rejects_non_candidate_responses(
    response: SimpleNamespace,
    expected_code: str,
) -> None:
    client = MagicMock(spec=OpenAI)
    client.responses.parse.return_value = response

    with pytest.raises(ProviderError) as captured:
        _provider(client).generate(_context())

    assert captured.value.code == expected_code
    assert "upstream refusal" not in str(captured.value)


def test_openai_provider_handles_missing_usage_metadata() -> None:
    client = MagicMock(spec=OpenAI)
    candidate = StructuredCandidate(action="execute_sql", sql="SELECT 1 AS value")
    client.responses.parse.return_value = _parsed_response(candidate, include_usage=False)

    result = _provider(client).generate(_context())

    assert result.usage.input_tokens is None
    assert result.usage.output_tokens is None
    assert result.usage.total_tokens is None


def _rate_limit_error() -> RateLimitError:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(429, request=request)
    return RateLimitError("secret rate-limit body", response=response, body={"secret": True})


def _authentication_error() -> AuthenticationError:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(401, request=request)
    return AuthenticationError("secret auth body", response=response, body={"secret": True})


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (
            APITimeoutError(httpx.Request("POST", "https://api.openai.com/v1/responses")),
            "provider_timeout",
        ),
        (_rate_limit_error(), "provider_rate_limited"),
        (_authentication_error(), "provider_authentication_failed"),
        (OpenAIError("secret upstream detail"), "provider_unavailable"),
    ],
)
def test_openai_provider_hides_sdk_exceptions(
    error: OpenAIError,
    expected_code: str,
) -> None:
    client = MagicMock(spec=OpenAI)
    client.responses.parse.side_effect = error

    with pytest.raises(ProviderError) as captured:
        _provider(client).generate(_context())

    assert captured.value.code == expected_code
    assert "secret" not in str(captured.value)


def test_openai_provider_closes_only_owned_client() -> None:
    owned_client = MagicMock(spec=OpenAI)
    with patch("insightops.query.providers.openai.OpenAI", return_value=owned_client):
        owned_provider = OpenAIQueryProvider(
            api_key="test-key",
            model="gpt-5.6-sol",
            timeout_seconds=1,
        )
    owned_provider.close()
    owned_client.close.assert_called_once_with()

    injected_client = MagicMock(spec=OpenAI)
    injected_provider = _provider(injected_client)
    injected_provider.close()
    injected_client.close.assert_not_called()
