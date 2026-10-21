from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.cache import Cache
from app.core.config import settings
from app.core.errors import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    TooLargeError,
    UnprocessableError,
    UnsupportedMediaError,
)
from app.core.logging import get_logger
from app.models import (
    Category,
    PriceHistory,
    Product,
    ProductAttribute,
    ProductColorLink,
    ProductImage,
    ProductMaterial,
    ProductSize,
    Source,
    User,
)
from app.schemas.catalog import ImageReorderIn, ProductCreateIn, ProductDetailOut, ProductUpdateIn
from app.services import catalog
from app.services.colors import hex_for
from app.services.s3 import S3StorageService

logger = get_logger(__name__)

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
NOT_NULL_FIELDS = {"name", "brand", "current_price", "status"}


async def _ensure_category(db: AsyncSession, category_id: int | None) -> None:
    if category_id is not None and await db.get(Category, category_id) is None:
        raise UnprocessableError(f"Категория id={category_id} не найдена.")


async def _default_source_id(db: AsyncSession) -> int:
    source_id = (await db.execute(select(Source.id).order_by(Source.id).limit(1))).scalar_one_or_none()
    if source_id is not None:
        return source_id
    source = Source(name="manual", base_url="")
    db.add(source)
    await db.flush()
    return source.id


async def create_product(db: AsyncSession, cache: Cache, admin: User, payload: ProductCreateIn) -> ProductDetailOut:
    if (await db.execute(select(Product.id).where(Product.slug == payload.slug))).first():
        raise ConflictError(f"Товар со slug «{payload.slug}» уже существует.")
    await _ensure_category(db, payload.category_id)

    product = Product(
        source_id=await _default_source_id(db),
        slug=payload.slug,
        name=payload.name,
        article=payload.article,
        brand=payload.brand,
        category_id=payload.category_id,
        color=payload.color,
        color_hex=payload.color_hex or hex_for(payload.color),
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
    await db.flush()  # autoflush выключен, id нужен для дочерних строк

    db.add(PriceHistory(product_id=product.id, price=payload.current_price, old_price=payload.old_price))
    for position, url in enumerate(payload.image_urls):
        db.add(ProductImage(product_id=product.id, position=position, url=url))
    for size_name, stock in payload.sizes_stock.items():
        db.add(ProductSize(product_id=product.id, size=size_name, stock=stock, sku=product.sku_for(size_name)))
    for m in payload.materials:
        db.add(ProductMaterial(product_id=product.id, material=m.material, percent=m.percent))
    for sibling in dict.fromkeys(s for s in payload.sibling_slugs if s != payload.slug):
        db.add(ProductColorLink(product_id=product.id, sibling_slug=sibling))
    for key, value in payload.attributes.items():
        db.add(ProductAttribute(product_id=product.id, attr_key=key, attr_value=value))

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError(f"Товар со slug «{payload.slug}» уже существует.") from None

    await cache.bump("catalog")
    logger.info("Товар создан", extra={"admin_id": admin.id, "product_id": product.id})
    return await catalog.get_product_detail(db, product_id=product.id, viewer=admin)


async def update_product(
    db: AsyncSession, cache: Cache, admin: User, product_id: int, payload: ProductUpdateIn
) -> ProductDetailOut:
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
        raise NotFoundError("Товар не найден.")

    provided = payload.model_fields_set
    collections = {"sizes_stock", "materials", "sibling_slugs", "attributes"}
    scalars = provided - collections

    for field in scalars & NOT_NULL_FIELDS:
        if getattr(payload, field) is None:
            raise UnprocessableError(f"Поле «{field}» нельзя очистить.")
    if "category_id" in provided:
        await _ensure_category(db, payload.category_id)

    new_price = payload.current_price if "current_price" in provided else product.current_price
    new_old = payload.old_price if "old_price" in provided else product.old_price
    if new_old is not None and new_old <= new_price:
        raise UnprocessableError(
            "Старая цена должна быть больше текущей. Чтобы убрать скидку, передайте old_price: null."
        )
    price_changed = (new_price, new_old) != (product.current_price, product.old_price)

    for field in scalars:
        setattr(product, field, getattr(payload, field))
    if "color" in provided and "color_hex" not in provided and payload.color:
        product.color_hex = hex_for(payload.color, product.color_hex)
    if price_changed:
        db.add(PriceHistory(product_id=product.id, price=new_price, old_price=new_old))

    if payload.sizes_stock is not None:
        existing = {size.size.upper(): size for size in product.sizes}
        for size_name, stock in payload.sizes_stock.items():
            if size_name in existing:
                existing[size_name].stock = stock
            else:
                product.sizes.append(ProductSize(size=size_name, stock=stock, sku=product.sku_for(size_name)))

    if payload.materials is not None:
        product.materials = [ProductMaterial(material=m.material, percent=m.percent) for m in payload.materials]
    if payload.attributes is not None:
        product.attributes = [ProductAttribute(attr_key=k, attr_value=v) for k, v in payload.attributes.items()]
    if payload.sibling_slugs is not None:
        wanted = {slug for slug in payload.sibling_slugs if slug != product.slug}
        current = {link.sibling_slug: link for link in product.color_links}
        for slug, link in current.items():
            if slug not in wanted:
                product.color_links.remove(link)
        for slug in wanted - current.keys():
            product.color_links.append(ProductColorLink(sibling_slug=slug))

    await db.commit()
    await cache.bump("catalog")
    logger.info("Товар изменён", extra={"admin_id": admin.id, "product_id": product_id, "fields": sorted(provided)})
    return await catalog.get_product_detail(db, product_id=product_id, viewer=admin)


def _check_image_head(upload: UploadFile, head: bytes) -> None:
    """Content-Type присылает клиент, поэтому смотрим ещё и на первые байты."""
    is_jpeg = head.startswith(b"\xff\xd8\xff")
    is_png = head.startswith(b"\x89PNG\r\n\x1a\n")
    is_webp = head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if not (is_jpeg or is_png or is_webp):
        raise UnsupportedMediaError(f"Файл «{upload.filename}» не является изображением JPEG, PNG или WebP.")


async def add_images(
    db: AsyncSession,
    cache: Cache,
    s3: S3StorageService,
    admin: User,
    product_id: int,
    uploads: list[UploadFile],
) -> list[ProductImage]:
    """Сначала проверяются все файлы и только потом грузится первый, чтобы не оставить половину."""
    product = await db.get(Product, product_id)
    if not product:
        raise NotFoundError("Товар не найден.")

    uploads = [u for u in uploads if u.filename]  # пустое поле формы приходит файлом без имени
    if not uploads:
        raise UnprocessableError("Передайте хотя бы один файл в поле file или files.")
    if len(uploads) > settings.MAX_FILES_PER_REQUEST:
        raise BadRequestError(f"За один запрос можно загрузить не больше {settings.MAX_FILES_PER_REQUEST} файлов.")

    max_bytes = settings.MAX_IMAGE_MB * 1024 * 1024
    for upload in uploads:
        if upload.content_type not in ALLOWED_IMAGE_TYPES:
            raise UnsupportedMediaError(f"Файл «{upload.filename}»: допустимы JPEG, PNG и WebP.")
        if upload.size is not None and upload.size > max_bytes:
            raise TooLargeError(f"Файл «{upload.filename}» больше {settings.MAX_IMAGE_MB} МБ.")
        head = await upload.read(12)
        await upload.seek(0)
        _check_image_head(upload, head)

    max_position, count = (
        await db.execute(
            select(func.max(ProductImage.position), func.count(ProductImage.id)).where(
                ProductImage.product_id == product_id
            )
        )
    ).one()
    if count + len(uploads) > settings.MAX_IMAGES_PER_PRODUCT:
        raise BadRequestError(
            f"У товара не может быть больше {settings.MAX_IMAGES_PER_PRODUCT} фото, сейчас {count}."
        )

    start = 0 if max_position is None else max_position + 1
    created: list[ProductImage] = []
    for offset, upload in enumerate(uploads):
        url = await s3.upload_product_image(upload, product.slug)
        image = ProductImage(product_id=product_id, position=start + offset, url=url)
        db.add(image)
        created.append(image)
    await db.commit()
    await cache.bump("catalog")
    logger.info("Фото добавлены", extra={"admin_id": admin.id, "product_id": product_id, "count": len(created)})
    return created


async def reorder_images(
    db: AsyncSession, cache: Cache, product_id: int, payload: ImageReorderIn
) -> list[ProductImage]:
    images = list(
        (await db.execute(select(ProductImage).where(ProductImage.product_id == product_id))).scalars()
    )
    if not images:
        raise NotFoundError("У товара нет фото.")
    if sorted(payload.image_ids) != sorted(i.id for i in images):
        raise UnprocessableError("Список должен содержать id всех фото этого товара без повторов и чужих id.")

    by_id = {i.id: i for i in images}
    for position, image_id in enumerate(payload.image_ids):
        by_id[image_id].position = position
    await db.commit()
    await cache.bump("catalog")
    return [by_id[i] for i in payload.image_ids]


async def delete_image(db: AsyncSession, cache: Cache, product_id: int, image_id: int) -> None:
    """Файл в хранилище остаётся, из карточки он пропадает, позиции остальных сдвигаются."""
    images = list(
        (
            await db.execute(
                select(ProductImage).where(ProductImage.product_id == product_id).order_by(ProductImage.position)
            )
        ).scalars()
    )
    target = next((i for i in images if i.id == image_id), None)
    if not target:
        raise NotFoundError("Фото не найдено.")

    await db.delete(target)
    for position, image in enumerate(i for i in images if i.id != image_id):
        image.position = position
    await db.commit()
    await cache.bump("catalog")
