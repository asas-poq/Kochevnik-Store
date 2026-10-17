"""
Роутер каталога товаров (`app/api/v1/products.py`).

Публичные ручки (покупатель):
- GET  /products                  — рекомендации: хиты, сезонная подборка, новинки, скидки
- GET  /products/catalog          — каталог: фильтры, поиск, сортировка, пагинация, фасеты
- GET  /products/{slug}           — карточка товара: фото, размеры, остатки, переключатель цветов

Админские ручки:
- POST   /products                          — создать карточку (один цвет = одна карточка)
- PATCH  /products/{id}                     — частично изменить цену, остатки, описание, статус
- POST   /products/{id}/images              — загрузить одно или несколько фото
- PUT    /products/{id}/images/order        — задать порядок фото (первое — главное)
- DELETE /products/{id}/images/{image_id}   — удалить фото

Вся бизнес-логика (фильтры, популярность, сезоны) вынесена в `app/services/catalog.py`.
"""

import math
from typing import List, Literal, Optional, Set

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
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
    ProductAttribute,
    ProductColorLink,
    ProductImage,
    ProductMaterial,
    ProductSize,
    Source,
)
from app.models.interactions import ProductLike
from app.models.user import User
from app.schemas.catalog import (
    ImageReorderIn,
    PaginatedProductsOut,
    ProductCardOut,
    ProductCreateIn,
    ProductDetailOut,
    ProductImageOut,
    ProductUpdateIn,
    RecommendationsOut,
)
from app.services import catalog as catalog_service
from app.services.s3 import S3StorageService, get_s3_service
from app.services.tasks import COLOR_HEX_MAP

logger = get_logger(__name__)

router = APIRouter(prefix="/products", tags=["3. Каталог и Карточка товара"])

# --- Ограничения загрузки фото ---
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_FILES_PER_REQUEST = 10
MAX_IMAGES_PER_PRODUCT = 20


# ==============================================================================
# Вспомогательные функции
# ==============================================================================
def _sku(product: Product, size: str) -> str:
    return f"UB-{product.article or product.id}-{size.replace(' ', '')}"


async def _liked_ids(db: DBSessionDep, user: Optional[User], product_ids: List[int]) -> Set[int]:
    if not user or not product_ids:
        return set()
    rows = await db.execute(
        select(ProductLike.product_id).where(
            ProductLike.user_id == user.id, ProductLike.product_id.in_(product_ids)
        )
    )
    return set(rows.scalars().all())


async def _to_cards(db: DBSessionDep, products: List[Product], user: Optional[User]) -> List[ProductCardOut]:
    liked = await _liked_ids(db, user, [p.id for p in products])
    cards: List[ProductCardOut] = []
    for product in products:
        card = ProductCardOut.model_validate(product)
        card.is_liked_by_me = product.id in liked
        cards.append(card)
    return cards


async def _load_detail(
    db: DBSessionDep,
    *,
    slug: Optional[str] = None,
    product_id: Optional[int] = None,
    viewer: Optional[User] = None,
) -> ProductDetailOut:
    """Собирает полную карточку. Черновики и архив видит только администратор."""
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

    is_admin = bool(viewer and viewer.is_admin)
    if not product or (product.status != "active" and not is_admin):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Товар не найден.")

    detail = ProductDetailOut.model_validate(product)
    detail.is_liked_by_me = bool(await _liked_ids(db, viewer, [product.id]))
    detail.color_variants = await catalog_service.resolve_color_variants(db, product)
    detail.price_history = detail.price_history[:30]  # последние 30 записей, остальное фронту не нужно
    return detail


async def _ensure_category(db: DBSessionDep, category_id: Optional[int]) -> None:
    if category_id is not None and await db.get(Category, category_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Категория id={category_id} не найдена.")


async def _default_source_id(db: DBSessionDep) -> int:
    """Источник для товаров, созданных вручную: первый существующий или новый служебный."""
    source_id = (await db.execute(select(Source.id).order_by(Source.id).limit(1))).scalar_one_or_none()
    if source_id is not None:
        return source_id
    source = Source(name="manual", base_url="")
    db.add(source)
    await db.flush()
    return source.id


def _validate_image(upload: UploadFile) -> None:
    if upload.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Файл «{upload.filename}»: допустимы только JPEG, PNG и WebP.",
        )
    if upload.size is not None and upload.size > MAX_IMAGE_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Файл «{upload.filename}» больше {MAX_IMAGE_BYTES // (1024 * 1024)} МБ.",
        )


