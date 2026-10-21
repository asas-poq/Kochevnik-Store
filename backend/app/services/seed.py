import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import get_logger
from app.core.security import get_password_hash
from app.db.session import AsyncSessionLocal
from app.db.types import utc_now
from app.models import (
    Category,
    CrawlQueue,
    PriceHistory,
    Product,
    ProductColorLink,
    ProductImage,
    ProductLike,
    ProductMaterial,
    ProductReview,
    ProductSize,
    Source,
    User,
)
from app.services.colors import hex_for
from app.services.interactions import recalculate_stats

logger = get_logger(__name__)

CLOTHES = ("пуловер", "джемпер", "кардиган", "свитер", "водолазка", "платье", "брюки", "жилет")
DEFAULT_CARE = (
    "Деликатная ручная стирка при 30°C специальным шампунем для кашемира и пуха яка. "
    "Не выкручивать. Сушить горизонтально вдали от прямых солнечных лучей."
)
DEFAULT_YARN = "2-ply (26/2 Nm) премиальная монгольская нить"


def _when(value: Any) -> datetime:
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return utc_now()


async def import_parser_dump(
    path: Path, session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal
) -> dict[str, int]:
    """Идемпотентный импорт parsed_dump.json. Записи с уже существующим id пропускаются.
    Если в дампе нет размеров, для товара создаётся стандартная сетка."""
    data = json.loads(path.read_text(encoding="utf-8"))
    stats = dict.fromkeys(
        ("sources", "categories", "products", "price_history", "images", "materials", "color_links", "sizes", "crawl_queue"), 0
    )

    async with session_factory() as db:
        async def known(model: Any) -> set[int]:
            return set((await db.execute(select(model.id))).scalars())

        have = await known(Source)
        for row in data.get("sources", []):
            if row["id"] not in have:
                db.add(Source(id=row["id"], name=row["name"], base_url=row["base_url"]))
                stats["sources"] += 1
        await db.flush()

        have = await known(Category)
        for row in data.get("categories", []):
            if row["id"] not in have:
                db.add(
                    Category(
                        id=row["id"], source_id=row.get("source_id", 1), slug=row["slug"], name=row["name"],
                        url=row.get("url"), parent_id=row.get("parent_id"),
                    )
                )
                stats["categories"] += 1
        await db.flush()

        last_price = {ph["product_id"]: ph for ph in data.get("price_history", [])}
        have = await known(Product)
        for row in data.get("products", []):
            if row["id"] in have:
                continue
            raw = row.get("raw_json") or {}
            price_row = last_price.get(row["id"], {})
            price = price_row.get("price") or raw.get("price")
            brand = row.get("brand", "Ulaanbaatar")
            db.add(
                Product(
                    id=row["id"], source_id=row.get("source_id", 1), slug=row["slug"], url=row.get("url"),
                    article=row.get("article"), name=row["name"], brand=brand,
                    category_id=row.get("category_id"), color=row.get("color"),
                    color_hex=hex_for(row.get("color")), color_group=row.get("color_group"),
                    composition=row.get("composition"), density_yarn=DEFAULT_YARN,
                    care_text=row.get("care_text") or DEFAULT_CARE, measurements=row.get("measurements"),
                    description=row.get("description")
                    or f"Изделие «{row['name']}» от монгольского бренда {brand}. "
                    f"Состав: {row.get('composition') or '100% кашемир'}.",
                    current_price=price or 0,
                    old_price=price_row.get("old_price") or raw.get("old_price"),
                    currency=price_row.get("currency") or raw.get("currency") or "RUB",
                    status=row.get("status", "active") if price else "draft",
                    first_seen=_when(row.get("first_seen")), last_seen=_when(row.get("last_seen")),
                    content_hash=row.get("content_hash"), raw_json=raw,
                )
            )
            stats["products"] += 1
        await db.flush()

        have = await known(PriceHistory)
        for row in data.get("price_history", []):
            if row["id"] not in have:
                db.add(
                    PriceHistory(
                        id=row["id"], product_id=row["product_id"], price=row["price"],
                        old_price=row.get("old_price"), currency=row.get("currency", "RUB"),
                        scraped_at=_when(row.get("scraped_at")),
                    )
                )
                stats["price_history"] += 1

        have = await known(ProductImage)
        for row in data.get("product_images", []):
            if row["id"] not in have:
                db.add(ProductImage(id=row["id"], product_id=row["product_id"], position=row.get("position", 0), url=row["url"]))
                stats["images"] += 1

        pairs = set((await db.execute(select(ProductMaterial.product_id, ProductMaterial.material))).all())
        for row in data.get("product_materials", []):
            key = (row["product_id"], row["material"])
            if key not in pairs:
                db.add(ProductMaterial(product_id=key[0], material=key[1], percent=float(row.get("percent", 100.0))))
                pairs.add(key)
                stats["materials"] += 1

        pairs = set((await db.execute(select(ProductColorLink.product_id, ProductColorLink.sibling_slug))).all())
        for row in data.get("product_color_links", []):
            key = (row["product_id"], row["sibling_slug"])
            if key not in pairs:
                db.add(ProductColorLink(product_id=key[0], sibling_slug=key[1]))
                pairs.add(key)
                stats["color_links"] += 1
        await db.flush()

        sized = set((await db.execute(select(ProductSize.product_id, ProductSize.size))).all())
        for row in data.get("product_sizes", []):
            key = (row["product_id"], row["size"])
            if key not in sized:
                db.add(ProductSize(product_id=key[0], size=key[1], stock=row.get("stock", 5)))
                sized.add(key)
                stats["sizes"] += 1
        with_sizes = {pid for pid, _ in sized}
        for product in (await db.execute(select(Product))).scalars():
            if product.id in with_sizes:
                continue
            if any(word in product.name.lower() for word in CLOTHES):
                grid = [
                    ("S (42-44)", 4, "Длина 62 см, ОГ 104 см, Рукав 58 см"),
                    ("M (46-48)", 6, "Длина 64 см, ОГ 110 см, Рукав 60 см"),
                    ("L (48-50)", 3, "Длина 66 см, ОГ 116 см, Рукав 61 см"),
                ]
            else:
                grid = [("ONE SIZE", 8, "Единый размер")]
            for label, stock, measurements in grid:
                db.add(
                    ProductSize(
                        product_id=product.id, size=label, stock=stock,
                        sku=product.sku_for(label.split()[0]), measurements_cm=measurements,
                    )
                )
                stats["sizes"] += 1

        urls = set((await db.execute(select(CrawlQueue.url))).scalars())
        for row in data.get("crawl_queue", []):
            if row["url"] not in urls:
                db.add(
                    CrawlQueue(
                        source_id=row.get("source_id", 1), url=row["url"], status=row.get("status", "pending"),
                        error=row.get("error"), updated_at=_when(row.get("updated_at")),
                    )
                )
                urls.add(row["url"])
                stats["crawl_queue"] += 1

        await db.commit()
    logger.info("Дамп парсера импортирован", extra=stats)
    return stats


