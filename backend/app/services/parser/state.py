import json
from typing import Any

from redis.asyncio import Redis

from app.core.config import settings
from app.core.errors import BadGatewayError, ConflictError
from app.db.types import utc_now

STATUS_KEY = "parser:status"
LOCK_KEY = "parser:lock"


def _stamp() -> str:
    return utc_now().isoformat(timespec="seconds")


async def _save(redis: Redis, **changes: Any) -> None:
    raw = await redis.get(STATUS_KEY)
    state = json.loads(raw) if raw else {}
    state.update(changes)
    state["running"] = state.get("state") in ("queued", "running")
    await redis.set(STATUS_KEY, json.dumps(state, ensure_ascii=False))


async def get_status(redis: Redis) -> dict[str, Any]:
    raw = await redis.get(STATUS_KEY)
    if raw:
        return json.loads(raw)
    return {"name": None, "state": "idle", "running": False, "result": None, "error": None}


async def enqueue(redis: Redis, arq: Any, name: str, params: dict[str, Any]) -> None:
    """Замок живёт в Redis, поэтому две задачи не стартуют даже при нескольких воркерах API.
    Если воркер умер, замок сам протухнет через PARSER_LOCK_TTL_SECONDS."""
    if not await redis.set(LOCK_KEY, name, nx=True, ex=settings.PARSER_LOCK_TTL_SECONDS):
        raise ConflictError("Парсер уже выполняет задачу. Состояние в GET /api/v1/parser/status")
    await _save(
        redis, name=name, state="queued", params=params, queued_at=_stamp(),
        started_at=None, finished_at=None, result=None, error=None,
    )
    job = await arq.enqueue_job("run_parser_job", name, params)
    if job is None:
        await redis.delete(LOCK_KEY)
        await _save(redis, state="idle")
        raise BadGatewayError("Не удалось поставить задачу в очередь.")


async def mark_running(redis: Redis) -> None:
    await _save(redis, state="running", started_at=_stamp())


async def mark_finished(redis: Redis, *, result: dict | None = None, error: str | None = None) -> None:
    await _save(redis, state="error" if error else "done", finished_at=_stamp(), result=result, error=error)
    await redis.delete(LOCK_KEY)
