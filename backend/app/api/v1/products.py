"""
Роутер каталога товаров (`app/api/v1/products.py`).
Реализует:
1. Умную фильтрацию, поиск, сортировку и пагинацию каталога (`GET /api/v1/products`)
2. Детальную карточку товара со связанными цветами из `product_color_links` (`GET /api/v1/products/{slug}`)
3. Создание и обновление товаров администратором (`POST /api/v1/products`)
4. Загрузку фото в S3/MinIO с привязкой к товару (`POST /api/v1/products/{product_id}/images`)
"""

import math
from typing import Dict, List, Set
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import (
    AdminUserDep,
    DBSessionDep,
    OptionalUserDep,
    ProductFilterDep,
)
from app.core.logging import get_logger
from app.models.catalog import (
    Category,
    PriceHistory,
    Product,
    ProductColorLink,
    ProductImage,
    ProductMaterial,
    ProductSize,
)
from app.models.interactions import ProductLike
from app.schemas.catalog import (
    PaginatedProductsOut,
    ProductCardOut,
    ProductCreateUpdateIn,
    ProductDetailOut,
    ProductImageOut,
    SiblingColorVariantOut,
)
from app.services.s3 import S3StorageService, get_s3_service
from app.services.tasks import COLOR_HEX_MAP

logger = get_logger(__name__)

router = APIRouter(prefix="/products", tags=["3. Каталог и Карточка товара"])


