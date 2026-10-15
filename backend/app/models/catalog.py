"""
Модели каталога и парсера (`app/models/catalog.py`).
Полностью повторяют и расширяют структуру таблиц вашего парсера `ubcashmere.ru`:
- `sources` — источники парсинга
- `categories` — древовидные категории товаров
- `crawl_queue` — очередь обхода ссылок парсером
- `products` — основная таблица товаров (с полями парсера + денормализованными счетчиками для быстрой выборки)
- `price_history` — история изменения цен и скидок
- `product_images` — галерея фотографий товара с позицией сортировки
- `product_materials` — состав изделия в процентах (кашемир, пух яка, верблюжья шерсть, кожа)
- `product_color_links` — перелинковка соседних цветов одной модели (`sibling_slug`)
- `product_sizes` — размеры, HEX-коды и складские остатки (`stock`) для покупки и резервирования
- `product_attributes` — дополнительные характеристики товара (Плотность/Нить, Крой, Уход и т.д.)
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    """Возвращает текущее время в UTC."""
    return datetime.now(timezone.utc)


class Source(Base):
    """
    Таблица `sources` — источники данных парсера (например, `ubcashmere.ru`).
    """

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    base_url: Mapped[str] = mapped_column(String(255), nullable=False)

    # Связи
    categories: Mapped[List["Category"]] = relationship(
        "Category", back_populates="source", cascade="all, delete-orphan"
    )
    products: Mapped[List["Product"]] = relationship(
        "Product", back_populates="source", cascade="all, delete-orphan"
    )
    crawl_items: Mapped[List["CrawlQueue"]] = relationship(
        "CrawlQueue", back_populates="source", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Source id={self.id} name={self.name}>"


class Category(Base):
    """
    Таблица `categories` — категории каталога с поддержкой вложенности (`parent_id`).
    Поля в точности соответствуют дампу парсера.
    """

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, default=1
    )
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )

    # Связи
    source: Mapped["Source"] = relationship("Source", back_populates="categories")
    parent: Mapped[Optional["Category"]] = relationship(
        "Category", remote_side=[id], back_populates="children"
    )
    children: Mapped[List["Category"]] = relationship(
        "Category", back_populates="parent"
    )
    products: Mapped[List["Product"]] = relationship(
        "Product", back_populates="category"
    )

    def __repr__(self) -> str:
        return f"<Category id={self.id} slug={self.slug}>"


class CrawlQueue(Base):
    """
    Таблица `crawl_queue` — очередь ссылок парсера.
    Хранит статус парсинга каждой страницы (`pending`, `done`, `error`).
    """

    __tablename__ = "crawl_queue"
    __table_args__ = (
        UniqueConstraint("source_id", "url", name="uq_crawl_queue_source_url"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, default=1
    )
    url: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", index=True
    )  # 'pending', 'done', 'error'
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    source: Mapped["Source"] = relationship("Source", back_populates="crawl_items")

    def __repr__(self) -> str:
        return f"<CrawlQueue url={self.url} status={self.status}>"


class Product(Base):
    """
    Таблица `products` — основная карточка товара.
    Содержит все оригинальные поля парсера (`slug`, `article`, `color`, `color_group`,
    `composition`, `care_text`, `measurements`, `raw_json` и др.), а также
    актуальную цену (`current_price`, `old_price`) и счетчики лайков/отзывов
    для молниеносной фильтрации и сортировки в каталоге.
    """

    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_category_status", "category_id", "status"),
        Index("ix_products_color_group", "color_group"),
        Index("ix_products_current_price", "current_price"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, default=1
    )
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    article: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    brand: Mapped[Optional[str]] = mapped_column(
        String(120), default="Ulaanbaatar", nullable=True
    )
    category_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Атрибуты цвета и группировки моделей
    color: Mapped[Optional[str]] = mapped_column(String(80), index=True, nullable=True)
    color_hex: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True, default="#D8CFC4"
    )
    color_group: Mapped[Optional[str]] = mapped_column(
        String(255), index=True, nullable=True
    )

    # Характеристики монгольского трикотажа
    composition: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    density_yarn: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True, comment="Плотность / Нить (например, 2-ply 26/2 Nm)"
    )
    care_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    measurements: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Быстрые поля цены (синхронизируются с последней записью в price_history)
    current_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    old_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="RUB")

    # Денормализованные счетчики для быстрого рендера карточек в каталоге
    likes_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reviews_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rating_avg: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Статус и метаданные парсера
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", index=True
    )
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    raw_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # --- Связи с дочерними таблицами ---
    source: Mapped["Source"] = relationship("Source", back_populates="products")
    category: Mapped[Optional["Category"]] = relationship(
        "Category", back_populates="products"
    )
    images: Mapped[List["ProductImage"]] = relationship(
        "ProductImage",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductImage.position.asc()",
    )
    price_history: Mapped[List["PriceHistory"]] = relationship(
        "PriceHistory",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="PriceHistory.scraped_at.desc()",
    )
    materials: Mapped[List["ProductMaterial"]] = relationship(
        "ProductMaterial", back_populates="product", cascade="all, delete-orphan"
    )
    color_links: Mapped[List["ProductColorLink"]] = relationship(
        "ProductColorLink", back_populates="product", cascade="all, delete-orphan"
    )
    sizes: Mapped[List["ProductSize"]] = relationship(
        "ProductSize", back_populates="product", cascade="all, delete-orphan"
    )
    attributes: Mapped[List["ProductAttribute"]] = relationship(
        "ProductAttribute", back_populates="product", cascade="all, delete-orphan"
    )
    likes: Mapped[List["ProductLike"]] = relationship(
        "ProductLike", back_populates="product", cascade="all, delete-orphan"
    )
    reviews: Mapped[List["ProductReview"]] = relationship(
        "ProductReview", back_populates="product", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Product id={self.id} slug={self.slug} price={self.current_price}>"


class PriceHistory(Base):
    """
    Таблица `price_history` — история цен товара из парсера.
    """

    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    old_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="RUB")
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    product: Mapped["Product"] = relationship("Product", back_populates="price_history")


class ProductImage(Base):
    """
    Таблица `product_images` — фотографии товара в порядке `position`.
    Поддерживает как ссылки с CDN парсера, так и загруженные через админку S3-файлы.
    """

    __tablename__ = "product_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    url: Mapped[str] = mapped_column(String(500), nullable=False)

    product: Mapped["Product"] = relationship("Product", back_populates="images")


class ProductMaterial(Base):
    """
    Таблица `product_materials` — состав товара по материалам (например: кашемир 100%, пух яка 100%).
    Используется для точной фильтрации в каталоге (`?material=кашемир`).
    """

    __tablename__ = "product_materials"
    __table_args__ = (
        Index("ix_product_materials_material", "material"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    material: Mapped[str] = mapped_column(String(100), nullable=False)
    percent: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)

    product: Mapped["Product"] = relationship("Product", back_populates="materials")


class ProductColorLink(Base):
    """
    Таблица `product_color_links` — ссылки на другие цвета того же изделия (`sibling_slug`).
    Позволяет на карточке товара переключаться между цветами кружочками.
    """

    __tablename__ = "product_color_links"
    __table_args__ = (
        UniqueConstraint("product_id", "sibling_slug", name="uq_product_color_sibling"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sibling_slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    product: Mapped["Product"] = relationship("Product", back_populates="color_links")


class ProductSize(Base):
    """
    Таблица `product_sizes` (выступает также как `ProductVariant` для корзины и заказов).
    Хранит конкретный размер товара (`S`, `M`, `L`, `XL`, `ONE SIZE`),
    складской остаток (`stock`) и артикул варианта (`sku`).
    При оформлении заказа строка блокируется через `SELECT ... FOR UPDATE`.
    """

    __tablename__ = "product_sizes"
    __table_args__ = (
        UniqueConstraint("product_id", "size", name="uq_product_size"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    size: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    sku: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    measurements_cm: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, comment="Обмеры конкретного размера в см (Длина, ОГ, Рукав)"
    )

    product: Mapped["Product"] = relationship("Product", back_populates="sizes")


class ProductAttribute(Base):
    """
    Таблица `product_attributes` — произвольные атрибуты товара (ключ-значение).
    Например: {'Плотность': '2 нити', 'Страна производства': 'Монголия', 'Посадка': 'Свободный крой'}.
    """

    __tablename__ = "product_attributes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attr_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    attr_value: Mapped[str] = mapped_column(String(500), nullable=False)

    product: Mapped["Product"] = relationship("Product", back_populates="attributes")
