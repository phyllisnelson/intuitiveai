"""Error handling — both the explicit domain translator and FastAPI app-level handlers.

Two patterns live here:

1. ``handle_domain_error`` — called explicitly inside endpoint try/except blocks
   to map known domain exceptions to the right HTTP status code.

2. ``register_exception_handlers`` — registers catch-all FastAPI handlers so
   that any unhandled ``VMAPIError`` subclass or bare ``Exception`` gets a clean
   JSON response instead of an unformatted 500.
"""

import structlog
from fastapi import FastAPI, HTTPException, status
from fastapi.requests import Request
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    FlavorNotFoundError,
    InvalidVMStateError,
    OpenStackConnectionError,
    VMAPIError,
    VMNotFoundError,
    VMOperationError,
)

log = structlog.get_logger(__name__)


_STATUS_MAP: dict[type[Exception], int] = {
    VMNotFoundError: status.HTTP_404_NOT_FOUND,
    FlavorNotFoundError: status.HTTP_404_NOT_FOUND,
    InvalidVMStateError: status.HTTP_409_CONFLICT,
    VMOperationError: status.HTTP_502_BAD_GATEWAY,
    OpenStackConnectionError: status.HTTP_503_SERVICE_UNAVAILABLE,
}


def handle_domain_error(exc: Exception) -> None:
    """Re-raise a domain exception as an HTTPException.

    Walks ``_STATUS_MAP`` for a matching type.  Falls through to a bare
    ``raise`` so unexpected exceptions become unhandled 500s rather than
    being swallowed silently.
    """
    for exc_type, status_code in _STATUS_MAP.items():
        if isinstance(exc, exc_type):
            raise HTTPException(status_code=status_code, detail=str(exc))
    raise exc


async def _vm_api_error_handler(_request: Request, exc: VMAPIError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": type(exc).__name__},
    )


async def _generic_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    log.error("unhandled.exception", error=str(exc), exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An unexpected server error occurred.",
            "code": "InternalError",
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach all exception handlers to *app*."""
    app.add_exception_handler(
        VMAPIError,
        _vm_api_error_handler,  # type: ignore[arg-type]
    )
    app.add_exception_handler(Exception, _generic_error_handler)
