import hashlib
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.types import utc_now
from app.models import (
    Category,
    PriceHistory,
    Product,
    ProductColorLink,
    ProductImage,
    ProductMaterial,
    ProductSize,
    Source,
)
from app.services.colors import hex_for
from app.services.parser.parse import ParsedProduct

# Фото с чужого CDN считаем парсерными. Загруженные через админку лежат не в /media/
SOURCE_IMAGE_PREFIX = "https://cdn.ubcashmere.ru/media/"


async def ensure_source(db: AsyncSession) -> Source:
    source = (
        await db.execute(select(Source).where(Source.name == settings.PARSER_SOURCE_NAME))
    ).scalar_one_or_none()
    if source is None:
        source = Source(name=settings.PARSER_SOURCE_NAME, base_url=settings.PARSER_BASE_URL)
        db.add(source)
        await db.flush()
    return source


async def _category_id(db: AsyncSession, source_id: int, category: dict[str, str] | None) -> int | None:
    if not category:
        return None
    row = (
        await db.execute(
            select(Category).where(Category.source_id == source_id, Category.slug == category["slug"])
        )
    ).scalar_one_or_none()
    if row is None:
        row = Category(source_id=source_id, slug=category["slug"], name=category["name"], url=category["url"])
        db.add(row)
        await db.flush()
    return row.id


def _content_hash(p: ParsedProduct) -> str:
    keys = ("name", "brand", "article", "color", "composition", "sizes", "images", "care_text", "measurements")
    content = {k: p[k] for k in keys}  # type: ignore[literal-required]
    return hashlib.sha1(json.dumps(content, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


async def save_product(db: AsyncSession, source_id: int, p: ParsedProduct) -> Product:
    """Upsert карточки. Commit на вызывающем.
    Остатки и размеры не пересоздаём: на них ссылаются заказы. Статус и атрибуты, которые правил админ, не трогаем."""
    now = utc_now()
    product = (
        await db.execute(
            select(Product)
            .where(Product.source_id == source_id, Product.slug == p["slug"])
            .options(
                selectinload(Product.sizes),
                selectinload(Product.images),
                selectinload(Product.materials),
                selectinload(Product.color_links),
            )
        )
    ).scalar_one_or_none()

    is_new = product is None
    if product is None:
        # Товар без цены не должен продаваться за ноль, поэтому уходит в черновик
        product = Product(
            source_id=source_id,
            slug=p["slug"],
            first_seen=now,
            current_price=p["price"] or 0,
            old_price=p["old_price"],
            status="active" if p["price"] else "draft",
            sizes=[],
            images=[],
            materials=[],
            color_links=[],
        )
        db.add(product)

    product.url = p["url"]
    product.name = p["name"]
    product.category_id = await _category_id(db, source_id, p["category"])
    product.color_group = min([p["slug"], *p["color_links"]])
    product.content_hash = _content_hash(p)
    product.raw_json = json.loads(json.dumps(p, ensure_ascii=False, default=str))
    product.last_seen = now
    if is_new or product.color != p["color"]:
        product.color_hex = hex_for(p["color"])
    product.color = p["color"]
    # Раздел, который сайт не отдал, считаем неизвестным и не затираем прежнее значение
    for field in ("brand", "article", "composition", "care_text", "measurements", "description"):
        if p[field] is not None:  # type: ignore[literal-required]
            setattr(product, field, p[field])  # type: ignore[literal-required]
    await db.flush()

    price, old_price = p["price"], p["old_price"]
    if price is not None and (is_new or (price, old_price) != (product.current_price, product.old_price)):
        product.current_price, product.old_price = price, old_price
        db.add(PriceHistory(product_id=product.id, price=price, old_price=old_price, currency=p["currency"]))

    _sync_sizes(db, product, p)
    _sync_images(db, product, p["images"])
    _sync_materials(db, product, p["materials"])
    _sync_color_links(db, product, p["color_links"])
    await db.flush()
    return product


def _sync_sizes(db: AsyncSession, product: Product, p: ParsedProduct) -> None:
    """Сайт отдаёт только «есть или нет», штуки неизвестны. Новому размеру ставим PARSER_DEFAULT_STOCK."""
    if not p["sizes"]:
        return
    existing = {s.size: s for s in product.sizes}
    for name in p["sizes"]:
        available = p["sizes_stock"].get(name)
        row = existing.get(name)
        if row is None:
            db.add(
                ProductSize(
                    product_id=product.id,
                    size=name,
                    stock=0 if available == 0 else settings.PARSER_DEFAULT_STOCK,
                    sku=product.sku_for(name),
                )
            )
        elif available == 0:
            row.stock = 0
        elif available == 1 and row.stock == 0:
            row.stock = settings.PARSER_DEFAULT_STOCK
    for name, row in existing.items():
        if name not in p["sizes"]:
            row.stock = 0


def _sync_images(db: AsyncSession, product: Product, parsed: list[str]) -> None:
    if not parsed:
        return
    ordered = sorted(product.images, key=lambda i: i.position)
    ours = [i for i in ordered if i.url.startswith(SOURCE_IMAGE_PREFIX)]
    if [i.url for i in ours] == parsed:
        return
    for image in ours:
        product.images.remove(image)
    for position, url in enumerate(parsed):
        db.add(ProductImage(product_id=product.id, position=position, url=url))
    for offset, image in enumerate(i for i in ordered if not i.url.startswith(SOURCE_IMAGE_PREFIX)):
        image.position = len(parsed) + offset


def _sync_materials(db: AsyncSession, product: Product, parsed: list[tuple[str, float]]) -> None:
    if not parsed or {(m.material, m.percent) for m in product.materials} == set(parsed):
        return
    for material in list(product.materials):
        product.materials.remove(material)
    for name, percent in parsed:
        db.add(ProductMaterial(product_id=product.id, material=name, percent=percent))


def _sync_color_links(db: AsyncSession, product: Product, parsed: list[str]) -> None:
    if not parsed:
        return
    current = {link.sibling_slug: link for link in product.color_links}
    for slug, link in current.items():
        if slug not in parsed:
            product.color_links.remove(link)
    for slug in parsed:
        if slug not in current:
            db.add(ProductColorLink(product_id=product.id, sibling_slug=slug))
