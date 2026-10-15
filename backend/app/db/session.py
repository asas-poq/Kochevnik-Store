"""
Модуль управления асинхронными сессиями базы данных (`app/db/session.py`).
Использует SQLAlchemy 2.0 `create_async_engine` и `async_sessionmaker`.
"""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Определяем дополнительные аргументы движка (для SQLite отключаем check_same_thread,
# для PostgreSQL настраиваем пул соединений для высокой нагрузки)
engine_kwargs = {"echo": False, "future": True}
if not settings.async_database_url.startswith("sqlite"):
    engine_kwargs.update(
        {
            "pool_size": 20,
            "max_overflow": 10,
            "pool_pre_ping": True,
        }
    )

# Создаем асинхронный движок БД
engine = create_async_engine(settings.async_database_url, **engine_kwargs)

# Фабрика асинхронных сессий (expire_on_commit=False обязателен для async SQLAlchemy)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Зависимость FastAPI (`Depends(get_db)`), которая открывает асинхронную сессию БД
    на время обработки одного HTTP-запроса и гарантированно закрывает её после завершения.
    При возникновении необработанного исключения выполняет откат транзакции (`rollback`).
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as exc:
            logger.error(f"Ошибка транзакции БД, выполняем rollback: {exc}")
            await session.rollback()
            raise
        finally:
            await session.close()
