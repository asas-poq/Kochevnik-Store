import fakeredis
import httpx
from fastapi import Depends, FastAPI

from app.core.errors import install_error_handlers
from app.core.ratelimit import rate_limit
from app.core.redis import get_redis


async def test_limit_blocks_after_threshold_with_retry_after():
    app = FastAPI()
    install_error_handlers(app)
    redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: redis

    @app.get("/ping", dependencies=[Depends(rate_limit("ping", 2))])
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        codes = [(await c.get("/ping")).status_code for _ in range(3)]
        blocked = await c.get("/ping")

    assert codes == [200, 200, 429]
    assert blocked.json()["code"] == "rate_limited"
    assert "retry-after" in blocked.headers
