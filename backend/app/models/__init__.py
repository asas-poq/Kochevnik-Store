"""
Единая точка экспорта всех моделей SQLAlchemy (`app/models/__init__.py`).
Импорт этого пакета гарантирует, что все таблицы зарегистрированы в `Base.metadata`
для автогенерации миграций Alembic и создания таблиц.
"""

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
from app.models.order import Order, OrderItem
from app.models.session import UserSession
from app.models.telegram_message import OrderTelegramMessage
from app.models.user import User

__all__ = [
    "Source",
    "Category",
    "CrawlQueue",
    "Product",
    "PriceHistory",
    "ProductImage",
    "ProductMaterial",
    "ProductColorLink",
    "ProductSize",
    "ProductAttribute",
    "User",
    "UserSession",
    "ProductLike",
    "ProductReview",
    "Order",
    "OrderItem",
    "OrderTelegramMessage",
]