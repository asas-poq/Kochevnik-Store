"""
Роутер оформления заказов и чекаута (`app/api/v1/orders.py`).
Реализует транзакционное списание складских остатков через `SELECT ... FOR UPDATE`,
расчет стоимости доставки (бесплатно от 15 000 ₽ по стандарту Ulaanbaatar),
генерацию платежной ссылки СБП (ЮKassa / Т-Касса), отмену и проверку оплаты заказа,
а также админские ручки (список заказов и смена статуса доставки).

Заказ можно оформить только после регистрации и входа (JWT обязателен).
Посмотреть заказ по ID может его владелец или администратор. Чужой заказ отдаёт 404 (а не 403),
чтобы нельзя было перебирать ID. Администратор может посмотреть все заказы любого пользователя.
"""

from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import AdminUserDep, CurrentUserDep, DBSessionDep
from app.core.logging import get_logger
from app.models.catalog import Product, ProductSize
from app.models.order import Order, OrderItem, OrderStatus
from app.schemas.order import AdminOrderStatusIn, OrderCreateIn, OrderOut
from app.services.orders import (
    InvalidOrderTransition,
    apply_payment_result,
    cancel_order,
    ensure_transition,
    payment_expires_at,
    schedule_payment_notifications,
)
from app.services.payment_sbp import (
    PaymentGatewayError,
    SBPPaymentService,
    get_sbp_service,
)
from app.services.telegram import TelegramNotificationService, get_telegram_service

logger = get_logger(__name__)

router = APIRouter(prefix="/orders", tags=["5. Заказы, Чекаут и Доставка (СДЭК)"])

# Порог бесплатной доставки по России (согласно данным парсера: «Бесплатная доставка по России от 15 000 ₽»)
FREE_DELIVERY_THRESHOLD_RUB = 15000
DEFAULT_DELIVERY_COST_RUB = 490


# ==============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================================================================
def _to_out(order: Order) -> OrderOut:
    out = OrderOut.model_validate(order)
    out.payment_expires_at = payment_expires_at(order)
    return out


async def _load_order(
    db: DBSessionDep, order_id: int, *, for_update: bool = False
) -> Optional[Order]:
    stmt = (
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.items))
        .execution_options(populate_existing=True)
    )
    if for_update:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


async def _get_accessible_order(
    db: DBSessionDep,
    order_id: int,
    user,
    *,
    for_update: bool = False,
) -> Order:
    """Возвращает заказ, только если пользователь — его владелец или админ; иначе 404."""
    order = await _load_order(db, order_id, for_update=for_update)
    has_access = bool(order and (user.is_admin or order.user_id == user.id))
    if not order or not has_access:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Заказ #{order_id} не найден."
        )
    return order


