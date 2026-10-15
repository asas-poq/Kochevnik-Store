#!/usr/bin/env python3
"""
Парсер каталога ubcashmere.ru -> SQLite.

Команды:
  python parser.py discover            найти все URL товаров (sitemap, при неудаче обход каталога)
  python parser.py scrape [--limit N]  скачать и разобрать карточки из очереди
  python parser.py debug URL           разобрать ОДНУ страницу, показать результат, сохранить HTML в debug/
  python parser.py export              выгрузить CSV в export/
  python parser.py stats               краткая статистика по БД

Вежливость: проверка robots.txt, пауза между запросами, повторы при ошибках, докачка после обрыва.
"""
import argparse
import csv
import hashlib
import json
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://ubcashmere.ru"
SOURCE_NAME = "ubcashmere"
DB_PATH = Path("ubcashmere.db")
SCHEMA = Path(__file__).with_name("schema.sql")
DELAY = 1.5  # секунд между запросами
UA = "Mozilla/5.0 (compatible; PriceResearchBot/1.0; +contact: replace-with-your-email)"

session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept-Language": "ru-RU,ru;q=0.9"})
_last_request = 0.0


# ----------------------------------------------------------------- сеть
def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get(url, retries=3):
    """GET с паузой и повторами."""
    global _last_request
    for attempt in range(1, retries + 1):
        wait = DELAY - (time.time() - _last_request)
        if wait > 0:
            time.sleep(wait)
        try:
            r = session.get(url, timeout=30)
            _last_request = time.time()
            if r.status_code == 200:
                r.encoding = "utf-8"
                return r.text
            if r.status_code in (404, 410):
                return None
            print(f"  [{r.status_code}] {url} (попытка {attempt})")
        except requests.RequestException as e:
            _last_request = time.time()
            print(f"  [ошибка] {e} (попытка {attempt})")
        time.sleep(3 * attempt)
    return None


def robots():
    rp = robotparser.RobotFileParser()
    try:
        rp.parse(session.get(BASE + "/robots.txt", timeout=15).text.splitlines())
    except Exception:
        rp.parse([])
    return rp


# ----------------------------------------------------------------- БД
def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.execute("INSERT OR IGNORE INTO sources(name, base_url) VALUES (?, ?)", (SOURCE_NAME, BASE))
    con.commit()
    return con


def source_id(con):
    return con.execute("SELECT id FROM sources WHERE name=?", (SOURCE_NAME,)).fetchone()["id"]


# ----------------------------------------------------------------- поиск URL
PRODUCT_RE = re.compile(r"^https?://[^/]+/products/[^/?#]+/?$")


def discover(con, rp):
    sid = source_id(con)
    urls = set()

    # 1) sitemap(ы): сначала те, что указаны в robots.txt, потом стандартный
    sitemaps = list(rp.site_maps() or []) or [BASE + "/sitemap.xml"]
    seen_maps = set()
    while sitemaps:
        sm = sitemaps.pop()
        if sm in seen_maps:
            continue
        seen_maps.add(sm)
        xml = get(sm)
        if not xml:
            continue
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
        for loc in locs:
            if loc.endswith(".xml") or "sitemap" in loc.lower() and loc.endswith(".xml.gz"):
                sitemaps.append(loc)
            elif PRODUCT_RE.match(loc):
                urls.add(loc if loc.endswith("/") else loc + "/")
    print(f"sitemap: найдено товаров {len(urls)}")

    # 2) запасной путь: обход каталога с пагинацией
    if not urls:
        print("sitemap пуст, обхожу каталог...")
        urls |= crawl_catalog(rp)

    added = 0
    for u in sorted(urls):
        cur = con.execute(
            "INSERT OR IGNORE INTO crawl_queue(source_id, url, status, updated_at) VALUES (?,?, 'pending', ?)",
            (sid, u, now()),
        )
        added += cur.rowcount
    con.commit()
    print(f"новых URL в очереди: {added}, всего найдено: {len(urls)}")


def crawl_catalog(rp):
    found, todo, seen = set(), [BASE + "/catalog/"], set()
    while todo:
        url = todo.pop()
        if url in seen or not rp.can_fetch(UA, url):
            continue
        seen.add(url)
        html = get(url)
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")
        new_products = 0
        for a in soup.find_all("a", href=True):
            full = urljoin(url, a["href"]).split("#")[0].split("?")[0]
            if PRODUCT_RE.match(full):
                if full not in found:
                    new_products += 1
                found.add(full if full.endswith("/") else full + "/")
            elif urlparse(full).netloc == urlparse(BASE).netloc and "/catalog/" in full:
                todo.append(full if full.endswith("/") else full + "/")
        # пагинация ?page=N: идём дальше, пока на странице появляются новые товары
        if new_products and "?page=" not in url:
            todo.append(f"{url}?page=2")
        m = re.search(r"\?page=(\d+)", url)
        if m and new_products:
            todo.append(re.sub(r"\?page=\d+", f"?page={int(m.group(1)) + 1}", url))
    return found


