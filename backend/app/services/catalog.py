import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.api.deps import ProductFilterParams
from app.core.cache import Cache
from app.core.config import settings
from app.core.errors import NotFoundError, UnauthorizedError
from app.db.utils import escape_like
from app.models import (
    Category,
    Order,
    OrderItem,
    Product,
    ProductAttribute,
    ProductColorLink,
    ProductLike,
    ProductMaterial,
    ProductSize,
    User,
)
from app.schemas.catalog import (
    CatalogFacetsOut,
    CategoryTreeList,
    CategoryTreeOut,
    FacetColorOut,
    FacetOptionOut,
    PaginatedProductsOut,
    PriceRangeOut,
    ProductCardOut,
    ProductDetailOut,
    RecommendationsOut,
    SiblingColorVariantOut,
)
from app.services.colors import hex_for

SALE_ORDER_STATUSES = ("paid", "shipped", "completed")
SIZE_ORDER = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL", "ONE SIZE"]


@dataclass(frozen=True)
class SeasonRule:
    key: str
    label: str
    months: tuple[int, ...]
    tag_stems: tuple[str, ...]  # что искать в характеристике «Сезон»
    keywords: tuple[str, ...]  # что искать в названии и составе, если «Сезон» не задан


SEASON_RULES: dict[str, SeasonRule] = {
    "winter": SeasonRule(
        "winter", "Зима", (12, 1, 2), ("зим", "всесезон"),
        ("пух яка", "верблюж", "палантин", "шарф", "шапк", "варежк", "перчатк", "плед", "пальто", "шуб"),
    ),
    "spring": SeasonRule(
        "spring", "Весна", (3, 4, 5), ("весн", "демисезон", "всесезон"),
        ("кардиган", "жилет", "пончо", "шарф", "сумк", "кожан"),
    ),
    "summer": SeasonRule(
        "summer", "Лето", (6, 7, 8), ("лет", "всесезон"),
        ("шёлк", "шелк", "лён", "хлопок", "сумк", "кросс", "клатч", "топ", "платье"),
    ),
    "autumn": SeasonRule(
        "autumn", "Осень", (9, 10, 11), ("осен", "демисезон", "всесезон"),
        ("кашемир", "свитер", "пуловер", "джемпер", "кардиган", "водолазк", "палантин", "шарф", "сумк", "кожан"),
    ),
}  # fmt: skip


def current_season(now: datetime | None = None) -> SeasonRule:
    month = (now or datetime.now(timezone.utc)).month
    return next(rule for rule in SEASON_RULES.values() if month in rule.months)


def seasonal_condition(rule: SeasonRule) -> ColumnElement[bool]:
    """Характеристика «Сезон» у товара важнее ключевых слов в названии и составе."""
    tagged = Product.attributes.any(
        and_(
            func.lower(ProductAttribute.attr_key).like("%сезон%"),
            or_(*[func.lower(ProductAttribute.attr_value).like(f"%{stem}%") for stem in rule.tag_stems]),
        )
    )
    by_text = [
        column.ilike(f"%{word}%") for word in rule.keywords for column in (Product.name, Product.composition)
    ]
    return or_(tagged, *by_text)


