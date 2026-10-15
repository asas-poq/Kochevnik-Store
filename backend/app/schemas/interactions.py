"""
Pydantic v2 схемы для лайков (избранного) и комментариев/отзывов к товарам (`app/schemas/interactions.py`).
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class LikeToggleOut(BaseModel):
    """Ответ при нажатии на сердечко (лайк / удаление из избранного)."""
    product_id: int
    product_slug: str
    is_liked: bool = Field(..., description="Текущее состояние: True — лайк стоит, False — лайк убран")
    likes_count: int = Field(..., description="Обновленное общее число лайков у товара")
    message: str


class ReviewAuthorOut(BaseModel):
    """Краткая информация об авторе отзыва/комментария."""
    id: int
    full_name: str

    model_config = ConfigDict(from_attributes=True)


class ReviewCreateIn(BaseModel):
    """Входные данные для добавления нового отзыва или комментария к товару."""
    rating: int = Field(
        5, ge=1, le=5, description="Оценка товара по 5-балльной шкале (от 1 до 5)"
    )
    comment_text: str = Field(
        ...,
        min_length=3,
        max_length=3000,
        description="Текст отзыва или вопроса о товаре (например, о мягкости кашемира или размерной сетке)",
    )
    advantages: Optional[str] = Field(
        None, max_length=500, description="Достоинства изделия (например: Невероятно мягкий, не колется)"
    )
    disadvantages: Optional[str] = Field(
        None, max_length=500, description="Недостатки или особенности"
    )
    parent_id: Optional[int] = Field(
        None, description="ID родительского комментария, если это ответ в ветке обсуждения"
    )


class ReviewAdminReplyIn(BaseModel):
    """Схема для добавления официального ответа магазина (только для администратора)."""
    admin_reply: str = Field(
        ..., min_length=2, max_length=2000, description="Официальный ответ бренда Ulaanbaatar"
    )


class ReviewOut(BaseModel):
    """Схема отображения отзыва/комментария со списком вложенных ответов."""
    id: int
    product_id: int
    user_id: int
    parent_id: Optional[int] = None
    rating: int
    comment_text: str
    advantages: Optional[str] = None
    disadvantages: Optional[str] = None
    is_verified_purchase: bool
    admin_reply: Optional[str] = None
    created_at: datetime
    user: Optional[ReviewAuthorOut] = None
    replies: List["ReviewOut"] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
