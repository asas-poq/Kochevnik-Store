"""
Роутер интеграции с парсером (`app/api/v1/parser_sync.py`).
Позволяет:
1. Посмотреть статистику очереди парсера (`crawl_queue`: сколько ссылок `done`, сколько `pending`, сколько `error`)
2. Получить список ссылок из `crawl_queue` для воркера парсера
3. Запустить фоновую синхронизацию (`BackgroundTasks`) JSON-дампа парсера в базу данных
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, BackgroundTasks, Query
from sqlalchemy import func, select

from app.api.deps import DBSessionDep
from app.core.logging import get_logger
from app.models.catalog import CrawlQueue
from app.schemas.catalog import CrawlQueueItemOut
from app.services.tasks import import_parser_dump_task

logger = get_logger(__name__)

router = APIRouter(prefix="/parser", tags=["7. Синхронизация с Парсером и Очередь (Crawl Queue)"])


# ==============================================================================
# РУЧКА 1: Статистика очереди парсера (done / pending / error)
# ==============================================================================
@router.get(
    "/queue/stats",
    summary="Статистика очереди парсера (crawl_queue)",
)
async def get_crawl_queue_stats(
    db: DBSessionDep,
) -> Dict[str, Any]:
    """
    Возвращает сводную статистику по таблице `crawl_queue` из вашего парсера:
    общее число найденных ссылок на товары `ubcashmere.ru`, сколько уже спарсено (`done`)
    и сколько ожидают обхода (`pending`).
    """
    logger.info("Запрос статистики очереди парсера GET /api/v1/parser/queue/stats")
    rows = (
        await db.execute(
            select(CrawlQueue.status, func.count(CrawlQueue.id)).group_by(
                CrawlQueue.status
            )
        )
    ).all()

    by_status = {status_name: count for status_name, count in rows}
    total = sum(by_status.values())
    return {
        "total_urls": total,
        "by_status": by_status,
    }


# ==============================================================================
# РУЧКА 2: Получить ссылки из очереди парсера (например, все pending для обхода)
# ==============================================================================
@router.get(
    "/queue",
    response_model=List[CrawlQueueItemOut],
    summary="Получить список URL из очереди парсера (crawl_queue)",
)
async def list_crawl_queue(
    db: DBSessionDep,
    status_filter: Optional[str] = Query(
        None, description="Фильтр по статусу: done, pending, error"
    ),
    limit: int = Query(50, ge=1, le=300),
) -> List[CrawlQueueItemOut]:
    """
    Отдает список URL из таблицы `crawl_queue`.
    Ваш парсер может обращаться к этой ручке с параметром `?status_filter=pending`,
    чтобы брать следующую пачку товаров для парсинга.
    """
    stmt = select(CrawlQueue).order_by(CrawlQueue.id.asc()).limit(limit)
    if status_filter:
        stmt = stmt.where(CrawlQueue.status == status_filter)

    items = (await db.execute(stmt)).scalars().all()
    return [CrawlQueueItemOut.model_validate(item) for item in items]


# ==============================================================================
# РУЧКА 3: Запустить импорт JSON-дампа парсера в фоне
# ==============================================================================
@router.post(
    "/sync-dump",
    summary="Запустить синхронизацию JSON-дампа парсера (data/parsed_dump.json) в фоновом режиме",
)
async def trigger_parser_dump_sync(
    background_tasks: BackgroundTasks,
    json_path: str = Query(
        "data/parsed_dump.json",
        description="Путь к JSON-файлу с выгрузкой парсера",
    ),
) -> Dict[str, str]:
    """
    Запускает асинхронную фоновую задачу (`BackgroundTasks`) импорта всех категорий,
    товаров, фотографий, материалов, связей цветов и очереди `crawl_queue` из JSON-файла парсера.
    """
    logger.info(f"Запуск фоновой синхронизации дампа парсера из файла: {json_path}")
    background_tasks.add_task(import_parser_dump_task, json_path)
    return {
        "status": "scheduled",
        "message": f"Фоновая задача импорта данных парсера из '{json_path}' успешно запущена.",
    }
