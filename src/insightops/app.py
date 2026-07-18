"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from typing import cast
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from insightops.api.health import router as health_router
from insightops.api.query import router as query_router
from insightops.core.config import Settings
from insightops.frontend import configure_frontend
from insightops.query.contracts import QueryErrorBody
from insightops.query.service import QueryService


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        service = cast(QueryService | None, application.state.query_service)
        if service is not None:
            service.close()
            application.state.query_service = None


async def _request_validation_error(
    _request: Request,
    _error: Exception,
) -> JSONResponse:
    body = QueryErrorBody(
        request_id=str(uuid4()),
        code="request_validation_error",
        message="The query request was invalid.",
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=body.model_dump(mode="json"),
    )


def create_app(
    settings: Settings,
    *,
    query_service: QueryService | None = None,
    frontend_dist: Path | None = None,
) -> FastAPI:
    """Create an application instance from explicit validated settings."""
    application = FastAPI(
        title=settings.app_name,
        debug=settings.app_debug,
        version="0.1.0",
        lifespan=_lifespan,
    )
    application.state.settings = settings
    application.state.query_service = query_service
    application.state.query_service_lock = Lock()
    application.add_exception_handler(RequestValidationError, _request_validation_error)
    application.include_router(health_router)
    application.include_router(query_router)
    configure_frontend(application, frontend_dist)
    return application
