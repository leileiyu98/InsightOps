"""Unit tests for the FastAPI query composition boundary."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, patch

from fastapi import Request

from insightops.api.query import _query_service
from insightops.app import create_app
from insightops.core.config import Settings
from insightops.query.service import QueryService


def test_concurrent_first_requests_build_only_one_query_service() -> None:
    settings = MagicMock(spec=Settings)
    settings.app_name = "InsightOps Test"
    settings.app_debug = False
    app = create_app(settings)
    request = cast(Request, SimpleNamespace(app=app))
    service = MagicMock(spec=QueryService)

    def resolve_service(_index: int) -> QueryService:
        return _query_service(request)

    with (
        patch("insightops.api.query.build_query_service", return_value=service) as build,
        ThreadPoolExecutor(max_workers=8) as executor,
    ):
        resolved = tuple(executor.map(resolve_service, range(16)))

    assert all(item is service for item in resolved)
    build.assert_called_once_with(settings)
