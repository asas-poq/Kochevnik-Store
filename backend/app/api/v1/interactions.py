"""
Роутер социального взаимодействия: Лайки (Избранное) и Комментарии/Отзывы (`app/api/v1/interactions.py`).
Использует `BackgroundTasks` для асинхронного пересчета счетчиков лайков и среднего рейтинга товара.
"""

from enum import Enum
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.api.deps import AdminUserDep, CurrentUserDep, DBSessionDep
from app.core.logging import get_logger
from app.models.catalog import Product
from app.models.interactions import ProductLike, ProductReview
from app.models.order import Order, OrderItem, OrderStatus
from app.schemas.catalog import ProductCardOut
from app.schemas.interactions import (
    LikeToggleOut,
    MyReviewOut,
    ReviewAdminReplyIn,
    ReviewCreateIn,
    ReviewOut,
    ReviewSummaryOut,
    ReviewUpdateIn,
)
from app.services.tasks import recalculate_product_stats_task

logger = get_logger(__name__)

router = APIRouter(prefix="/interactions", tags=["4. Лайки (Избранное) и Комментарии"])

# Если True — новые и отредактированные отзывы попадают на премодерацию (is_approved=False).
REVIEWS_PREMODERATION = False

# Отзыв можно оставить только после того, как продавец отметил заказ доставленным (completed).
VERIFIED_ORDER_STATUSES = (OrderStatus.COMPLETED.value,)


class ReviewSort(str, Enum):
    newest = "newest"
    oldest = "oldest"
    rating_desc = "rating_desc"
    rating_asc = "rating_asc"


# ==============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================================================================
def _review_load_options():
    """Стандартный набор eager-загрузки для сериализации ReviewOut (без MissingGreenlet)."""
    return (
        selectinload(ProductReview.user),
        selectinload(ProductReview.replies).options(
            selectinload(ProductReview.user),
            selectinload(ProductReview.replies),
        ),
    )


async def _load_review(db: DBSessionDep, review_id: int) -> Optional[ProductReview]:
    """Загружает отзыв со всеми связями; populate_existing гарантирует свежие данные после commit."""
    stmt = (
        select(ProductReview)
        .where(ProductReview.id == review_id)
        .options(*_review_load_options())
        .execution_options(populate_existing=True)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _get_review_or_404(db: DBSessionDep, review_id: int) -> ProductReview:
    review = await _load_review(db, review_id)
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Отзыв не найден."
        )
    return review


async def _ensure_product_exists(db: DBSessionDep, product_id: int) -> Product:
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден."
        )
    return product


def _to_my_review_out(review: ProductReview) -> MyReviewOut:
    """Собирает MyReviewOut: данные отзыва + краткая информация о товаре."""
    base = ReviewOut.model_validate(review).model_dump()
    product = review.product
    base.pop("is_approved", None)
    return MyReviewOut(
        **base,
        is_approved=review.is_approved,
        product_slug=product.slug,
        product_name=product.name,
        product_image_url=product.images[0].url if product.images else None,
    )


def _my_reviews_options():
    return (
        *_review_load_options(),
        selectinload(ProductReview.product).selectinload(Product.images),
    )


# ==============================================================================
# РУЧКА 1: Поставить или убрать лайк товару (Toggle Like / Избранное)
# ==============================================================================
@router.post(
    "/products/{product_id}/like",
    response_model=LikeToggleOut,
    summary="Поставить или убрать лайк товару (добавить/удалить из Избранного)",
)
async def toggle_product_like(
    product_id: int,
    background_tasks: BackgroundTasks,
    current_user: CurrentUserDep,
    db: DBSessionDep,
) -> LikeToggleOut:
    """
    Переключает состояние лайка (сердечка) для выбранного товара:
    - Если пользователь еще не лайкал товар — добавляет запись в `product_likes` и увеличивает счетчик.
    - Если лайк уже стоял — удаляет запись из `product_likes` и уменьшает счетчик.
    - Защищено от гонок: уникальный индекс (user_id, product_id) + обработка IntegrityError.
    - Запускает фоновую задачу синхронизации статистики товара (`BackgroundTasks`).
    """
    product = await _ensure_product_exists(db, product_id)

    existing_q = await db.execute(
        select(ProductLike).where(
            ProductLike.user_id == current_user.id,
            ProductLike.product_id == product_id,
        )
    )
    existing_like = existing_q.scalar_one_or_none()

    if existing_like:
        await db.delete(existing_like)
        product.likes_count = max(0, product.likes_count - 1)
        is_liked = False
        msg = "Товар удален из избранного"
    else:
        db.add(ProductLike(user_id=current_user.id, product_id=product_id))
        product.likes_count += 1
        is_liked = True
        msg = "Товар добавлен в избранное"

    # Запоминаем значения до commit, чтобы не обращаться к «протухшим» атрибутам
    slug = product.slug
    likes_count = product.likes_count

    try:
        await db.commit()
    except IntegrityError:
        # Параллельный запрос уже поставил лайк — считаем, что товар в избранном
        await db.rollback()
        await db.refresh(product)
        logger.warning(
            f"Конфликт лайка: пользователь ID={current_user.id}, товар ID={product_id}"
        )
        return LikeToggleOut(
            product_id=product_id,
            product_slug=product.slug,
            is_liked=True,
            likes_count=product.likes_count,
            message="Товар добавлен в избранное",
        )

    logger.info(
        f"Пользователь ID={current_user.id} {'поставил' if is_liked else 'убрал'} лайк "
        f"товару ID={product_id} ({slug})"
    )

    # Фоновый точный пересчет статистики (страховка от рассинхрона счетчика)
    background_tasks.add_task(recalculate_product_stats_task, product_id)

    return LikeToggleOut(
        product_id=product_id,
        product_slug=slug,
        is_liked=is_liked,
        likes_count=likes_count,
        message=msg,
    )


