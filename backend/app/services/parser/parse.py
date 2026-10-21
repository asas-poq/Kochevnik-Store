import json
import re
from typing import Any, TypedDict
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.core.config import settings

PRODUCT_RE = re.compile(r"^https?://[^/]+/products/[^/?#]+/?$")
PRICE_RE = re.compile(r"(\d{1,3}(?:[\s\u00a0]\d{3})+|\d+)\s*₽")
SIZE_RE = re.compile(
    r"^(?:\d{2,3}(?:[/-]\d{2,3})?|XXS|XS|S|M|L|XL|XXL|XXXL|ONE ?SIZE|[Оо]дин размер)$", re.I
)


class ParsedProduct(TypedDict):
    url: str
    slug: str
    name: str
    brand: str | None
    composition: str | None
    article: str | None
    price: int | None
    old_price: int | None
    currency: str
    color: str | None
    sizes: list[str]
    sizes_stock: dict[str, int | None]
    color_links: list[str]
    category: dict[str, str] | None
    images: list[str]
    care_text: str | None
    measurements: str | None
    description: str | None
    materials: list[tuple[str, float]]
    attributes: dict[str, str]


def ensure_own_url(url: str) -> None:
    """Защита, чтобы ручка preview не стала открытым прокси."""
    if urlparse(url).netloc != urlparse(settings.PARSER_BASE_URL).netloc:
        raise ValueError(f"URL должен принадлежать {settings.PARSER_BASE_URL}")


def with_slash(url: str) -> str:
    return url if url.endswith("/") else url + "/"


def to_int(raw: str) -> int:
    return int(re.sub(r"\D", "", raw))


def page_lines(soup: BeautifulSoup) -> list[str]:
    return [t.strip() for t in soup.get_text("\n").split("\n") if t.strip()]


def parse_jsonld(soup: BeautifulSoup) -> dict[str, Any]:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("@type") == "Product":
                return item
    return {}


def section_text(soup: BeautifulSoup, label: str) -> str | None:
    """Содержимое аккордеона «Состав и уход» или «Замеры изделия» лежит в соседнем блоке.
    Если сайт подгружает его скриптом и в HTML пусто, возвращаем None, а не мусор."""
    node = soup.find(string=re.compile(rf"^\s*{label}\s*$"))
    if not node:
        return None
    el = node.parent
    for _ in range(3):
        sibling = el.find_next_sibling()
        if sibling:
            text = sibling.get_text("\n", strip=True)
            noise = "Выберите размер" in text or text in ("Состав и уход", "Замеры изделия")
            return text if text and len(text) < 3000 and not noise else None
        el = el.parent
        if el is None:
            break
    return None


def parse_materials(composition: str | None) -> list[tuple[str, float]]:
    """'70% кашемир, 30% шёлк' даёт [('кашемир', 70.0), ('шёлк', 30.0)]."""
    if not composition:
        return []
    return [
        (name.strip().lower(), float(pct.replace(",", ".")))
        for pct, name in re.findall(r"(\d+(?:[.,]\d+)?)\s*%\s*([^,;+/\d]+)", composition)
    ]


def size_stock(soup: BeautifulSoup, sizes: list[str]) -> dict[str, int | None]:
    """По классам и disabled понимаем, какие размеры закончились. Не вышло, значит None."""
    result: dict[str, int | None] = {s: None for s in sizes}
    for el in soup.find_all(["li", "button", "label", "div", "span"]):
        text = el.get_text(strip=True)
        if text in result and not el.find(True):
            classes = " ".join(el.get("class", []) + (el.parent.get("class", []) if el.parent else [])).lower()
            off = el.has_attr("disabled") or any(w in classes for w in ("disabled", "unavailable", "out-of-stock", "soldout"))
            result[text] = 0 if off else 1
    return result


def color_siblings(html: str, own_slug: str) -> list[str]:
    """Ссылки /products/... между словами «Цвет» и «Размер» ведут на другие цвета этой модели."""
    i = html.find("Цвет")
    j = html.find("Размер", i if i >= 0 else 0)
    if i < 0 or j < 0:
        return []
    slugs = re.findall(r"/products/([^/\"'?#\s<>]+)", html[i:j])
    return [s for s in dict.fromkeys(slugs) if s != own_slug]