async def _check_image_signature(upload: UploadFile) -> None:
    """Content-Type присылает клиент и его легко подделать — проверяем первые байты файла."""
    head = await upload.read(12)
    await upload.seek(0)
    is_jpeg = head.startswith(b"\xff\xd8\xff")
    is_png = head.startswith(b"\x89PNG\r\n\x1a\n")
    is_webp = head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if not (is_jpeg or is_png or is_webp):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Файл «{upload.filename}» не является изображением JPEG, PNG или WebP.",
        )


# ==============================================================================
# РУЧКА 1: Рекомендации (GET /api/v1/products)
# ==============================================================================
@router.get(
    "",
    response_model=RecommendationsOut,
    summary="Рекомендации: хиты, сезонное, новинки, скидки",
)
async def get_recommendations(
    db: DBSessionDep,
    current_user: OptionalUserDep,
    limit: int = Query(8, ge=1, le=24, description="Сколько товаров в каждой секции"),
    category: Optional[str] = Query(None, description="Ограничить подборки категорией (slug, с подкатегориями)"),
    season: Optional[Literal["winter", "spring", "summer", "autumn"]] = Query(
        None, description="Принудительно выбрать сезон. По умолчанию определяется по текущему месяцу"
    ),
) -> RecommendationsOut:
    """
    Витрина главной страницы. Секции:
    - `popular` — хиты: продажи за 90 дней, лайки, отзывы и оценки;
    - `seasonal` — подборка под сезон: по характеристике товара «Сезон» или по ключевым словам
      в названии и составе (пух яка и верблюжья шерсть зимой, лёгкий кашемир и сумки весной и т.д.);
    - `new_arrivals` — новинки;
    - `on_sale` — товары со скидкой, сначала с самой большой.
    Показываются только активные товары, которые есть в наличии.
    """
    season_rule = catalog_service.SEASON_RULES[season] if season else catalog_service.current_season()
    category_ids = await catalog_service.resolve_category_ids(db, [category] if category else [])

    sections = await catalog_service.build_recommendations(
        db, limit=limit, season=season_rule, category_ids=category_ids
    )
    return RecommendationsOut(
        season=season_rule.key,  # type: ignore[arg-type]
        season_label=season_rule.label,
        popular=await _to_cards(db, sections["popular"], current_user),
        seasonal=await _to_cards(db, sections["seasonal"], current_user),
        new_arrivals=await _to_cards(db, sections["new_arrivals"], current_user),
        on_sale=await _to_cards(db, sections["on_sale"], current_user),
    )


# ==============================================================================
# РУЧКА 2: Каталог с фильтрами (GET /api/v1/products/catalog)
# ==============================================================================
@router.get(
    "/catalog",
    response_model=PaginatedProductsOut,
    summary="Каталог: фильтры, поиск, сортировка, пагинация",
)
async def list_catalog(
    filters: ProductFilterDep,
    db: DBSessionDep,
    current_user: OptionalUserDep,
) -> PaginatedProductsOut:
    """
    Правила фильтрации:
    - значения внутри одного фильтра — ИЛИ (`color=Серый&color=Бежевый`), разные фильтры — И;
    - `category` включает все вложенные подкатегории;
    - `size` и `only_in_stock` учитывают только размеры с остатком больше нуля;
    - в выдаче только активные товары.

    В `available_filters` приходят цвета, материалы и размеры со счётчиками ПОД ТЕКУЩУЮ ВЫБОРКУ:
    выбрали «кашемир» — цвета и размеры пересчитались только по кашемиру.
    """
    if filters.only_liked and not current_user:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Войдите в аккаунт, чтобы просматривать избранное.",
        )
    user_id = current_user.id if current_user else None

    category_ids = await catalog_service.resolve_category_ids(db, filters.category)
    conditions = catalog_service.build_conditions(filters, category_ids=category_ids, user_id=user_id)

    total = (await db.execute(select(func.count()).select_from(Product).where(*conditions))).scalar_one()

    stmt = (
        select(Product)
        .where(*conditions)
        .options(*catalog_service.card_loader_options())
        .order_by(*catalog_service.order_clauses(filters.sort))
        .offset((filters.page - 1) * filters.per_page)
        .limit(filters.per_page)
    )
    products = list((await db.execute(stmt)).scalars().all())

    facets = await catalog_service.build_facets(db, filters, category_ids=category_ids, user_id=user_id)

    logger.info(
        f"Каталог: найдено={total}, страница={filters.page}, sort={filters.sort}, "
        f"category={filters.category}, color={filters.color}, material={filters.material}, size={filters.size}"
    )
    return PaginatedProductsOut(
        total=total,
        page=filters.page,
        per_page=filters.per_page,
        total_pages=max(1, math.ceil(total / filters.per_page)),
        items=await _to_cards(db, products, current_user),
        available_filters=facets,
    )