# ----------------------------------------------------------------- разбор карточки
PRICE_RE = re.compile(r"(\d{1,3}(?:[\s\u00a0]\d{3})+|\d+)\s*₽")
SIZE_RE = re.compile(r"^(?:\d{2,3}(?:[/-]\d{2,3})?|XXS|XS|S|M|L|XL|XXL|XXXL|ONE ?SIZE|[Оо]дин размер)$", re.I)


def to_int(s):
    return int(re.sub(r"\D", "", s))


def page_lines(soup):
    """Текст страницы построчно (по одному элементу на строку)."""
    return [t.strip() for t in soup.get_text("\n").split("\n") if t.strip()]


def parse_jsonld(soup):
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except Exception:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("@type") == "Product":
                return item
    return {}


def section_text(soup, label):
    """Содержимое аккордеона ('Состав и уход', 'Замеры изделия') - это СОСЕДНИЙ блок после заголовка.
    Если контент подгружается JS-ом и в HTML его нет - вернём None (не мусор)."""
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


def parse_product(html, url):
    soup = BeautifulSoup(html, "lxml")
    h1 = soup.find("h1")
    if not h1:
        return None
    ld = parse_jsonld(soup)
    lines = page_lines(soup)
    slug = urlparse(url).path.strip("/").split("/")[-1]
    p = {"url": url, "slug": slug, "name": h1.get_text(" ", strip=True)}

    # --- блок рядом с заголовком: берём текст ПОСЛЕ самого <h1> (а не после хлебных крошек)
    head = [t.strip() for t in h1.find_all_next(string=True) if t.strip() and h1 not in t.parents][:30]
    head_text = "\n".join(head)

    p["brand"] = (ld.get("brand", {}).get("name") if isinstance(ld.get("brand"), dict) else ld.get("brand")) \
        or (head[0] if head and not head[0].startswith("Арт") else None)

    comp = next((l for l in head if re.search(r"\d+\s*%", l)), None)
    p["composition"] = comp

    m = re.search(r"Арт\.?\s*\n?\s*([A-Za-zА-Яа-я0-9\-_/.]+)", head_text) or re.search(r"Арт\.?\s*([\w\-./]+)", head_text)
    p["article"] = m.group(1) if m else ld.get("sku")

    prices = sorted({to_int(x) for x in PRICE_RE.findall(head_text)})
    offers = ld.get("offers") if isinstance(ld.get("offers"), dict) else {}
    if not prices and offers.get("price"):
        prices = [int(float(offers["price"]))]
    p["price"] = prices[0] if prices else None  # если цен две - дешёвая актуальная
    p["old_price"] = prices[-1] if len(prices) > 1 and prices[-1] != prices[0] else None
    p["currency"] = "RUB"

    # --- цвет
    m = re.search(r"Цвет:\s*([^\n]+)", "\n".join(lines))
    p["color"] = m.group(1).strip() if m else None

    # --- размеры: всё между 'Размер' и 'Выберите размер'
    sizes = []
    try:
        a = next(i for i, l in enumerate(lines) if l == "Размер")
        b = next(i for i in range(a, len(lines)) if lines[i].startswith("Выберите размер"))
        sizes = [l for l in lines[a + 1:b] if SIZE_RE.match(l)]
    except StopIteration:
        pass
    p["sizes"] = list(dict.fromkeys(sizes))
    p["sizes_stock"] = size_stock(soup, p["sizes"])

    # --- соседние цвета: ссылки /products/... между 'Цвет' и 'Размер' в HTML
    p["color_links"] = color_siblings(html, slug)

    # --- категория: ближайшая ссылка /catalog/... перед h1 (хлебные крошки)
    cat = None
    for a_ in h1.find_all_previous("a", href=re.compile(r"/catalog/[^/]+/?$")):
        cat = {"slug": a_["href"].rstrip("/").split("/")[-1], "name": a_.get_text(" ", strip=True),
               "url": urljoin(BASE, a_["href"])}
        break
    p["category"] = cat

    # --- картинки
    p["images"] = collect_images(soup, html)

    # --- аккордеоны
    p["care_text"] = section_text(soup, "Состав и уход")
    p["measurements"] = section_text(soup, "Замеры изделия")
    p["description"] = ld.get("description")

    p["materials"] = parse_materials(p["composition"])
    p["attributes"] = {}
    return p