def collect_images(soup: BeautifulSoup, html: str) -> list[str]:
    """Берём только cdn.ubcashmere.ru/media и выкидываем служебные картинки."""
    urls: list[str] = []
    for tag in soup.find_all("img"):
        for attr in ("src", "data-src", "data-lazy-src", "data-original"):
            if tag.get(attr):
                urls.append(tag[attr])
        for part in (tag.get("srcset") or tag.get("data-srcset") or "").split(","):
            if part.strip():
                urls.append(part.strip().split()[0])
    urls += re.findall(r"https://cdn\.ubcashmere\.ru/media/[^\"'\s)<>]+\.(?:jpg|jpeg|png|webp)", html)
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        urls.append(og["content"])

    out: list[str] = []
    for raw in urls:
        url = urljoin(settings.PARSER_BASE_URL, raw)
        if "cdn.ubcashmere.ru/media" in url and not re.search(r"hero|logo|icon|og-image", url) and url not in out:
            out.append(url)
    return out


def parse_product(html: str, url: str) -> ParsedProduct | None:
    """None, если на странице нет h1, то есть это не карточка товара."""
    soup = BeautifulSoup(html, "lxml")
    h1 = soup.find("h1")
    if not h1:
        return None
    ld = parse_jsonld(soup)
    lines = page_lines(soup)
    slug = urlparse(url).path.strip("/").split("/")[-1]

    # Блок рядом с заголовком берём после самого h1, а не после хлебных крошек
    head = [t.strip() for t in h1.find_all_next(string=True) if t.strip() and h1 not in t.parents][:30]
    head_text = "\n".join(head)

    ld_brand = ld.get("brand")
    brand = (ld_brand.get("name") if isinstance(ld_brand, dict) else ld_brand) or (
        head[0] if head and not head[0].startswith("Арт") else None
    )
    composition = next((line for line in head if re.search(r"\d+\s*%", line)), None)
    match = re.search(r"Арт\.?\s*\n?\s*([A-Za-zА-Яа-я0-9\-_/.]+)", head_text) or re.search(
        r"Арт\.?\s*([\w\-./]+)", head_text
    )
    article = match.group(1) if match else ld.get("sku")

    prices = sorted({to_int(x) for x in PRICE_RE.findall(head_text)})
    offers = ld.get("offers") if isinstance(ld.get("offers"), dict) else {}
    if not prices and offers.get("price"):
        prices = [int(float(offers["price"]))]
    # Две цены на странице: дешёвая актуальная, дорогая зачёркнутая
    price = prices[0] if prices else None
    old_price = prices[-1] if len(prices) > 1 and prices[-1] != prices[0] else None

    color_match = re.search(r"Цвет:\s*([^\n]+)", "\n".join(lines))

    sizes: list[str] = []
    try:
        start = next(i for i, line in enumerate(lines) if line == "Размер")
        end = next(i for i in range(start, len(lines)) if lines[i].startswith("Выберите размер"))
        sizes = [line for line in lines[start + 1 : end] if SIZE_RE.match(line)]
    except StopIteration:
        pass
    sizes = list(dict.fromkeys(sizes))

    category = None
    for link in h1.find_all_previous("a", href=re.compile(r"/catalog/[^/]+/?$")):
        category = {
            "slug": link["href"].rstrip("/").split("/")[-1],
            "name": link.get_text(" ", strip=True),
            "url": urljoin(settings.PARSER_BASE_URL, link["href"]),
        }
        break

    return ParsedProduct(
        url=url,
        slug=slug,
        name=h1.get_text(" ", strip=True),
        brand=brand,
        composition=composition,
        article=article,
        price=price,
        old_price=old_price,
        currency="RUB",
        color=color_match.group(1).strip() if color_match else None,
        sizes=sizes,
        sizes_stock=size_stock(soup, sizes),
        color_links=color_siblings(html, slug),
        category=category,
        images=collect_images(soup, html),
        care_text=section_text(soup, "Состав и уход"),
        measurements=section_text(soup, "Замеры изделия"),
        description=ld.get("description"),
        materials=parse_materials(composition),
        attributes={},
    )
