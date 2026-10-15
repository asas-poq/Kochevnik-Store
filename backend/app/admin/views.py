"""
Модуль настройки Админ-панели на базе `sqladmin` (`app/admin/views.py`).
Предоставляет удобный веб-интерфейс по адресу `http://localhost:8000/admin`
для управления товарами, остатками, фотографиями, категориями, очередью парсера,
отзывами покупателей и заказами.
"""

from fastapi import FastAPI
from sqladmin import Admin, ModelView

from app.core.logging import get_logger
from app.db.session import engine
from app.models.catalog import (
    Category,
    CrawlQueue,
    PriceHistory,
    Product,
    ProductColorLink,
    ProductImage,
    ProductMaterial,
    ProductSize,
    Source,
)
from app.models.interactions import ProductLike, ProductReview
from app.models.order import Order, OrderItem
from app.models.user import User

logger = get_logger(__name__)


class ProductAdmin(ModelView, model=Product):
    """Управление карточками товаров в админ-панели."""
    name = "Товар"
    name_plural = "Товары (Каталог)"
    icon = "fa-solid fa-shirt"
    column_list = [
        Product.id,
        Product.article,
        Product.name,
        Product.color,
        Product.composition,
        Product.current_price,
        Product.old_price,
        Product.likes_count,
        Product.reviews_count,
        Product.status,
    ]
    column_searchable_list = [Product.name, Product.slug, Product.article, Product.color]
    column_sortable_list = [
        Product.id,
        Product.current_price,
        Product.likes_count,
        Product.reviews_count,
    ]


class CategoryAdmin(ModelView, model=Category):
    """Управление категориями товаров."""
    name = "Категория"
    name_plural = "Категории"
    icon = "fa-solid fa-folder-tree"
    column_list = [Category.id, Category.name, Category.slug, Category.parent_id]
    column_searchable_list = [Category.name, Category.slug]


class ProductSizeAdmin(ModelView, model=ProductSize):
    """Управление размерами и складскими остатками (`stock`)."""
    name = "Размер / Остаток"
    name_plural = "Размеры и Склад"
    icon = "fa-solid fa-boxes-stacked"
    column_list = [
        ProductSize.id,
        ProductSize.product_id,
        ProductSize.size,
        ProductSize.stock,
        ProductSize.sku,
        ProductSize.measurements_cm,
    ]
    column_sortable_list = [ProductSize.stock, ProductSize.product_id]


class ProductImageAdmin(ModelView, model=ProductImage):
    """Управление фотографиями товаров."""
    name = "Фото товара"
    name_plural = "Фотографии товаров"
    icon = "fa-solid fa-images"
    column_list = [
        ProductImage.id,
        ProductImage.product_id,
        ProductImage.position,
        ProductImage.url,
    ]


class ProductMaterialAdmin(ModelView, model=ProductMaterial):
    """Управление материалами состава (кашемир, пух яка, верблюжья шерсть, кожа)."""
    name = "Материал"
    name_plural = "Материалы состава"
    icon = "fa-solid fa-layer-group"
    column_list = [
        ProductMaterial.id,
        ProductMaterial.product_id,
        ProductMaterial.material,
        ProductMaterial.percent,
    ]


class ProductColorLinkAdmin(ModelView, model=ProductColorLink):
    """Перелинковка цветов одной модели товара."""
    name = "Связь цвета"
    name_plural = "Связи цветов (Color Links)"
    icon = "fa-solid fa-palette"
    column_list = [
        ProductColorLink.id,
        ProductColorLink.product_id,
        ProductColorLink.sibling_slug,
    ]


class PriceHistoryAdmin(ModelView, model=PriceHistory):
    """История изменения цен из парсера."""
    name = "Запись цены"
    name_plural = "История цен"
    icon = "fa-solid fa-chart-line"
    column_list = [
        PriceHistory.id,
        PriceHistory.product_id,
        PriceHistory.price,
        PriceHistory.old_price,
        PriceHistory.scraped_at,
    ]


