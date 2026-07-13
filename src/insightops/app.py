"""FastAPI application factory."""

from fastapi import FastAPI

from insightops.api.health import router as health_router
from insightops.core.config import Settings


def create_app(settings: Settings) -> FastAPI:
    """Create an application instance from explicit validated settings."""
    application = FastAPI(
        title=settings.app_name,
        debug=settings.app_debug,
        version="0.1.0",
    )
    application.include_router(health_router)
    return application