def popularity_expr():  # type: ignore[no-untyped-def]
    since = datetime.now(timezone.utc) - timedelta(days=settings.POPULARITY_WINDOW_DAYS)
    sold = (
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
    return (
        sold * settings.POPULARITY_W_SOLD
        + Product.likes_count * settings.POPULARITY_W_LIKES
        + Product.reviews_count * settings.POPULARITY_W_REVIEWS
        + Product.rating_avg * settings.POPULARITY_W_RATING
    )


def bayesian_rating_expr(prior_mean: float = 4.0, prior_weight: int = 3):  # type: ignore[no-untyped-def]
    """Одна пятёрка не должна обгонять 40 отзывов со средним 4.8."""
    return (Product.rating_avg * Product.reviews_count + prior_mean * prior_weight) / (
        Product.reviews_count + prior_weight
    )


def on_sale_condition() -> ColumnElement[bool]:
    return and_(Product.old_price.is_not(None), Product.old_price > Product.current_price)


def discount_percent_expr():  # type: ignore[no-untyped-def]
    return case(
        (on_sale_condition(), (Product.old_price - Product.current_price) * 100.0 / Product.old_price),
        else_=0.0,
    )


def in_stock_condition() -> ColumnElement[bool]:
    return Product.sizes.any(ProductSize.stock > 0)


def card_loader_options():  # type: ignore[no-untyped-def]
    return (
        selectinload(Product.images),
        selectinload(Product.sizes),
        selectinload(Product.materials),
    )


async def resolve_category_ids(db: AsyncSession, slugs: list[str]) -> set[int] | None:
    """None значит фильтра нет, пустое множество значит такой категории не существует."""
    if not slugs:
        return None
    rows = (await db.execute(select(Category.id, Category.slug, Category.parent_id))).all()
    children: dict[int | None, list[int]] = defaultdict(list)
    for row in rows:
        children[row.parent_id].append(row.id)

    wanted = {slug.lower() for slug in slugs}
    result = {row.id for row in rows if row.slug.lower() in wanted}
    stack = list(result)
    while stack:
        for child_id in children.get(stack.pop(), []):
            if child_id not in result:
                result.add(child_id)
                stack.append(child_id)
    return result


async def resolve_colors(db: AsyncSession, requested: list[str]) -> list[str] | None:
    """Названия цветов из запроса приводим к тем, что лежат в БД. lower() в SQLite не понижает кириллицу,
    поэтому регистр сравниваем в Python. None значит фильтра нет, пустой список значит такого цвета нет."""
    if not requested:
        return None
    stored = (await db.execute(select(Product.color).where(Product.color.is_not(None)).distinct())).scalars()
    wanted = {name.casefold() for name in requested}
    return [name for name in stored if name.casefold() in wanted]


def build_conditions(
    f: ProductFilterParams,
    *,
    category_ids: set[int] | None,
    color_names: list[str] | None,
    user_id: int | None,
    exclude: frozenset[str] = frozenset(),
) -> list[ColumnElement[bool]]:
    """Единственное место с условиями каталога. exclude нужен фасетам: группа считается без своего фильтра.
    EXISTS вместо JOIN, чтобы не было дублей строк и total совпадал со страницей."""
    conditions: list[ColumnElement[bool]] = [Product.status == "active"]

    if category_ids is not None and "category" not in exclude:
        conditions.append(Product.category_id.in_(category_ids))
    if color_names is not None and "color" not in exclude:
        conditions.append(Product.color.in_(color_names))
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
            pattern = escape_like(token)
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


def order_clauses(sort: str) -> list:  # type: ignore[type-arg]
    """В конце всегда Product.id, иначе при равных значениях страницы пересекаются."""
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
    return [popularity_expr().desc(), Product.id.asc()]


def _size_sort_key(name: str) -> tuple[int, str]:
    return (SIZE_ORDER.index(name), name) if name in SIZE_ORDER else (len(SIZE_ORDER), name)


async def build_facets(
    db: AsyncSession,
    f: ProductFilterParams,
    *,
    category_ids: set[int] | None,
    color_names: list[str] | None,
    user_id: int | None,
) -> CatalogFacetsOut:
    def cond(*exclude: str) -> list[ColumnElement[bool]]:
        return build_conditions(
            f, category_ids=category_ids, color_names=color_names, user_id=user_id, exclude=frozenset(exclude)
        )

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
            FacetColorOut(name=name, hex=hex_for(name, hex_code), count=count)
            for name, count, hex_code in color_rows
        ],
        materials=[FacetOptionOut(name=name.capitalize(), count=count) for name, count in material_rows],
        sizes=sorted(
            (FacetOptionOut(name=name, count=count) for name, count in size_rows),
            key=lambda option: _size_sort_key(option.name),
        ),
        price_range=PriceRangeOut(min=price_min or 0, max=price_max or 0),
    )


