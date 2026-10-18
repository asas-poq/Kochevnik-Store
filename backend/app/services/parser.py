#!/usr/bin/env python3
"""
Парсер каталога ubcashmere.ru (`app/services/parser.py`).

Что изменилось по сравнению со старой версией:
  * Подключение к БД берётся ТОЛЬКО из `Settings` (`app/core/config.py`: DATABASE_URL или POSTGRES_*).
    Мелкие внутренние настройки (адрес сайта, пауза, User-Agent, папка файлов) лежат
    константами в начале этого файла; в конфиг бэкенда ничего добавлять не нужно.
  * Парсер пишет НАПРЯМУЮ в основную БД бэкенда (PostgreSQL / SQLite — какая указана
    в `DATABASE_URL` или `POSTGRES_*`). Отдельного файла `ubcashmere.db` больше нет.
  * Парсер не создаёт таблицы: они уже созданы бэкендом (миграции / create_all).
  * Парсер можно вызвать двумя способами, логика одна и та же:
      1) из API-ручек (`app/api/v1/parser_sync.py`) — через фоновую задачу;
      2) из командной строки (из корня проекта):
           python -m app.services.parser discover
           python -m app.services.parser scrape --limit 20
           python -m app.services.parser scrape --retry-errors
           python -m app.services.parser debug https://ubcashmere.ru/products/<slug>/
           python -m app.services.parser stats
           python -m app.services.parser export

Вежливость к сайту: проверка robots.txt, пауза между запросами, повторы при ошибках,
докачка после обрыва (очередь `crawl_queue` хранит статус каждой ссылки).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import re
import sys
import threading
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.engine import Connection, Engine

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# --- Внутренние настройки парсера (живут здесь, в конфиг бэкенда не выносятся) ---
BASE_URL = "https://ubcashmere.ru"   # сайт-источник
SOURCE_NAME = "ubcashmere"           # имя источника в таблице sources
DELAY_SECONDS = 1.5                  # пауза между запросами к сайту (вежливость)
HTTP_TIMEOUT = 30                    # таймаут одного запроса, секунд
RETRIES = 3                          # сколько раз повторять запрос при ошибке
USER_AGENT = "Mozilla/5.0 (compatible; PriceResearchBot/1.0; +contact: replace-with-your-email)"
DATA_DIR = "data/parser"             # сюда пишутся debug/ (HTML) и export/ (CSV)


# =============================================================================
# 1. БАЗА ДАННЫХ — подключение берётся ТОЛЬКО из Settings
# =============================================================================
def _sync_database_url() -> str:
    """
    Подключение к основной БД берётся ТОЛЬКО из Settings (DATABASE_URL или POSTGRES_*).
    Парсер синхронный, поэтому async-драйвер заменяем на обычный:
      postgresql+asyncpg://...  ->  postgresql+psycopg2://...
      sqlite+aiosqlite:///...   ->  sqlite:///...
    """
    return settings.async_database_url.replace("+asyncpg", "+psycopg2").replace("+aiosqlite", "")


@lru_cache()
def get_engine() -> Engine:
    """
    Синхронный движок SQLAlchemy к ОСНОВНОЙ базе бэкенда.
    URL берётся из `settings.async_database_url` (DATABASE_URL или POSTGRES_*) и тут же
    переводится в синхронный вид (asyncpg -> psycopg2, aiosqlite -> sqlite).
    Парсер — обычный блокирующий скрипт, поэтому асинхронный движок ему не нужен.
    """
    return create_engine(_sync_database_url(), pool_pre_ping=True)


def now() -> str:
    """Текущее время UTC в ISO-формате (строка подходит и для SQLite, и для PostgreSQL)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- SQL-запросы вынесены в одно место. Синтаксис ON CONFLICT / RETURNING одинаково
#     работает и в PostgreSQL, и в SQLite (3.35+), поэтому тип БД не важен. ---
SQL_SOURCE_INSERT = text("INSERT INTO sources(name, base_url) VALUES (:name, :base) ON CONFLICT DO NOTHING")
SQL_SOURCE_ID = text("SELECT id FROM sources WHERE name = :name")

