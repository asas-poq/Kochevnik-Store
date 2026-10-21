from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator


class LikeToggleOut(BaseModel):
    product_id: int
    product_slug: str
    is_liked: bool
    likes_count: int
    message: str


class ReviewAuthorOut(BaseModel):
    id: int
    full_name: str

    model_config = ConfigDict(from_attributes=True)


class ReviewCreateIn(BaseModel):
    rating: int = Field(5, ge=1, le=5, description="У ответов (parent_id) игнорируется")
    comment_text: str = Field(min_length=3, max_length=3000)
    advantages: str | None = Field(None, max_length=500)
    disadvantages: str | None = Field(None, max_length=500)
    parent_id: int | None = Field(None, description="Id корневого отзыва, если это ответ")


class ReviewAdminReplyIn(BaseModel):
    admin_reply: str = Field(min_length=2, max_length=2000)


class ReviewOut(BaseModel):
    id: int
    product_id: int
    user_id: int
    parent_id: int | None = None
    rating: int | None = None
    comment_text: str
    advantages: str | None = None
    disadvantages: str | None = None
    is_verified_purchase: bool
    admin_reply: str | None = None
    created_at: datetime
    user: ReviewAuthorOut | None = None
    replies: list["ReviewOut"] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ReviewListOut(RootModel[list[ReviewOut]]):
    pass


class ReviewUpdateIn(BaseModel):
    rating: int | None = Field(None, ge=1, le=5)
    comment_text: str | None = Field(None, min_length=3, max_length=3000)
    advantages: str | None = Field(None, max_length=500)
    disadvantages: str | None = Field(None, max_length=500)

    @model_validator(mode="after")
    def _not_empty(self) -> "ReviewUpdateIn":
        if not self.model_fields_set:
            raise ValueError("Передайте хотя бы одно поле для изменения.")
        return self


class MyReviewOut(ReviewOut):
    is_approved: bool
    product_slug: str
    product_name: str
    product_image_url: str | None = None


class ReviewSummaryOut(BaseModel):
    product_id: int
    total_reviews: int
    average_rating: float
    distribution: dict[int, int] = Field(description="Число отзывов по звёздам: {5: 12, 4: 3, ...}")
