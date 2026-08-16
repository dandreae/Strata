"""Application-wide error types and FastAPI exception handlers.

Domain-specific errors (e.g. `SlicerUnavailableError`) live next to the code
that raises them (see `app/slicer/base.py`) but subclass `StrataError` so a
single handler can catch every expected failure mode and turn it into a
well-formed HTTP response instead of an opaque 500.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger(__name__)


class StrataError(Exception):
    """Base class for all expected/handled application errors."""

    status_code: int = status.HTTP_400_BAD_REQUEST

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(StrataError):
    status_code = status.HTTP_404_NOT_FOUND


class ValidationFailedError(StrataError):
    status_code = 422  # HTTP 422 Unprocessable Entity/Content


def register_exception_handlers(app: FastAPI) -> None:
    """Attach handlers so StrataError subclasses map to clean JSON responses.

    Anything *not* a StrataError is a bug — we log it with a traceback and
    return a generic 500 rather than leaking internals to the client.
    """

    @app.exception_handler(StrataError)
    async def handle_strata_error(request: Request, exc: StrataError) -> JSONResponse:
        logger.warning(
            "handled application error",
            extra={"context": {"path": request.url.path, "error": exc.message}},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.__class__.__name__, "message": exc.message, "details": exc.details},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled exception",
            extra={"context": {"path": request.url.path}},
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "InternalServerError", "message": "An unexpected error occurred.", "details": {}},
        )