SQL_QUEUE_INSERT = text(
    "INSERT INTO crawl_queue(source_id, url, status, updated_at) "
    "VALUES (:sid, :url, 'pending', :ts) ON CONFLICT DO NOTHING"
)
SQL_QUEUE_SELECT = text(
    "SELECT url FROM crawl_queue WHERE source_id = :sid AND status IN :statuses ORDER BY id"
).bindparams(bindparam("statuses", expanding=True))
SQL_QUEUE_MARK = text(
    "UPDATE crawl_queue SET status = :status, error = :error, updated_at = :ts "
    "WHERE source_id = :sid AND url = :url"
)

SQL_CATEGORY_INSERT = text(
    "INSERT INTO categories(source_id, slug, name, url) VALUES (:sid, :slug, :name, :url) ON CONFLICT DO NOTHING"
)
SQL_CATEGORY_ID = text("SELECT id FROM categories WHERE source_id = :sid AND slug = :slug")

SQL_PRODUCT_UPSERT = text("""
    INSERT INTO products(source_id, slug, url, article, name, brand, category_id, color, color_group,
                         composition, care_text, measurements, description, status,
                         first_seen, last_seen, content_hash, raw_json)
    VALUES (:sid, :slug, :url, :article, :name, :brand, :cat_id, :color, :grp,
            :composition, :care_text, :measurements, :description, 'active',
            :ts, :ts, :chash, :raw)
    ON CONFLICT(source_id, slug) DO UPDATE SET
        url = excluded.url, article = excluded.article, name = excluded.name, brand = excluded.brand,
        category_id = excluded.category_id, color = excluded.color, color_group = excluded.color_group,
        composition = excluded.composition, care_text = excluded.care_text,
        measurements = excluded.measurements, description = excluded.description,
        status = 'active', last_seen = excluded.last_seen,
        content_hash = excluded.content_hash, raw_json = excluded.raw_json
    RETURNING id
""")

# Дочерние таблицы пересобираем целиком (данных мало). Колонки — по порядку из schema.sql.
CHILD_TABLES = ("product_sizes", "product_images", "product_materials", "product_color_links", "product_attributes")
SQL_SIZE_INSERT = text("INSERT INTO product_sizes VALUES (:pid, :a, :b) ON CONFLICT DO NOTHING")
SQL_IMAGE_INSERT = text(
    "INSERT INTO product_images(product_id, position, url) VALUES (:pid, :pos, :url) ON CONFLICT DO NOTHING"
)
SQL_MATERIAL_INSERT = text("INSERT INTO product_materials VALUES (:pid, :a, :b) ON CONFLICT DO NOTHING")
SQL_COLORLINK_INSERT = text("INSERT INTO product_color_links VALUES (:pid, :a) ON CONFLICT DO NOTHING")
SQL_ATTR_INSERT = text("INSERT INTO product_attributes VALUES (:pid, :a, :b) ON CONFLICT DO NOTHING")

SQL_PRICE_LAST = text("SELECT price, old_price FROM price_history WHERE product_id = :pid ORDER BY id DESC LIMIT 1")
SQL_PRICE_INSERT = text(
    "INSERT INTO price_history(product_id, price, old_price, currency, scraped_at) "
    "VALUES (:pid, :price, :old, :cur, :ts)"
)


def ensure_source(con: Connection) -> int:
    """Гарантирует, что источник (ubcashmere) есть в таблице `sources`, и возвращает его id."""
    con.execute(SQL_SOURCE_INSERT, {"name": SOURCE_NAME, "base": BASE_URL})
    return con.execute(SQL_SOURCE_ID, {"name": SOURCE_NAME}).scalar_one()


def mark_queue(sid: int, url: str, status: str, error: Optional[str] = None) -> None:
    """Меняет статус ссылки в очереди (pending / done / error)."""
    with get_engine().begin() as con:
        con.execute(SQL_QUEUE_MARK, {"status": status, "error": error, "ts": now(), "sid": sid, "url": url})


