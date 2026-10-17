"""Consistent error responses: {"error": {"code": "...", "message": "..."}}."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import DBAPIError

from .responses import AppJSONResponse

log = logging.getLogger("mytrakin")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def not_found(what: str = "Record") -> ApiError:
    return ApiError(404, "not_found", f"{what} not found")


def forbidden(message: str = "You don't have permission to do that") -> ApiError:
    return ApiError(403, "forbidden", message)


def bad_request(message: str, code: str = "invalid") -> ApiError:
    return ApiError(400, code, message)


def conflict(message: str, code: str = "conflict") -> ApiError:
    return ApiError(409, code, message)


# Postgres SQLSTATE -> (HTTP status, code, message)
_PG_ERRORS = {
    "42501": (403, "forbidden", "You don't have permission to do that"),  # RLS / privileges
    "23505": (409, "duplicate", "A record with the same key already exists"),
    "23503": (409, "in_use", "This record is linked to other records"),
    "23514": (422, "invalid", "A value is outside what is allowed"),
    "23502": (422, "missing", "A required value is missing"),
    "22P02": (422, "invalid", "A value has the wrong format"),
    "22007": (422, "invalid", "A date has the wrong format"),
}


# Business rules raised by the database (own SQLSTATE codes): the message is written for the user.
_RULE_ERRORS = {
    "MT403": (403, "forbidden"),
    "MT404": (404, "not_found"),
    "MT409": (409, "conflict"),
    "MT422": (422, "invalid"),
}


def _sqlstate(exc: DBAPIError) -> str | None:
    orig = exc.orig
    for candidate in (orig, getattr(orig, "__cause__", None)):
        code = getattr(candidate, "sqlstate", None) or getattr(candidate, "pgcode", None)
        if code:
            return str(code)
    return None


def _body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return AppJSONResponse(_body(exc.code, exc.message), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", [])[1:]) or "request"
        return AppJSONResponse(_body("invalid", f"{field}: {first.get('msg', 'invalid value')}"), status_code=422)

    @app.exception_handler(DBAPIError)
    async def _db_error(_: Request, exc: DBAPIError):
        state = _sqlstate(exc)
        if state in _RULE_ERRORS:
            status, code = _RULE_ERRORS[state]
            message = getattr(exc.orig, "message", None) or str(exc.orig).splitlines()[0]
            if message.startswith("<class"):   # asyncpg wraps custom SQLSTATEs as "<class '…'>: text"
                message = message.split(": ", 1)[-1]
            return AppJSONResponse(_body(code, message), status_code=status)
        if state in _PG_ERRORS:
            status, code, message = _PG_ERRORS[state]
            return AppJSONResponse(_body(code, message), status_code=status)
        log.exception("database error (sqlstate=%s)", state)
        return AppJSONResponse(_body("server_error", "Something went wrong. Please try again."), status_code=500)
