from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import AdminUserDep, CurrentUserDep, DBSessionDep
from app.core.cache import CacheDep
from app.core.config import settings
from app.core.ratelimit import rate_limit
from app.schemas.catalog import ProductCardOut
from app.schemas.common import ErrorOut
from app.schemas.interactions import (
    LikeToggleOut,
    MyReviewOut,
    ReviewAdminReplyIn,
    ReviewCreateIn,
    ReviewOut,
    ReviewSummaryOut,
    ReviewUpdateIn,
)
from app.services import interactions
from app.services.interactions import ReviewSort

router = APIRouter(prefix="/interactions", tags=["4. Лайки и отзывы"])

review_limit = Depends(rate_limit("reviews", settings.RATE_REVIEWS_PER_MIN))
NOT_FOUND = {404: {"model": ErrorOut, "description": "Не найдено"}}
FORBIDDEN = {403: {"model": ErrorOut, "description": "Нет прав"}}


@router.post(
    "/products/{product_id}/like",
    response_model=LikeToggleOut,
    summary="Поставить или снять лайк",
    responses=NOT_FOUND,
)
async def toggle_like(product_id: int, user: CurrentUserDep, db: DBSessionDep) -> LikeToggleOut:
    """Повторный вызов снимает лайк. Одновременные запросы не создают дубль."""
    return await interactions.toggle_like(db, user, product_id)


@router.get("/my-likes", response_model=list[ProductCardOut], summary="Избранное текущего пользователя")
async def my_likes(
    user: CurrentUserDep, db: DBSessionDep, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)
) -> list[ProductCardOut]:
    return await interactions.my_likes(db, user, limit, offset)


@router.get(
    "/products/{product_id}/reviews",
    response_model=list[ReviewOut],
    summary="Отзывы к товару",
    responses=NOT_FOUND,
)
async def list_reviews(
    product_id: int,
    db: DBSessionDep,
    cache: CacheDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort: ReviewSort = Query(ReviewSort.newest),
    rating: int | None = Query(None, ge=1, le=5),
    only_verified: bool = Query(False, description="Только подтверждённые покупки"),
) -> list[ReviewOut]:
    """Одобренные корневые отзывы с одобренными ответами. Ответ кэшируется на 2 минуты."""
    return await interactions.list_reviews(
        db, cache, product_id, limit=limit, offset=offset, sort=sort, rating=rating, only_verified=only_verified
    )


@router.get(
    "/products/{product_id}/reviews/summary",
    response_model=ReviewSummaryOut,
    summary="Средняя оценка и распределение по звёздам",
    responses=NOT_FOUND,
)
async def reviews_summary(product_id: int, db: DBSessionDep, cache: CacheDep) -> ReviewSummaryOut:
    return await interactions.reviews_summary(db, cache, product_id)


@router.post(
    "/products/{product_id}/reviews",
    response_model=ReviewOut,
    status_code=status.HTTP_201_CREATED,
    summary="Оставить отзыв или ответ",
    dependencies=[review_limit],
    responses={
        403: {"model": ErrorOut, "description": "Нет заказа с этим товаром в статусе completed"},
        409: {"model": ErrorOut, "description": "Отзыв на этот товар уже есть"},
        429: {"model": ErrorOut, "description": "Слишком много запросов"},
        **NOT_FOUND,
    },
)
async def create_review(
    product_id: int, payload: ReviewCreateIn, user: CurrentUserDep, db: DBSessionDep, cache: CacheDep
) -> ReviewOut:
    """Корневой отзыв доступен после получения товара. С parent_id создаётся ответ на корневой отзыв,
    его может оставить любой вошедший пользователь, оценка у ответа не сохраняется."""
    return await interactions.create_review(db, cache, user, product_id, payload)


@router.patch(
    "/reviews/{review_id}/admin-reply",
    response_model=ReviewOut,
    summary="Ответ магазина на отзыв (админ)",
    responses={**NOT_FOUND, **FORBIDDEN},
)
async def admin_reply(
    review_id: int, payload: ReviewAdminReplyIn, admin: AdminUserDep, db: DBSessionDep, cache: CacheDep
) -> ReviewOut:
    return await interactions.set_admin_reply(db, cache, review_id, payload)


@router.get("/my-reviews", response_model=list[MyReviewOut], summary="Мои отзывы, в том числе на модерации")
async def my_reviews(
    user: CurrentUserDep, db: DBSessionDep, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)
) -> list[MyReviewOut]:
    return await interactions.list_user_reviews(db, user.id, limit, offset)


@router.patch(
    "/reviews/{review_id}",
    response_model=ReviewOut,
    summary="Изменить свой отзыв",
    dependencies=[review_limit],
    responses={**NOT_FOUND, **FORBIDDEN},
)
async def update_review(
    review_id: int, payload: ReviewUpdateIn, user: CurrentUserDep, db: DBSessionDep, cache: CacheDep
) -> ReviewOut:
    """При включённой премодерации изменённый отзыв снова уходит на проверку."""
    return await interactions.update_review(db, cache, user, review_id, payload)


@router.delete(
    "/reviews/{review_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить отзыв",
    responses={**NOT_FOUND, **FORBIDDEN},
)
async def delete_review(review_id: int, user: CurrentUserDep, db: DBSessionDep, cache: CacheDep) -> Response:
    """Свой удаляет автор, любой админ. Вместе с корневым отзывом удаляются ответы."""
    await interactions.delete_review(db, cache, user, review_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/admin/reviews/pending", response_model=list[ReviewOut], summary="Отзывы на модерации (админ)")
async def pending_reviews(
    admin: AdminUserDep, db: DBSessionDep, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)
) -> list[ReviewOut]:
    return await interactions.pending_reviews(db, limit, offset)


@router.post(
    "/admin/reviews/{review_id}/approve",
    response_model=ReviewOut,
    summary="Одобрить отзыв (админ)",
    responses=NOT_FOUND,
)
async def approve_review(review_id: int, admin: AdminUserDep, db: DBSessionDep, cache: CacheDep) -> ReviewOut:
    return await interactions.approve_review(db, cache, review_id)


@router.post(
    "/admin/reviews/{review_id}/reject",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Отклонить и удалить отзыв (админ)",
    responses=NOT_FOUND,
)
async def reject_review(review_id: int, admin: AdminUserDep, db: DBSessionDep, cache: CacheDep) -> Response:
    await interactions.reject_review(db, cache, review_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/admin/users/{user_id}/reviews", response_model=list[MyReviewOut], summary="Отзывы пользователя (админ)"
)
async def user_reviews(
    user_id: int, admin: AdminUserDep, db: DBSessionDep,
    limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
) -> list[MyReviewOut]:
    return await interactions.list_user_reviews(db, user_id, limit, offset)