# ==============================================================================
# РУЧКА 2: Получить список всех лайкнутых товаров («Моё Избранное»)
# ==============================================================================
@router.get(
    "/my-likes",
    response_model=List[ProductCardOut],
    summary="Получить все товары из списка «Избранное» текущего пользователя",
)
async def list_my_liked_products(
    current_user: CurrentUserDep,
    db: DBSessionDep,
    limit: int = Query(20, ge=1, le=100, description="Сколько товаров вернуть"),
    offset: int = Query(0, ge=0, description="Сколько товаров пропустить"),
) -> List[ProductCardOut]:
    """
    Возвращает карточки товаров, которым текущий авторизованный покупатель поставил лайк
    (с пагинацией, сначала самые недавние).
    """
    logger.info(f"Запрос списка избранного для пользователя ID={current_user.id}")

    stmt = (
        select(Product)
        .join(ProductLike, Product.id == ProductLike.product_id)
        .where(ProductLike.user_id == current_user.id)
        .options(
            selectinload(Product.images),
            selectinload(Product.sizes),
            selectinload(Product.materials),
        )
        .order_by(ProductLike.created_at.desc(), ProductLike.id.desc())
        .limit(limit)
        .offset(offset)
    )
    products = (await db.execute(stmt)).scalars().all()

    cards: List[ProductCardOut] = []
    for p in products:
        card = ProductCardOut.model_validate(p)
        card.is_liked_by_me = True
        cards.append(card)
    return cards


# ==============================================================================
# РУЧКА 3: Получить все отзывы и комментарии к товару
# ==============================================================================
@router.get(
    "/products/{product_id}/reviews",
    response_model=List[ReviewOut],
    summary="Получить список отзывов и комментариев к товару",
)
async def list_product_reviews(
    product_id: int,
    db: DBSessionDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort: ReviewSort = Query(ReviewSort.newest, description="Сортировка"),
    rating: Optional[int] = Query(None, ge=1, le=5, description="Только с этой оценкой"),
    only_verified: bool = Query(False, description="Только подтверждённые покупки"),
) -> List[ReviewOut]:
    """
    Возвращает древовидный список одобренных отзывов к товару:
    - Для несуществующего товара — 404.
    - Корневые отзывы с пагинацией, фильтрами (оценка, подтверждённая покупка) и сортировкой.
    - Внутри каждого отзыва возвращаются одобренные ответы (`replies`) и ответ бутика (`admin_reply`).
    """
    await _ensure_product_exists(db, product_id)
    logger.debug(f"Запрос отзывов для товара ID={product_id}")

    conditions = [
        ProductReview.product_id == product_id,
        ProductReview.is_approved.is_(True),
        ProductReview.parent_id.is_(None),
    ]
    if rating is not None:
        conditions.append(ProductReview.rating == rating)
    if only_verified:
        conditions.append(ProductReview.is_verified_purchase.is_(True))

    order_map = {
        ReviewSort.newest: (ProductReview.created_at.desc(), ProductReview.id.desc()),
        ReviewSort.oldest: (ProductReview.created_at.asc(), ProductReview.id.asc()),
        ReviewSort.rating_desc: (
            ProductReview.rating.desc(),
            ProductReview.created_at.desc(),
        ),
        ReviewSort.rating_asc: (
            ProductReview.rating.asc(),
            ProductReview.created_at.desc(),
        ),
    }

    stmt = (
        select(ProductReview)
        .where(*conditions)
        .options(
            selectinload(ProductReview.user),
            selectinload(
                ProductReview.replies.and_(ProductReview.is_approved.is_(True))
            ).options(
                selectinload(ProductReview.user),
                selectinload(ProductReview.replies),
            ),
        )
        .order_by(*order_map[sort])
        .limit(limit)
        .offset(offset)
    )
    reviews = (await db.execute(stmt)).scalars().all()
    return [ReviewOut.model_validate(r) for r in reviews]


