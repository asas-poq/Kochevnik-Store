"""
Pydantic v2 схемы для лайков (избранного) и комментариев/отзывов к товарам (`app/schemas/interactions.py`).
"""

from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    rating: Optional[int] = None  # у ответов (parent_id != None) оценки нет
    comment_text: str
    advantages: Optional[str] = None
    disadvantages: Optional[str] = None
    is_verified_purchase: bool
    admin_reply: Optional[str] = None
    created_at: datetime
    user: Optional[ReviewAuthorOut] = None
    replies: List["ReviewOut"] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ReviewUpdateIn(BaseModel):
    """Частичное редактирование своего отзыва (передавать только изменяемые поля)."""

    rating: Optional[int] = Field(None, ge=1, le=5)
    comment_text: Optional[str] = Field(None, min_length=3, max_length=3000)
    advantages: Optional[str] = Field(None, max_length=500)
    disadvantages: Optional[str] = Field(None, max_length=500)

    @model_validator(mode="after")
    def at_least_one_field(self):
        if not self.model_fields_set:
            raise ValueError("Передайте хотя бы одно поле для изменения.")
        return self


class MyReviewOut(ReviewOut):
    """Отзыв в личном кабинете: + краткая информация о товаре и статус модерации."""

    is_approved: bool
    product_slug: str
    product_name: str
    product_image_url: Optional[str] = None


class ReviewSummaryOut(BaseModel):
    """Сводка рейтинга товара: средняя оценка и распределение по звёздам."""

    product_id: int
    total_reviews: int
    average_rating: float
    distribution: Dict[int, int] = Field(..., description="{5: 12, 4: 3, 3: 0, 2: 1, 1: 0}")
