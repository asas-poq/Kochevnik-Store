from typing import Annotated, Any

from arq.connections import ArqRedis, RedisSettings, create_pool
from fastapi import Depends, Request

from app.core.config import settings
from app.core.errors import ServiceUnavailableError


async def create_arq_pool() -> ArqRedis:
    return await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))


def get_arq(request: Request) -> Any:
    pool = getattr(request.app.state, "arq", None)
    if pool is None:
        raise ServiceUnavailableError("Очередь задач недоступна.")
    return pool


ArqDep = Annotated[Any, Depends(get_arq)]
