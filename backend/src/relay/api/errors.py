from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from relay.domain.errors import AuthenticationError, DomainError, TooManyRequestsError
from relay.domain.models import FieldErrorOut
from relay.logging import get_logger

log = get_logger(__name__)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[FieldErrorOut] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


def _error(
    status: int,
    code: str,
    message: str,
    details: list[FieldErrorOut] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details))
    if status == 401:
        headers = {**(headers or {}), "www-authenticate": "Bearer"}
    return JSONResponse(jsonable_encoder(body), status_code=status, headers=headers)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error(_request: Request, exc: DomainError) -> JSONResponse:
        headers: dict[str, str] | None = None
        if isinstance(exc, AuthenticationError):
            log.info("auth.rejected", reason=exc.message)
        if isinstance(exc, TooManyRequestsError):
            headers = {"retry-after": str(exc.retry_after_seconds)}
        details = [FieldErrorOut(**d) for d in exc.details] if exc.details else None
        return _error(exc.status_code, exc.code, exc.message, details, headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            FieldErrorOut(path="/".join(str(p) for p in err["loc"]), message=err["msg"])
            for err in exc.errors()
        ]
        return _error(422, "validation_failed", "request validation failed", details)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _error(exc.status_code, "http_error", str(exc.detail), headers=exc.headers)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("request.unhandled", path=request.url.path, error=str(exc))
        return _error(500, "internal_error", "something went wrong on our side")
