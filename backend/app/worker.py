import asyncio
from typing import Any

from arq import cron
from arq.connections import RedisSettings

from app.core.cache import Cache
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.core.redis import create_redis
from app.db.session import AsyncSessionLocal, engine
from app.services import orders
from app.services.parser import jobs, state
from app.services.telegram import telegram_service

logger = get_logger("worker")


async def startup(ctx: dict[str, Any]) -> None:
    setup_logging()
    ctx["redis"] = create_redis()
    # Polling живёт здесь, а не в API: токен нельзя опрашивать из нескольких процессов
    ctx["telegram_task"] = asyncio.create_task(telegram_service.polling_loop())


async def shutdown(ctx: dict[str, Any]) -> None:
    ctx["telegram_task"].cancel()
    await ctx["redis"].aclose()
    await engine.dispose()


async def run_parser_job(ctx: dict[str, Any], name: str, params: dict[str, Any]) -> None:
    redis = ctx["redis"]
    await state.mark_running(redis)
    try:
        result = await jobs.run_named(name, params)
    except Exception as exc:
        logger.exception("Задача парсера упала", extra={"job": name})
        await state.mark_finished(redis, error=str(exc)[:500])
        return
    await state.mark_finished(redis, result=result)
    await Cache(redis).bump("catalog")


async def cancel_expired_orders(ctx: dict[str, Any]) -> None:
    count = await orders.cancel_expired_pending_orders(AsyncSessionLocal)
    if count:
        logger.info("Автоотмена неоплаченных заказов", extra={"count": count})
        await Cache(ctx["redis"]).bump("catalog")


class WorkerSettings:
    functions = [run_parser_job]
    cron_jobs = [cron(cancel_expired_orders, second=0)]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    on_startup = startup
    on_shutdown = shutdown
    job_timeout = settings.PARSER_LOCK_TTL_SECONDS
    max_jobs = 2
    health_check_interval = 30