# =============================================================================
# 2. СЕТЬ — HTTP-клиент с паузой, повторами и robots.txt
# =============================================================================
class Fetcher:
    """Скачивает страницы вежливо: пауза между запросами и повторы при ошибках."""

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": USER_AGENT, "Accept-Language": "ru-RU,ru;q=0.9"}
        )
        self._last_request = 0.0

    def get(self, url: str, retries: Optional[int] = None) -> Optional[str]:
        """GET с паузой. Возвращает текст страницы или None (404/410/исчерпаны попытки)."""
        retries = retries or RETRIES
        for attempt in range(1, retries + 1):
            wait = DELAY_SECONDS - (time.time() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            try:
                r = self.session.get(url, timeout=HTTP_TIMEOUT)
                self._last_request = time.time()
                if r.status_code == 200:
                    r.encoding = "utf-8"
                    return r.text
                if r.status_code in (404, 410):
                    return None
                logger.warning(f"[{r.status_code}] {url} (попытка {attempt})")
            except requests.RequestException as e:
                self._last_request = time.time()
                logger.warning(f"[ошибка сети] {e} (попытка {attempt})")
            time.sleep(3 * attempt)
        return None

    def robots(self) -> robotparser.RobotFileParser:
        """Читает robots.txt сайта; если не удалось — считаем, что ограничений нет."""
        rp = robotparser.RobotFileParser()
        try:
            resp = self.session.get(BASE_URL + "/robots.txt", timeout=15)
            rp.parse(resp.text.splitlines())
        except Exception:
            rp.parse([])
        return rp


def ensure_own_url(url: str) -> None:
    """Защита: парсер ходит только на сайт из настроек (чтобы ручка не стала открытым прокси)."""
    if urlparse(url).netloc != urlparse(BASE_URL).netloc:
        raise ValueError(f"URL должен принадлежать {BASE_URL}")


# =============================================================================
# 3. ПОИСК URL ТОВАРОВ (sitemap, запасной вариант — обход каталога)
# =============================================================================
PRODUCT_RE = re.compile(r"^https?://[^/]+/products/[^/?#]+/?$")


def _slash(u: str) -> str:
    return u if u.endswith("/") else u + "/"


def collect_sitemap_urls(fetcher: Fetcher, rp: robotparser.RobotFileParser) -> set:
    """Собирает ссылки на товары из sitemap (вложенные sitemap обходятся рекурсивно)."""
    urls: set = set()
    sitemaps = list(rp.site_maps() or []) or [BASE_URL + "/sitemap.xml"]
    seen_maps: set = set()
    while sitemaps:
        sm = sitemaps.pop()
        if sm in seen_maps:
            continue
        seen_maps.add(sm)
        xml = fetcher.get(sm)
        if not xml:
            continue
        for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml):
            if loc.endswith(".xml") or ("sitemap" in loc.lower() and loc.endswith(".xml.gz")):
                sitemaps.append(loc)
            elif PRODUCT_RE.match(loc):
                urls.add(_slash(loc))
    return urls


def crawl_catalog(fetcher: Fetcher, rp: robotparser.RobotFileParser) -> set:
    """Запасной путь: обход /catalog/ с пагинацией ?page=N, пока появляются новые товары."""
    base = BASE_URL
    found, todo, seen = set(), [base + "/catalog/"], set()
    while todo:
        url = todo.pop()
        if url in seen or not rp.can_fetch(USER_AGENT, url):
            continue
        seen.add(url)
        html = fetcher.get(url)
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")
        new_products = 0
        for a in soup.find_all("a", href=True):
            full = urljoin(url, a["href"]).split("#")[0].split("?")[0]
            if PRODUCT_RE.match(full):
                if _slash(full) not in found:
                    new_products += 1
                found.add(_slash(full))
            elif urlparse(full).netloc == urlparse(base).netloc and "/catalog/" in full:
                todo.append(_slash(full))
        if new_products and "?page=" not in url:
            todo.append(f"{url}?page=2")
        m = re.search(r"\?page=(\d+)", url)
        if m and new_products:
            todo.append(re.sub(r"\?page=\d+", f"?page={int(m.group(1)) + 1}", url))
    return found


