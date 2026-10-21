"""Заливает data/parsed_dump.json и демо-пользователей. Таблицы должны уже быть: make migrate.

Запуск из корня проекта: python -m scripts.seed_from_parser
"""
import asyncio
import sys
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.db.session import engine
from app.services.seed import import_parser_dump, seed_demo_users

DUMP = Path(__file__).resolve().parent.parent / "data" / "parsed_dump.json"


async def main() -> None:
    setup_logging()
    logger = get_logger("seed")
    if settings.is_production:
        sys.exit("Сид с демо-паролями в production не запускается.")
    logger.info("Импорт дампа", extra={"file": str(DUMP)})
    await import_parser_dump(DUMP)
    await seed_demo_users()
    logger.info("Админ admin@ubcashmere.ru / Admin123!, покупатель anna@example.com / Customer123!")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
