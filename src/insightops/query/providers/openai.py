"""OpenAI Responses API adapter using native Pydantic Structured Outputs."""

from openai import (
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)

from insightops.query.context import QueryContext
from insightops.query.contracts import ProviderOutput, ProviderUsage, StructuredCandidate
from insightops.query.providers.base import ProviderError


class OpenAIQueryProvider:
    """Generate candidates through one configured OpenAI model."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        client: OpenAI | None = None,
    ) -> None:
        self._model = model
        self._owns_client = client is None
        self._client = client or OpenAI(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=1,
        )

    @property
    def name(self) -> str:
        return "openai"

    @property
    def model(self) -> str:
        return self._model

    def generate(self, context: QueryContext) -> ProviderOutput:
        try:
            response = self._client.responses.parse(
                model=self._model,
                input=[
                    {"role": "system", "content": context.system_prompt},
                    {"role": "user", "content": context.user_prompt},
                ],
                text_format=StructuredCandidate,
                reasoning={"effort": "low"},
                store=False,
            )
        except APITimeoutError as error:
            raise ProviderError("provider_timeout") from error
        except RateLimitError as error:
            raise ProviderError("provider_rate_limited") from error
        except AuthenticationError as error:
            raise ProviderError("provider_authentication_failed") from error
        except (OpenAIError, TypeError, ValueError) as error:
            raise ProviderError() from error

        try:
            if response.status == "incomplete":
                raise ProviderError("provider_incomplete_response")
            if response.status != "completed":
                raise ProviderError("provider_failed_response")
            for item in response.output:
                if item.type != "message":
                    continue
                for content in item.content:
                    if content.type == "refusal":
                        raise ProviderError("provider_refusal")
            candidate = response.output_parsed
            if not isinstance(candidate, StructuredCandidate):
                raise ProviderError("provider_invalid_response")
            usage = response.usage
        except ProviderError:
            raise
        except (AttributeError, TypeError, ValueError) as error:
            raise ProviderError("provider_invalid_response") from error
        return ProviderOutput(
            candidate=candidate,
            provider=self.name,
            model=self._model,
            usage=ProviderUsage(
                input_tokens=usage.input_tokens if usage is not None else None,
                output_tokens=usage.output_tokens if usage is not None else None,
                total_tokens=usage.total_tokens if usage is not None else None,
            ),
        )

    def close(self) -> None:
        """Close only a client created by this adapter."""
        if self._owns_client:
            self._client.close()
