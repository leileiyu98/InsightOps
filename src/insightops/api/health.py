"""Process liveness endpoint."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    """Response returned when the API process is alive."""

    status: Literal["ok"]


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health_check() -> HealthResponse:
    """Report process liveness without depending on external services."""
    return HealthResponse(status="ok")