# ==============================================================================
# РУЧКА 1: Получение каталога товаров с фильтрацией, сортировкой и пагинацией
# ==============================================================================
@router.get(
    "",
    response_model=PaginatedProductsOut,
    summary="Каталог товаров с фильтрацией (GET /api/v1/products)",
)
async def list_products(
    filters: ProductFilterDep,
    db: DBSessionDep,
    current_user: OptionalUserDep,
) -> PaginatedProductsOut:
    """
    Главная ручка витрины каталога (`GET /api/v1/products`).
    Поддерживает все фильтры из вашего плана и данных парсера через зависимость `Depends(ProductFilterParams)`:
    - `category` — slug категории (например, трикотаж из кашемира/пуха яка или кожаные сумки)
    - `material` — фильтр по волокну из таблицы `product_materials` (`кашемир`, `пух яка`, `кожа`, `верблюжья шерсть`)
    - `color` — фильтр по цвету (`Бежевый`, `Молочный`, `Капучино`, `Серый`, `Голубой` и др.)
    - `size` — фильтр по размеру в наличии из таблицы `product_sizes` (`S`, `M`, `L`, `ONE SIZE`)
    - `min_price`, `max_price` — диапазон цены в рублях
    - `search` — поиск по названию, артикулу или составу
    - `only_liked` — показать только товары, лайкнутые текущим пользователем
    - `sort` — `price_asc`, `price_desc`, `newest`, `popular`, `rating_desc`

    Также возвращает объект `available_filters` с доступными цветами, материалами, размерами
    и минимальной/максимальной ценой для построения боковой панели фильтров на React-фронтенде.
    """
    logger.info(
        f"Запрос каталога: category={filters.category}, material={filters.material}, "
        f"color={filters.color}, size={filters.size}, sort={filters.sort}, page={filters.page}"
    )

    # Базовый запрос активных товаров с жадной подгрузкой (selectinload) фото, размеров и материалов
    stmt = (
        select(Product)
        .where(Product.status == "active")
        .options(
            selectinload(Product.images),
            selectinload(Product.sizes),
            selectinload(Product.materials),
        )
    )

    # 1. Фильтр по slug категории
    if filters.category:
        stmt = stmt.join(Category, Product.category_id == Category.id).where(
            Category.slug == filters.category
        )

    # 2. Фильтр по материалу (таблица product_materials)
    if filters.material:
        stmt = stmt.join(
            ProductMaterial, Product.id == ProductMaterial.product_id
        ).where(func.lower(ProductMaterial.material) == filters.material.lower())

    # 3. Фильтр по цвету
    if filters.color:
        stmt = stmt.where(func.lower(Product.color) == filters.color.lower())

    # 4. Фильтр по размеру и наличию на складе
    if filters.size:
        stmt = stmt.join(ProductSize, Product.id == ProductSize.product_id).where(
            ProductSize.size.ilike(f"{filters.size}%"),
            ProductSize.stock > 0,
        )
    elif filters.only_in_stock:
        stmt = stmt.join(ProductSize, Product.id == ProductSize.product_id).where(
            ProductSize.stock > 0
        )

    # 5. Фильтр по диапазону цены
    if filters.min_price is not None:
        stmt = stmt.where(Product.current_price >= filters.min_price)
    if filters.max_price is not None:
        stmt = stmt.where(Product.current_price <= filters.max_price)

    # 6. Текстовый поиск по названию, артикулу или составу
    if filters.search:
        q = f"%{filters.search.strip()}%"
        stmt = stmt.where(
            or_(
                Product.name.ilike(q),
                Product.article.ilike(q),
                Product.composition.ilike(q),
            )
        )

    # 7. Фильтр «Только мои лайки (Избранное)»
    if filters.only_liked:
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Войдите в аккаунт, чтобы просматривать список избранных товаров.",
            )
        stmt = stmt.join(ProductLike, Product.id == ProductLike.product_id).where(
            ProductLike.user_id == current_user.id
        )

    # Убираем возможные дубликаты строк после JOIN
    stmt = stmt.distinct()

    # Считаем общее количество подходящих товаров до пагинации
    count_subq = stmt.with_only_columns(Product.id).subquery()
    total_q = await db.execute(select(func.count()).select_from(count_subq))
    total = total_q.scalar() or 0

    # 8. Применяем сортировку
    if filters.sort == "price_asc":
        stmt = stmt.order_by(Product.current_price.asc(), Product.id.asc())
    elif filters.sort == "price_desc":
        stmt = stmt.order_by(Product.current_price.desc(), Product.id.asc())
    elif filters.sort == "newest":
        stmt = stmt.order_by(Product.first_seen.desc(), Product.id.desc())
    elif filters.sort == "rating_desc":
        stmt = stmt.order_by(Product.rating_avg.desc(), Product.reviews_count.desc())
    else:  # popular
        stmt = stmt.order_by(Product.likes_count.desc(), Product.id.asc())

    # 9. Пагинация (OFFSET / LIMIT)
    offset = (filters.page - 1) * filters.per_page
    stmt = stmt.offset(offset).limit(filters.per_page)

    products = (await db.execute(stmt)).scalars().all()

    # Если пользователь авторизован, определяем, каким товарам из выдачи он уже поставил лайк
    liked_ids: Set[int] = set()
    if current_user and products:
        prod_ids = [p.id for p in products]
        likes_res = await db.execute(
            select(ProductLike.product_id).where(
                ProductLike.user_id == current_user.id,
                ProductLike.product_id.in_(prod_ids),
            )
        )
        liked_ids = set(likes_res.scalars().all())

    items_out: List[ProductCardOut] = []
    for p in products:
        card = ProductCardOut.model_validate(p)
        card.is_liked_by_me = p.id in liked_ids
        items_out.append(card)

    # Собираем фасеты доступных фильтров для боковой панели каталога
    colors_res = await db.execute(
        select(Product.color)
        .where(Product.status == "active", Product.color.is_not(None))
        .distinct()
    )
    available_colors = sorted([c for c in colors_res.scalars().all() if c])

    materials_res = await db.execute(
        select(ProductMaterial.material).distinct()
    )
    available_materials = sorted([m for m in materials_res.scalars().all() if m])

    sizes_res = await db.execute(
        select(ProductSize.size).where(ProductSize.stock > 0).distinct()
    )
    available_sizes = sorted([s for s in sizes_res.scalars().all() if s])

    price_bounds = await db.execute(
        select(func.min(Product.current_price), func.max(Product.current_price)).where(
            Product.status == "active"
        )
    )
    min_p, max_p = price_bounds.one()

    total_pages = max(1, math.ceil(total / filters.per_page))
    return PaginatedProductsOut(
        total=total,
        page=filters.page,
        per_page=filters.per_page,
        total_pages=total_pages,
        items=items_out,
        available_filters={
            "colors": [
                {"name": c, "hex": COLOR_HEX_MAP.get(c, "#D8CFC4")}
                for c in available_colors
            ],
            "materials": available_materials,
            "sizes": available_sizes,
            "price_range": {"min": min_p or 0, "max": max_p or 0},
        },
    )