# ==============================================================================
# РУЧКА 3: Карточка товара (GET /api/v1/products/{slug})
# ==============================================================================
@router.get(
    "/{slug}",
    response_model=ProductDetailOut,
    summary="Карточка товара: фото, размеры, остатки, цвета",
)
async def get_product_detail(
    slug: str,
    db: DBSessionDep,
    current_user: OptionalUserDep,
) -> ProductDetailOut:
    """
    Полная карточка. `color_variants` — все цвета этой модели (текущий цвет первым):
    для каждого есть slug, HEX, фото и цена, чтобы нарисовать кружки переключения.
    Скрытые товары (`draft`, `archived`) отдаются только администратору.
    """
    return await _load_detail(db, slug=slug, viewer=current_user)


# ==============================================================================
# РУЧКА 4: Создание товара (администратор)
# ==============================================================================
@router.post(
    "",
    response_model=ProductDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать карточку товара (один цвет = одна карточка)",
)
async def create_product(
    payload: ProductCreateIn,
    db: DBSessionDep,
    admin_user: AdminUserDep,
) -> ProductDetailOut:
    """
    Создаёт товар вместе с размерами и остатками, составом, характеристиками, ссылками на другие
    цвета, историей цены и фото по готовым ссылкам (`image_urls`). Файлы фото загружаются
    отдельно: `POST /products/{id}/images`.

    Товар в двух цветах — это ДВЕ карточки с одинаковым `color_group` (у каждой свои slug,
    фото и остатки). Переключатель цветов на сайте соберётся сам.
    """
    if (await db.execute(select(Product.id).where(Product.slug == payload.slug))).first():
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"Товар со slug «{payload.slug}» уже существует.")
    await _ensure_category(db, payload.category_id)

    color_name = payload.color or ""
    product = Product(
        source_id=await _default_source_id(db),
        slug=payload.slug,
        name=payload.name,
        article=payload.article,
        brand=payload.brand,
        category_id=payload.category_id,
        color=payload.color,
        color_hex=payload.color_hex or COLOR_HEX_MAP.get(color_name, catalog_service.DEFAULT_COLOR_HEX),
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
    await db.flush()  # получаем product.id (autoflush в проекте выключен)

    db.add(PriceHistory(product_id=product.id, price=payload.current_price, old_price=payload.old_price))
    for position, url in enumerate(payload.image_urls):
        db.add(ProductImage(product_id=product.id, position=position, url=url))
    for size_name, stock in payload.sizes_stock.items():
        db.add(ProductSize(product_id=product.id, size=size_name, stock=stock, sku=_sku(product, size_name)))
    for material in payload.materials:
        db.add(ProductMaterial(product_id=product.id, material=material.material, percent=material.percent))
    for sibling in dict.fromkeys(s for s in payload.sibling_slugs if s != payload.slug):
        db.add(ProductColorLink(product_id=product.id, sibling_slug=sibling))
    for key, value in payload.attributes.items():
        db.add(ProductAttribute(product_id=product.id, attr_key=key, attr_value=value))

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"Товар со slug «{payload.slug}» уже существует.")

    logger.info(f"Администратор ID={admin_user.id} создал товар ID={product.id} slug={payload.slug}")
    return await _load_detail(db, product_id=product.id, viewer=admin_user)