# ==============================================================================
# РУЧКА 1: Создание нового заказа и получение ссылки на оплату по СБП
# ==============================================================================
@router.post(
    "",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать заказ с проверкой остатков (SELECT ... FOR UPDATE) и получить ссылку СБП",
)
async def create_order(
    payload: OrderCreateIn,
    db: DBSessionDep,
    current_user: CurrentUserDep,
    sbp_service: SBPPaymentService = Depends(get_sbp_service),
) -> OrderOut:
    """
    Оформляет заказ из корзины (`POST /api/v1/orders`). Требуется вход в аккаунт:
    1. Позиции объединяются (одинаковый размер — одной строкой) и сортируются, затем для каждой
       блокируется строка размера через `SELECT ... FOR UPDATE` (сортировка исключает дедлоки
       между параллельными заказами).
    2. Проверяется остаток (`stock >= quantity`), остаток резервируется (списывается).
    3. Доставка: от **15 000 ₽** или самовывоз (`showroom_pickup`) — **0 ₽**, иначе **490 ₽**.
    4. Заказ в статусе `pending` СРАЗУ коммитится (блокировки строк не держатся во время
       запроса к платёжному шлюзу), затем запрашивается ссылка СБП (`payment_url`).
    5. Если шлюз недоступен — заказ отменяется, остатки возвращаются, клиент получает 502.
    6. В ответе возвращается `payment_expires_at`: неоплаченный заказ автоматически
       отменяется по таймауту.
    """
    logger.info(
        f"Создание нового заказа: клиент='{payload.customer_name}', тел='{payload.customer_phone}', "
        f"доставка='{payload.delivery_method}', позиций={len(payload.items)}"
    )

    # Объединяем одинаковые позиции и сортируем: единый порядок блокировок = нет дедлоков
    merged: Dict[Tuple[int, int, str], object] = {}
    for item_in in payload.items:
        key = (item_in.product_id, item_in.variant_id or 0, item_in.size or "")
        if key in merged:
            merged[key] = merged[key].model_copy(
                update={"quantity": merged[key].quantity + item_in.quantity}
            )
        else:
            merged[key] = item_in
    sorted_items = [merged[k] for k in sorted(merged)]

    items_total = 0
    order_items_to_create: List[OrderItem] = []

    for item_in in sorted_items:
        product = await db.get(Product, item_in.product_id)
        if not product or product.status != "active":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Товар ID={item_in.product_id} не найден или снят с продажи.",
            )

        # Находим и блокируем строку размера в таблице product_sizes с помощью SELECT ... FOR UPDATE
        if item_in.variant_id:
            size_stmt = (
                select(ProductSize)
                .where(
                    ProductSize.id == item_in.variant_id,
                    ProductSize.product_id == product.id,
                )
                .with_for_update()
            )
        else:
            size_stmt = (
                select(ProductSize)
                .where(
                    ProductSize.product_id == product.id,
                    ProductSize.size == item_in.size,
                )
                .with_for_update()
            )

        size_variant = (await db.execute(size_stmt)).scalar_one_or_none()
        if not size_variant:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Размер '{item_in.size}' для товара «{product.name}» не найден.",
            )

        if size_variant.stock < item_in.quantity:
            logger.warning(
                f"Недостаточно остатка на складе для товара ID={product.id} (размер {size_variant.size}): "
                f"запрошено={item_in.quantity}, в наличии={size_variant.stock}"
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"К сожалению, товара «{product.name}» (размер {size_variant.size}) "
                    f"осталось всего {size_variant.stock} шт. на складе."
                ),
            )

        # Списываем (резервируем) остаток со склада
        size_variant.stock -= item_in.quantity

        unit_price = product.current_price
        subtotal = unit_price * item_in.quantity
        items_total += subtotal

        order_items_to_create.append(
            OrderItem(
                product_id=product.id,
                variant_id=size_variant.id,
                product_name=product.name,
                product_slug=product.slug,
                color=product.color,
                size=size_variant.size,
                quantity=item_in.quantity,
                unit_price=unit_price,
                subtotal=subtotal,
            )
        )

    # Расчет стоимости доставки (бесплатно от 15 000 ₽ или при самовывозе из шоурума Москвы/СПб)
    if (
        items_total >= FREE_DELIVERY_THRESHOLD_RUB
        or payload.delivery_method == "showroom_pickup"
    ):
        delivery_cost = 0
    else:
        delivery_cost = DEFAULT_DELIVERY_COST_RUB

    total_amount = items_total + delivery_cost

    # Создаем запись заказа в статусе pending и фиксируем резерв остатков
    new_order = Order(
        user_id=current_user.id,
        customer_name=payload.customer_name,
        customer_phone=payload.customer_phone,
        customer_email=payload.customer_email,
        delivery_method=payload.delivery_method,
        delivery_city=payload.delivery_city,
        delivery_address=payload.delivery_address,
        cdek_pvz_code=payload.cdek_pvz_code,
        customer_comment=payload.customer_comment,
        items_total=items_total,
        delivery_cost=delivery_cost,
        total_amount=total_amount,
        currency="RUB",
        status=OrderStatus.PENDING.value,
        items=order_items_to_create,
    )
    db.add(new_order)
    await db.flush()
    order_id = new_order.id
    await db.commit()  # блокировки сняты; заказ и резерв зафиксированы

    # Генерируем платежную ссылку СБП (внешний HTTP-запрос — уже вне блокировок)
    try:
        payment_id, payment_url = await sbp_service.create_sbp_payment(
            order_id=order_id,
            total_amount=total_amount,
            description=f"Заказ #{order_id} в бутике Ulaanbaatar Cashmere",
            customer_phone=payload.customer_phone,
        )
    except PaymentGatewayError:
        await cancel_order(db, new_order, "платёжный шлюз недоступен")
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Платёжный сервис временно недоступен. Заказ не оформлен, попробуйте позже.",
        )

    new_order.payment_id = payment_id
    new_order.payment_url = payment_url
    await db.commit()

    created_order = await _load_order(db, order_id)
    logger.info(
        f"Заказ #{order_id} успешно создан на сумму {total_amount} ₽. Ссылка СБП: {payment_url}"
    )
    return _to_out(created_order)


