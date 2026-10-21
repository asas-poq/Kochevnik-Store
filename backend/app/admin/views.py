from fastapi import FastAPI
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from app.core.config import settings
from app.core.security import verify_password
from app.db.session import AsyncSessionLocal, engine
from app.models import (
    Category,
    CrawlQueue,
    Order,
    OrderItem,
    PriceHistory,
    Product,
    ProductColorLink,
    ProductImage,
    ProductLike,
    ProductMaterial,
    ProductReview,
    ProductSize,
    Source,
    User,
)
from sqlalchemy import select


class AdminAuth(AuthenticationBackend):
    """Вход в панель по email и паролю существующего пользователя с ролью admin."""

    async def login(self, request: Request) -> bool:
        form = await request.form()
        email = str(form.get("username", "")).strip().lower()
        async with AsyncSessionLocal() as db:
            user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if not (user and user.is_admin and user.is_active):
            return False
        if not verify_password(str(form.get("password", "")), user.hashed_password):
            return False
        request.session["admin_id"] = user.id
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        admin_id = request.session.get("admin_id")
        if not admin_id:
            return False
        async with AsyncSessionLocal() as db:
            user = await db.get(User, admin_id)
        return bool(user and user.is_admin and user.is_active)


class ProductAdmin(ModelView, model=Product):
    name, name_plural, icon = "Товар", "Товары", "fa-solid fa-shirt"
    column_list = [
        Product.id, Product.article, Product.name, Product.color, Product.current_price,
        Product.old_price, Product.likes_count, Product.reviews_count, Product.status,
    ]  # fmt: skip
    column_searchable_list = [Product.name, Product.slug, Product.article, Product.color]
    column_sortable_list = [Product.id, Product.current_price, Product.likes_count, Product.reviews_count]


class CategoryAdmin(ModelView, model=Category):
    name, name_plural, icon = "Категория", "Категории", "fa-solid fa-folder-tree"
    column_list = [Category.id, Category.name, Category.slug, Category.parent_id]
    column_searchable_list = [Category.name, Category.slug]


class ProductSizeAdmin(ModelView, model=ProductSize):
    name, name_plural, icon = "Размер", "Размеры и склад", "fa-solid fa-boxes-stacked"
    column_list = [ProductSize.id, ProductSize.product_id, ProductSize.size, ProductSize.stock, ProductSize.sku]
    column_sortable_list = [ProductSize.stock, ProductSize.product_id]


class ProductImageAdmin(ModelView, model=ProductImage):
    name, name_plural, icon = "Фото", "Фотографии", "fa-solid fa-images"
    column_list = [ProductImage.id, ProductImage.product_id, ProductImage.position, ProductImage.url]


class ProductMaterialAdmin(ModelView, model=ProductMaterial):
    name, name_plural, icon = "Материал", "Материалы", "fa-solid fa-layer-group"
    column_list = [ProductMaterial.id, ProductMaterial.product_id, ProductMaterial.material, ProductMaterial.percent]


class ProductColorLinkAdmin(ModelView, model=ProductColorLink):
    name, name_plural, icon = "Связь цвета", "Связи цветов", "fa-solid fa-palette"
    column_list = [ProductColorLink.id, ProductColorLink.product_id, ProductColorLink.sibling_slug]


class PriceHistoryAdmin(ModelView, model=PriceHistory):
    name, name_plural, icon = "Цена", "История цен", "fa-solid fa-chart-line"
    column_list = [PriceHistory.id, PriceHistory.product_id, PriceHistory.price, PriceHistory.old_price, PriceHistory.scraped_at]
    can_create = can_edit = can_delete = False


class CrawlQueueAdmin(ModelView, model=CrawlQueue):
    name, name_plural, icon = "Ссылка парсера", "Очередь парсера", "fa-solid fa-spider"
    column_list = [CrawlQueue.id, CrawlQueue.url, CrawlQueue.status, CrawlQueue.error, CrawlQueue.updated_at]
    column_searchable_list = [CrawlQueue.url, CrawlQueue.status]


class OrderAdmin(ModelView, model=Order):
    name, name_plural, icon = "Заказ", "Заказы", "fa-solid fa-cart-shopping"
    column_list = [
        Order.id, Order.customer_name, Order.customer_phone, Order.delivery_method,
        Order.total_amount, Order.status, Order.created_at, Order.paid_at,
    ]  # fmt: skip
    column_searchable_list = [Order.customer_name, Order.customer_phone, Order.payment_id]
    column_sortable_list = [Order.id, Order.total_amount, Order.created_at]
    # Статус и остатки меняет только сервис заказов, иначе ломается резерв на складе
    can_create = can_edit = can_delete = False


class OrderItemAdmin(ModelView, model=OrderItem):
    name, name_plural, icon = "Позиция заказа", "Позиции заказов", "fa-solid fa-list-check"
    column_list = [OrderItem.id, OrderItem.order_id, OrderItem.product_name, OrderItem.size, OrderItem.quantity, OrderItem.subtotal]
    can_create = can_edit = can_delete = False


class ProductReviewAdmin(ModelView, model=ProductReview):
    name, name_plural, icon = "Отзыв", "Отзывы", "fa-solid fa-comments"
    column_list = [
        ProductReview.id, ProductReview.product_id, ProductReview.user_id, ProductReview.rating,
        ProductReview.comment_text, ProductReview.is_approved, ProductReview.created_at,
    ]  # fmt: skip


class ProductLikeAdmin(ModelView, model=ProductLike):
    name, name_plural, icon = "Лайк", "Лайки", "fa-solid fa-heart"
    column_list = [ProductLike.id, ProductLike.user_id, ProductLike.product_id, ProductLike.created_at]
    can_create = can_edit = False


class UserAdmin(ModelView, model=User):
    name, name_plural, icon = "Пользователь", "Пользователи", "fa-solid fa-users"
    column_list = [User.id, User.email, User.phone, User.full_name, User.role, User.is_active, User.created_at]
    column_searchable_list = [User.email, User.phone, User.full_name]
    column_details_exclude_list = [User.hashed_password]
    form_excluded_columns = [User.hashed_password]
    can_create = False


class SourceAdmin(ModelView, model=Source):
    name, name_plural, icon = "Источник", "Источники парсера", "fa-solid fa-database"
    column_list = [Source.id, Source.name, Source.base_url]


VIEWS = (
    ProductAdmin, CategoryAdmin, ProductSizeAdmin, ProductImageAdmin, ProductMaterialAdmin,
    ProductColorLinkAdmin, PriceHistoryAdmin, OrderAdmin, OrderItemAdmin, ProductReviewAdmin,
    ProductLikeAdmin, UserAdmin, CrawlQueueAdmin, SourceAdmin,
)  # fmt: skip


def setup_admin(app: FastAPI) -> Admin:
    admin = Admin(
        app=app,
        engine=engine,
        title="Ulaanbaatar Cashmere, админ-панель",
        base_url="/admin",
        authentication_backend=AdminAuth(secret_key=settings.SECRET_KEY),
    )
    for view in VIEWS:
        admin.add_view(view)
    return admin
