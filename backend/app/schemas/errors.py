"""The API-wide error envelope.

Every error response — unhandled exceptions, HTTPExceptions (including FastAPI's own
404/405), and request validation errors — is shaped through these models so clients can
read `error.code` / `error.message` / `error.details` / `error.error_id` unconditionally,
regardless of which handler produced the response. See `app/core/error_handlers.py`.
"""

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    field: str
    message: str
    type: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] | None = None
    error_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
