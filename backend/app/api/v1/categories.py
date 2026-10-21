from fastapi import APIRouter

from app.api.deps import DBSessionDep
from app.core.cache import CacheDep
from app.schemas.catalog import CategoryTreeOut
from app.schemas.common import ErrorOut
from app.services import catalog

router = APIRouter(prefix="/categories", tags=["2. Категории"])


@router.get("", response_model=list[CategoryTreeOut], summary="Дерево категорий")
async def list_categories(db: DBSessionDep, cache: CacheDep) -> list[CategoryTreeOut]:
    """В products_count родителя входят товары вложенных категорий. Ответ кэшируется."""
    return await catalog.category_tree(db, cache)


@router.get(
    "/{slug}",
    response_model=CategoryTreeOut,
    summary="Категория по slug",
    responses={404: {"model": ErrorOut, "description": "Категории нет"}},
)
async def get_category(slug: str, db: DBSessionDep) -> CategoryTreeOut:
    return await catalog.get_category(db, slug)
