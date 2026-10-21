from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime, utc_now

if TYPE_CHECKING:
    from app.models.interactions import ProductLike


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    base_url: Mapped[str] = mapped_column(String(255))


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), default=1)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(String(500))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))


class CrawlQueue(Base):
    __tablename__ = "crawl_queue"
    __table_args__ = (
        UniqueConstraint("source_id", "url", name="uq_crawl_queue_source_url"),
        Index("ix_crawl_queue_source_status", "source_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), default=1)
    url: Mapped[str] = mapped_column(String(500), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_category_status", "category_id", "status"),
        Index("ix_products_current_price", "current_price"),
        Index("ix_products_status_first_seen", "status", "first_seen"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), default=1)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    url: Mapped[str | None] = mapped_column(String(500))
    article: Mapped[str | None] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(300), index=True)
    brand: Mapped[str | None] = mapped_column(String(120), default="Ulaanbaatar")
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )

    color: Mapped[str | None] = mapped_column(String(80), index=True)
    color_hex: Mapped[str | None] = mapped_column(String(16), default="#D8CFC4")
    color_group: Mapped[str | None] = mapped_column(String(255), index=True)

    composition: Mapped[str | None] = mapped_column(String(255))
    density_yarn: Mapped[str | None] = mapped_column(String(120))
    care_text: Mapped[str | None] = mapped_column(Text)
    measurements: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)

    current_price: Mapped[int] = mapped_column(Integer, default=0)
    old_price: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(10), default="RUB")

    # Счётчики пересчитываются в сервисе отзывов и лайков, чтобы каталог не считал их на лету
    likes_count: Mapped[int] = mapped_column(Integer, default=0)
    reviews_count: Mapped[int] = mapped_column(Integer, default=0)
    rating_avg: Mapped[float] = mapped_column(Float, default=0.0)

    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    first_seen: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    last_seen: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    category: Mapped[Category | None] = relationship()
    images: Mapped[list["ProductImage"]] = relationship(
        cascade="all, delete-orphan", order_by="ProductImage.position"
    )
    price_history: Mapped[list["PriceHistory"]] = relationship(
        cascade="all, delete-orphan", order_by="PriceHistory.scraped_at.desc()"
    )
    materials: Mapped[list["ProductMaterial"]] = relationship(cascade="all, delete-orphan")
    color_links: Mapped[list["ProductColorLink"]] = relationship(cascade="all, delete-orphan")
    sizes: Mapped[list["ProductSize"]] = relationship(cascade="all, delete-orphan")
    attributes: Mapped[list["ProductAttribute"]] = relationship(cascade="all, delete-orphan")
    likes: Mapped[list["ProductLike"]] = relationship(cascade="all, delete-orphan")

    def sku_for(self, size: str) -> str:
        return f"UB-{self.article or self.id}-{size.replace(' ', '')}"


class PriceHistory(Base):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    price: Mapped[int] = mapped_column(Integer)
    old_price: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(10), default="RUB")
    scraped_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class ProductImage(Base):
    __tablename__ = "product_images"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    url: Mapped[str] = mapped_column(String(500))


class ProductMaterial(Base):
    __tablename__ = "product_materials"
    __table_args__ = (Index("ix_product_materials_material", "material"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    material: Mapped[str] = mapped_column(String(100))
    percent: Mapped[float] = mapped_column(Float, default=100.0)


class ProductColorLink(Base):
    __tablename__ = "product_color_links"
    __table_args__ = (UniqueConstraint("product_id", "sibling_slug", name="uq_product_color_sibling"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    sibling_slug: Mapped[str] = mapped_column(String(255), index=True)


class ProductSize(Base):
    """Размер товара и есть вариант для корзины: на него ссылается order_items.variant_id."""

    __tablename__ = "product_sizes"
    __table_args__ = (UniqueConstraint("product_id", "size", name="uq_product_size"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    size: Mapped[str] = mapped_column(String(32), index=True)
    stock: Mapped[int] = mapped_column(Integer, default=5)
    sku: Mapped[str | None] = mapped_column(String(80))
    measurements_cm: Mapped[str | None] = mapped_column(String(255))


class ProductAttribute(Base):
    __tablename__ = "product_attributes"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    attr_key: Mapped[str] = mapped_column(String(120), index=True)
    attr_value: Mapped[str] = mapped_column(String(500))