def size_stock(soup, sizes):
    """Пытаемся понять, какие размеры недоступны (по class/disabled). Если не вышло - None."""
    res = {s: None for s in sizes}
    for el in soup.find_all(["li", "button", "label", "div", "span"]):
        txt = el.get_text(strip=True)
        if txt in res and not el.find(True):
            cls = " ".join(el.get("class", []) + (el.parent.get("class", []) if el.parent else [])).lower()
            disabled = el.has_attr("disabled") or any(w in cls for w in ("disabled", "unavailable", "out-of-stock", "soldout"))
            res[txt] = 0 if disabled else 1
    return res


def color_siblings(html, own_slug):
    i = html.find("Цвет")
    j = html.find("Размер", i if i >= 0 else 0)
    if i < 0 or j < 0:
        return []
    seg = html[i:j]
    slugs = re.findall(r"/products/([^/\"'?#\s<>]+)", seg)
    return [s for s in dict.fromkeys(slugs) if s != own_slug]


def collect_images(soup, html):
    urls = []
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
    out = []
    for u in urls:
        u = urljoin(BASE, u)
        if "cdn.ubcashmere.ru/media" in u and not re.search(r"hero|logo|icon|og-image", u) and u not in out:
            out.append(u)
    return out


def parse_materials(comp):
    if not comp:
        return []
    res = []
    for pct, name in re.findall(r"(\d+(?:[.,]\d+)?)\s*%\s*([^,;+/\d]+)", comp):
        res.append((name.strip().lower(), float(pct.replace(",", "."))))
    return res


