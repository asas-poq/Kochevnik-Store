import time
from collections.abc import Awaitable, Callable

from fastapi import Request
from redis.exceptions import RedisError

from app.core.errors import TooManyRequestsError
from app.core.logging import get_logger
from app.core.redis import RedisDep

logger = get_logger(__name__)


def rate_limit(name: str, per_minute: int) -> Callable[..., Awaitable[None]]:
    """Фиксированное окно в минуту на IP. Если Redis лёг, пропускаем запрос, иначе упадёт и вход."""

    async def check(request: Request, redis: RedisDep) -> None:
        ip = request.client.host if request.client else "unknown"
        now = int(time.time())
        key = f"rl:{name}:{ip}:{now // 60}"
        try:
            async with redis.pipeline(transaction=True) as pipe:
                pipe.incr(key)
                pipe.expire(key, 60)
                count, _ = await pipe.execute()
        except RedisError:
            logger.warning("Redis недоступен, лимит не применён", extra={"limit": name})
            return
        if count > per_minute:
            retry = 60 - now % 60
            raise TooManyRequestsError(
                f"Слишком много запросов. Повторите через {retry} с.",
                headers={"Retry-After": str(retry)},
            )

    return check