# ==============================================================================
# РУЧКА 3.1: Сводка по рейтингу товара (распределение по звёздам)
# ==============================================================================
@router.get(
    "/products/{product_id}/reviews/summary",
    response_model=ReviewSummaryOut,
    summary="Сводка рейтинга товара: средняя оценка и распределение по звёздам",
)
async def get_product_reviews_summary(
    product_id: int,
    db: DBSessionDep,
) -> ReviewSummaryOut:
    """
    Считает по одобренным корневым отзывам с оценкой: общее число, среднюю оценку
    и сколько отзывов с 5, 4, 3, 2 и 1 звездой.
    """
    await _ensure_product_exists(db, product_id)

    stmt = (
        select(ProductReview.rating, func.count(ProductReview.id))
        .where(
            ProductReview.product_id == product_id,
            ProductReview.is_approved.is_(True),
            ProductReview.parent_id.is_(None),
            ProductReview.rating.is_not(None),
        )
        .group_by(ProductReview.rating)
    )
    rows = (await db.execute(stmt)).all()

    distribution = {star: 0 for star in range(5, 0, -1)}
    for star, cnt in rows:
        distribution[int(star)] = cnt

    total = sum(distribution.values())
    average = (
        round(sum(star * cnt for star, cnt in distribution.items()) / total, 2)
        if total
        else 0.0
    )
    return ReviewSummaryOut(
        product_id=product_id,
        total_reviews=total,
        average_rating=average,
        distribution=distribution,
    )


# ==============================================================================
# РУЧКА 4: Оставить отзыв или комментарий к товару
# ==============================================================================
@router.post(
    "/products/{product_id}/reviews",
    response_model=ReviewOut,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить новый отзыв или комментарий к товару",
)
async def create_product_review(
    product_id: int,
    payload: ReviewCreateIn,
    background_tasks: BackgroundTasks,
    current_user: CurrentUserDep,
    db: DBSessionDep,
) -> ReviewOut:
    """
    Создает новый отзыв (с оценкой 1–5) или ответ на чужой отзыв (`parent_id`):
    1. Корневой отзыв: не более одного на товар от одного пользователя (иначе 409), оценка обязательна.
    2. Ответ: `parent_id` должен существовать, быть одобренным корневым отзывом этого же товара;
       оценка у ответов не сохраняется и в рейтинг не попадает.
    3. Корневой отзыв (с оценкой) можно оставить ТОЛЬКО после получения товара: у пользователя
       должен быть заказ с этим товаром в статусе `completed` (его выставляет продавец через
       `PATCH /orders/admin/{id}/status`). Иначе — 403. Отзыв получает `is_verified_purchase = True`.
       Ответы на чужие отзывы (`parent_id`) доступны любому авторизованному пользователю.
    4. В фоне пересчитывает средний рейтинг товара.
    """
    await _ensure_product_exists(db, product_id)

    # --- Валидация parent_id / рейтинга ---
    if payload.parent_id is not None:
        parent = await db.get(ProductReview, payload.parent_id)
        if not parent or parent.product_id != product_id or not parent.is_approved:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Родительский отзыв не найден.",
            )
        if parent.parent_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Отвечать можно только на корневой отзыв.",
            )
        rating = None  # у ответов оценки нет
    else:
        rating = payload.rating

        duplicate_q = await db.execute(
            select(ProductReview.id)
            .where(
                ProductReview.user_id == current_user.id,
                ProductReview.product_id == product_id,
                ProductReview.parent_id.is_(None),
            )
            .limit(1)
        )
        if duplicate_q.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Вы уже оставляли отзыв на этот товар. Отредактируйте его.",
            )

    # --- Подтверждённая покупка ---
    purchase_q = await db.execute(
        select(OrderItem.id)
        .join(Order, OrderItem.order_id == Order.id)
        .where(
            Order.user_id == current_user.id,
            OrderItem.product_id == product_id,
            Order.status.in_(VERIFIED_ORDER_STATUSES),
        )
        .limit(1)
    )
    is_verified = purchase_q.scalar_one_or_none() is not None

    if payload.parent_id is None and not is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Оставить отзыв можно только после получения заказа с этим товаром.",
        )

    review = ProductReview(
        product_id=product_id,
        user_id=current_user.id,
        parent_id=payload.parent_id,
        rating=rating,
        comment_text=payload.comment_text,
        advantages=payload.advantages,
        disadvantages=payload.disadvantages,
        is_verified_purchase=is_verified,
        is_approved=not REVIEWS_PREMODERATION,
    )
    db.add(review)
    try:
        await db.flush()
        review_id = review.id
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Вы уже оставляли отзыв на этот товар.",
        )

    created_review = await _get_review_or_404(db, review_id)

    logger.info(
        f"Пользователь ID={current_user.id} оставил отзыв ID={review_id} "
        f"к товару ID={product_id} (оценка={rating}, verified={is_verified}, "
        f"reply_to={payload.parent_id})"
    )

    background_tasks.add_task(recalculate_product_stats_task, product_id)

    return ReviewOut.model_validate(created_review)