# ----------------------------------------------------------------- сохранение
def save_product(con, p):
    sid = source_id(con)
    ts = now()
    cat_id = None
    if p["category"]:
        c = p["category"]
        con.execute("INSERT OR IGNORE INTO categories(source_id, slug, name, url) VALUES (?,?,?,?)",
                    (sid, c["slug"], c["name"], c["url"]))
        cat_id = con.execute("SELECT id FROM categories WHERE source_id=? AND slug=?", (sid, c["slug"])).fetchone()["id"]

    group = min([p["slug"]] + p["color_links"])  # детерминированный ключ группы цветов
    content = {k: p[k] for k in ("name", "brand", "article", "color", "composition", "sizes", "images",
                                 "care_text", "measurements")}
    chash = hashlib.sha1(json.dumps(content, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    con.execute("""
        INSERT INTO products(source_id, slug, url, article, name, brand, category_id, color, color_group,
                             composition, care_text, measurements, description, status,
                             first_seen, last_seen, content_hash, raw_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?, 'active', ?,?,?,?)
        ON CONFLICT(source_id, slug) DO UPDATE SET
            url=excluded.url, article=excluded.article, name=excluded.name, brand=excluded.brand,
            category_id=excluded.category_id, color=excluded.color, color_group=excluded.color_group,
            composition=excluded.composition, care_text=excluded.care_text,
            measurements=excluded.measurements, description=excluded.description,
            status='active', last_seen=excluded.last_seen,
            content_hash=excluded.content_hash, raw_json=excluded.raw_json
    """, (sid, p["slug"], p["url"], p["article"], p["name"], p["brand"], cat_id, p["color"], group,
          p["composition"], p["care_text"], p["measurements"], p["description"],
          ts, ts, chash, json.dumps(p, ensure_ascii=False, default=str)))
    pid = con.execute("SELECT id FROM products WHERE source_id=? AND slug=?", (sid, p["slug"])).fetchone()["id"]

    # дочерние таблицы: пересобираем целиком (данные маленькие)
    for t in ("product_sizes", "product_images", "product_materials", "product_color_links", "product_attributes"):
        con.execute(f"DELETE FROM {t} WHERE product_id=?", (pid,))
    for s in p["sizes"]:
        con.execute("INSERT INTO product_sizes VALUES (?,?,?)", (pid, s, p["sizes_stock"].get(s)))
    for i, u in enumerate(p["images"]):
        con.execute("INSERT OR IGNORE INTO product_images(product_id, position, url) VALUES (?,?,?)", (pid, i, u))
    for m, pct in p["materials"]:
        con.execute("INSERT OR REPLACE INTO product_materials VALUES (?,?,?)", (pid, m, pct))
    for sl in p["color_links"]:
        con.execute("INSERT OR IGNORE INTO product_color_links VALUES (?,?)", (pid, sl))
    for k, v in p["attributes"].items():
        con.execute("INSERT OR REPLACE INTO product_attributes VALUES (?,?,?)", (pid, k, v))

    # цена: пишем только при изменении
    if p["price"] is not None:
        last = con.execute("SELECT price, old_price FROM price_history WHERE product_id=? ORDER BY id DESC LIMIT 1",
                           (pid,)).fetchone()
        if not last or last["price"] != p["price"] or last["old_price"] != p["old_price"]:
            con.execute("INSERT INTO price_history(product_id, price, old_price, currency, scraped_at) VALUES (?,?,?,?,?)",
                        (pid, p["price"], p["old_price"], p["currency"], ts))
    return pid


def scrape(con, rp, limit=None, retry_errors=False):
    sid = source_id(con)
    statuses = ("pending", "error") if retry_errors else ("pending",)
    q = f"SELECT url FROM crawl_queue WHERE source_id=? AND status IN ({','.join('?' * len(statuses))})"
    urls = [r["url"] for r in con.execute(q, (sid, *statuses))]
    if limit:
        urls = urls[:limit]
    print(f"к обработке: {len(urls)}")
    ok = bad = 0
    for n, url in enumerate(urls, 1):
        if not rp.can_fetch(UA, url):
            con.execute("UPDATE crawl_queue SET status='error', error='robots.txt' WHERE source_id=? AND url=?", (sid, url))
            continue
        html = get(url)
        p = parse_product(html, url) if html else None
        if not p or not p["name"]:
            con.execute("UPDATE crawl_queue SET status='error', error=?, updated_at=? WHERE source_id=? AND url=?",
                        ("нет страницы или заголовка", now(), sid, url))
            bad += 1
            print(f"[{n}/{len(urls)}] ОШИБКА {url}")
        else:
            save_product(con, p)
            con.execute("UPDATE crawl_queue SET status='done', error=NULL, updated_at=? WHERE source_id=? AND url=?",
                        (now(), sid, url))
            ok += 1
            warn = [k for k in ("price", "article", "sizes", "images") if not p[k]]
            print(f"[{n}/{len(urls)}] {p['name'][:50]} | {p['price']} ₽" + (f" | ПУСТО: {warn}" if warn else ""))
        con.commit()
    print(f"готово: ok={ok}, ошибок={bad}")


# ----------------------------------------------------------------- прочее
def debug(url):
    html = get(url)
    if not html:
        sys.exit("страница не скачалась")
    Path("debug").mkdir(exist_ok=True)
    out = Path("debug") / (urlparse(url).path.strip("/").replace("/", "_") + ".html")
    out.write_text(html, encoding="utf-8")
    p = parse_product(html, url)
    print(json.dumps(p, ensure_ascii=False, indent=2, default=str))
    print(f"\nHTML сохранён: {out}")


def export(con):
    Path("export").mkdir(exist_ok=True)
    tables = {
        "products": "SELECT p.*, c.name AS category FROM products p LEFT JOIN categories c ON c.id=p.category_id",
        "sizes": "SELECT p.slug, s.size, s.in_stock FROM product_sizes s JOIN products p ON p.id=s.product_id",
        "images": "SELECT p.slug, i.position, i.url FROM product_images i JOIN products p ON p.id=i.product_id",
        "prices": "SELECT p.slug, h.price, h.old_price, h.scraped_at FROM price_history h JOIN products p ON p.id=h.product_id",
    }
    for name, sql in tables.items():
        rows = con.execute(sql).fetchall()
        if not rows:
            continue
        with open(f"export/{name}.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(rows[0].keys())
            w.writerows([tuple(r) for r in rows])
        print(f"export/{name}.csv: {len(rows)} строк")


def stats(con):
    q = lambda s: con.execute(s).fetchone()[0]
    print("товаров:", q("SELECT COUNT(*) FROM products"))
    print("групп цветов (моделей):", q("SELECT COUNT(DISTINCT color_group) FROM products"))
    print("категорий:", q("SELECT COUNT(*) FROM categories"))
    print("без цены:", q("SELECT COUNT(*) FROM products p WHERE NOT EXISTS (SELECT 1 FROM price_history h WHERE h.product_id=p.id)"))
    print("без размеров:", q("SELECT COUNT(*) FROM products p WHERE NOT EXISTS (SELECT 1 FROM product_sizes s WHERE s.product_id=p.id)"))
    print("без картинок:", q("SELECT COUNT(*) FROM products p WHERE NOT EXISTS (SELECT 1 FROM product_images i WHERE i.product_id=p.id)"))
    print("очередь:", [tuple(r) for r in con.execute("SELECT status, COUNT(*) FROM crawl_queue GROUP BY status")])


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("discover")
    s = sub.add_parser("scrape")
    s.add_argument("--limit", type=int)
    s.add_argument("--retry-errors", action="store_true")
    d = sub.add_parser("debug")
    d.add_argument("url")
    sub.add_parser("export")
    sub.add_parser("stats")
    args = ap.parse_args()

    if args.cmd == "debug":
        return debug(args.url)
    con = db()
    rp = robots()
    if args.cmd == "discover":
        discover(con, rp)
    elif args.cmd == "scrape":
        scrape(con, rp, args.limit, args.retry_errors)
    elif args.cmd == "export":
        export(con)
    elif args.cmd == "stats":
        stats(con)


if __name__ == "__main__":
    main()
