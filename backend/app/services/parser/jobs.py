import csv
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.db.types import utc_now
from app.models import CrawlQueue, Product
from app.services.parser.fetch import Fetcher
from app.services.parser.parse import (
    PRODUCT_RE,
    ParsedProduct,
    ensure_own_url,
    parse_product,
    with_slash,
)
from app.services.parser.store import ensure_source, save_product

logger = get_logger(__name__)

SessionFactory = async_sessionmaker[AsyncSession]


async def collect_sitemap_urls(fetcher: Fetcher, robots: Any) -> set[str]:
    urls: set[str] = set()
    pending = list(robots.site_maps() or []) or [settings.PARSER_BASE_URL + "/sitemap.xml"]
    seen: set[str] = set()
    while pending:
        sitemap = pending.pop()
        if sitemap in seen:
            continue
        seen.add(sitemap)
        xml = await fetcher.get(sitemap)
        if not xml:
            continue
        for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml):
            if loc.endswith(".xml") or loc.endswith(".xml.gz"):
                pending.append(loc)
            elif PRODUCT_RE.match(loc):
                urls.add(with_slash(loc))
    return urls


async def crawl_catalog(fetcher: Fetcher, robots: Any) -> set[str]:
    """Запасной путь, если sitemap пуст: обходим /catalog/ с ?page=N, пока появляются новые товары."""
    base = settings.PARSER_BASE_URL
    found: set[str] = set()
    todo, seen = [base + "/catalog/"], set()
    while todo:
        url = todo.pop()
        if url in seen or not robots.can_fetch(settings.PARSER_USER_AGENT, url):
            continue
        seen.add(url)
        html = await fetcher.get(url)
        if not html:
            continue
        new_products = 0
        for a in BeautifulSoup(html, "lxml").find_all("a", href=True):
            full = urljoin(url, a["href"]).split("#")[0].split("?")[0]
            if PRODUCT_RE.match(full):
                new_products += with_slash(full) not in found
                found.add(with_slash(full))
            elif urlparse(full).netloc == urlparse(base).netloc and "/catalog/" in full:
                todo.append(with_slash(full))
        if new_products and "?page=" not in url:
            todo.append(f"{url}?page=2")
        page = re.search(r"\?page=(\d+)", url)
        if page and new_products:
            todo.append(re.sub(r"\?page=\d+", f"?page={int(page.group(1)) + 1}", url))
    return found


async def run_discover(fetcher: Fetcher, session_factory: SessionFactory) -> dict[str, int]:
    robots = await fetcher.robots()
    urls = await collect_sitemap_urls(fetcher, robots)
    if not urls:
        logger.info("Sitemap пуст, обходим каталог")
        urls = await crawl_catalog(fetcher, robots)

    async with session_factory() as db:
        source = await ensure_source(db)
        known = set((await db.execute(select(CrawlQueue.url).where(CrawlQueue.source_id == source.id))).scalars())
        fresh = sorted(urls - known)
        db.add_all(CrawlQueue(source_id=source.id, url=url, status="pending") for url in fresh)
        await db.commit()
    logger.info("Поиск ссылок завершён", extra={"found": len(urls), "added": len(fresh)})
    return {"found": len(urls), "added": len(fresh)}


async def _mark(db: AsyncSession, source_id: int, url: str, status: str, error: str | None = None) -> None:
    await db.execute(
        update(CrawlQueue)
        .where(CrawlQueue.source_id == source_id, CrawlQueue.url == url)
        .values(status=status, error=error, updated_at=utc_now())
    )


