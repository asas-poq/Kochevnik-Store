"""
Главная точка входа FastAPI-приложения (`app/main.py`).
Отвечает за:
- Инициализацию логирования (`setup_logging`)
- Жизненный цикл приложения (`lifespan`): создание таблиц БД и автозагрузку данных парсера при первом старте
- Middleware трассировки запросов (`X-Request-ID`) и замера времени выполнения каждого эндпоинта
- Подключение CORS, статики `/media`, Админ-панели `/admin` (`sqladmin`) и роутера `/api/v1`
"""

import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.admin.views import setup_admin
from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.logging import get_logger, request_id_ctx_var, setup_logging
from app.db.base import Base
from app.db.session import engine
from app.services.orders import expire_orders_loop
from app.services.telegram import telegram_service
from app.services.tasks import import_parser_dump_task

# Инициализируем профессиональный логгер при запуске модуля
setup_logging()
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Асинхронный контекстный менеджер жизненного цикла FastAPI:
    1. При старте гарантирует создание всех таблиц в БД (`Base.metadata.create_all`).
    2. Если в папке `data/parsed_dump.json` лежит дамп вашего парсера, автоматически
       синхронизирует его с базой данных (идемпотентно, без дубликатов).
    3. При остановке корректно закрывает пул соединений БД.
    """
    logger.info(
        f"Запуск {settings.PROJECT_NAME} v{settings.VERSION} (окружение: {settings.ENVIRONMENT})"
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Схема таблиц базы данных успешно проверена / создана.")

    # Автоматическая подгрузка JSON-дампа парсера, если он присутствует
    dump_path = Path("data/parsed_dump.json")
    if dump_path.exists():
        try:
            stats = await import_parser_dump_task(str(dump_path))
            logger.info(f"Авто-синхронизация дампа парсера при старте: {stats}")
        except Exception as exc:
            logger.error(f"Ошибка при авто-импорте дампа парсера: {exc}")

    # Предупреждения о небезопасных настройках в боевом окружении
    if settings.ENVIRONMENT.lower() == "production":
        if settings.payments_sandbox_mode:
            logger.critical("PRODUCTION с тестовыми ключами платежей (YOOKASSA_SHOP_ID=test_*)!")
        if settings.PAYMENT_WEBHOOK_SECRET.startswith("sbp_webhook_secret"):
            logger.critical("PRODUCTION со стандартным PAYMENT_WEBHOOK_SECRET — смените его в .env!")

    telegram_task = None
    if telegram_service.is_demo:
        logger.warning("Telegram: ДЕМО-РЕЖИМ (токен не задан) — уведомления только в логе.")
    else:
        logger.info(
            f"Telegram: уведомления включены (личка={settings.TELEGRAM_OWNER_CHAT_ID}, "
            f"группа={settings.TELEGRAM_STAFF_CHAT_ID or 'не задана'}, "
            f"приём кнопок={settings.TELEGRAM_UPDATES_MODE})."
        )
        if settings.TELEGRAM_UPDATES_MODE == "polling":
            telegram_task = asyncio.create_task(telegram_service.polling_loop())

    # Фоновая автоотмена неоплаченных заказов (возврат остатков на склад)
    expire_task = asyncio.create_task(expire_orders_loop())

    yield

    for task in (expire_task, telegram_task):
        if task is None:
            continue
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    logger.info("Остановка приложения, закрываем соединения с БД...")
    await engine.dispose()


# Создаем экземпляр FastAPI с подробным русскоязычным описанием для Swagger (/docs)
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=(
        "Профессиональный асинхронный бэкенд интернет-магазина Kochevnik.\n\n"
        "### Ключевые возможности:\n"
        "- **Полная совместимость с БД парсера** (`categories`, `products`, `price_history`, "
        "`product_images`, `product_materials`, `product_color_links`, `crawl_queue`)\n"
        "- **Авторизация и Профиль** (JWT Access/Refresh, `Depends`)\n"
        "- **Лайки (Избранное) и Отзывы/Комментарии** с проверкой реальной покупки и ответами бутика\n"
        "- **Чекаут с блокировкой остатков** (`SELECT ... FOR UPDATE`), доставкой СДЭК/Почта/Шоурум "
        "и оплатой по **СБП** (ЮKassa / Т-Касса) + уведомления владельцу в **Telegram**"
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Настраиваем CORS для работы с фронтендом на React / Next.js / Vite
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next) -> Response:
    """
    Профессиональный HTTP-middleware:
    - Присваивает каждому запросу уникальный `X-Request-ID` и сохраняет его в `ContextVar`,
      благодаря чему все вызовы `logger.info()` внутри роутеров автоматически помечаются этим ID.
    - Замеряет точное время выполнения запроса в миллисекундах (`X-Process-Time-Ms`).
    """
    req_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:10]
    token = request_id_ctx_var.set(req_id)
    start_time = time.perf_counter()

    logger.info(
        f"--> Входящий запрос: {request.method} {request.url.path}"
        + (f"?{request.url.query}" if request.url.query else "")
    )
    try:
        response: Response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        response.headers["X-Request-ID"] = req_id
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
        logger.info(
            f"<-- Ответ: {request.method} {request.url.path} | "
            f"Статус: {response.status_code} | Время: {elapsed_ms:.2f} мс"
        )
        return response
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.exception(
            f"<!- Необработанная ошибка в {request.method} {request.url.path} "
            f"после {elapsed_ms:.2f} мс: {exc}"
        )
        raise
    finally:
        request_id_ctx_var.reset(token)


# Монтируем локальную папку для раздачи загруженных фото (в режиме разработки)
media_dir = Path("media")
media_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(media_dir)), name="media")

# Подключаем Админ-панель sqladmin по адресу /admin
setup_admin(app)

# Подключаем все роутеры API v1
app.include_router(api_v1_router, prefix=settings.API_V1_STR)


@app.get("/", tags=["0. Проверка состояния (Healthcheck)"])
async def root_healthcheck() -> dict:
    """
    Корневая ручка проверки работоспособности сервера (Healthcheck).
    Возвращает статус сервиса и ссылки на документацию Swagger и Админ-панель.
    """
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "ok",
        "swagger_docs": "/docs",
        "admin_panel": "/admin",
        "api_v1_prefix": settings.API_V1_STR,
    }