# ==============================================================================
# РУЧКА 5: Изменение товара (администратор)
# ==============================================================================
@router.patch(
    "/{product_id}",
    response_model=ProductDetailOut,
    summary="Изменить товар: цену, остатки, описание, статус",
)
async def update_product(
    product_id: int,
    payload: ProductUpdateIn,
    db: DBSessionDep,
    admin_user: AdminUserDep,
) -> ProductDetailOut:
    """
    Меняются только переданные поля. Что важно знать:
    - смена `current_price` / `old_price` добавляет запись в историю цен;
    - `sizes_stock` — слияние: можно прислать только `{"M": 10}`; размер с остатком 0 остаётся в базе,
      потому что на него могут ссылаться старые заказы;
    - `materials`, `sibling_slugs`, `attributes` заменяются целиком;
    - `status`: `draft`/`archived` скрывают товар от покупателей, удалять товары не нужно.
    """
    product = (
        await db.execute(
            select(Product)
            .where(Product.id == product_id)
            .options(
                selectinload(Product.sizes),
                selectinload(Product.materials),
                selectinload(Product.color_links),
                selectinload(Product.attributes),
            )
        )
    ).scalar_one_or_none()
    if not product:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Товар не найден.")

    provided = payload.model_fields_set
    collections = {"sizes_stock", "materials", "sibling_slugs", "attributes"}
    required_columns = {"name", "brand", "current_price", "status"}

    for field in provided - collections:
        value = getattr(payload, field)
        if value is None and field in required_columns:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Поле «{field}» нельзя очистить.")

    if "category_id" in provided:
        await _ensure_category(db, payload.category_id)

    new_price = payload.current_price if "current_price" in provided else product.current_price
    new_old_price = payload.old_price if "old_price" in provided else product.old_price
    if new_old_price is not None and new_old_price <= new_price:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Старая цена должна быть больше текущей. Чтобы убрать скидку, передайте old_price: null.",
        )
    price_changed = (new_price, new_old_price) != (product.current_price, product.old_price)

    for field in provided - collections:
        setattr(product, field, getattr(payload, field))
    if "color" in provided and "color_hex" not in provided and payload.color:
        product.color_hex = COLOR_HEX_MAP.get(payload.color, product.color_hex)

    if price_changed:
        db.add(PriceHistory(product_id=product.id, price=new_price, old_price=new_old_price))

    if payload.sizes_stock is not None:
        existing = {size.size.upper(): size for size in product.sizes}
        for size_name, stock in payload.sizes_stock.items():
            if size_name in existing:
                existing[size_name].stock = stock
            else:
                product.sizes.append(ProductSize(size=size_name, stock=stock, sku=_sku(product, size_name)))

    if payload.materials is not None:
        product.materials = [ProductMaterial(material=m.material, percent=m.percent) for m in payload.materials]

    if payload.attributes is not None:
        product.attributes = [ProductAttribute(attr_key=k, attr_value=v) for k, v in payload.attributes.items()]

    if payload.sibling_slugs is not None:
        wanted = {slug for slug in payload.sibling_slugs if slug != product.slug}
        current = {link.sibling_slug: link for link in product.color_links}
        for slug, link in current.items():  # сначала удаляем лишние, чтобы не нарушить уникальность
            if slug not in wanted:
                product.color_links.remove(link)
        for slug in wanted - current.keys():
            product.color_links.append(ProductColorLink(sibling_slug=slug))

    await db.commit()
    logger.info(f"Администратор ID={admin_user.id} изменил товар ID={product_id}: {sorted(provided)}")
    return await _load_detail(db, product_id=product_id, viewer=admin_user)


