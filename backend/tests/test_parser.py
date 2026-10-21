from pathlib import Path
from urllib.robotparser import RobotFileParser

from sqlalchemy import select, update

from app.core.errors import ConflictError
from app.db.session import AsyncSessionLocal
from app.models import CrawlQueue, PriceHistory, Product, ProductSize, Source
from app.services.parser import jobs, state
from app.services.parser.parse import parse_materials, parse_product
from tests.conftest import FakeArq

HTML = (Path(__file__).parent / "fixtures" / "product.html").read_text(encoding="utf-8")
URL = "https://ubcashmere.ru/products/sviter-molochnyi/"


class FakeFetcher:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages

    async def get(self, url: str) -> str | None:
        return self.pages.get(url)

    async def robots(self) -> RobotFileParser:
        parser = RobotFileParser()
        parser.parse([])
        return parser


def test_parse_product_page():
    p = parse_product(HTML, URL)

    assert p is not None
    assert (p["slug"], p["name"], p["article"]) == ("sviter-molochnyi", "Свитер Ulaanbaatar", "UB-1001")
    assert (p["price"], p["old_price"]) == (14200, 18900)
    assert p["color"] == "Молочный"
    assert p["sizes"] == ["S", "M", "L"]
    assert p["sizes_stock"] == {"S": 1, "M": 1, "L": 0}
    assert p["color_links"] == ["sviter-kapuchino", "sviter-seryi"]
    assert p["materials"] == [("кашемир", 70.0), ("шёлк", 30.0)]
    assert p["category"]["slug"] == "sviteri"
    assert p["images"] == ["https://cdn.ubcashmere.ru/media/a.jpg", "https://cdn.ubcashmere.ru/media/b.jpg"]
    assert p["care_text"] == "Ручная стирка при 30 градусах"


def test_page_without_h1_is_not_a_product():
    assert parse_product("<html><body><p>404</p></body></html>", URL) is None


def test_materials_with_decimal_comma():
    assert parse_materials("99,5% кашемир") == [("кашемир", 99.5)]
    assert parse_materials(None) == []


async def queue_one(url: str = URL) -> None:
    async with AsyncSessionLocal() as db:
        source = Source(name="ubcashmere", base_url="https://ubcashmere.ru")
        db.add(source)
        await db.flush()
        db.add(CrawlQueue(source_id=source.id, url=url, status="pending"))
        await db.commit()


async def test_scrape_saves_product_with_prices_and_sizes():
    await queue_one()

    result = await jobs.run_scrape(FakeFetcher({URL: HTML}), AsyncSessionLocal)

    assert result == {"total": 1, "ok": 1, "errors": 0}
    async with AsyncSessionLocal() as db:
        product = (await db.execute(select(Product))).scalar_one()
        sizes = {s.size: s.stock for s in (await db.execute(select(ProductSize))).scalars()}
        history = (await db.execute(select(PriceHistory))).scalars().all()
        queue = (await db.execute(select(CrawlQueue))).scalar_one()
    assert (product.current_price, product.old_price, product.status) == (14200, 18900, "active")
    assert sizes == {"S": 5, "M": 5, "L": 0}
    assert len(history) == 1
    assert queue.status == "done"


async def test_rescrape_keeps_stock_variant_ids_and_admin_status():
    await queue_one()
    fetcher = FakeFetcher({URL: HTML})
    await jobs.run_scrape(fetcher, AsyncSessionLocal)
    async with AsyncSessionLocal() as db:
        size_s = (await db.execute(select(ProductSize).where(ProductSize.size == "S"))).scalar_one()
        size_id = size_s.id
        size_s.stock = 2
        await db.execute(update(Product).values(status="archived"))
        await db.execute(update(CrawlQueue).values(status="pending"))
        await db.commit()
    fetcher.pages[URL] = HTML.replace("14 200", "12 000")

    await jobs.run_scrape(fetcher, AsyncSessionLocal)

    async with AsyncSessionLocal() as db:
        product = (await db.execute(select(Product))).scalar_one()
        size_s = (await db.execute(select(ProductSize).where(ProductSize.size == "S"))).scalar_one()
        history = (await db.execute(select(PriceHistory))).scalars().all()
    assert (size_s.id, size_s.stock) == (size_id, 2)
    assert product.status == "archived"
    assert (product.current_price, len(history)) == (12000, 2)


async def test_missing_page_marks_queue_item_as_error():
    await queue_one()

    result = await jobs.run_scrape(FakeFetcher({}), AsyncSessionLocal)

    assert result["errors"] == 1
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(CrawlQueue.status))).scalar_one() == "error"


async def test_second_start_is_rejected_while_job_is_running(redis):
    arq = FakeArq()

    await state.enqueue(redis, arq, "scrape", {"limit": 5})
    try:
        await state.enqueue(redis, arq, "discover", {})
    except ConflictError:
        pass
    else:
        raise AssertionError("второй запуск должен быть отклонён")

    assert len(arq.jobs) == 1
    status = await state.get_status(redis)
    assert (status["state"], status["running"], status["name"]) == ("queued", True, "scrape")

    await state.mark_running(redis)
    await state.mark_finished(redis, result={"ok": 1})
    status = await state.get_status(redis)
    assert (status["state"], status["running"], status["result"]) == ("done", False, {"ok": 1})
    await state.enqueue(redis, arq, "discover", {})


async def test_parser_endpoints_need_admin(client):
    assert (await client.get("/api/v1/parser/status")).status_code == 401
    assert (await client.post("/api/v1/parser/scrape")).status_code == 401