# ==============================================================================
# РУЧКА 2: Детальная карточка товара по его slug (GET /api/v1/products/{slug})
# ==============================================================================
@router.get(
    "/{slug}",
    response_model=ProductDetailOut,
    summary="Детальная карточка товара со всеми цветами, фото и размерами (GET /api/v1/products/{slug})",
)
async def get_product_detail(
    slug: str,
    db: DBSessionDep,
    current_user: OptionalUserDep,
) -> ProductDetailOut:
    """
    Возвращает полную информацию о товаре по его `slug` для страницы Карточки товара:
    - Все фотографии в правильном порядке `position`
    - Доступные размеры и остатки на складе (`sizes`)
    - Состав (`materials`), плотность/нить, уход и обмеры
    - Историю изменения цены из парсера (`price_history`)
    - **Перелинковку цветов (`color_variants`)**: берет все связанные `sibling_slug` из таблицы
      `product_color_links` (а также товары с тем же `article` или `color_group`),
      находит их цвета, HEX-коды и главные фото, чтобы на фронтенде отрисовать кружочки переключения цветов!
    """
    logger.info(f"Запрос детальной карточки товара: slug='{slug}'")

    stmt = (
        select(Product)
        .where(Product.slug == slug)
        .options(
            selectinload(Product.category),
            selectinload(Product.images),
            selectinload(Product.sizes),
            selectinload(Product.materials),
            selectinload(Product.attributes),
            selectinload(Product.color_links),
            selectinload(Product.price_history),
        )
    )
    result = await db.execute(stmt)
    product = result.scalar_one_or_none()

    if not product:
        logger.warning(f"Товар со slug='{slug}' не найден в БД")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Товар со slug '{slug}' не найден.",
        )

    # Проверяем, лайкнул ли текущий пользователь этот товар
    is_liked = False
    if current_user:
        like_q = await db.execute(
            select(ProductLike.id).where(
                ProductLike.user_id == current_user.id,
                ProductLike.product_id == product.id,
            )
        )
        is_liked = like_q.scalar_one_or_none() is not None

    # Формируем список кружочков переключения цвета (`color_variants`)
    sibling_slugs = [link.sibling_slug for link in product.color_links]
    siblings_by_slug: Dict[str, Product] = {}

    if sibling_slugs:
        sib_stmt = (
            select(Product)
            .where(Product.slug.in_(sibling_slugs))
            .options(selectinload(Product.images))
        )
        sib_products = (await db.execute(sib_stmt)).scalars().all()
        siblings_by_slug = {sp.slug: sp for sp in sib_products}

    # Первым в список вариантов всегда добавляем текущий цвет товара
    color_variants: List[SiblingColorVariantOut] = [
        SiblingColorVariantOut(
            sibling_slug=product.slug,
            color=product.color,
            color_hex=product.color_hex or COLOR_HEX_MAP.get(product.color or "", "#D8CFC4"),
            in_catalog=True,
            preview_image=product.images[0].url if product.images else None,
            price=product.current_price,
        )
    ]

    for s_slug in sibling_slugs:
        if s_slug == product.slug:
            continue
        matched = siblings_by_slug.get(s_slug)
        if matched:
            color_variants.append(
                SiblingColorVariantOut(
                    sibling_slug=matched.slug,
                    color=matched.color,
                    color_hex=matched.color_hex
                    or COLOR_HEX_MAP.get(matched.color or "", "#D8CFC4"),
                    in_catalog=True,
                    preview_image=matched.images[0].url if matched.images else None,
                    price=matched.current_price,
                )
            )
        else:
            # Если связанный цвет еще находится в очереди парсинга `crawl_queue`
            color_variants.append(
                SiblingColorVariantOut(
                    sibling_slug=s_slug,
                    color=s_slug.split("-")[0].capitalize(),
                    color_hex="#D8CFC4",
                    in_catalog=False,
                    preview_image=None,
                    price=None,
                )
            )

    detail_out = ProductDetailOut.model_validate(product)
    detail_out.is_liked_by_me = is_liked
    detail_out.color_variants = color_variants
    return detail_out


