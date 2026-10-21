from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime, utc_now
from app.models.catalog import Product


class OrderStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    SHIPPED = "shipped"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_user_created", "user_id", "created_at"),
        Index("ix_orders_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    customer_name: Mapped[str] = mapped_column(String(150))
    customer_phone: Mapped[str] = mapped_column(String(32), index=True)
    customer_email: Mapped[str | None] = mapped_column(String(255))

    # cdek_pvz, cdek_courier, russian_post или showroom_pickup
    delivery_method: Mapped[str] = mapped_column(String(50), default="cdek_pvz")
    delivery_city: Mapped[str] = mapped_column(String(120), default="Москва")
    delivery_address: Mapped[str] = mapped_column(String(500))
    cdek_pvz_code: Mapped[str | None] = mapped_column(String(64))
    customer_comment: Mapped[str | None] = mapped_column(Text)

    items_total: Mapped[int] = mapped_column(Integer, default=0)
    delivery_cost: Mapped[int] = mapped_column(Integer, default=0)
    total_amount: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(10), default="RUB")

    status: Mapped[str] = mapped_column(String(32), default=OrderStatus.PENDING.value, index=True)
    payment_id: Mapped[str | None] = mapped_column(String(120), unique=True, index=True)
    payment_url: Mapped[str | None] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    paid_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), index=True)
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("product_sizes.id", ondelete="SET NULL"))

    product_name: Mapped[str] = mapped_column(String(300))
    product_slug: Mapped[str] = mapped_column(String(255))
    color: Mapped[str | None] = mapped_column(String(80))
    size: Mapped[str] = mapped_column(String(32), default="ONE SIZE")

    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[int] = mapped_column(Integer)
    subtotal: Mapped[int] = mapped_column(Integer)

    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()


class OrderTelegramMessage(Base):
    """Последнее сообщение по заказу в каждом чате: owner (личка) и staff (группа)."""

    __tablename__ = "order_telegram_messages"
    __table_args__ = (UniqueConstraint("order_id", "role", name="uq_order_telegram_role"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    chat_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(BigInteger)


class PaymentEvent(Base):
    """Обработанные уведомления шлюза. Повтор того же события отвечает duplicate и ничего не меняет."""

    __tablename__ = "payment_events"
    __table_args__ = (UniqueConstraint("payment_id", "event", name="uq_payment_event"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[str] = mapped_column(String(120))
    event: Mapped[str] = mapped_column(String(40))
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    result: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
