"""FastAPI boundary for the M1.3 Text2SQL demo."""

from typing import cast
from uuid import uuid4

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from insightops.query.contracts import QueryErrorBody, QueryRequest, QueryResponse
from insightops.query.runtime import build_query_service
from insightops.query.service import QueryService, QueryServiceError

router = APIRouter(prefix="/v1", tags=["query"])

_ERROR_STATUS = {
    "case_not_found": status.HTTP_404_NOT_FOUND,
    "case_not_available": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "provider_not_configured": status.HTTP_503_SERVICE_UNAVAILABLE,
    "provider_unavailable": status.HTTP_502_BAD_GATEWAY,
    "provider_timeout": status.HTTP_504_GATEWAY_TIMEOUT,
    "provider_rate_limited": status.HTTP_503_SERVICE_UNAVAILABLE,
    "provider_authentication_failed": status.HTTP_503_SERVICE_UNAVAILABLE,
    "provider_refusal": status.HTTP_502_BAD_GATEWAY,
    "provider_incomplete_response": status.HTTP_502_BAD_GATEWAY,
    "provider_failed_response": status.HTTP_502_BAD_GATEWAY,
    "provider_invalid_response": status.HTTP_502_BAD_GATEWAY,
    "fake_candidate_not_configured": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "evaluation_unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
    "dataset_verification_failed": status.HTTP_503_SERVICE_UNAVAILABLE,
}


@router.post("/query", response_model=QueryResponse)
def query(payload: QueryRequest, request: Request) -> QueryResponse | JSONResponse:
    """Generate, evaluate, and safely execute one business query."""
    try:
        service = _query_service(request)
        return service.query(payload)
    except QueryServiceError as error:
        body = QueryErrorBody(
            request_id=str(uuid4()),
            code=error.code,
            message=error.message,
        )
        return JSONResponse(
            status_code=_ERROR_STATUS.get(error.code, status.HTTP_500_INTERNAL_SERVER_ERROR),
            content=body.model_dump(mode="json"),
        )


def _query_service(request: Request) -> QueryService:
    service = cast(QueryService | None, request.app.state.query_service)
    if service is None:
        with request.app.state.query_service_lock:
            service = cast(QueryService | None, request.app.state.query_service)
            if service is None:
                service = build_query_service(request.app.state.settings)
                request.app.state.query_service = service
    return service