# =============================================================================
# 4. РАЗБОР КАРТОЧКИ ТОВАРА (логика не менялась)
# =============================================================================
PRICE_RE = re.compile(r"(\d{1,3}(?:[\s\u00a0]\d{3})+|\d+)\s*₽")
SIZE_RE = re.compile(r"^(?:\d{2,3}(?:[/-]\d{2,3})?|XXS|XS|S|M|L|XL|XXL|XXXL|ONE ?SIZE|[Оо]дин размер)$", re.I)


def to_int(s: str) -> int:
    return int(re.sub(r"\D", "", s))


def page_lines(soup: BeautifulSoup) -> List[str]:
    """Текст страницы построчно (по одному элементу на строку)."""
    return [t.strip() for t in soup.get_text("\n").split("\n") if t.strip()]


def parse_jsonld(soup: BeautifulSoup) -> dict:
    """Достаёт микроразметку schema.org/Product (если она есть на странице)."""
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except Exception:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("@type") == "Product":
                return item
    return {}


def section_text(soup: BeautifulSoup, label: str) -> Optional[str]:
    """Содержимое аккордеона ('Состав и уход', 'Замеры изделия') — соседний блок после заголовка.
    Если контент подгружается JS-ом и в HTML его нет — вернём None (не мусор)."""
    node = soup.find(string=re.compile(rf"^\s*{label}\s*$"))
    if not node:
        return None
    el = node.parent
    for _ in range(3):
        sib = el.find_next_sibling()
        if sib:
            txt = sib.get_text("\n", strip=True)
            if txt and len(txt) < 3000 and "Выберите размер" not in txt and txt not in ("Состав и уход", "Замеры изделия"):
                return txt
            return None
        el = el.parent
        if el is None:
            break
    return None


def parse_product(html: str, url: str) -> Optional[Dict[str, Any]]:
    """Разбирает HTML карточки в словарь с полями товара. None — если это не карточка (нет <h1>)."""
    soup = BeautifulSoup(html, "lxml")
    h1 = soup.find("h1")
    if not h1:
        return None
    ld = parse_jsonld(soup)
    lines = page_lines(soup)
    slug = urlparse(url).path.strip("/").split("/")[-1]
    p: Dict[str, Any] = {"url": url, "slug": slug, "name": h1.get_text(" ", strip=True)}

    # Блок рядом с заголовком: текст ПОСЛЕ самого <h1> (а не после хлебных крошек)
    head = [t.strip() for t in h1.find_all_next(string=True) if t.strip() and h1 not in t.parents][:30]
    head_text = "\n".join(head)

    p["brand"] = (ld.get("brand", {}).get("name") if isinstance(ld.get("brand"), dict) else ld.get("brand")) \
        or (head[0] if head and not head[0].startswith("Арт") else None)
    p["composition"] = next((l for l in head if re.search(r"\d+\s*%", l)), None)

    m = re.search(r"Арт\.?\s*\n?\s*([A-Za-zА-Яа-я0-9\-_/.]+)", head_text) or re.search(r"Арт\.?\s*([\w\-./]+)", head_text)
    p["article"] = m.group(1) if m else ld.get("sku")

    prices = sorted({to_int(x) for x in PRICE_RE.findall(head_text)})
    offers = ld.get("offers") if isinstance(ld.get("offers"), dict) else {}
    if not prices and offers.get("price"):
        prices = [int(float(offers["price"]))]
    p["price"] = prices[0] if prices else None  # если цен две — дешёвая актуальная
    p["old_price"] = prices[-1] if len(prices) > 1 and prices[-1] != prices[0] else None
    p["currency"] = "RUB"

    m = re.search(r"Цвет:\s*([^\n]+)", "\n".join(lines))
    p["color"] = m.group(1).strip() if m else None

    # Размеры: всё между 'Размер' и 'Выберите размер'
    sizes: List[str] = []
    try:
        a = next(i for i, l in enumerate(lines) if l == "Размер")
        b = next(i for i in range(a, len(lines)) if lines[i].startswith("Выберите размер"))
        sizes = [l for l in lines[a + 1:b] if SIZE_RE.match(l)]
    except StopIteration:
        pass
    p["sizes"] = list(dict.fromkeys(sizes))
    p["sizes_stock"] = size_stock(soup, p["sizes"])

    p["color_links"] = color_siblings(html, slug)

    # Категория: ближайшая ссылка /catalog/... перед h1 (хлебные крошки)
    cat = None
    for a_ in h1.find_all_previous("a", href=re.compile(r"/catalog/[^/]+/?$")):
        cat = {"slug": a_["href"].rstrip("/").split("/")[-1], "name": a_.get_text(" ", strip=True),
               "url": urljoin(BASE_URL, a_["href"])}
        break
    p["category"] = cat

    p["images"] = collect_images(soup, html)
    p["care_text"] = section_text(soup, "Состав и уход")
    p["measurements"] = section_text(soup, "Замеры изделия")
    p["description"] = ld.get("description")
    p["materials"] = parse_materials(p["composition"])
    p["attributes"] = {}
    return p