# ==============================================================================
# РУЧКА 5: Официальный ответ магазина на отзыв покупателя (для Администратора)
# ==============================================================================
@router.patch(
    "/reviews/{review_id}/admin-reply",
    response_model=ReviewOut,
    summary="Ответить на отзыв от лица бутика Ulaanbaatar (только Администратор)",
)
async def add_admin_reply_to_review(
    review_id: int,
    payload: ReviewAdminReplyIn,
    admin_user: AdminUserDep,
    db: DBSessionDep,
) -> ReviewOut:
    """
    Позволяет администратору опубликовать официальный ответ магазина под отзывом клиента.
    """
    review = await _get_review_or_404(db, review_id)
    review.admin_reply = payload.admin_reply
    await db.commit()

    # Перезагружаем объект запросом вместо refresh — связи остаются загруженными
    review = await _get_review_or_404(db, review_id)

    logger.info(
        f"Администратор ID={admin_user.id} добавил ответ бутика к отзыву ID={review_id}"
    )
    return ReviewOut.model_validate(review)


# ==============================================================================
# РУЧКА 6: Все отзывы текущего пользователя («Мои отзывы»)
# ==============================================================================
@router.get(
    "/my-reviews",
    response_model=List[MyReviewOut],
    summary="Получить все отзывы текущего пользователя",
)
async def list_my_reviews(
    current_user: CurrentUserDep,
    db: DBSessionDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> List[MyReviewOut]:
    """
    Возвращает отзывы и ответы текущего пользователя вместе с краткой информацией о товаре
    (slug, название, картинка). Включает отзывы, ожидающие модерации (`is_approved=False`).
    """
    stmt = (
        select(ProductReview)
        .where(ProductReview.user_id == current_user.id)
        .options(*_my_reviews_options())
        .order_by(ProductReview.created_at.desc(), ProductReview.id.desc())
        .limit(limit)
        .offset(offset)
    )
    reviews = (await db.execute(stmt)).scalars().all()
    return [_to_my_review_out(r) for r in reviews]


# ==============================================================================
# РУЧКА 7: Редактировать свой отзыв
# ==============================================================================
@router.patch(
    "/reviews/{review_id}",
    response_model=ReviewOut,
    summary="Отредактировать свой отзыв",
)
async def update_my_review(
    review_id: int,
    payload: ReviewUpdateIn,
    background_tasks: BackgroundTasks,
    current_user: CurrentUserDep,
    db: DBSessionDep,
) -> ReviewOut:
    """
    Автор может изменить оценку, текст, достоинства и недостатки своего отзыва.
    Чужой отзыв — 403. У ответов (не корневых отзывов) оценку менять нельзя.
    При включённой премодерации отредактированный отзыв снова уходит на проверку.
    """
    review = await _get_review_or_404(db, review_id)

    if review.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Вы можете редактировать только свои отзывы.",
        )

    data = payload.model_dump(exclude_unset=True)

    if "rating" in data:
        if review.parent_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="У ответа не может быть оценки.",
            )
        if data["rating"] is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Оценку нельзя убрать у отзыва.",
            )

    for field, value in data.items():
        setattr(review, field, value)

    if REVIEWS_PREMODERATION:
        review.is_approved = False

    product_id = review.product_id
    await db.commit()

    review = await _get_review_or_404(db, review_id)
    logger.info(
        f"Пользователь ID={current_user.id} отредактировал отзыв ID={review_id} "
        f"(поля: {', '.join(data.keys())})"
    )

    background_tasks.add_task(recalculate_product_stats_task, product_id)
    return ReviewOut.model_validate(review)


