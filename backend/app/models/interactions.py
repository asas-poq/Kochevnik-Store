"""
Модели социального взаимодействия с товарами (`app/models/interactions.py`):
- `product_likes` — лайки / добавление товаров в «Избранное»
- `product_reviews` — комментарии, вопросы и отзывы покупателей с оценкой (1–5 звезд),
  поддержкой древовидных ответов (`parent_id`) и официального ответа магазина (`admin_reply`).
"""

from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProductLike(Base):
    """
    Таблица `product_likes` — лайки товаров (список желаний / Избранное).
    Один пользователь может поставить лайк конкретному товару только один раз
    (гарантируется уникальным индексом `uq_user_product_like`).
    """

    __tablename__ = "product_likes"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_user_product_like"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="likes")
    product: Mapped["Product"] = relationship("Product", back_populates="likes")

    def __repr__(self) -> str:
        return f"<ProductLike user_id={self.user_id} product_id={self.product_id}>"


class ProductReview(Base):
    """
    Таблица `product_reviews` — комментарии и отзывы покупателей к товарам.
    Поддерживает:
    - Оценку от 1 до 5 звезд (`rating`)
    - Текст комментария (`comment_text`), достоинства (`advantages`) и недостатки (`disadvantages`)
    - Пометку реальной покупки (`is_verified_purchase`)
    - Ответы других пользователей (`parent_id`) и официальный ответ бренда (`admin_reply`)
    """

    __tablename__ = "product_reviews"
    __table_args__ = (
        # Один пользователь — один корневой отзыв на товар (ответы parent_id != NULL не ограничиваются)
        Index(
            "uq_review_user_product_root",
            "user_id",
            "product_id",
            unique=True,
            postgresql_where=text("parent_id IS NULL"),
            sqlite_where=text("parent_id IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("product_reviews.id", ondelete="CASCADE"), nullable=True
    )

    rating: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        default=5,
        comment="Оценка товара от 1 до 5. NULL у ответов (parent_id != NULL)",
    )
    comment_text: Mapped[str] = mapped_column(Text, nullable=False)
    advantages: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    disadvantages: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    is_verified_purchase: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    is_approved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    admin_reply: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Официальный ответ бутика Ulaanbaatar"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    # Связи
    product: Mapped["Product"] = relationship("Product", back_populates="reviews")
    user: Mapped["User"] = relationship("User", back_populates="reviews")
    parent: Mapped[Optional["ProductReview"]] = relationship(
        "ProductReview", remote_side=[id], back_populates="replies"
    )
    replies: Mapped[List["ProductReview"]] = relationship(
        "ProductReview", back_populates="parent", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ProductReview id={self.id} product_id={self.product_id} rating={self.rating}>"
