from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime, utc_now
from app.models.catalog import Product
from app.models.user import User


class ProductLike(Base):
    __tablename__ = "product_likes"
    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_user_product_like"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class ProductReview(Base):
    __tablename__ = "product_reviews"
    __table_args__ = (
        # Один корневой отзыв на пользователя и товар. Ответы (parent_id не NULL) не ограничены
        Index(
            "uq_review_user_product_root",
            "user_id",
            "product_id",
            unique=True,
            postgresql_where=text("parent_id IS NULL"),
            sqlite_where=text("parent_id IS NULL"),
        ),
        Index("ix_product_reviews_parent_id", "parent_id"),
        Index("ix_product_reviews_listing", "product_id", "is_approved", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("product_reviews.id", ondelete="CASCADE"))
    rating: Mapped[int | None] = mapped_column()  # у ответов NULL, default тут нельзя: None заменился бы на него
    comment_text: Mapped[str] = mapped_column(Text)
    advantages: Mapped[str | None] = mapped_column(String(500))
    disadvantages: Mapped[str | None] = mapped_column(String(500))
    is_verified_purchase: Mapped[bool] = mapped_column(Boolean, default=False)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=True)
    admin_reply: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)

    user: Mapped[User] = relationship()
    product: Mapped[Product] = relationship()
    replies: Mapped[list["ProductReview"]] = relationship(
        back_populates="parent", cascade="all, delete-orphan"
    )
    parent: Mapped["ProductReview | None"] = relationship(
        back_populates="replies", remote_side=[id]
    )