def size_stock(soup: BeautifulSoup, sizes: List[str]) -> Dict[str, Optional[int]]:
    """Пытаемся понять, какие размеры недоступны (по class/disabled). Не вышло — None."""
    res: Dict[str, Optional[int]] = {s: None for s in sizes}
    for el in soup.find_all(["li", "button", "label", "div", "span"]):
        txt = el.get_text(strip=True)
        if txt in res and not el.find(True):
            cls = " ".join(el.get("class", []) + (el.parent.get("class", []) if el.parent else [])).lower()
            disabled = el.has_attr("disabled") or any(w in cls for w in ("disabled", "unavailable", "out-of-stock", "soldout"))
            res[txt] = 0 if disabled else 1
    return res


def color_siblings(html: str, own_slug: str) -> List[str]:
    """Ссылки /products/... между 'Цвет' и 'Размер' — это другие цвета этой же модели."""
    i = html.find("Цвет")
    j = html.find("Размер", i if i >= 0 else 0)
    if i < 0 or j < 0:
        return []
    slugs = re.findall(r"/products/([^/\"'?#\s<>]+)", html[i:j])
    return [s for s in dict.fromkeys(slugs) if s != own_slug]


def collect_images(soup: BeautifulSoup, html: str) -> List[str]:
    """Собирает URL картинок товара из img/srcset/og:image/сырого HTML (только cdn.ubcashmere.ru/media)."""
    urls: List[str] = []
    og = soup.find("meta", property="og:image")
    for tag in soup.find_all("img"):
        for attr in ("src", "data-src", "data-lazy-src", "data-original"):
            v = tag.get(attr)
            if v:
                urls.append(v)
        for v in (tag.get("srcset") or tag.get("data-srcset") or "").split(","):
            if v.strip():
                urls.append(v.strip().split()[0])
    urls += re.findall(r"https://cdn\.ubcashmere\.ru/media/[^\"'\s)<>]+\.(?:jpg|jpeg|png|webp)", html)
    if og and og.get("content"):
        urls.append(og["content"])
    out: List[str] = []
    for u in urls:
        u = urljoin(BASE_URL, u)
        if "cdn.ubcashmere.ru/media" in u and not re.search(r"hero|logo|icon|og-image", u) and u not in out:
            out.append(u)
    return out


def parse_materials(comp: Optional[str]) -> List[tuple]:
    """'70% кашемир, 30% шёлк' -> [('кашемир', 70.0), ('шёлк', 30.0)]."""
    if not comp:
        return []
    return [(name.strip().lower(), float(pct.replace(",", ".")))
            for pct, name in re.findall(r"(\d+(?:[.,]\d+)?)\s*%\s*([^,;+/\d]+)", comp)]


