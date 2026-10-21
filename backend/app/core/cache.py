import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Annotated, TypeVar

from fastapi import Depends
from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.logging import get_logger
from app.core.redis import RedisDep

logger = get_logger(__name__)

M = TypeVar("M", bound=BaseModel)


class Cache:
    """Кэш ответов с версией на группу. Сброс группы это INCR версии, старые ключи доживают TTL."""

    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def bump(self, scope: str) -> None:
        try:
            await self.redis.incr(f"cache:ver:{scope}")
        except RedisError:
            logger.warning("Redis недоступен, версия кэша не сброшена", extra={"scope": scope})

    async def remember(
        self,
        scope: str,
        params: dict,
        ttl: int,
        model: type[M],
        build: Callable[[], Awaitable[M]],
    ) -> M:
        """Redis лёг, значит отдаём данные из БД, а не 500."""
        digest = hashlib.sha1(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()[:16]
        try:
            version = await self.redis.get(f"cache:ver:{scope}") or 0
            key = f"cache:{scope}:{version}:{digest}"
            raw = await self.redis.get(key)
            if raw:
                return model.model_validate_json(raw)
        except RedisError:
            logger.warning("Redis недоступен, читаем без кэша", extra={"scope": scope})
            return await build()

        value = await build()
        try:
            await self.redis.set(key, value.model_dump_json(), ex=ttl)
        except RedisError:
            logger.warning("Не удалось записать кэш", extra={"scope": scope})
        return value


def get_cache(redis: RedisDep) -> Cache:
    return Cache(redis)


CacheDep = Annotated[Cache, Depends(get_cache)]