async def liked_ids(db: AsyncSession, user: User | None, product_ids: list[int]) -> set[int]:
    if not user or not product_ids:
        return set()
    rows = await db.execute(
        select(ProductLike.product_id).where(
            ProductLike.user_id == user.id, ProductLike.product_id.in_(product_ids)
        )
    )
    return set(rows.scalars())


async def mark_liked(db: AsyncSession, cards: list[ProductCardOut], user: User | None) -> None:
    """В кэше лежит ответ без лайков, личный флаг дописываем после."""
    liked = await liked_ids(db, user, [c.id for c in cards])
    for card in cards:
        card.is_liked_by_me = card.id in liked


async def _build_catalog(db: AsyncSession, f: ProductFilterParams, user_id: int | None) -> PaginatedProductsOut:
    category_ids = await resolve_category_ids(db, f.category)
    color_names = await resolve_colors(db, f.color)
    conditions = build_conditions(f, category_ids=category_ids, color_names=color_names, user_id=user_id)

    total = (await db.execute(select(func.count()).select_from(Product).where(*conditions))).scalar_one()
    products = (
        (
            await db.execute(
                select(Product)
                .where(*conditions)
                .options(*card_loader_options())
                .order_by(*order_clauses(f.sort))
                .offset((f.page - 1) * f.per_page)
                .limit(f.per_page)
            )
        )
        .scalars()
        .all()
    )
    return PaginatedProductsOut(
        total=total,
        page=f.page,
        per_page=f.per_page,
        total_pages=max(1, math.ceil(total / f.per_page)),
        items=[ProductCardOut.model_validate(p) for p in products],
        available_filters=await build_facets(
            db, f, category_ids=category_ids, color_names=color_names, user_id=user_id
        ),
    )


async def list_catalog(
    db: AsyncSession, cache: Cache, f: ProductFilterParams, user: User | None
) -> PaginatedProductsOut:
    if f.only_liked:
        if not user:
            raise UnauthorizedError("Войдите в аккаунт, чтобы просматривать избранное.")
        page = await _build_catalog(db, f, user.id)
    else:
        params = {k: v for k, v in vars(f).items() if k != "only_liked"}
        page = await cache.remember(
            "catalog", params, settings.CATALOG_CACHE_TTL, PaginatedProductsOut, lambda: _build_catalog(db, f, None)
        )
    await mark_liked(db, page.items, user)
    return page


async def _build_recommendations(
    db: AsyncSession, limit: int, season: SeasonRule, category_ids: set[int] | None
) -> RecommendationsOut:
    async def pick(extra: list[ColumnElement[bool]], order_by: list) -> list[ProductCardOut]:  # type: ignore[type-arg]
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
        return [ProductCardOut.model_validate(p) for p in (await db.execute(stmt)).scalars()]

    return RecommendationsOut(
        season=season.key,  # type: ignore[arg-type]
        season_label=season.label,
        popular=await pick([], [popularity_expr().desc()]),
        seasonal=await pick([seasonal_condition(season)], [popularity_expr().desc()]),
        new_arrivals=await pick([], [Product.first_seen.desc()]),
        on_sale=await pick([on_sale_condition()], [discount_percent_expr().desc(), popularity_expr().desc()]),
    )


async def recommendations(
    db: AsyncSession, cache: Cache, user: User | None, *, limit: int, category: str | None, season: str | None
) -> RecommendationsOut:
    rule = SEASON_RULES[season] if season else current_season()
    params = {"limit": limit, "category": category, "season": rule.key}

    async def build() -> RecommendationsOut:
        category_ids = await resolve_category_ids(db, [category] if category else [])
        return await _build_recommendations(db, limit, rule, category_ids)

    result = await cache.remember("catalog", params, settings.CATALOG_CACHE_TTL, RecommendationsOut, build)
    for section in (result.popular, result.seasonal, result.new_arrivals, result.on_sale):
        await mark_liked(db, section, user)
    return result


