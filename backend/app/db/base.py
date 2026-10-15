"""
Базовый декларативный класс SQLAlchemy 2.0 (`app/db/base.py`).
Все модели таблиц наследуются от `Base`.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Базовый класс для всех ORM-моделей проекта.
    Позволяет Alembic автоматически находить все таблицы через `Base.metadata`.
    """
    pass
