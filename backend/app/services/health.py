import asyncio

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.services.s3 import S3StorageService
from app.services.telegram import TelegramService


async def _probe(coro) -> str:  # type: ignore[no-untyped-def]
    try:
        await asyncio.wait_for(coro, timeout=3)
        return "ok"
    except Exception as exc:
        return f"error: {type(exc).__name__}"


async def _db(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def check_all(
    engine: AsyncEngine, redis: Redis, s3: S3StorageService, telegram: TelegramService
) -> dict[str, str]:
    db, cache, storage = await asyncio.gather(_probe(_db(engine)), _probe(redis.ping()), _probe(s3.ping()))
    return {"db": db, "redis": cache, "s3": storage, "telegram": await telegram.ping()}
