import os

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from app.db.base import Base


def test_migrations_produce_the_same_schema_as_models(tmp_path):
    """Ловит модель, у которой забыли миграцию."""
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path}/m.db"
    # settings читается при импорте, поэтому подменяем значение напрямую
    from app.core.config import settings

    settings.DATABASE_URL = os.environ["DATABASE_URL"]

    command.upgrade(Config("alembic.ini"), "head")

    engine = create_engine(f"sqlite:///{tmp_path}/m.db")
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    engine.dispose()
    assert diff == []
