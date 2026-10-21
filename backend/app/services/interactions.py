from enum import Enum

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.cache import Cache
from app.core.config import settings
from app.core.errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError, UnprocessableError
from app.core.logging import get_logger
from app.models import Order, OrderItem, OrderStatus, Product, ProductLike, ProductReview, User
from app.schemas.catalog import ProductCardOut
from app.schemas.interactions import (
    LikeToggleOut,
    MyReviewOut,
    ReviewAdminReplyIn,
    ReviewCreateIn,
    ReviewListOut,
    ReviewOut,
    ReviewSummaryOut,
    ReviewUpdateIn,
)
from app.services.catalog import card_loader_options

logger = get_logger(__name__)


class ReviewSort(str, Enum):
    newest = "newest"
    oldest = "oldest"
    rating_desc = "rating_desc"
    rating_asc = "rating_asc"


def _scope(product_id: int) -> str:
    return f"reviews:{product_id}"


async def _get_product(db: AsyncSession, product_id: int) -> Product:
    product = await db.get(Product, product_id)
    if not product:
        raise NotFoundError("Товар не найден.")
    return product


async def recalculate_stats(db: AsyncSession, product_id: int) -> int:
    """Пересчёт в той же транзакции, что и изменение. Без commit, его делает вызывающий.
    В рейтинг идут только одобренные корневые отзывы с оценкой, ответы не считаются."""
    likes = (
        await db.execute(select(func.count(ProductLike.id)).where(ProductLike.product_id == product_id))
    ).scalar_one()
    count, avg = (
        await db.execute(
            select(func.count(ProductReview.id), func.avg(ProductReview.rating)).where(
                ProductReview.product_id == product_id,
                ProductReview.is_approved.is_(True),
                ProductReview.parent_id.is_(None),
                ProductReview.rating.is_not(None),
            )
        )
    ).one()
    product = await db.get(Product, product_id)
    if product:
        product.likes_count = likes
        product.reviews_count = count or 0
        product.rating_avg = round(float(avg or 0.0), 2)
    return likes


async def toggle_like(db: AsyncSession, user: User, product_id: int) -> LikeToggleOut:
    slug = (await _get_product(db, product_id)).slug
    existing = (
        await db.execute(
            select(ProductLike).where(ProductLike.user_id == user.id, ProductLike.product_id == product_id)
        )
    ).scalar_one_or_none()

    if existing:
        await db.delete(existing)
        liked = False
    else:
        db.add(ProductLike(user_id=user.id, product_id=product_id))
        liked = True
    try:
        await db.flush()
        likes = await recalculate_stats(db, product_id)
        await db.commit()
    except IntegrityError:
        # Параллельный запрос уже поставил этот лайк
        await db.rollback()
        liked = True
        likes = await recalculate_stats(db, product_id)
        await db.commit()

    return LikeToggleOut(
        product_id=product_id,
        product_slug=slug,
        is_liked=liked,
        likes_count=likes,
        message="Товар добавлен в избранное" if liked else "Товар удалён из избранного",
    )


