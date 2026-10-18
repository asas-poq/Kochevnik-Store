"""
Модель связи заказа с сообщениями в Telegram (`app/models/telegram_message.py`).

Для каждого оплаченного заказа бот отправляет сообщения в личный чат владельца (с кнопками)
и в группу сотрудников (без кнопок, только статус). Чтобы при смене статуса отредактировать
сообщение владельца и заменить сообщение в группе, нужно помнить `message_id`.
Новая таблица создаётся автоматически через `Base.metadata.create_all` — миграция не нужна.
"""

from sqlalchemy import BigInteger, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OrderTelegramMessage(Base):
    """Таблица `order_telegram_messages`: одно актуальное сообщение заказа на каждую роль."""

    __tablename__ = "order_telegram_messages"
    __table_args__ = (
        UniqueConstraint("order_id", "role", name="uq_order_telegram_role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="'owner' — личка владельца, 'staff' — группа"
    )
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)