# ==============================================================================
# РУЧКА 2: Получение списка заказов текущего авторизованного покупателя
# ==============================================================================
@router.get(
    "/my",
    response_model=List[OrderOut],
    summary="История заказов текущего авторизованного покупателя",
)
async def list_my_orders(
    current_user: CurrentUserDep,
    db: DBSessionDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status_filter: Optional[OrderStatus] = Query(
        None, alias="status", description="Фильтр по статусу"
    ),
) -> List[OrderOut]:
    """
    Возвращает заказы авторизованного пользователя (новые первыми) со статусами оплаты и составом.
    """
    logger.debug(f"Запрос истории заказов для пользователя ID={current_user.id}")
    stmt = select(Order).where(Order.user_id == current_user.id)
    if status_filter:
        stmt = stmt.where(Order.status == status_filter.value)
    stmt = (
        stmt.options(selectinload(Order.items))
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(limit)
        .offset(offset)
    )
    orders = (await db.execute(stmt)).scalars().all()
    return [_to_out(o) for o in orders]


# ==============================================================================
# АДМИН: список всех заказов
# ==============================================================================
@router.get(
    "/admin/list",
    response_model=List[OrderOut],
    summary="Все заказы магазина с фильтрами (только Администратор)",
)
async def admin_list_orders(
    admin_user: AdminUserDep,
    db: DBSessionDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status_filter: Optional[OrderStatus] = Query(None, alias="status"),
    user_id: Optional[int] = Query(None, description="Только заказы этого пользователя"),
    q: Optional[str] = Query(
        None, min_length=2, description="Поиск по имени, телефону или ID платежа"
    ),
) -> List[OrderOut]:
    stmt = select(Order)
    if user_id is not None:
        stmt = stmt.where(Order.user_id == user_id)
    if status_filter:
        stmt = stmt.where(Order.status == status_filter.value)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                Order.customer_name.ilike(like),
                Order.customer_phone.ilike(like),
                Order.payment_id.ilike(like),
            )
        )
    stmt = (
        stmt.options(selectinload(Order.items))
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(limit)
        .offset(offset)
    )
    orders = (await db.execute(stmt)).scalars().all()
    return [_to_out(o) for o in orders]


# ==============================================================================
# АДМИН: все заказы конкретного пользователя по его ID
# ==============================================================================
@router.get(
    "/admin/users/{user_id}",
    response_model=List[OrderOut],
    summary="Все заказы пользователя по его ID (только Администратор)",
)
async def admin_list_user_orders(
    user_id: int,
    admin_user: AdminUserDep,
    db: DBSessionDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status_filter: Optional[OrderStatus] = Query(None, alias="status"),
) -> List[OrderOut]:
    """Возвращает заказы выбранного пользователя (новые первыми), можно фильтровать по статусу."""
    stmt = select(Order).where(Order.user_id == user_id)
    if status_filter:
        stmt = stmt.where(Order.status == status_filter.value)
    stmt = (
        stmt.options(selectinload(Order.items))
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(limit)
        .offset(offset)
    )
    orders = (await db.execute(stmt)).scalars().all()
    return [_to_out(o) for o in orders]


