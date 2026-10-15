"""
Роутер социального взаимодействия: Лайки (Избранное) и Комментарии/Отзывы (`app/api/v1/interactions.py`).
Использует `BackgroundTasks` для асинхронного пересчета счетчиков лайков и среднего рейтинга товара.
"""

from typing import List
from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import AdminUserDep, CurrentUserDep, DBSessionDep
from app.core.logging import get_logger
from app.models.catalog import Product
from app.models.interactions import ProductLike, ProductReview
from app.models.order import Order, OrderItem
from app.schemas.catalog import ProductCardOut
from app.schemas.interactions import (
    LikeToggleOut,
    ReviewAdminReplyIn,
    ReviewCreateIn,
    ReviewOut,
)
from app.services.tasks import recalculate_product_stats_task

logger = get_logger(__name__)

router = APIRouter(prefix="/interactions", tags=["4. Лайки (Избранное) и Комментарии"])


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
    - Запускает фоновую задачу синхронизации статистики товара (`BackgroundTasks`).
    """
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден."
        )

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
        logger.info(
            f"Пользователь ID={current_user.id} убрал лайк с товара ID={product_id} ({product.slug})"
        )
    else:
        new_like = ProductLike(user_id=current_user.id, product_id=product_id)
        db.add(new_like)
        product.likes_count += 1
        is_liked = True
        msg = "Товар добавлен в избранное"
        logger.info(
            f"Пользователь ID={current_user.id} поставил лайк товару ID={product_id} ({product.slug})"
        )

    await db.commit()

    # Запускаем фоновый точный пересчет статистики в БД
    background_tasks.add_task(recalculate_product_stats_task, product_id)

    return LikeToggleOut(
        product_id=product.id,
        product_slug=product.slug,
        is_liked=is_liked,
        likes_count=product.likes_count,
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
) -> List[ProductCardOut]:
    """
    Возвращает карточки всех товаров, которым текущий авторизованный покупатель поставил лайк.
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
        .order_by(ProductLike.created_at.desc())
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
) -> List[ReviewOut]:
    """
    Возвращает древовидный список одобренных комментариев и отзывов к товару:
    - Корневые отзывы сортируются от самых новых к старым.
    - Внутри каждого отзыва возвращаются ответы (`replies`) и официальный ответ бутика (`admin_reply`).
    """
    logger.debug(f"Запрос отзывов для товара ID={product_id}")

    stmt = (
        select(ProductReview)
        .where(
            ProductReview.product_id == product_id,
            ProductReview.is_approved.is_(True),
            ProductReview.parent_id.is_(None),
        )
        .options(
            selectinload(ProductReview.user),
            selectinload(ProductReview.replies).selectinload(ProductReview.user),
        )
        .order_by(ProductReview.created_at.desc())
    )
    reviews = (await db.execute(stmt)).scalars().all()
    return [ReviewOut.model_validate(r) for r in reviews]


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
    Создает новый комментарий или отзыв покупателя с оценкой (1–5 звезд):
    1. Автоматически проверяет по базе заказов (`orders`), покупал ли этот клиент данный товар раніше.
       Если да — ставит бейдж `is_verified_purchase = True` («Подтвержденная покупка»).
    2. Сохраняет комментарий и в фоновом режиме (`BackgroundTasks`) пересчитывает средний рейтинг товара.
    """
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден."
        )

    # Проверяем, покупал ли клиент этот товар (статус заказа paid или completed)
    purchase_q = await db.execute(
        select(OrderItem.id)
        .join(Order, OrderItem.order_id == Order.id)
        .where(
            Order.user_id == current_user.id,
            OrderItem.product_id == product_id,
            Order.status.in_(["paid", "shipped", "completed"]),
        )
        .limit(1)
    )
    is_verified = purchase_q.scalar_one_or_none() is not None

    review = ProductReview(
        product_id=product_id,
        user_id=current_user.id,
        parent_id=payload.parent_id,
        rating=payload.rating,
        comment_text=payload.comment_text,
        advantages=payload.advantages,
        disadvantages=payload.disadvantages,
        is_verified_purchase=is_verified,
        is_approved=True,
    )
    db.add(review)
    await db.commit()

    # Перезагружаем отзыв вместе с автором и ответами
    stmt = (
        select(ProductReview)
        .where(ProductReview.id == review.id)
        .options(
            selectinload(ProductReview.user),
            selectinload(ProductReview.replies),
        )
    )
    created_review = (await db.execute(stmt)).scalar_one()

    logger.info(
        f"Пользователь ID={current_user.id} оставил отзыв ID={created_review.id} "
        f"к товару ID={product_id} (оценка={payload.rating}, verified={is_verified})"
    )

    # Асинхронный пересчет рейтинга карточки товара в фоне
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
    stmt = (
        select(ProductReview)
        .where(ProductReview.id == review_id)
        .options(
            selectinload(ProductReview.user),
            selectinload(ProductReview.replies).selectinload(ProductReview.user),
        )
    )
    review = (await db.execute(stmt)).scalar_one_or_none()
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Отзыв не найден."
        )

    review.admin_reply = payload.admin_reply
    await db.commit()
    await db.refresh(review)

    logger.info(
        f"Администратор ID={admin_user.id} добавил ответ бутика к отзыву ID={review_id}"
    )
    return ReviewOut.model_validate(review)