# ==============================================================================
# РУЧКА 6: Загрузка фото (одно или несколько)
# ==============================================================================
@router.post(
    "/{product_id}/images",
    response_model=List[ProductImageOut],
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить одно или несколько фото товара",
)
async def upload_product_photos(
    product_id: int,
    db: DBSessionDep,
    admin_user: AdminUserDep,
    file: Optional[UploadFile] = File(
        None, description="Одно фото. Это поле удобно для проверки в Swagger (там есть кнопка выбора файла)"
    ),
    files: Optional[List[UploadFile]] = File(
        None,
        description=(
            "Несколько фото: поле `files` повторяется для каждого файла (FormData, curl, Postman). "
            "В Swagger UI для списка файлов нет кнопки выбора — используйте поле `file`"
        ),
    ),
    s3: S3StorageService = Depends(get_s3_service),
) -> List[ProductImageOut]:
    """
    Принимает `multipart/form-data`: одно фото в поле `file` и/или несколько в поле `files`.
    Фото добавляются в конец галереи в том порядке, в каком присланы.
    Если у товара ещё нет фото, первое загруженное станет главным (позиция 0).
    Проверяются тип, размер и реальное содержимое файла. Если хотя бы один файл не прошёл
    проверку, не сохраняется ни один.
    """
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Товар не найден.")

    # Пустые поля формы браузер присылает как файл без имени — их пропускаем
    uploads = [u for u in ([file] if file else []) + list(files or []) if u.filename]
    if not uploads:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Передайте хотя бы один файл в поле `file` или `files`.",
        )

    if len(uploads) > MAX_FILES_PER_REQUEST:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"За один запрос можно загрузить не больше {MAX_FILES_PER_REQUEST} файлов.",
        )
    for upload in uploads:  # сначала проверяем всё, и только потом грузим
        _validate_image(upload)
        await _check_image_signature(upload)

    max_position = (
        await db.execute(select(func.max(ProductImage.position)).where(ProductImage.product_id == product_id))
    ).scalar()
    images_count = (
        await db.execute(select(func.count(ProductImage.id)).where(ProductImage.product_id == product_id))
    ).scalar_one()
    if images_count + len(uploads) > MAX_IMAGES_PER_PRODUCT:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"У товара не может быть больше {MAX_IMAGES_PER_PRODUCT} фото (сейчас {images_count}).",
        )

    next_position = 0 if max_position is None else max_position + 1
    created: List[ProductImage] = []
    for offset, upload in enumerate(uploads):
        url = await s3.upload_product_image(file=upload, product_slug=product.slug)
        image = ProductImage(product_id=product_id, position=next_position + offset, url=url)
        db.add(image)
        created.append(image)

    await db.commit()
    logger.info(f"Администратор ID={admin_user.id} добавил {len(created)} фото к товару ID={product_id}")
    return [ProductImageOut.model_validate(image) for image in created]


# ==============================================================================
# РУЧКА 7: Порядок фото (главное фото — первое)
# ==============================================================================
@router.put(
    "/{product_id}/images/order",
    response_model=List[ProductImageOut],
    summary="Задать порядок фото (первое — главное)",
)
async def reorder_product_photos(
    product_id: int,
    payload: ImageReorderIn,
    db: DBSessionDep,
    admin_user: AdminUserDep,
) -> List[ProductImageOut]:
    """Нужно прислать id ВСЕХ фото товара в новом порядке. Чтобы сделать фото главным — поставьте его первым."""
    images = list(
        (await db.execute(select(ProductImage).where(ProductImage.product_id == product_id))).scalars().all()
    )
    if not images:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="У товара нет фото.")
    if sorted(payload.image_ids) != sorted(image.id for image in images):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Список должен содержать id всех фото этого товара, без повторов и чужих id.",
        )

    by_id = {image.id: image for image in images}
    for position, image_id in enumerate(payload.image_ids):
        by_id[image_id].position = position
    await db.commit()
    logger.info(f"Администратор ID={admin_user.id} изменил порядок фото товара ID={product_id}")
    return [ProductImageOut.model_validate(by_id[i]) for i in payload.image_ids]


# ==============================================================================
# РУЧКА 8: Удаление фото
# ==============================================================================
@router.delete(
    "/{product_id}/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить фото товара",
)
async def delete_product_photo(
    product_id: int,
    image_id: int,
    db: DBSessionDep,
    admin_user: AdminUserDep,
) -> None:
    """Убирает фото из карточки, остальные сдвигаются без «дырок» в порядке. Сам файл в хранилище не удаляется."""
    images = list(
        (
            await db.execute(
                select(ProductImage).where(ProductImage.product_id == product_id).order_by(ProductImage.position)
            )
        )
        .scalars()
        .all()
    )
    target = next((image for image in images if image.id == image_id), None)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Фото не найдено.")

    await db.delete(target)
    for position, image in enumerate(i for i in images if i.id != image_id):
        image.position = position
    await db.commit()
    logger.info(f"Администратор ID={admin_user.id} удалил фото ID={image_id} товара ID={product_id}")