async def category_tree(db: AsyncSession, cache: Cache) -> list[CategoryTreeOut]:
    async def build() -> CategoryTreeList:
        categories = (await db.execute(select(Category).order_by(Category.id))).scalars().all()
        counts = dict(
            (
                await db.execute(
                    select(Product.category_id, func.count(Product.id))
                    .where(Product.status == "active", Product.category_id.is_not(None))
                    .group_by(Product.category_id)
                )
            ).all()
        )
        nodes = {
            c.id: CategoryTreeOut(
                id=c.id,
                source_id=c.source_id,
                slug=c.slug,
                name=c.name,
                url=c.url,
                parent_id=c.parent_id,
                products_count=counts.get(c.id, 0),
            )
            for c in categories
        }
        roots: list[CategoryTreeOut] = []
        for node in nodes.values():
            parent = nodes.get(node.parent_id) if node.parent_id else None
            if parent:
                parent.children.append(node)
            else:
                roots.append(node)

        def add_children(node: CategoryTreeOut) -> int:
            node.products_count += sum(add_children(child) for child in node.children)
            return node.products_count

        for root in roots:
            add_children(root)
        return CategoryTreeList(roots)

    tree = await cache.remember("catalog", {"view": "categories"}, settings.CATEGORIES_CACHE_TTL, CategoryTreeList, build)
    return tree.root


async def get_category(db: AsyncSession, slug: str) -> CategoryTreeOut:
    category = (await db.execute(select(Category).where(Category.slug == slug))).scalar_one_or_none()
    if not category:
        raise NotFoundError(f"Категория «{slug}» не найдена.")
    count = (
        await db.execute(
            select(func.count(Product.id)).where(Product.category_id == category.id, Product.status == "active")
        )
    ).scalar_one()
    return CategoryTreeOut(
        id=category.id,
        source_id=category.source_id,
        slug=category.slug,
        name=category.name,
        url=category.url,
        parent_id=category.parent_id,
        products_count=count,
    )


async def resolve_color_variants(db: AsyncSession, product: Product) -> list[SiblingColorVariantOut]:
    """Цвета одной модели: ссылки из этого товара, ссылки на него из других (связь могли записать
    только в одну сторону) и товары с тем же color_group. Показываем только активные."""
    linked_out = {link.sibling_slug for link in product.color_links}
    linked_in = (
        select(Product.slug)
        .join(ProductColorLink, ProductColorLink.product_id == Product.id)
        .where(ProductColorLink.sibling_slug == product.slug)
    )
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

    def variant(p: Product) -> SiblingColorVariantOut:
        return SiblingColorVariantOut(
            sibling_slug=p.slug,
            color=p.color,
            color_hex=p.color_hex or hex_for(p.color),
            in_catalog=True,
            preview_image=p.images[0].url if p.images else None,
            price=p.current_price,
        )

    ordered = sorted(siblings, key=lambda p: ((p.color or "").lower(), p.slug))
    return [variant(product), *map(variant, ordered)]


async def get_product_detail(
    db: AsyncSession, *, slug: str | None = None, product_id: int | None = None, viewer: User | None = None
) -> ProductDetailOut:
    """Черновики и архив видит только администратор."""
    stmt = (
        select(Product)
        .where(Product.slug == slug if slug is not None else Product.id == product_id)
        .options(
            selectinload(Product.category),
            selectinload(Product.images),
            selectinload(Product.sizes),
            selectinload(Product.materials),
            selectinload(Product.attributes),
            selectinload(Product.color_links),
            selectinload(Product.price_history),
        )
        .execution_options(populate_existing=True)
    )
    product = (await db.execute(stmt)).scalar_one_or_none()
    if not product or (product.status != "active" and not (viewer and viewer.is_admin)):
        raise NotFoundError("Товар не найден.")

    detail = ProductDetailOut.model_validate(product)
    detail.is_liked_by_me = bool(await liked_ids(db, viewer, [product.id]))
    detail.color_variants = await resolve_color_variants(db, product)
    detail.price_history = detail.price_history[:30]
    return detail