async def seed_demo_users(session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal) -> None:
    """Администратор, покупатель и пара лайков и отзывов, чтобы ручки можно было пройти в Swagger."""
    async with session_factory() as db:
        admin = (await db.execute(select(User).where(User.email == "admin@ubcashmere.ru"))).scalar_one_or_none()
        if not admin:
            db.add(
                User(
                    email="admin@ubcashmere.ru", phone="+79990000001", full_name="Администратор Ulaanbaatar",
                    hashed_password=get_password_hash("Admin123!"), role="admin", default_city="Москва",
                    default_delivery_address="Шоурум Ulaanbaatar, Москва",
                )
            )
        customer = (await db.execute(select(User).where(User.email == "anna@example.com"))).scalar_one_or_none()
        if not customer:
            customer = User(
                email="anna@example.com", phone="+79991112233", full_name="Анна Морозова",
                hashed_password=get_password_hash("Customer123!"), role="customer", default_city="Москва",
                default_delivery_address="ПВЗ СДЭК MSK142, ул. Тверская, д. 12",
            )
            db.add(customer)
        await db.flush()

        if (await db.execute(select(ProductReview.id).limit(1))).first():
            await db.commit()
            return
        existing = set((await db.execute(select(Product.id).where(Product.id.in_((1, 2, 4))))).scalars())
        for product_id in existing:
            db.add(ProductLike(user_id=customer.id, product_id=product_id))
        if 1 in existing:
            db.add(
                ProductReview(
                    product_id=1, user_id=customer.id, rating=5, is_verified_purchase=True,
                    comment_text="Очень лёгкий палантин, при этом хорошо греет. Кашемир настоящий.",
                    advantages="Тонкая ажурная вязка, благородный оттенок", disadvantages="Нет",
                    admin_reply="Спасибо за отзыв, носите с удовольствием.",
                )
            )
        if 2 in existing:
            db.add(
                ProductReview(
                    product_id=2, user_id=customer.id, rating=5, is_verified_purchase=True,
                    comment_text="Пуловер сел идеально, после стирки стал ещё мягче.",
                    advantages="Мягкость, посадка", disadvantages="Не обнаружено",
                )
            )
        await db.flush()
        for product_id in existing:
            await recalculate_stats(db, product_id)
        await db.commit()