class CrawlQueueAdmin(ModelView, model=CrawlQueue):
    """Мониторинг очереди обхода ссылок парсера (`crawl_queue`)."""
    name = "Ссылка парсера"
    name_plural = "Очередь парсера (Crawl Queue)"
    icon = "fa-solid fa-spider"
    column_list = [
        CrawlQueue.id,
        CrawlQueue.url,
        CrawlQueue.status,
        CrawlQueue.error,
        CrawlQueue.updated_at,
    ]
    column_searchable_list = [CrawlQueue.url, CrawlQueue.status]


class OrderAdmin(ModelView, model=Order):
    """Управление заказами и оплатами по СБП."""
    name = "Заказ"
    name_plural = "Заказы покупателей"
    icon = "fa-solid fa-cart-shopping"
    column_list = [
        Order.id,
        Order.customer_name,
        Order.customer_phone,
        Order.delivery_method,
        Order.delivery_city,
        Order.total_amount,
        Order.status,
        Order.created_at,
        Order.paid_at,
    ]
    column_searchable_list = [Order.customer_name, Order.customer_phone, Order.payment_id]
    column_sortable_list = [Order.id, Order.total_amount, Order.created_at]


class OrderItemAdmin(ModelView, model=OrderItem):
    """Позиции внутри заказов."""
    name = "Позиция заказа"
    name_plural = "Позиции заказов"
    icon = "fa-solid fa-list-check"
    column_list = [
        OrderItem.id,
        OrderItem.order_id,
        OrderItem.product_name,
        OrderItem.color,
        OrderItem.size,
        OrderItem.quantity,
        OrderItem.subtotal,
    ]


class ProductReviewAdmin(ModelView, model=ProductReview):
    """Модерация отзывов и ответов магазина."""
    name = "Отзыв / Комментарий"
    name_plural = "Отзывы и Комментарии"
    icon = "fa-solid fa-comments"
    column_list = [
        ProductReview.id,
        ProductReview.product_id,
        ProductReview.user_id,
        ProductReview.rating,
        ProductReview.comment_text,
        ProductReview.is_approved,
        ProductReview.created_at,
    ]


class ProductLikeAdmin(ModelView, model=ProductLike):
    """Просмотр лайков товаров."""
    name = "Лайк"
    name_plural = "Лайки (Избранное)"
    icon = "fa-solid fa-heart"
    column_list = [
        ProductLike.id,
        ProductLike.user_id,
        ProductLike.product_id,
        ProductLike.created_at,
    ]


class UserAdmin(ModelView, model=User):
    """Управление пользователями и администраторами."""
    name = "Пользователь"
    name_plural = "Пользователи"
    icon = "fa-solid fa-users"
    column_list = [
        User.id,
        User.email,
        User.phone,
        User.full_name,
        User.role,
        User.is_active,
        User.created_at,
    ]
    column_searchable_list = [User.email, User.phone, User.full_name]


class SourceAdmin(ModelView, model=Source):
    """Источники парсинга."""
    name = "Источник"
    name_plural = "Источники парсера"
    icon = "fa-solid fa-database"
    column_list = [Source.id, Source.name, Source.base_url]


def setup_admin(app: FastAPI) -> Admin:
    """
    Регистрирует все представления моделей в `sqladmin` и монтирует админку по адресу `/admin`.
    """
    admin = Admin(
        app=app,
        engine=engine,
        title="Ulaanbaatar Cashmere — Админ-панель",
        base_url="/admin",
    )
    admin.add_view(ProductAdmin)
    admin.add_view(CategoryAdmin)
    admin.add_view(ProductSizeAdmin)
    admin.add_view(ProductImageAdmin)
    admin.add_view(ProductMaterialAdmin)
    admin.add_view(ProductColorLinkAdmin)
    admin.add_view(PriceHistoryAdmin)
    admin.add_view(OrderAdmin)
    admin.add_view(OrderItemAdmin)
    admin.add_view(ProductReviewAdmin)
    admin.add_view(ProductLikeAdmin)
    admin.add_view(UserAdmin)
    admin.add_view(CrawlQueueAdmin)
    admin.add_view(SourceAdmin)

    logger.info("Админ-панель sqladmin успешно инициализирована по адресу /admin")
    return admin
