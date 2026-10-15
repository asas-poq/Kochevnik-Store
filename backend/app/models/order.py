"""
Модели заказов, позиций заказа и платежей СБП (`app/models/order.py`).
Реализуют бизнес-логику чекаута, доставки (СДЭК ПВЗ/курьер, Почта России, Самовывоз из шоурума)
и оплаты через Систему Быстрых Платежей (ЮKassa / Т-Касса).
"""

from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Order(Base):
    """
    Таблица `orders` — заказы покупателей.
    Статусы заказа (`status`):
    - `pending` — создан, товар зарезервирован, ожидает оплаты по СБП
    - `paid` — успешно оплачен по QR-коду СБП (подтвержден вебхуком банка)
    - `shipped` — передан в доставку (СДЭК / Почта России)
    - `completed` — вручен покупателю
    - `cancelled` — отменен (остатки товара возвращены на склад)
    """

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Контактные данные покупателя на момент оформления
    customer_name: Mapped[str] = mapped_column(String(150), nullable=False)
    customer_phone: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    customer_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Параметры логистики и доставки
    delivery_method: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="cdek_pvz",
        comment="cdek_pvz | cdek_courier | russian_post | showroom_pickup",
    )
    delivery_city: Mapped[str] = mapped_column(String(120), nullable=False, default="Москва")
    delivery_address: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="Адрес курьерской доставки или код/адрес ПВЗ СДЭК"
    )
    cdek_pvz_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    customer_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Финансовые итоги заказа (в рублях)
    items_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    delivery_cost: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Бесплатно от 15 000 ₽"
    )
    total_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="RUB")

    # Статус заказа и данные платежа СБП
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", index=True
    )
    payment_id: Mapped[Optional[str]] = mapped_column(
        String(120), unique=True, index=True, nullable=True, comment="ID платежа в ЮKassa / Т-Кассе"
    )
    payment_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, comment="Ссылка на QR-код СБП для редиректа клиента"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    paid_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Связи
    user: Mapped[Optional["User"]] = relationship("User", back_populates="orders")
    items: Mapped[List["OrderItem"]] = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Order id={self.id} status={self.status} total={self.total_amount}>"


class OrderItem(Base):
    """
    Таблица `order_items` — товарные позиции внутри конкретного заказа.
    Фиксирует название, цвет, размер и цену товара на момент покупки.
    """

    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    variant_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("product_sizes.id", ondelete="SET NULL"), nullable=True
    )

    product_name: Mapped[str] = mapped_column(String(300), nullable=False)
    product_slug: Mapped[str] = mapped_column(String(255), nullable=False)
    color: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    size: Mapped[str] = mapped_column(String(32), nullable=False, default="ONE SIZE")

    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[int] = mapped_column(Integer, nullable=False)
    subtotal: Mapped[int] = mapped_column(Integer, nullable=False)

    order: Mapped["Order"] = relationship("Order", back_populates="items")
    product: Mapped["Product"] = relationship("Product")