# ==============================================================================
# РУЧКА 3: Создание или обновление товара (для Администратора)
# ==============================================================================
@router.post(
    "",
    response_model=ProductDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать новый товар в каталоге (только для Администратора)",
)
async def create_product(
    payload: ProductCreateUpdateIn,
    db: DBSessionDep,
    admin_user: AdminUserDep,
) -> ProductDetailOut:
    """
    Позволяет администратору магазина добавить новый свитер, кардиган или сумку через API,
    автоматически создавая записи в `products`, `product_images`, `product_sizes`,
    `product_materials`, `product_color_links` и `price_history`.
    """
    logger.info(
        f"Администратор ID={admin_user.id} создает новый товар: slug={payload.slug}"
    )

    existing = (
        await db.execute(select(Product).where(Product.slug == payload.slug))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Товар со slug '{payload.slug}' уже существует.",
        )

    product = Product(
        source_id=1,
        slug=payload.slug,
        name=payload.name,
        article=payload.article,
        brand=payload.brand,
        category_id=payload.category_id,
        color=payload.color,
        color_hex=payload.color_hex or COLOR_HEX_MAP.get(payload.color or "", "#D8CFC4"),
        color_group=payload.color_group or payload.slug,
        composition=payload.composition,
        density_yarn=payload.density_yarn,
        care_text=payload.care_text,
        measurements=payload.measurements,
        description=payload.description,
        current_price=payload.current_price,
        old_price=payload.old_price,
        status="active",
    )
    db.add(product)
    await db.flush()

    # Сохраняем историю цены
    db.add(
        PriceHistory(
            product_id=product.id,
            price=payload.current_price,
            old_price=payload.old_price,
            currency="RUB",
        )
    )

    # Сохраняем фотографии
    for idx, url in enumerate(payload.image_urls):
        db.add(ProductImage(product_id=product.id, position=idx, url=url))

    # Сохраняем размеры и остатки на складе
    for size_name, stock_qty in payload.sizes_stock.items():
        db.add(
            ProductSize(
                product_id=product.id,
                size=size_name,
                stock=stock_qty,
                sku=f"UB-{product.article or product.id}-{size_name}",
            )
        )

    # Сохраняем материалы
    for mat in payload.materials:
        db.add(
            ProductMaterial(
                product_id=product.id,
                material=mat.material,
                percent=mat.percent,
            )
        )

    # Сохраняем связанные цвета
    for sib in payload.sibling_slugs:
        db.add(ProductColorLink(product_id=product.id, sibling_slug=sib))

    await db.commit()
    return await get_product_detail(slug=product.slug, db=db, current_user=admin_user)


# ==============================================================================
# РУЧКА 4: Загрузка фото товара в облачное S3-хранилище (MinIO)
# ==============================================================================
@router.post(
    "/{product_id}/images",
    response_model=ProductImageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить фотографию товара в S3/MinIO и привязать к карточке",
)
async def upload_product_photo(
    product_id: int,
    db: DBSessionDep,
    admin_user: AdminUserDep,
    file: UploadFile = File(..., description="Файл изображения (.webp, .jpg, .png)"),
    s3: S3StorageService = Depends(get_s3_service),
) -> ProductImageOut:
    """
    Принимает файл фотографии от администратора, отправляет его в S3-бакет (или MinIO)
    и сохраняет прямую ссылку `url` в таблицу `product_images`.
    """
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден."
        )

    image_url = await s3.upload_product_image(file=file, product_slug=product.slug)

    # Вычисляем следующую позицию в галерее
    max_pos_q = await db.execute(
        select(func.max(ProductImage.position)).where(
            ProductImage.product_id == product_id
        )
    )
    max_pos = max_pos_q.scalar()
    next_position = 0 if max_pos is None else max_pos + 1

    new_img = ProductImage(
        product_id=product_id, position=next_position, url=image_url
    )
    db.add(new_img)
    await db.commit()
    await db.refresh(new_img)

    logger.info(
        f"Администратор ID={admin_user.id} добавил фото к товару ID={product_id}: {image_url}"
    )
    return ProductImageOut.model_validate(new_img)
