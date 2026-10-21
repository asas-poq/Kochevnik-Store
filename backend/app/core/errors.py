from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger, request_id_ctx

logger = get_logger(__name__)


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, detail: str, *, headers: dict[str, str] | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.headers = headers


class BadRequestError(AppError):
    status_code = 400
    code = "bad_request"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"

    def __init__(self, detail: str) -> None:
        super().__init__(detail, headers={"WWW-Authenticate": "Bearer"})


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class TooLargeError(AppError):
    status_code = 413
    code = "payload_too_large"


class UnsupportedMediaError(AppError):
    status_code = 415
    code = "unsupported_media"


class UnprocessableError(AppError):
    status_code = 422
    code = "validation_error"


class TooManyRequestsError(AppError):
    status_code = 429
    code = "rate_limited"


class BadGatewayError(AppError):
    status_code = 502
    code = "bad_gateway"


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "unavailable"


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            {"detail": exc.detail, "code": exc.code}, status_code=exc.status_code, headers=exc.headers
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            {"detail": str(exc.detail), "code": f"http_{exc.status_code}"},
            status_code=exc.status_code,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {
                "field": ".".join(str(p) for p in e["loc"] if p != "body"),
                "message": e["msg"].removeprefix("Value error, "),
            }
            for e in exc.errors()
        ]
        first = errors[0]
        detail = f"{first['field']}: {first['message']}" if first["field"] else first["message"]
        return JSONResponse(
            {"detail": detail, "code": "validation_error", "errors": errors}, status_code=422
        )

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Необработанная ошибка")
        return JSONResponse(
            {"detail": f"Внутренняя ошибка. Номер запроса: {request_id_ctx.get()}", "code": "internal_error"},
            status_code=500,
        )
