"""
Роутер управления парсером (`app/api/v1/parser_sync.py`).

Схема работы:
    клиент -> ручка API -> фоновая задача -> app/services/parser.py -> ОСНОВНАЯ БД (из Settings)

Парсер сам подключается к основной базе (PostgreSQL / SQLite — как указано в `.env`)
и пишет туда товары напрямую, поэтому передавать ему путь к БД или файлы не нужно.
Ручки передают парсеру только параметры самой задачи (limit, retry_errors, url).

Ручки:
  GET  /parser/status          — идёт ли сейчас задача парсера и чем она закончилась
  GET  /parser/queue/stats     — сколько ссылок done / pending / error
  GET  /parser/queue           — список ссылок из очереди (с фильтром по статусу)
  POST /parser/discover        — найти URL товаров и добавить новые в очередь
  POST /parser/scrape          — обработать очередь (limit, retry_errors)
  GET  /parser/preview         — разобрать одну страницу, НЕ записывая в БД (проверка парсера)
  POST /parser/sync-dump       — (устаревшее) импорт JSON-дампа; оставлено для совместимости
"""

from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select

from app.api.deps import DBSessionDep
from app.core.logging import get_logger
from app.models.catalog import CrawlQueue
from app.schemas.catalog import CrawlQueueItemOut
from app.services.parser import (
    get_job_status,
    preview_product,
    run_discover,
    run_job,
    run_scrape,
    start_job,
)
from app.services.tasks import import_parser_dump_task

logger = get_logger(__name__)

router = APIRouter(prefix="/parser", tags=["7. Синхронизация с Парсером и Очередь (Crawl Queue)"])


def _schedule(
    background_tasks: BackgroundTasks,
    job_name: str,
    func: Callable[..., Any],
    **params: Any,
) -> Dict[str, Any]:
    """
    Общий запуск фоновой задачи парсера.
    Если парсер уже занят — отвечаем 409, чтобы два обхода не работали одновременно
    (иначе они бы бились за одни и те же ссылки очереди и нагружали сайт).
    """
    if not start_job(job_name):
        raise HTTPException(
            status_code=409,
            detail="Парсер уже выполняет задачу. Состояние смотрите в GET /api/v1/parser/status",
        )
    # run_job — обычная (не async) функция, Starlette выполнит её в пуле потоков,
    # поэтому блокирующие запросы парсера не вешают event loop приложения.
    background_tasks.add_task(run_job, job_name, func, **params)
    logger.info(f"Парсер: задача '{job_name}' поставлена в фон, параметры: {params}")
    return {"status": "scheduled", "job": job_name, "params": params}


# ==============================================================================
# Состояние парсера
# ==============================================================================
@router.get("/status", summary="Состояние парсера: идёт ли задача и чем закончилась последняя")
async def get_parser_status() -> Dict[str, Any]:
    """
    Возвращает: имя задачи, `running` (идёт ли сейчас), время старта/окончания,
    `result` (например `{"total": 20, "ok": 19, "errors": 1}`) или `error`, если задача упала.
    Состояние хранится в памяти процесса и сбрасывается при перезапуске бэкенда.
    """
    return get_job_status()


# ==============================================================================
# Очередь (crawl_queue)
# ==============================================================================
@router.get("/queue/stats", summary="Статистика очереди парсера (crawl_queue)")
async def get_crawl_queue_stats(db: DBSessionDep) -> Dict[str, Any]:
    """Сколько всего ссылок в `crawl_queue` и сколько в каждом статусе (done / pending / error)."""
    rows = (
        await db.execute(select(CrawlQueue.status, func.count(CrawlQueue.id)).group_by(CrawlQueue.status))
    ).all()
    by_status = {status_name: count for status_name, count in rows}
    return {"total_urls": sum(by_status.values()), "by_status": by_status}


@router.get(
    "/queue",
    response_model=List[CrawlQueueItemOut],
    summary="Список URL из очереди парсера (crawl_queue)",
)
async def list_crawl_queue(
    db: DBSessionDep,
    status_filter: Optional[str] = Query(None, description="Фильтр по статусу: done, pending, error"),
    limit: int = Query(50, ge=1, le=300),
) -> List[CrawlQueueItemOut]:
    """Отдаёт ссылки из `crawl_queue` по порядку добавления — удобно смотреть, что ждёт обхода или упало."""
    stmt = select(CrawlQueue).order_by(CrawlQueue.id.asc()).limit(limit)
    if status_filter:
        stmt = stmt.where(CrawlQueue.status == status_filter)
    items = (await db.execute(stmt)).scalars().all()
    return [CrawlQueueItemOut.model_validate(item) for item in items]


# ==============================================================================
# Запуск парсера
# ==============================================================================
@router.post(
    "/discover",
    status_code=202,
    summary="Шаг 1: найти все URL товаров и добавить новые в очередь",
)
async def trigger_discover(background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """
    Парсер читает sitemap сайта (если пуст — обходит каталог) и добавляет новые ссылки
    в `crawl_queue` со статусом `pending`. Уже известные ссылки не дублируются.
    """
    return _schedule(background_tasks, "discover", run_discover)


@router.post(
    "/scrape",
    status_code=202,
    summary="Шаг 2: спарсить карточки товаров из очереди и записать в основную БД",
)
async def trigger_scrape(
    background_tasks: BackgroundTasks,
    limit: Optional[int] = Query(
        None, ge=1, description="Сколько карточек обработать за запуск (пусто — вся очередь)"
    ),
    retry_errors: bool = Query(False, description="Заодно повторить ссылки со статусом error"),
) -> Dict[str, Any]:
    """
    Берёт ссылки `pending` (и `error`, если `retry_errors=true`), скачивает карточки
    и сохраняет товары, фото, размеры, материалы и историю цен в основную БД.
    Для пробы можно начать с `?limit=20`.
    """
    return _schedule(background_tasks, "scrape", run_scrape, limit=limit, retry_errors=retry_errors)


@router.get("/preview", summary="Проверка: разобрать одну страницу товара без записи в БД")
async def preview_page(
    url: str = Query(..., description="Полная ссылка на карточку, например https://ubcashmere.ru/products/<slug>/"),
    save_html: bool = Query(False, description="Сохранить скачанный HTML в data/parser/debug"),
) -> Dict[str, Any]:
    """Аналог `parser.py debug`: показывает, что парсер «видит» на странице. В БД ничего не пишется."""
    try:
        # парсер блокирующий (requests + пауза), поэтому уводим его в поток
        product = await run_in_threadpool(preview_product, url, save_html)
    except ValueError as e:  # URL чужого сайта
        raise HTTPException(status_code=400, detail=str(e))
    if product is None:
        raise HTTPException(status_code=404, detail="Страница не скачалась или это не карточка товара")
    return product



