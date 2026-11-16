"""Наполняет базу: создаёт демо-пользователей и загружает 50 товаров парсером.

Таблицы должны уже существовать: make migrate.
Запуск из каталога backend: python -m scripts.seed_from_parser
"""
import asyncio
import sys

from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.db.session import engine
from app.services.parser import jobs
from app.services.seed import seed_demo_users

PRODUCTS_LIMIT = 50


async def main() -> None:
    setup_logging()
    logger = get_logger("seed")
    if settings.is_production:
        sys.exit("Сид с демо-паролями в production не запускается.")

    await seed_demo_users()
    logger.info("Пользователи: admin@example.com / Admin123!, anna@example.com / Customer123!")

    discovered = await jobs.run_named("discover", {})
    logger.info("Найдено ссылок на товары", extra={"result": discovered})
    scraped = await jobs.run_named("scrape", {"limit": PRODUCTS_LIMIT})
    logger.info("Товары загружены", extra={"result": scraped})
    await engine.dispose()
    if not scraped.get("ok"):
        sys.exit("Парсер не загрузил ни одного товара: проверьте доступность источника.")


if __name__ == "__main__":
    asyncio.run(main())