# ==============================================================================
# АДМИН: смена статуса оплаченного заказа (shipped / completed)
# ==============================================================================
@router.patch(
    "/admin/{order_id}/status",
    response_model=OrderOut,
    summary="Передать заказ в доставку / отметить врученным (только Администратор)",
)
async def admin_update_order_status(
    order_id: int,
    payload: AdminOrderStatusIn,
    background_tasks: BackgroundTasks,
    admin_user: AdminUserDep,
    db: DBSessionDep,
    telegram: TelegramNotificationService = Depends(get_telegram_service),
) -> OrderOut:
    """
    Допустимые переходы: `paid → shipped → completed`. После `shipped`/`completed`
    покупатель может оставить отзыв с бейджем «Подтверждённая покупка».
    """
    order = await _load_order(db, order_id, for_update=True)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Заказ #{order_id} не найден."
        )
    try:
        ensure_transition(order, payload.status)
    except InvalidOrderTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    order.status = payload.status
    await db.commit()
    logger.info(
        f"Администратор ID={admin_user.id} перевёл заказ #{order_id} в статус '{payload.status}'"
    )
    # Сообщения в Telegram (личка и группа) обновятся так же, как после нажатия кнопки
    background_tasks.add_task(telegram.sync_order_status, order_id, f"админ ID={admin_user.id}")
    return _to_out(await _load_order(db, order_id))


# ==============================================================================
# РУЧКА 3: Получение статуса конкретного заказа по его ID
# ==============================================================================
@router.get(
    "/{order_id}",
    response_model=OrderOut,
    summary="Проверить статус заказа и детали оплаты по ID заказа",
)
async def get_order_by_id(
    order_id: int,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> OrderOut:
    """
    Проверка заказа по его ID (номер покупки): статус, оплата, состав, ссылка на оплату.
    Используется страницей успешной оплаты. Доступ: владелец заказа или администратор
    (администратор может открыть любой заказ по ID); иначе 404.
    """
    order = await _get_accessible_order(db, order_id, current_user)
    return _to_out(order)


# ==============================================================================
# РУЧКА 4: Отмена неоплаченного заказа покупателем
# ==============================================================================
@router.post(
    "/{order_id}/cancel",
    response_model=OrderOut,
    summary="Отменить неоплаченный заказ (остатки вернутся на склад)",
)
async def cancel_my_order(
    order_id: int,
    db: DBSessionDep,
    current_user: CurrentUserDep,
) -> OrderOut:
    """Отменить можно только заказ в статусе `pending`. Оплаченный заказ — через магазин."""
    order = await _get_accessible_order(db, order_id, current_user, for_update=True)
    if order.status != OrderStatus.PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Заказ в статусе '{order.status}' отменить нельзя. Свяжитесь с магазином.",
        )
    await cancel_order(db, order, "по просьбе покупателя")
    await db.commit()
    return _to_out(order)


# ==============================================================================
# РУЧКА 5: Принудительная проверка оплаты у платёжного шлюза
# ==============================================================================
@router.post(
    "/{order_id}/check-payment",
    response_model=OrderOut,
    summary="Сверить статус оплаты со шлюзом (если вебхук потерялся)",
)
async def check_order_payment(
    order_id: int,
    background_tasks: BackgroundTasks,
    db: DBSessionDep,
    current_user: CurrentUserDep,
    sbp_service: SBPPaymentService = Depends(get_sbp_service),
    telegram: TelegramNotificationService = Depends(get_telegram_service),
) -> OrderOut:
    """
    В боевом режиме спрашивает у ЮKassa актуальный статус платежа и синхронизирует заказ.
    В песочнице внешнего шлюза нет — просто возвращает текущее состояние
    (оплату имитируйте через `/api/v1/payments/sandbox/...`).
    """
    order = await _get_accessible_order(db, order_id, current_user, for_update=True)

    if (
        order.status == OrderStatus.PENDING.value
        and order.payment_id
        and not sbp_service.is_sandbox
    ):
        try:
            gateway = await sbp_service.fetch_payment(order.payment_id)
        except PaymentGatewayError:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Не удалось связаться с платёжным сервисом, попробуйте позже.",
            )
        if gateway["status"] in ("succeeded", "canceled"):
            result = await apply_payment_result(
                db,
                order,
                succeeded=gateway["status"] == "succeeded",
                paid_amount=gateway["amount"],
            )
            schedule_payment_notifications(background_tasks, telegram, order, result)

    return _to_out(order)