# =============================================================================
# 5. СОХРАНЕНИЕ ТОВАРА В ОСНОВНУЮ БД
# =============================================================================
def save_product(con: Connection, sid: int, p: Dict[str, Any]) -> int:
    """
    Записывает товар и все связанные данные (категория, размеры, фото, материалы,
    соседние цвета, история цен). Вызывать внутри транзакции `with engine.begin()`.
    """
    ts = now()
    cat_id = None
    if p["category"]:
        c = p["category"]
        con.execute(SQL_CATEGORY_INSERT, {"sid": sid, "slug": c["slug"], "name": c["name"], "url": c["url"]})
        cat_id = con.execute(SQL_CATEGORY_ID, {"sid": sid, "slug": c["slug"]}).scalar_one()

    group = min([p["slug"]] + p["color_links"])  # детерминированный ключ группы цветов
    content = {k: p[k] for k in ("name", "brand", "article", "color", "composition", "sizes", "images",
                                 "care_text", "measurements")}
    chash = hashlib.sha1(json.dumps(content, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    pid = con.execute(SQL_PRODUCT_UPSERT, {
        "sid": sid, "slug": p["slug"], "url": p["url"], "article": p["article"], "name": p["name"],
        "brand": p["brand"], "cat_id": cat_id, "color": p["color"], "grp": group,
        "composition": p["composition"], "care_text": p["care_text"], "measurements": p["measurements"],
        "description": p["description"], "ts": ts, "chash": chash,
        "raw": json.dumps(p, ensure_ascii=False, default=str),
    }).scalar_one()

    for t in CHILD_TABLES:
        con.execute(text(f"DELETE FROM {t} WHERE product_id = :pid"), {"pid": pid})
    for s in p["sizes"]:
        stock = p["sizes_stock"].get(s)
        con.execute(SQL_SIZE_INSERT, {"pid": pid, "a": s, "b": None if stock is None else bool(stock)})
    for i, u in enumerate(p["images"]):
        con.execute(SQL_IMAGE_INSERT, {"pid": pid, "pos": i, "url": u})
    for name, pct in p["materials"]:
        con.execute(SQL_MATERIAL_INSERT, {"pid": pid, "a": name, "b": pct})
    for sl in p["color_links"]:
        con.execute(SQL_COLORLINK_INSERT, {"pid": pid, "a": sl})
    for k, v in p["attributes"].items():
        con.execute(SQL_ATTR_INSERT, {"pid": pid, "a": k, "b": v})

    # Цена: новая запись в историю только если цена изменилась
    if p["price"] is not None:
        last = con.execute(SQL_PRICE_LAST, {"pid": pid}).mappings().first()
        if not last or last["price"] != p["price"] or last["old_price"] != p["old_price"]:
            con.execute(SQL_PRICE_INSERT, {"pid": pid, "price": p["price"], "old": p["old_price"],
                                           "cur": p["currency"], "ts": ts})
    return pid


# =============================================================================
# 6. ПУБЛИЧНЫЕ КОМАНДЫ (их вызывают и CLI, и API-ручки)
# =============================================================================
def run_discover() -> Dict[str, Any]:
    """Находит все URL товаров (sitemap, при неудаче — обход каталога) и кладёт новые в crawl_queue."""
    fetcher = Fetcher()
    rp = fetcher.robots()
    urls = collect_sitemap_urls(fetcher, rp)
    logger.info(f"sitemap: найдено товаров {len(urls)}")
    if not urls:
        logger.info("sitemap пуст, обхожу каталог...")
        urls = crawl_catalog(fetcher, rp)

    added = 0
    with get_engine().begin() as con:
        sid = ensure_source(con)
        for u in sorted(urls):
            added += con.execute(SQL_QUEUE_INSERT, {"sid": sid, "url": u, "ts": now()}).rowcount or 0
    logger.info(f"новых URL в очереди: {added}, всего найдено: {len(urls)}")
    return {"found": len(urls), "added": added}


def run_scrape(limit: Optional[int] = None, retry_errors: bool = False) -> Dict[str, Any]:
    """
    Берёт ссылки из crawl_queue (pending, а с retry_errors ещё и error), скачивает карточки
    и пишет товары в основную БД. Каждый товар — своя транзакция: сбой одного не ломает остальные.
    """
    fetcher = Fetcher()
    rp = fetcher.robots()
    statuses = ["pending", "error"] if retry_errors else ["pending"]
    with get_engine().begin() as con:
        sid = ensure_source(con)
        urls = [r[0] for r in con.execute(SQL_QUEUE_SELECT, {"sid": sid, "statuses": statuses})]
    if limit:
        urls = urls[:limit]
    logger.info(f"к обработке: {len(urls)}")

    ok = bad = 0
    for n, url in enumerate(urls, 1):
        if not rp.can_fetch(USER_AGENT, url):
            mark_queue(sid, url, "error", "robots.txt")
            bad += 1
            continue
        try:
            html = fetcher.get(url)
            p = parse_product(html, url) if html else None
            if not p or not p["name"]:
                mark_queue(sid, url, "error", "нет страницы или заголовка")
                bad += 1
                logger.warning(f"[{n}/{len(urls)}] ОШИБКА {url}")
                continue
            # Товар и статус 'done' пишутся в одной транзакции — либо всё, либо ничего
            with get_engine().begin() as con:
                save_product(con, sid, p)
                con.execute(SQL_QUEUE_MARK, {"status": "done", "error": None, "ts": now(), "sid": sid, "url": url})
            ok += 1
            warn = [k for k in ("price", "article", "sizes", "images") if not p[k]]
            logger.info(f"[{n}/{len(urls)}] {p['name'][:50]} | {p['price']} ₽" + (f" | ПУСТО: {warn}" if warn else ""))
        except Exception as e:  # noqa: BLE001 — одна плохая карточка не должна останавливать весь обход
            logger.exception(f"[{n}/{len(urls)}] сбой на {url}")
            mark_queue(sid, url, "error", str(e)[:500])
            bad += 1
    logger.info(f"готово: ok={ok}, ошибок={bad}")
    return {"total": len(urls), "ok": ok, "errors": bad}


def preview_product(url: str, save_html: bool = False) -> Optional[Dict[str, Any]]:
    """Разбирает ОДНУ страницу и возвращает результат, в БД ничего не пишет (для проверки парсера)."""
    ensure_own_url(url)
    html = Fetcher().get(url)
    if not html:
        return None
    if save_html:
        out_dir = Path(DATA_DIR) / "debug"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / (urlparse(url).path.strip("/").replace("/", "_") + ".html")
        out.write_text(html, encoding="utf-8")
        logger.info(f"HTML сохранён: {out}")
    return parse_product(html, url)


def get_stats() -> Dict[str, Any]:
    """Краткая статистика по спарсенным данным в основной БД."""
    def one(con: Connection, sql: str) -> Any:
        return con.execute(text(sql)).scalar_one()

    with get_engine().connect() as con:
        return {
            "products": one(con, "SELECT COUNT(*) FROM products"),
            "color_groups": one(con, "SELECT COUNT(DISTINCT color_group) FROM products"),
            "categories": one(con, "SELECT COUNT(*) FROM categories"),
            "without_price": one(con, "SELECT COUNT(*) FROM products p WHERE NOT EXISTS (SELECT 1 FROM price_history h WHERE h.product_id=p.id)"),
            "without_sizes": one(con, "SELECT COUNT(*) FROM products p WHERE NOT EXISTS (SELECT 1 FROM product_sizes s WHERE s.product_id=p.id)"),
            "without_images": one(con, "SELECT COUNT(*) FROM products p WHERE NOT EXISTS (SELECT 1 FROM product_images i WHERE i.product_id=p.id)"),
            "queue": {r[0]: r[1] for r in con.execute(text("SELECT status, COUNT(*) FROM crawl_queue GROUP BY status"))},
        }


def run_export() -> Dict[str, int]:
    """Выгружает таблицы в CSV (папка DATA_DIR/export). Возвращает {файл: число строк}."""
    out_dir = Path(DATA_DIR) / "export"
    out_dir.mkdir(parents=True, exist_ok=True)
    tables = {
        "products": "SELECT p.*, c.name AS category FROM products p LEFT JOIN categories c ON c.id=p.category_id",
        "sizes": "SELECT p.slug, s.size, s.in_stock FROM product_sizes s JOIN products p ON p.id=s.product_id",
        "images": "SELECT p.slug, i.position, i.url FROM product_images i JOIN products p ON p.id=i.product_id",
        "prices": "SELECT p.slug, h.price, h.old_price, h.scraped_at FROM price_history h JOIN products p ON p.id=h.product_id",
    }
    result: Dict[str, int] = {}
    with get_engine().connect() as con:
        for name, sql in tables.items():
            res = con.execute(text(sql))
            rows = res.fetchall()
            if not rows:
                continue
            with open(out_dir / f"{name}.csv", "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(res.keys())
                w.writerows([tuple(r) for r in rows])
            result[f"{name}.csv"] = len(rows)
            logger.info(f"{out_dir / (name + '.csv')}: {len(rows)} строк")
    return result


# =============================================================================
# 7. ФОНОВЫЕ ЗАДАЧИ ДЛЯ API: не даём запустить две задачи парсера одновременно
# =============================================================================
_job_lock = threading.Lock()
_job: Dict[str, Any] = {"name": None, "running": False, "started_at": None,
                        "finished_at": None, "result": None, "error": None}


def start_job(name: str) -> bool:
    """Помечает, что задача началась. False — если парсер уже занят другой задачей."""
    with _job_lock:
        if _job["running"]:
            return False
        _job.update(name=name, running=True, started_at=now(), finished_at=None, result=None, error=None)
        return True


def run_job(name: str, func: Callable[..., Any], **kwargs: Any) -> None:
    """Обёртка для BackgroundTasks: выполняет func, сохраняет результат/ошибку и снимает флаг занятости."""
    try:
        result = func(**kwargs)
        with _job_lock:
            _job["result"] = result
    except Exception as e:  # noqa: BLE001
        logger.exception(f"Задача парсера '{name}' завершилась ошибкой")
        with _job_lock:
            _job["error"] = str(e)
    finally:
        with _job_lock:
            _job["running"] = False
            _job["finished_at"] = now()


def get_job_status() -> Dict[str, Any]:
    """Состояние последней/текущей задачи парсера (для ручки GET /parser/status)."""
    with _job_lock:
        return dict(_job)


# =============================================================================
# 8. КОМАНДНАЯ СТРОКА
# =============================================================================
def main() -> None:
    ap = argparse.ArgumentParser(description="Парсер ubcashmere.ru -> основная БД бэкенда")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("discover", help="найти URL товаров и положить в crawl_queue")
    s = sub.add_parser("scrape", help="скачать и разобрать карточки из очереди")
    s.add_argument("--limit", type=int, help="сколько карточек обработать за запуск")
    s.add_argument("--retry-errors", action="store_true", help="повторить ссылки со статусом error")
    d = sub.add_parser("debug", help="разобрать одну страницу, ничего не писать в БД")
    d.add_argument("url")
    sub.add_parser("export", help="выгрузить CSV")
    sub.add_parser("stats", help="статистика по БД")
    args = ap.parse_args()

    if not logging.getLogger().handlers:  # при запуске из консоли показываем логи
        logging.basicConfig(level=settings.LOG_LEVEL, format="%(message)s")

    if args.cmd == "discover":
        print(run_discover())
    elif args.cmd == "scrape":
        print(run_scrape(args.limit, args.retry_errors))
    elif args.cmd == "debug":
        p = preview_product(args.url, save_html=True)
        if p is None:
            sys.exit("страница не скачалась")
        print(json.dumps(p, ensure_ascii=False, indent=2, default=str))
    elif args.cmd == "export":
        print(run_export())
    elif args.cmd == "stats":
        print(json.dumps(get_stats(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()