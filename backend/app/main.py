import os
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
    multiprocess,
)

from app.admin.views import setup_admin
from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.errors import UnauthorizedError, install_error_handlers
from app.core.logging import get_logger, request_id_ctx, setup_logging
from app.core.queue import create_arq_pool
from app.core.redis import RedisDep, create_redis
from app.db.session import engine
from app.services.health import check_all
from app.services.s3 import S3StorageService, get_s3_service
from app.services.telegram import TelegramService, get_telegram_service

setup_logging()
logger = get_logger("main")

REQUESTS = Counter("http_requests_total", "HTTP запросы", ["method", "route", "status"])
LATENCY = Histogram("http_request_duration_seconds", "Время ответа", ["method", "route"])


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    app.state.redis = create_redis()
    try:
        app.state.arq = await create_arq_pool()
    except Exception:
        # API без очереди остаётся рабочим, не работают только ручки запуска парсера
        logger.exception("Не удалось подключиться к очереди задач")
        app.state.arq = None
    logger.info("Запуск", extra={"version": settings.VERSION, "environment": settings.ENVIRONMENT})
    yield
    if app.state.arq is not None:
        await app.state.arq.aclose()
    await app.state.redis.aclose()
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description="Бэкенд интернет-магазина монгольского кашемира и кожи. Ошибки приходят в виде {detail, code}.",
        lifespan=lifespan,
    )
    install_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def access_log(request: Request, call_next):  # type: ignore[no-untyped-def]
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:10]
        token = request_id_ctx.set(rid)
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            elapsed = time.perf_counter() - started
            route = getattr(request.scope.get("route"), "path", "unmatched")
            REQUESTS.labels(request.method, route, status_code).inc()
            LATENCY.labels(request.method, route).observe(elapsed)
            logger.info(
                "request",
                extra={"method": request.method, "path": request.url.path, "status": status_code, "ms": round(elapsed * 1000, 1)},
            )
            request_id_ctx.reset(token)

    Path("media").mkdir(exist_ok=True)
    app.mount("/media", StaticFiles(directory="media"), name="media")
    setup_admin(app)
    app.include_router(api_v1_router, prefix=settings.API_V1_STR)

    @app.get("/", tags=["0. Состояние"], summary="Корень сервиса")
    async def root() -> dict[str, str]:
        return {
            "service": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "status": "ok",
            "swagger_docs": "/docs",
            "admin_panel": "/admin",
            "api_v1_prefix": settings.API_V1_STR,
        }

    @app.get("/health", tags=["0. Состояние"], summary="Состояние БД, Redis, S3 и Telegram")
    async def health(
        redis: RedisDep,
        s3: S3StorageService = Depends(get_s3_service),
        telegram: TelegramService = Depends(get_telegram_service),
    ) -> JSONResponse:
        """БД и Redis критичны, при их сбое ответ 503. S3 и Telegram только показываются,
        иначе контейнер перезапускался бы из-за внешнего сервиса. Telegram off значит токен не задан."""
        checks = await check_all(engine, redis, s3, telegram)
        critical_ok = checks["db"] == "ok" and checks["redis"] == "ok"
        return JSONResponse(
            {"status": "ok" if critical_ok else "fail", **checks}, status_code=200 if critical_ok else 503
        )

    if settings.METRICS_ENABLED:

        @app.get("/metrics", include_in_schema=False)
        async def metrics(authorization: str | None = Header(None)) -> Response:
            if settings.METRICS_TOKEN and authorization != f"Bearer {settings.METRICS_TOKEN}":
                raise UnauthorizedError("Нужен токен метрик.")
            if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
                registry = CollectorRegistry()
                multiprocess.MultiProcessCollector(registry)
                body = generate_latest(registry)
            else:
                body = generate_latest()
            return Response(body, media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
