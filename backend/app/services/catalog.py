"""
Бизнес-логика каталога (`app/services/catalog.py`).

Роутер `products.py` остаётся тонким, а вся «умная» часть живёт здесь:
- фильтры каталога (одна функция строит условия и для выдачи, и для счётчиков фильтров);
- фасеты — доступные значения фильтров с количеством товаров под текущую выборку;
- рейтинг популярности, сезонные правила и подборки рекомендаций;
- переключатель цветов модели (связи в обе стороны + общий `color_group`).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Dict, FrozenSet, List, Optional, Sequence, Set, Tuple

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.models.catalog import (
    Category,
    Product,
    ProductAttribute,
    ProductColorLink,
    ProductMaterial,
    ProductSize,
)
from app.models.interactions import ProductLike
from app.models.order import Order, OrderItem
from app.schemas.catalog import (
    CatalogFacetsOut,
    FacetColorOut,
    FacetOptionOut,
    PriceRangeOut,
    SiblingColorVariantOut,
)
from app.services.tasks import COLOR_HEX_MAP

if TYPE_CHECKING:  # только для подсказок типов, без циклических импортов
    from app.api.deps import ProductFilterParams

DEFAULT_COLOR_HEX = "#D8CFC4"

# --- Рейтинг популярности: чем «весомее» сигнал, тем выше коэффициент ---
POPULARITY_WINDOW_DAYS = 90          # продажи учитываются за последние N дней
SALE_ORDER_STATUSES = ("paid", "shipped", "completed")  # заказы, которые считаются продажей
W_SOLD, W_LIKES, W_REVIEWS, W_RATING = 5, 2, 3, 2

# Порядок размеров в панели фильтров
SIZE_ORDER = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL", "ONE SIZE"]


# ==============================================================================
# Сезоны
# ==============================================================================
@dataclass(frozen=True)
class SeasonRule:
    key: str
    label: str
    months: Tuple[int, ...]
    tag_stems: Tuple[str, ...]   # что искать в характеристике товара «Сезон»
    keywords: Tuple[str, ...]    # что искать в названии и составе, если «Сезон» не задан


SEASON_RULES: Dict[str, SeasonRule] = {
    "winter": SeasonRule(
        "winter", "Зима", (12, 1, 2),
        ("зим", "всесезон"),
        ("пух яка", "верблюж", "палантин", "шарф", "шапк", "варежк", "перчатк", "плед", "пальто", "шуб"),
    ),
    "spring": SeasonRule(
        "spring", "Весна", (3, 4, 5),
        ("весн", "демисезон", "всесезон"),
        ("кардиган", "жилет", "пончо", "шарф", "сумк", "кожан"),
    ),
    "summer": SeasonRule(
        "summer", "Лето", (6, 7, 8),
        ("лет", "всесезон"),
        ("шёлк", "шелк", "лён", "хлопок", "сумк", "кросс", "клатч", "топ", "платье"),
    ),
    "autumn": SeasonRule(
        "autumn", "Осень", (9, 10, 11),
        ("осен", "демисезон", "всесезон"),
        ("кашемир", "свитер", "пуловер", "джемпер", "кардиган", "водолазк", "палантин", "шарф", "сумк", "кожан"),
    ),
}


def current_season(now: Optional[datetime] = None) -> SeasonRule:
    month = (now or datetime.now(timezone.utc)).month
    return next(rule for rule in SEASON_RULES.values() if month in rule.months)


def seasonal_condition(rule: SeasonRule) -> ColumnElement[bool]:
    """
    Товар «сезонный», если у него есть характеристика «Сезон» с подходящим значением
    (приоритет админа) ИЛИ в названии/составе встречается ключевое слово сезона.
    """
    tagged = Product.attributes.any(
        and_(
            func.lower(ProductAttribute.attr_key).like("%сезон%"),
            or_(*[func.lower(ProductAttribute.attr_value).like(f"%{stem}%") for stem in rule.tag_stems]),
        )
    )
    by_text = [
        column.ilike(f"%{word}%")
        for word in rule.keywords
        for column in (Product.name, Product.composition)
    ]
    return or_(tagged, *by_text)


# ==============================================================================
# Выражения для сортировки и скидок
# ==============================================================================
def _sold_units_expr():
    """Сколько штук товара продано за последние POPULARITY_WINDOW_DAYS дней."""
    since = datetime.now(timezone.utc) - timedelta(days=POPULARITY_WINDOW_DAYS)
    return (
        select(func.coalesce(func.sum(OrderItem.quantity), 0))
        .select_from(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            OrderItem.product_id == Product.id,
            Order.status.in_(SALE_ORDER_STATUSES),
            Order.created_at >= since,
        )
        .correlate(Product)
        .scalar_subquery()
    )


def popularity_expr():
    """Рейтинг популярности = продажи*5 + лайки*2 + отзывы*3 + средняя оценка*2."""
    return (
        _sold_units_expr() * W_SOLD
        + Product.likes_count * W_LIKES
        + Product.reviews_count * W_REVIEWS
        + Product.rating_avg * W_RATING
    )


def bayesian_rating_expr(prior_mean: float = 4.0, prior_weight: int = 3):
    """Оценка с поправкой на число отзывов: одна «пятёрка» не обгоняет 40 отзывов с 4.8."""
    return (Product.rating_avg * Product.reviews_count + prior_mean * prior_weight) / (
        Product.reviews_count + prior_weight
    )


def on_sale_condition() -> ColumnElement[bool]:
    return and_(Product.old_price.is_not(None), Product.old_price > Product.current_price)


def discount_percent_expr():
    return case(
        (on_sale_condition(), (Product.old_price - Product.current_price) * 100.0 / Product.old_price),
        else_=0.0,
    )


def in_stock_condition() -> ColumnElement[bool]:
    return Product.sizes.any(ProductSize.stock > 0)


def card_loader_options():
    """Жадная подгрузка того, что нужно карточке в списке (без N+1 запросов)."""
    return (
        selectinload(Product.images),
        selectinload(Product.sizes),
        selectinload(Product.materials),
    )


# ==============================================================================
# Фильтры каталога
# ==============================================================================
def _like_pattern(token: str) -> str:
    escaped = token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def resolve_category_ids(db: AsyncSession, slugs: Sequence[str]) -> Optional[Set[int]]:
    """
    Slug'и категорий -> множество id вместе со ВСЕМИ вложенными подкатегориями.
    None — фильтра по категории нет; пустое множество — такой категории не существует.
    """
    if not slugs:
        return None
    rows = (await db.execute(select(Category.id, Category.slug, Category.parent_id))).all()
    children: Dict[Optional[int], List[int]] = defaultdict(list)
    for row in rows:
        children[row.parent_id].append(row.id)

    wanted = {slug.lower() for slug in slugs}
    result: Set[int] = {row.id for row in rows if row.slug.lower() in wanted}
    stack = list(result)
    while stack:
        for child_id in children.get(stack.pop(), []):
            if child_id not in result:
                result.add(child_id)
                stack.append(child_id)
    return result


def build_conditions(
    f: "ProductFilterParams",
    *,
    category_ids: Optional[Set[int]],
    user_id: Optional[int],
    exclude: FrozenSet[str] = frozenset(),
) -> List[ColumnElement[bool]]:
    """
    Единственное место, где описаны условия фильтрации.
    `exclude` нужен для фасетов: счётчики группы считаются без фильтра этой же группы.
    Используются EXISTS-подзапросы, а не JOIN: нет дубликатов строк, DISTINCT не нужен,
    пагинация и total всегда совпадают.
    """
    conditions: List[ColumnElement[bool]] = [Product.status == "active"]

    if category_ids is not None and "category" not in exclude:
        conditions.append(Product.category_id.in_(category_ids))

    if f.color and "color" not in exclude:
        conditions.append(func.lower(Product.color).in_([c.lower() for c in f.color]))

    if f.material and "material" not in exclude:
        conditions.append(
            Product.materials.any(func.lower(ProductMaterial.material).in_([m.lower() for m in f.material]))
        )

    if "size" not in exclude:
        if f.size:
            conditions.append(
                Product.sizes.any(
                    and_(func.upper(ProductSize.size).in_([s.upper() for s in f.size]), ProductSize.stock > 0)
                )
            )
        elif f.only_in_stock:
            conditions.append(in_stock_condition())

    if "price" not in exclude:
        if f.min_price is not None:
            conditions.append(Product.current_price >= f.min_price)
        if f.max_price is not None:
            conditions.append(Product.current_price <= f.max_price)

    if f.on_sale:
        conditions.append(on_sale_condition())

    if f.search:
        for token in f.search.split()[:6]:
            pattern = _like_pattern(token)
            conditions.append(
                or_(
                    Product.name.ilike(pattern, escape="\\"),
                    Product.article.ilike(pattern, escape="\\"),
                    Product.composition.ilike(pattern, escape="\\"),
                    Product.color.ilike(pattern, escape="\\"),
                )
            )

    if f.only_liked and user_id is not None:
        conditions.append(Product.likes.any(ProductLike.user_id == user_id))

    return conditions


def order_clauses(sort: str) -> list:
    """Сортировка всегда заканчивается `Product.id` — иначе страницы «прыгают» при равных значениях."""
    if sort == "price_asc":
        return [Product.current_price.asc(), Product.id.asc()]
    if sort == "price_desc":
        return [Product.current_price.desc(), Product.id.asc()]
    if sort == "newest":
        return [Product.first_seen.desc(), Product.id.desc()]
    if sort == "rating_desc":
        return [bayesian_rating_expr().desc(), Product.reviews_count.desc(), Product.id.asc()]
    if sort == "discount":
        return [discount_percent_expr().desc(), popularity_expr().desc(), Product.id.asc()]
    return [popularity_expr().desc(), Product.id.asc()]  # popular


# ==============================================================================
# Фасеты (доступные значения фильтров со счётчиками)
# ==============================================================================
def _size_sort_key(name: str) -> Tuple[int, str]:
    return (SIZE_ORDER.index(name), name) if name in SIZE_ORDER else (len(SIZE_ORDER), name)


async def build_facets(
    db: AsyncSession,
    f: "ProductFilterParams",
    *,
    category_ids: Optional[Set[int]],
    user_id: Optional[int],
) -> CatalogFacetsOut:
    def cond(*exclude: str) -> List[ColumnElement[bool]]:
        return build_conditions(f, category_ids=category_ids, user_id=user_id, exclude=frozenset(exclude))

    color_rows = (
        await db.execute(
            select(Product.color, func.count(Product.id), func.max(Product.color_hex))
            .where(*cond("color"), Product.color.is_not(None))
            .group_by(Product.color)
            .order_by(func.count(Product.id).desc(), Product.color)
        )
    ).all()

    material_rows = (
        await db.execute(
            select(func.lower(ProductMaterial.material), func.count(func.distinct(ProductMaterial.product_id)))
            .select_from(ProductMaterial)
            .join(Product, Product.id == ProductMaterial.product_id)
            .where(*cond("material"))
            .group_by(func.lower(ProductMaterial.material))
            .order_by(func.count(func.distinct(ProductMaterial.product_id)).desc())
        )
    ).all()

    size_rows = (
        await db.execute(
            select(func.upper(ProductSize.size), func.count(func.distinct(ProductSize.product_id)))
            .select_from(ProductSize)
            .join(Product, Product.id == ProductSize.product_id)
            .where(ProductSize.stock > 0, *cond("size"))
            .group_by(func.upper(ProductSize.size))
        )
    ).all()

    price_min, price_max = (
        await db.execute(
            select(func.min(Product.current_price), func.max(Product.current_price)).where(*cond("price"))
        )
    ).one()

    return CatalogFacetsOut(
        colors=[
            FacetColorOut(
                name=name,
                hex=COLOR_HEX_MAP.get(name) or hex_code or DEFAULT_COLOR_HEX,
                count=count,
            )
            for name, count, hex_code in color_rows
        ],
        materials=[FacetOptionOut(name=name.capitalize(), count=count) for name, count in material_rows],
        sizes=sorted(
            (FacetOptionOut(name=name, count=count) for name, count in size_rows),
            key=lambda option: _size_sort_key(option.name),
        ),
        price_range=PriceRangeOut(min=price_min or 0, max=price_max or 0),
    )


# ==============================================================================
# Рекомендации
# ==============================================================================
async def build_recommendations(
    db: AsyncSession,
    *,
    limit: int,
    season: SeasonRule,
    category_ids: Optional[Set[int]],
) -> Dict[str, List[Product]]:
    """Четыре независимые подборки; в них попадают только товары в наличии."""

    async def pick(extra: List[ColumnElement[bool]], order_by: list) -> List[Product]:
        conditions = [Product.status == "active", in_stock_condition(), *extra]
        if category_ids is not None:
            conditions.append(Product.category_id.in_(category_ids))
        stmt = (
            select(Product)
            .where(*conditions)
            .options(*card_loader_options())
            .order_by(*order_by, Product.id.asc())
            .limit(limit)
        )
        return list((await db.execute(stmt)).scalars().all())

    return {
        "popular": await pick([], [popularity_expr().desc()]),
        "seasonal": await pick([seasonal_condition(season)], [popularity_expr().desc()]),
        "new_arrivals": await pick([], [Product.first_seen.desc()]),
        "on_sale": await pick([on_sale_condition()], [discount_percent_expr().desc(), popularity_expr().desc()]),
    }


# ==============================================================================
# Переключатель цветов на карточке
# ==============================================================================
async def resolve_color_variants(db: AsyncSession, product: Product) -> List[SiblingColorVariantOut]:
    """
    Цвета одной модели. Источники (объединяются, дубли убираются):
    1. ссылки `product_color_links` ИЗ этого товара;
    2. ссылки ИЗ других товаров НА этот (связь могла быть записана только в одну сторону);
    3. товары с тем же `color_group`.
    Показываются только активные товары: кружок, ведущий на 404, пользователю не нужен.
    """
    linked_out = {link.sibling_slug for link in product.color_links}
    linked_in = select(Product.slug).join(
        ProductColorLink, ProductColorLink.product_id == Product.id
    ).where(ProductColorLink.sibling_slug == product.slug)

    relation = [Product.slug.in_(linked_out), Product.slug.in_(linked_in)]
    if product.color_group:
        relation.append(Product.color_group == product.color_group)

    siblings = (
        (
            await db.execute(
                select(Product)
                .where(Product.status == "active", Product.id != product.id, or_(*relation))
                .options(selectinload(Product.images))
            )
        )
        .scalars()
        .all()
    )

    def to_variant(p: Product) -> SiblingColorVariantOut:
        return SiblingColorVariantOut(
            sibling_slug=p.slug,
            color=p.color,
            color_hex=p.color_hex or COLOR_HEX_MAP.get(p.color or "", DEFAULT_COLOR_HEX),
            in_catalog=True,
            preview_image=p.images[0].url if p.images else None,
            price=p.current_price,
        )

    ordered = sorted(siblings, key=lambda p: ((p.color or "").lower(), p.slug))
    return [to_variant(product), *[to_variant(p) for p in ordered]]
