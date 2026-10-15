"""
Роутер категорий каталога (`app/api/v1/categories.py`).
Отдает дерево категорий для навигационного меню в шапке сайта и фильтров каталога.
"""

from typing import Dict, List
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import DBSessionDep
from app.core.logging import get_logger
from app.models.catalog import Category, Product
from app.schemas.catalog import CategoryTreeOut

logger = get_logger(__name__)

router = APIRouter(prefix="/categories", tags=["2. Категории каталога"])


# ==============================================================================
# РУЧКА 1: Дерево категорий каталога с подсчетом количества активных товаров
# ==============================================================================
@router.get(
    "",
    response_model=List[CategoryTreeOut],
    summary="Получить дерево категорий для меню (GET /api/v1/categories)",
)
async def list_categories_tree(
    db: DBSessionDep,
) -> List[CategoryTreeOut]:
    """
    Возвращает иерархическое дерево категорий из таблицы `categories` (из дампа парсера):
    - «Женская одежда из кашемира, пуха яка и шерсти верблюда» (`id=1`)
    - «Кожаные изделия из Монголии» (`id=6`)
    А также любые дочерние подкатегории с автоматическим подсчетом числа активных товаров в каждой категории.
    """
    logger.info("Запрос дерева категорий каталога GET /api/v1/categories")

    # Загружаем все категории и количество активных товаров в каждой категории одним быстрым запросом
    cats_result = await db.execute(select(Category).order_by(Category.id.asc()))
    categories = cats_result.scalars().all()

    counts_result = await db.execute(
        select(Product.category_id, func.count(Product.id))
        .where(Product.status == "active")
        .group_by(Product.category_id)
    )
    counts_map: Dict[int, int] = {
        cat_id: count for cat_id, count in counts_result.all() if cat_id is not None
    }

    # Собираем узлы дерева
    nodes: Dict[int, CategoryTreeOut] = {}
    for cat in categories:
        nodes[cat.id] = CategoryTreeOut(
            id=cat.id,
            source_id=cat.source_id,
            slug=cat.slug,
            name=cat.name,
            url=cat.url,
            parent_id=cat.parent_id,
            products_count=counts_map.get(cat.id, 0),
            children=[],
        )

    root_categories: List[CategoryTreeOut] = []
    for cat_id, node in nodes.items():
        if node.parent_id and node.parent_id in nodes:
            nodes[node.parent_id].children.append(node)
            nodes[node.parent_id].products_count += node.products_count
        else:
            root_categories.append(node)

    logger.debug(f"Отдано корневых категорий: {len(root_categories)}")
    return root_categories


# ==============================================================================
# РУЧКА 2: Получение одной категории по её slug
# ==============================================================================
@router.get(
    "/{slug}",
    response_model=CategoryTreeOut,
    summary="Получить детальную информацию о категории по её slug",
)
async def get_category_by_slug(
    slug: str,
    db: DBSessionDep,
) -> CategoryTreeOut:
    """
    Возвращает данные конкретной категории по её ЧПУ (`slug`) и количество активных товаров в ней.
    Используется для SEO-заголовков и хлебных крошек на странице каталога.
    """
    logger.info(f"Запрос категории по slug='{slug}'")
    result = await db.execute(select(Category).where(Category.slug == slug))
    cat = result.scalar_one_or_none()
    if not cat:
        logger.warning(f"Категория со slug='{slug}' не найдена")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Категория '{slug}' не найдена.",
        )

    count_q = await db.execute(
        select(func.count(Product.id)).where(
            Product.category_id == cat.id, Product.status == "active"
        )
    )
    products_count = count_q.scalar() or 0

    return CategoryTreeOut(
        id=cat.id,
        source_id=cat.source_id,
        slug=cat.slug,
        name=cat.name,
        url=cat.url,
        parent_id=cat.parent_id,
        products_count=products_count,
        children=[],
    )
