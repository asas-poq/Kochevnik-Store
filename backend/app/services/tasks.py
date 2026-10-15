"""
Модуль асинхронных фоновых задач (`app/services/tasks.py`).
Позволяет выполнять тяжелые или сетевые операции (пересчет рейтинга товара,
импорт дампа парсера, отправка уведомлений в Telegram) в фоне через `BackgroundTasks`,
чтобы клиент получал ответ от API за считанные миллисекунды.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from sqlalchemy import func, select

from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.models.catalog import (
    Category,
    CrawlQueue,
    PriceHistory,
    Product,
    ProductAttribute,
    ProductColorLink,
    ProductImage,
    ProductMaterial,
    ProductSize,
    Source,
)
from app.models.interactions import ProductLike, ProductReview

logger = get_logger(__name__)

# Карта красивых HEX-оттенков для монгольского трикотажа и кожи (для UI кружочков выбора цвета)
COLOR_HEX_MAP: Dict[str, str] = {
    "Голубой": "#A5C4D4",
    "Молочный": "#FAF8F5",
    "Капучино": "#C2A894",
    "Серый": "#9E9E9E",
    "Тёмно-коричневый": "#4A3525",
    "Темно-коричневый": "#4A3525",
    "Белый": "#FFFFFF",
    "Бежевый": "#E3D3C1",
    "Коричневый": "#6E4F3A",
    "Черный": "#2C2623",
    "Бордовый": "#6E2631",
    "Фиолетовый": "#6C5B7B",
    "Оранжевый": "#D97B43",
    "Малиновый": "#A8385D",
    "Синий": "#34568B",
}


async def recalculate_product_stats_task(product_id: int) -> None:
    """
    Фоновая задача: пересчитывает денормализованные счетчики товара
    (`likes_count`, `reviews_count`, `rating_avg`) в таблице `products`.
    Вызывается автоматически после каждого лайка или нового отзыва.
    """
    logger.info(f"[BackgroundTask] Пересчет статистики для товара ID={product_id}...")
    async with AsyncSessionLocal() as db:
        try:
            # Считаем количество лайков
            likes_q = await db.execute(
                select(func.count(ProductLike.id)).where(
                    ProductLike.product_id == product_id
                )
            )
            likes_count = likes_q.scalar() or 0

            # Считаем количество одобренных отзывов и средний рейтинг
            reviews_q = await db.execute(
                select(
                    func.count(ProductReview.id),
                    func.avg(ProductReview.rating),
                ).where(
                    ProductReview.product_id == product_id,
                    ProductReview.is_approved.is_(True),
                )
            )
            reviews_count, rating_avg = reviews_q.one()
            reviews_count = reviews_count or 0
            rating_avg = round(float(rating_avg or 0.0), 2)

            # Обновляем запись товара
            product = await db.get(Product, product_id)
            if product:
                product.likes_count = likes_count
                product.reviews_count = reviews_count
                product.rating_avg = rating_avg
                await db.commit()
                logger.info(
                    f"[BackgroundTask] Статистика товара ID={product_id} обновлена: "
                    f"лайков={likes_count}, отзывов={reviews_count}, рейтинг={rating_avg}"
                )
        except Exception as exc:
            logger.error(
                f"[BackgroundTask] Ошибка пересчета статистики товара ID={product_id}: {exc}"
            )
            await db.rollback()


def _parse_iso_datetime(val: Any) -> datetime:
    """Вспомогательная функция парсинга ISO-даты из JSON парсера."""
    if isinstance(val, datetime):
        return val
    if isinstance(val, str) and val:
        try:
            return datetime.fromisoformat(val)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


async def import_parser_dump_task(json_path: str) -> Dict[str, int]:
    """
    Асинхронная задача полного импорта/синхронизации JSON-дампа парсера в БД.
    Безопасно загружает (идемпотентно — без дублей):
    - `sources`
    - `categories`
    - `crawl_queue`
    - `products` (включая подстановку актуальной цены из `price_history` или `raw_json`)
    - `price_history`
    - `product_images`
    - `product_materials`
    - `product_color_links`
    - `product_sizes` (автоматически создает стандартную размерную сетку S, M, L или ONE SIZE, если в парсере список размеров пуст)
    """
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"Файл дампа парсера не найден: {json_path}")

    logger.info(f"Начинаем импорт данных парсера из файла: {json_path}")
    data = json.loads(path.read_text(encoding="utf-8"))

    stats = {
        "sources": 0,
        "categories": 0,
        "crawl_queue": 0,
        "products": 0,
        "images": 0,
        "materials": 0,
        "color_links": 0,
        "price_history": 0,
        "sizes_generated": 0,
    }

    async with AsyncSessionLocal() as db:
        # 1. Источники (`sources`)
        for src in data.get("sources", []):
            existing = await db.get(Source, src["id"])
            if not existing:
                db.add(
                    Source(
                        id=src["id"],
                        name=src["name"],
                        base_url=src["base_url"],
                    )
                )
                stats["sources"] += 1
        await db.flush()

        # 2. Категории (`categories`)
        for cat in data.get("categories", []):
            existing = await db.get(Category, cat["id"])
            if not existing:
                db.add(
                    Category(
                        id=cat["id"],
                        source_id=cat.get("source_id", 1),
                        slug=cat["slug"],
                        name=cat["name"],
                        url=cat.get("url"),
                        parent_id=cat.get("parent_id"),
                    )
                )
                stats["categories"] += 1
        await db.flush()

        # Индексируем цены из `price_history` по `product_id` для быстрого заполнения `current_price`
        price_map: Dict[int, Dict[str, Any]] = {}
        for ph in data.get("price_history", []):
            price_map[ph["product_id"]] = ph

        # 3. Товары (`products`)
        for prod in data.get("products", []):
            pid = prod["id"]
            existing = await db.get(Product, pid)
            raw = prod.get("raw_json") or {}
            ph_entry = price_map.get(pid, {})

            current_price = ph_entry.get("price") or raw.get("price") or 14200
            old_price = ph_entry.get("old_price") or raw.get("old_price")
            currency = ph_entry.get("currency") or raw.get("currency") or "RUB"
            color_name = prod.get("color")
            color_hex = COLOR_HEX_MAP.get(color_name or "", "#D8CFC4")

            # Формируем деликатные рекомендации по уходу и обмеры, если парсер вернул null
            care_default = (
                prod.get("care_text")
                or "Деликатная ручная стирка при 30°C специальным шампунем для кашемира и пуха яка. "
                "Не выкручивать. Сушить горизонтально вдали от прямых солнечных лучей."
            )
            description_default = (
                prod.get("description")
                or f"Премиальное изделие «{prod['name']}» от монгольского бренда {prod.get('brand', 'Ulaanbaatar')}. "
                f"Выполнено из натурального сырья ({prod.get('composition', '100% кашемир')}), отличается исключительной мягкостью, "
                f"терморегуляцией и долговечностью."
            )

            if not existing:
                new_product = Product(
                    id=pid,
                    source_id=prod.get("source_id", 1),
                    slug=prod["slug"],
                    url=prod.get("url"),
                    article=prod.get("article"),
                    name=prod["name"],
                    brand=prod.get("brand", "Ulaanbaatar"),
                    category_id=prod.get("category_id"),
                    color=color_name,
                    color_hex=color_hex,
                    color_group=prod.get("color_group"),
                    composition=prod.get("composition"),
                    density_yarn="2-ply (26/2 Nm) премиальная монгольская нить",
                    care_text=care_default,
                    measurements=prod.get("measurements"),
                    description=description_default,
                    current_price=current_price,
                    old_price=old_price,
                    currency=currency,
                    status=prod.get("status", "active"),
                    first_seen=_parse_iso_datetime(prod.get("first_seen")),
                    last_seen=_parse_iso_datetime(prod.get("last_seen")),
                    content_hash=prod.get("content_hash"),
                    raw_json=raw,
                )
                db.add(new_product)
                stats["products"] += 1
        await db.flush()

        # 4. История цен (`price_history`)
        for ph in data.get("price_history", []):
            existing = await db.get(PriceHistory, ph["id"])
            if not existing:
                db.add(
                    PriceHistory(
                        id=ph["id"],
                        product_id=ph["product_id"],
                        price=ph["price"],
                        old_price=ph.get("old_price"),
                        currency=ph.get("currency", "RUB"),
                        scraped_at=_parse_iso_datetime(ph.get("scraped_at")),
                    )
                )
                stats["price_history"] += 1

        # 5. Фотографии (`product_images`)
        for img in data.get("product_images", []):
            existing = await db.get(ProductImage, img["id"])
            if not existing:
                db.add(
                    ProductImage(
                        id=img["id"],
                        product_id=img["product_id"],
                        position=img.get("position", 0),
                        url=img["url"],
                    )
                )
                stats["images"] += 1

        # 6. Материалы (`product_materials`)
        existing_mats = (await db.execute(select(ProductMaterial))).scalars().all()
        existing_mat_keys = {(m.product_id, m.material) for m in existing_mats}
        for mat in data.get("product_materials", []):
            key = (mat["product_id"], mat["material"])
            if key not in existing_mat_keys:
                db.add(
                    ProductMaterial(
                        product_id=mat["product_id"],
                        material=mat["material"],
                        percent=float(mat.get("percent", 100.0)),
                    )
                )
                existing_mat_keys.add(key)
                stats["materials"] += 1

        # 7. Связи соседних цветов (`product_color_links`)
        existing_links = (await db.execute(select(ProductColorLink))).scalars().all()
        existing_link_keys = {(l.product_id, l.sibling_slug) for l in existing_links}
        for link in data.get("product_color_links", []):
            key = (link["product_id"], link["sibling_slug"])
            if key not in existing_link_keys:
                db.add(
                    ProductColorLink(
                        product_id=link["product_id"],
                        sibling_slug=link["sibling_slug"],
                    )
                )
                existing_link_keys.add(key)
                stats["color_links"] += 1

        # 8. Размеры и складские остатки (`product_sizes`)
        # Если в дампе парсера `product_sizes` пустой, создаем реалистичные размеры:
        # для пуловеров/одежды — S, M, L; для сумок, шапок и палантинов — ONE SIZE + S/M.
        existing_sizes = (await db.execute(select(ProductSize))).scalars().all()
        existing_size_keys = {(s.product_id, s.size) for s in existing_sizes}

        for ps in data.get("product_sizes", []):
            key = (ps["product_id"], ps["size"])
            if key not in existing_size_keys:
                db.add(
                    ProductSize(
                        product_id=ps["product_id"],
                        size=ps["size"],
                        stock=ps.get("stock", 5),
                    )
                )
                existing_size_keys.add(key)
                stats["sizes_generated"] += 1

        all_products = (await db.execute(select(Product))).scalars().all()
        for prod in all_products:
            has_sizes = any(pid == prod.id for (pid, _) in existing_size_keys)
            if not has_sizes:
                name_lower = prod.name.lower()
                if any(w in name_lower for w in ["пуловер", "джемпер", "кардиган", "свитер", "водолазка", "платье", "брюки", "жилет"]):
                    default_sizes = [
                        ("S (42-44)", 4, "Длина 62 см, ОГ 104 см, Рукав 58 см"),
                        ("M (46-48)", 6, "Длина 64 см, ОГ 110 см, Рукав 60 см"),
                        ("L (48-50)", 3, "Длина 66 см, ОГ 116 см, Рукав 61 см"),
                    ]
                else:
                    default_sizes = [
                        ("ONE SIZE", 8, "Единый универсальный размер"),
                    ]
                for sz_label, stock_qty, meas in default_sizes:
                    db.add(
                        ProductSize(
                            product_id=prod.id,
                            size=sz_label,
                            stock=stock_qty,
                            sku=f"UB-{prod.article or prod.id}-{sz_label.split()[0]}",
                            measurements_cm=meas,
                        )
                    )
                    stats["sizes_generated"] += 1

        # 9. Очередь обхода парсера (`crawl_queue`)
        existing_urls = set(
            (await db.execute(select(CrawlQueue.url))).scalars().all()
        )
        for item in data.get("crawl_queue", []):
            if item["url"] not in existing_urls:
                db.add(
                    CrawlQueue(
                        source_id=item.get("source_id", 1),
                        url=item["url"],
                        status=item.get("status", "pending"),
                        error=item.get("error"),
                        updated_at=_parse_iso_datetime(item.get("updated_at")),
                    )
                )
                existing_urls.add(item["url"])
                stats["crawl_queue"] += 1

        await db.commit()
        logger.info(f"Импорт данных парсера успешно завершен: {stats}")
        return stats
