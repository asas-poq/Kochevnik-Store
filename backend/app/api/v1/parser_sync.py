from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.deps import DBSessionDep, get_current_admin
from app.core.config import settings
from app.core.errors import BadRequestError, NotFoundError
from app.core.ratelimit import rate_limit
from app.core.redis import RedisDep
from app.models import CrawlQueue
from app.schemas.catalog import CrawlQueueItemOut
from app.schemas.common import ErrorOut
from app.services.parser import jobs, state
from app.core.queue import ArqDep

router = APIRouter(
    prefix="/parser",
    tags=["7. Парсер и очередь"],
    dependencies=[Depends(get_current_admin), Depends(rate_limit("parser", settings.RATE_PARSER_PER_MIN))],
    responses={
        401: {"model": ErrorOut, "description": "Нет токена"},
        403: {"model": ErrorOut, "description": "Нужна роль admin"},
    },
)

BUSY = {409: {"model": ErrorOut, "description": "Парсер уже занят"}}


@router.get("/status", summary="Состояние парсера")
async def parser_status(redis: RedisDep) -> dict[str, Any]:
    """state: idle, queued, running, done или error. В result итог последней задачи, в error причина падения.
    Состояние хранится в Redis и переживает перезапуск API."""
    return await state.get_status(redis)


@router.get("/queue/stats", summary="Сколько ссылок в каждом статусе очереди")
async def queue_stats(db: DBSessionDep) -> dict[str, Any]:
    rows = (await db.execute(select(CrawlQueue.status, func.count(CrawlQueue.id)).group_by(CrawlQueue.status))).all()
    by_status = {name: count for name, count in rows}
    return {"total_urls": sum(by_status.values()), "by_status": by_status}


@router.get("/queue", response_model=list[CrawlQueueItemOut], summary="Ссылки из очереди")
async def list_queue(
    db: DBSessionDep,
    status_filter: str | None = Query(None, description="done, pending или error"),
    limit: int = Query(50, ge=1, le=300),
) -> list[CrawlQueueItemOut]:
    stmt = select(CrawlQueue).order_by(CrawlQueue.id).limit(limit)
    if status_filter:
        stmt = stmt.where(CrawlQueue.status == status_filter)
    return [CrawlQueueItemOut.model_validate(i) for i in (await db.execute(stmt)).scalars()]


@router.post("/discover", status_code=202, summary="Найти ссылки на товары", responses=BUSY)
async def discover(redis: RedisDep, arq: ArqDep) -> dict[str, Any]:
    """Читает sitemap, а если он пуст, обходит каталог. Новые ссылки попадают в очередь как pending."""
    await state.enqueue(redis, arq, "discover", {})
    return {"status": "scheduled", "job": "discover", "params": {}}


@router.post("/scrape", status_code=202, summary="Разобрать карточки из очереди", responses=BUSY)
async def scrape(
    redis: RedisDep,
    arq: ArqDep,
    limit: int | None = Query(None, ge=1, description="Сколько карточек за запуск, по умолчанию вся очередь"),
    retry_errors: bool = Query(False, description="Заодно повторить ссылки со статусом error"),
) -> dict[str, Any]:
    params = {"limit": limit, "retry_errors": retry_errors}
    await state.enqueue(redis, arq, "scrape", params)
    return {"status": "scheduled", "job": "scrape", "params": params}


@router.get(
    "/preview",
    summary="Разобрать одну страницу без записи в БД",
    responses={
        400: {"model": ErrorOut, "description": "Ссылка чужого сайта"},
        404: {"model": ErrorOut, "description": "Страница не скачалась или это не карточка"},
    },
)
async def preview(
    url: str = Query(description="Ссылка на карточку, например https://ubcashmere.ru/products/slug/"),
    save_html: bool = Query(False, description="Сохранить HTML в PARSER_DATA_DIR/debug"),
) -> Any:
    try:
        product = await jobs.preview_product(url, save_html)
    except ValueError as exc:
        raise BadRequestError(str(exc)) from None
    if product is None:
        raise NotFoundError("Страница не скачалась или это не карточка товара.")
    return product
