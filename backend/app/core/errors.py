"""Application error types and FastAPI exception handlers (consistent JSON errors)."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import DBAPIError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.observability import record_failure
from app.core.responses import error_response

log = logging.getLogger(__name__)


class AppError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None, details=None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.details = details


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class BadRequestError(AppError):
    status_code = 400
    code = "bad_request"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"


class DatabaseNotConfiguredError(ServiceUnavailableError):
    code = "database_not_configured"

    def __init__(self) -> None:
        super().__init__(
            "DATABASE_URL is not configured. Create a Neon PostgreSQL project and set DATABASE_URL in .env."
        )


class UpstreamError(AppError):
    status_code = 502
    code = "upstream_error"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        if exc.status_code >= 500 and exc.code not in ("database_not_configured",):
            record_failure("api", f"{exc.code}: {exc.message}")
        return error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        details = [
            {"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()
        ]
        return error_response(422, "validation_error", "Request parameters failed validation.", details)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return error_response(exc.status_code, code, str(exc.detail))

    @app.exception_handler(OperationalError)
    async def _db_operational(_: Request, exc: OperationalError):
        record_failure("database", f"operational error: {exc.orig}")
        return error_response(503, "database_unavailable", "The database is unreachable or refused the connection.")

    @app.exception_handler(DBAPIError)
    async def _db_error(_: Request, exc: DBAPIError):
        record_failure("database", f"database error: {exc.orig}")
        return error_response(500, "database_error", "A database error occurred while processing the request.")

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("unhandled error")
        record_failure("api", f"{type(exc).__name__} on {request.method} {request.url.path}")
        return error_response(500, "internal_error", "An unexpected error occurred.")
