"""
Модель пользователя (`app/models/user.py`).
Отвечает за хранение учетных записей покупателей и администраторов магазина.
"""

from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """
    Таблица `users` — зарегистрированные пользователи и администраторы.
    Позволяет пользователям сохранять товары в избранное (лайки),
    оставлять отзывы/комментарии и просматривать историю своих заказов.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(32), unique=True, index=True, nullable=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    # Роль пользователя: 'customer' (покупатель) или 'admin' (управляющий магазином)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="customer")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Предпочитаемый адрес доставки / ПВЗ СДЭК по умолчанию
    default_city: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    default_delivery_address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    # Связи с лайками, отзывами и заказами
    likes: Mapped[List["ProductLike"]] = relationship(
        "ProductLike", back_populates="user", cascade="all, delete-orphan"
    )
    reviews: Mapped[List["ProductReview"]] = relationship(
        "ProductReview", back_populates="user", cascade="all, delete-orphan"
    )
    orders: Mapped[List["Order"]] = relationship(
        "Order", back_populates="user"
    )

    @property
    def is_admin(self) -> bool:
        """Проверяет, обладает ли пользователь правами администратора."""
        return self.role == "admin"

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role}>"
