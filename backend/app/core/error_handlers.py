"""Global error handlers producing a single consistent JSON error envelope.

Three handlers cover every response FastAPI can produce for an error:

- `Exception` — anything unhandled falls through to a generic 500. The real exception
  message/traceback never reaches the client; Sentry gets the full detail.
- `starlette.exceptions.HTTPException` — registered on the Starlette class (not
  `fastapi.HTTPException`) so this also catches Starlette's own 404 (unknown route) and
  405, not just exceptions routes raise deliberately. FastAPI's `HTTPException` subclasses
  it, so both are covered by one handler.
- `RequestValidationError` — FastAPI's 422s, with `details` populated per-field.

Routes and services are untouched — this is purely a response-shaping layer registered
once in `main.py`.
"""

import logging

import sentry_sdk
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.errors import ErrorBody, ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)

_STATUS_CODES = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_401_UNAUTHORIZED: "unauthorized",
    status.HTTP_403_FORBIDDEN: "forbidden",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "validation_error",
}


def _code_for_status(status_code: int) -> str:
    return _STATUS_CODES.get(status_code, "http_error")


def _envelope(
    code: str,
    message: str,
    *,
    details: list[ErrorDetail] | None = None,
    error_id: str | None = None,
) -> dict:
    return ErrorResponse(
        error=ErrorBody(code=code, message=message, details=details, error_id=error_id)
    ).model_dump()


async def _handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    event_id = sentry_sdk.capture_exception(exc)

    logger.error(
        "Unhandled exception on %s %s",
        request.method,
        request.url.path,
        exc_info=True,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_envelope(
            "internal_error",
            "Internal server error",
            error_id=event_id,
        ),
    )


async def _handle_http_exception(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    code = _code_for_status(exc.status_code)
    message = str(exc.detail)

    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(code, message),
        headers=exc.headers,
    )


async def _handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    details = [
        ErrorDetail(
            field=".".join(str(part) for part in error["loc"]),
            message=error["msg"],
            type=error["type"],
        )
        for error in exc.errors()
    ]

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=_envelope(
            "validation_error",
            "Request validation failed",
            details=details,
        ),
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(Exception, _handle_unhandled_exception)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
