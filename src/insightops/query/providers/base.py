"""Provider-neutral Text2SQL generation interface."""

from typing import Protocol

from insightops.query.context import QueryContext
from insightops.query.contracts import ProviderOutput


class ProviderError(RuntimeError):
    """Stable model-provider failure safe for the application boundary."""

    def __init__(self, code: str = "provider_unavailable") -> None:
        self.code = code
        super().__init__(code)


class QueryProvider(Protocol):
    """Generate one validated SQL or clarification candidate."""

    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    def generate(self, context: QueryContext) -> ProviderOutput: ...

    def close(self) -> None: ...