async def run_scrape(
    fetcher: Fetcher, session_factory: SessionFactory, *, limit: int | None = None, retry_errors: bool = False
) -> dict[str, int]:
    """Каждый товар в своей транзакции вместе с отметкой done, один сбой не ломает обход."""
    robots = await fetcher.robots()
    statuses = ["pending", "error"] if retry_errors else ["pending"]
    async with session_factory() as db:
        source_id = (await ensure_source(db)).id
        await db.commit()
        urls = list(
            (
                await db.execute(
                    select(CrawlQueue.url)
                    .where(CrawlQueue.source_id == source_id, CrawlQueue.status.in_(statuses))
                    .order_by(CrawlQueue.id)
                )
            ).scalars()
        )
    if limit:
        urls = urls[:limit]

    ok = bad = 0
    for n, url in enumerate(urls, 1):
        outcome = "ok"
        try:
            if not robots.can_fetch(settings.PARSER_USER_AGENT, url):
                outcome = "robots.txt"
            else:
                html = await fetcher.get(url)
                parsed: ParsedProduct | None = parse_product(html, url) if html else None
                if not parsed or not parsed["name"]:
                    outcome = "нет страницы или заголовка"
                else:
                    async with session_factory() as db:
                        await save_product(db, source_id, parsed)
                        await _mark(db, source_id, url, "done")
                        await db.commit()
                    logger.info("Товар сохранён", extra={"n": n, "of": len(urls), "product": parsed["name"][:50], "price": parsed["price"]})
        except Exception as exc:
            logger.exception("Сбой на карточке", extra={"url": url})
            outcome = str(exc)[:500]

        if outcome == "ok":
            ok += 1
        else:
            bad += 1
            async with session_factory() as db:
                await _mark(db, source_id, url, "error", outcome)
                await db.commit()
    logger.info("Обход завершён", extra={"ok": ok, "errors": bad})
    return {"total": len(urls), "ok": ok, "errors": bad}


async def preview_product(url: str, save_html: bool = False) -> ParsedProduct | None:
    """Разбирает одну страницу, в БД ничего не пишет."""
    ensure_own_url(url)
    async with Fetcher() as fetcher:
        html = await fetcher.get(url)
    if not html:
        return None
    if save_html:
        out_dir = Path(settings.PARSER_DATA_DIR) / "debug"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / (urlparse(url).path.strip("/").replace("/", "_") + ".html")).write_text(html, encoding="utf-8")
    return parse_product(html, url)


async def run_named(name: str, params: dict[str, Any], session_factory: SessionFactory = AsyncSessionLocal) -> dict:
    async with Fetcher() as fetcher:
        if name == "discover":
            return await run_discover(fetcher, session_factory)
        if name == "scrape":
            return await run_scrape(fetcher, session_factory, **params)
    raise ValueError(f"Неизвестная задача парсера: {name}")


async def get_stats(session_factory: SessionFactory = AsyncSessionLocal) -> dict[str, Any]:
    async with session_factory() as db:
        async def one(sql: str) -> Any:
            return (await db.execute(text(sql))).scalar_one()

        queue = (await db.execute(select(CrawlQueue.status, func.count()).group_by(CrawlQueue.status))).all()
        return {
            "products": (await db.execute(select(func.count(Product.id)))).scalar_one(),
            "color_groups": await one("SELECT COUNT(DISTINCT color_group) FROM products"),
            "categories": await one("SELECT COUNT(*) FROM categories"),
            "without_price": await one(
                "SELECT COUNT(*) FROM products p WHERE NOT EXISTS (SELECT 1 FROM price_history h WHERE h.product_id = p.id)"
            ),
            "without_sizes": await one(
                "SELECT COUNT(*) FROM products p WHERE NOT EXISTS (SELECT 1 FROM product_sizes s WHERE s.product_id = p.id)"
            ),
            "without_images": await one(
                "SELECT COUNT(*) FROM products p WHERE NOT EXISTS (SELECT 1 FROM product_images i WHERE i.product_id = p.id)"
            ),
            "queue": {status: count for status, count in queue},
        }


EXPORTS = {
    "products": "SELECT p.*, c.name AS category FROM products p LEFT JOIN categories c ON c.id = p.category_id",
    "sizes": "SELECT p.slug, s.size, s.stock FROM product_sizes s JOIN products p ON p.id = s.product_id",
    "images": "SELECT p.slug, i.position, i.url FROM product_images i JOIN products p ON p.id = i.product_id",
    "prices": "SELECT p.slug, h.price, h.old_price, h.scraped_at FROM price_history h JOIN products p ON p.id = h.product_id",
}


async def run_export(session_factory: SessionFactory = AsyncSessionLocal) -> dict[str, int]:
    out_dir = Path(settings.PARSER_DATA_DIR) / "export"
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, int] = {}
    async with session_factory() as db:
        for name, sql in EXPORTS.items():
            result = await db.execute(text(sql))
            rows = result.fetchall()
            if not rows:
                continue
            with open(out_dir / f"{name}.csv", "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(result.keys())
                writer.writerows(tuple(r) for r in rows)
            written[f"{name}.csv"] = len(rows)
    return written