async def my_likes(db: AsyncSession, user: User, limit: int, offset: int) -> list[ProductCardOut]:
    products = (
        (
            await db.execute(
                select(Product)
                .join(ProductLike, ProductLike.product_id == Product.id)
                .where(ProductLike.user_id == user.id)
                .options(*card_loader_options())
                .order_by(ProductLike.created_at.desc(), ProductLike.id.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    cards = [ProductCardOut.model_validate(p) for p in products]
    for card in cards:
        card.is_liked_by_me = True
    return cards


def _review_options():  # type: ignore[no-untyped-def]
    return (
        selectinload(ProductReview.user),
        selectinload(ProductReview.replies).options(
            selectinload(ProductReview.user), selectinload(ProductReview.replies)
        ),
    )


def _my_review_options():  # type: ignore[no-untyped-def]
    return (*_review_options(), selectinload(ProductReview.product).selectinload(Product.images))


async def _load_review(db: AsyncSession, review_id: int) -> ProductReview:
    review = (
        await db.execute(
            select(ProductReview)
            .where(ProductReview.id == review_id)
            .options(*_review_options())
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if not review:
        raise NotFoundError("Отзыв не найден.")
    return review


def _to_my_review(review: ProductReview) -> MyReviewOut:
    product = review.product
    return MyReviewOut(
        **ReviewOut.model_validate(review).model_dump(),
        is_approved=review.is_approved,
        product_slug=product.slug,
        product_name=product.name,
        product_image_url=product.images[0].url if product.images else None,
    )


async def list_reviews(
    db: AsyncSession,
    cache: Cache,
    product_id: int,
    *,
    limit: int,
    offset: int,
    sort: ReviewSort,
    rating: int | None,
    only_verified: bool,
) -> list[ReviewOut]:
    await _get_product(db, product_id)

    async def build() -> ReviewListOut:
        conditions = [
            ProductReview.product_id == product_id,
            ProductReview.is_approved.is_(True),
            ProductReview.parent_id.is_(None),
        ]
        if rating is not None:
            conditions.append(ProductReview.rating == rating)
        if only_verified:
            conditions.append(ProductReview.is_verified_purchase.is_(True))
        order = {
            ReviewSort.newest: (ProductReview.created_at.desc(), ProductReview.id.desc()),
            ReviewSort.oldest: (ProductReview.created_at.asc(), ProductReview.id.asc()),
            ReviewSort.rating_desc: (ProductReview.rating.desc(), ProductReview.created_at.desc()),
            ReviewSort.rating_asc: (ProductReview.rating.asc(), ProductReview.created_at.desc()),
        }[sort]
        rows = (
            (
                await db.execute(
                    select(ProductReview)
                    .where(*conditions)
                    .options(
                        selectinload(ProductReview.user),
                        selectinload(ProductReview.replies.and_(ProductReview.is_approved.is_(True))).options(
                            selectinload(ProductReview.user), selectinload(ProductReview.replies)
                        ),
                    )
                    .order_by(*order)
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return ReviewListOut([ReviewOut.model_validate(r) for r in rows])

    params = {"limit": limit, "offset": offset, "sort": sort.value, "rating": rating, "verified": only_verified}
    result = await cache.remember(_scope(product_id), params, settings.REVIEWS_CACHE_TTL, ReviewListOut, build)
    return result.root


async def reviews_summary(db: AsyncSession, cache: Cache, product_id: int) -> ReviewSummaryOut:
    await _get_product(db, product_id)

    async def build() -> ReviewSummaryOut:
        rows = (
            await db.execute(
                select(ProductReview.rating, func.count(ProductReview.id))
                .where(
                    ProductReview.product_id == product_id,
                    ProductReview.is_approved.is_(True),
                    ProductReview.parent_id.is_(None),
                    ProductReview.rating.is_not(None),
                )
                .group_by(ProductReview.rating)
            )
        ).all()
        distribution = {star: 0 for star in range(5, 0, -1)}
        for star, count in rows:
            distribution[int(star)] = count
        total = sum(distribution.values())
        average = round(sum(s * c for s, c in distribution.items()) / total, 2) if total else 0.0
        return ReviewSummaryOut(
            product_id=product_id, total_reviews=total, average_rating=average, distribution=distribution
        )

    return await cache.remember(
        _scope(product_id), {"view": "summary"}, settings.REVIEWS_CACHE_TTL, ReviewSummaryOut, build
    )


async def create_review(
    db: AsyncSession, cache: Cache, user: User, product_id: int, payload: ReviewCreateIn
) -> ReviewOut:
    """Корневой отзыв только после получения товара: нужен заказ с ним в статусе completed.
    Ответить на чужой корневой отзыв может любой вошедший пользователь."""
    await _get_product(db, product_id)

    if payload.parent_id is not None:
        parent = await db.get(ProductReview, payload.parent_id)
        if not parent or parent.product_id != product_id or not parent.is_approved:
            raise NotFoundError("Родительский отзыв не найден.")
        if parent.parent_id is not None:
            raise BadRequestError("Отвечать можно только на корневой отзыв.")
        rating = None
    else:
        rating = payload.rating
        duplicate = await db.execute(
            select(ProductReview.id)
            .where(
                ProductReview.user_id == user.id,
                ProductReview.product_id == product_id,
                ProductReview.parent_id.is_(None),
            )
            .limit(1)
        )
        if duplicate.scalar_one_or_none() is not None:
            raise ConflictError("Вы уже оставляли отзыв на этот товар. Отредактируйте его.")

    bought = await db.execute(
        select(OrderItem.id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.user_id == user.id,
            OrderItem.product_id == product_id,
            Order.status == OrderStatus.COMPLETED.value,
        )
        .limit(1)
    )
    verified = bought.scalar_one_or_none() is not None
    if payload.parent_id is None and not verified:
        raise ForbiddenError("Оставить отзыв можно только после получения заказа с этим товаром.")

    review = ProductReview(
        product_id=product_id,
        user_id=user.id,
        parent_id=payload.parent_id,
        rating=rating,
        comment_text=payload.comment_text,
        advantages=payload.advantages,
        disadvantages=payload.disadvantages,
        is_verified_purchase=verified,
        is_approved=not settings.REVIEWS_PREMODERATION,
    )
    db.add(review)
    try:
        await db.flush()
        review_id = review.id
        await recalculate_stats(db, product_id)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError("Вы уже оставляли отзыв на этот товар.") from None

    await cache.bump(_scope(product_id))
    logger.info("Отзыв создан", extra={"user_id": user.id, "review_id": review_id, "product_id": product_id})
    return ReviewOut.model_validate(await _load_review(db, review_id))


async def update_review(
    db: AsyncSession, cache: Cache, user: User, review_id: int, payload: ReviewUpdateIn
) -> ReviewOut:
    review = await _load_review(db, review_id)
    if review.user_id != user.id:
        raise ForbiddenError("Вы можете редактировать только свои отзывы.")

    data = payload.model_dump(exclude_unset=True)
    if "rating" in data:
        if review.parent_id is not None:
            raise BadRequestError("У ответа не может быть оценки.")
        if data["rating"] is None:
            raise UnprocessableError("Оценку нельзя убрать у отзыва.")
    for field, value in data.items():
        setattr(review, field, value)
    if settings.REVIEWS_PREMODERATION:
        review.is_approved = False

    await db.flush()
    await recalculate_stats(db, review.product_id)
    await db.commit()
    await cache.bump(_scope(review.product_id))
    return ReviewOut.model_validate(await _load_review(db, review_id))


async def delete_review(db: AsyncSession, cache: Cache, user: User, review_id: int) -> None:
    """Свой отзыв удаляет автор, любой админ. Вместе с корневым уходят и ответы на него."""
    review = await db.get(ProductReview, review_id)
    if not review:
        raise NotFoundError("Отзыв не найден.")
    if review.user_id != user.id and not user.is_admin:
        raise ForbiddenError("Вы можете удалять только свои отзывы.")
    await _remove(db, cache, review)


async def _remove(db: AsyncSession, cache: Cache, review: ProductReview) -> None:
    product_id = review.product_id
    await db.execute(delete(ProductReview).where(ProductReview.parent_id == review.id))
    await db.execute(delete(ProductReview).where(ProductReview.id == review.id))
    await db.flush()
    await recalculate_stats(db, product_id)
    await db.commit()
    await cache.bump(_scope(product_id))


async def set_admin_reply(
    db: AsyncSession, cache: Cache, review_id: int, payload: ReviewAdminReplyIn
) -> ReviewOut:
    review = await _load_review(db, review_id)
    review.admin_reply = payload.admin_reply
    await db.commit()
    await cache.bump(_scope(review.product_id))
    return ReviewOut.model_validate(await _load_review(db, review_id))


async def list_user_reviews(db: AsyncSession, user_id: int, limit: int, offset: int) -> list[MyReviewOut]:
    rows = (
        (
            await db.execute(
                select(ProductReview)
                .where(ProductReview.user_id == user_id)
                .options(*_my_review_options())
                .order_by(ProductReview.created_at.desc(), ProductReview.id.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return [_to_my_review(r) for r in rows]


async def pending_reviews(db: AsyncSession, limit: int, offset: int) -> list[ReviewOut]:
    rows = (
        (
            await db.execute(
                select(ProductReview)
                .where(ProductReview.is_approved.is_(False))
                .options(*_review_options())
                .order_by(ProductReview.created_at, ProductReview.id)
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return [ReviewOut.model_validate(r) for r in rows]


async def approve_review(db: AsyncSession, cache: Cache, review_id: int) -> ReviewOut:
    review = await _load_review(db, review_id)
    review.is_approved = True
    await db.flush()
    await recalculate_stats(db, review.product_id)
    await db.commit()
    await cache.bump(_scope(review.product_id))
    return ReviewOut.model_validate(await _load_review(db, review_id))


async def reject_review(db: AsyncSession, cache: Cache, review_id: int) -> None:
    review = await db.get(ProductReview, review_id)
    if not review:
        raise NotFoundError("Отзыв не найден.")
    await _remove(db, cache, review)