# ==============================================================================
# РУЧКА 8: Удалить отзыв (автор или администратор)
# ==============================================================================
@router.delete(
    "/reviews/{review_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить отзыв (автор или администратор)",
)
async def delete_review(
    review_id: int,
    background_tasks: BackgroundTasks,
    current_user: CurrentUserDep,
    db: DBSessionDep,
) -> Response:
    """
    Автор удаляет свой отзыв, администратор — любой. Остальным — 403.
    При удалении корневого отзыва удаляются и все ответы к нему.
    """
    review = await db.get(ProductReview, review_id)
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Отзыв не найден."
        )

    is_admin = bool(getattr(current_user, "is_admin", False))
    if review.user_id != current_user.id and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Вы можете удалять только свои отзывы.",
        )

    product_id = review.product_id
    await db.execute(delete(ProductReview).where(ProductReview.parent_id == review_id))
    await db.execute(delete(ProductReview).where(ProductReview.id == review_id))
    await db.commit()

    logger.info(
        f"Пользователь ID={current_user.id} (admin={is_admin}) удалил отзыв ID={review_id} "
        f"товара ID={product_id}"
    )

    background_tasks.add_task(recalculate_product_stats_task, product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==============================================================================
# АДМИН-РУЧКИ: модерация и просмотр отзывов пользователя
# ==============================================================================
@router.get(
    "/admin/reviews/pending",
    response_model=List[ReviewOut],
    summary="Отзывы на модерации (только Администратор)",
)
async def admin_list_pending_reviews(
    admin_user: AdminUserDep,
    db: DBSessionDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> List[ReviewOut]:
    stmt = (
        select(ProductReview)
        .where(ProductReview.is_approved.is_(False))
        .options(*_review_load_options())
        .order_by(ProductReview.created_at.asc(), ProductReview.id.asc())
        .limit(limit)
        .offset(offset)
    )
    reviews = (await db.execute(stmt)).scalars().all()
    return [ReviewOut.model_validate(r) for r in reviews]


@router.post(
    "/admin/reviews/{review_id}/approve",
    response_model=ReviewOut,
    summary="Одобрить отзыв (только Администратор)",
)
async def admin_approve_review(
    review_id: int,
    background_tasks: BackgroundTasks,
    admin_user: AdminUserDep,
    db: DBSessionDep,
) -> ReviewOut:
    review = await _get_review_or_404(db, review_id)
    review.is_approved = True
    product_id = review.product_id
    await db.commit()

    review = await _get_review_or_404(db, review_id)
    logger.info(f"Администратор ID={admin_user.id} одобрил отзыв ID={review_id}")

    background_tasks.add_task(recalculate_product_stats_task, product_id)
    return ReviewOut.model_validate(review)


@router.post(
    "/admin/reviews/{review_id}/reject",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Отклонить (удалить) отзыв (только Администратор)",
)
async def admin_reject_review(
    review_id: int,
    background_tasks: BackgroundTasks,
    admin_user: AdminUserDep,
    db: DBSessionDep,
) -> Response:
    review = await db.get(ProductReview, review_id)
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Отзыв не найден."
        )

    product_id = review.product_id
    await db.execute(delete(ProductReview).where(ProductReview.parent_id == review_id))
    await db.execute(delete(ProductReview).where(ProductReview.id == review_id))
    await db.commit()

    logger.info(f"Администратор ID={admin_user.id} отклонил отзыв ID={review_id}")

    background_tasks.add_task(recalculate_product_stats_task, product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/admin/users/{user_id}/reviews",
    response_model=List[MyReviewOut],
    summary="Все отзывы конкретного пользователя (только Администратор)",
)
async def admin_list_user_reviews(
    user_id: int,
    admin_user: AdminUserDep,
    db: DBSessionDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> List[MyReviewOut]:
    stmt = (
        select(ProductReview)
        .where(ProductReview.user_id == user_id)
        .options(*_my_reviews_options())
        .order_by(ProductReview.created_at.desc(), ProductReview.id.desc())
        .limit(limit)
        .offset(offset)
    )
    reviews = (await db.execute(stmt)).scalars().all()
    return [_to_my_review_out(r) for r in reviews]