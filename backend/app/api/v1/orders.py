"""
Роутер оформления заказов и чекаута (`app/api/v1/orders.py`).
Реализует транзакционное списание складских остатков через `SELECT ... FOR UPDATE`,
расчет стоимости доставки (бесплатно от 15 000 ₽ по стандарту Ulaanbaatar)
и генерацию платежной ссылки СБП (ЮKassa / Т-Касса).
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUserDep, DBSessionDep, OptionalUserDep
from app.core.logging import get_logger
from app.models.catalog import Product, ProductSize
from app.models.order import Order, OrderItem
from app.schemas.order import OrderCreateIn, OrderOut
from app.services.payment_sbp import SBPPaymentService, get_sbp_service

logger = get_logger(__name__)

router = APIRouter(prefix="/orders", tags=["5. Заказы, Чекаут и Доставка (СДЭК)"])

# Порог бесплатной доставки по России (согласно данным парсера: «Бесплатная доставка по России от 15 000 ₽»)
FREE_DELIVERY_THRESHOLD_RUB = 15000
DEFAULT_DELIVERY_COST_RUB = 490


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
    current_user: OptionalUserDep,
    sbp_service: SBPPaymentService = Depends(get_sbp_service),
) -> OrderOut:
    """
    Оформляет заказ из корзины (`POST /api/v1/orders`):
    1. Для каждой позиции корзины блокирует строку размера на складе через `SELECT ... FOR UPDATE`,
       чтобы исключить гонку потоков (когда два покупателя одновременно покупают последний свитер).
    2. Проверяет достаточность остатка (`stock >= quantity`) и резервирует (списывает) его.
    3. Считает стоимость доставки:
       - При заказе от **15 000 ₽** или при самовывозе из шоурума (`showroom_pickup`) — доставка **0 ₽**.
       - Иначе — **490 ₽**.
    4. Создает заказ в статусе `pending` и запрашивает у платежного шлюза (ЮKassa / Т-Касса)
       ссылку на оплату по QR-коду СБП (`payment_url`).
    """
    logger.info(
        f"Создание нового заказа: клиент='{payload.customer_name}', тел='{payload.customer_phone}', "
        f"доставка='{payload.delivery_method}', позиций={len(payload.items)}"
    )

    items_total = 0
    order_items_to_create: List[OrderItem] = []

    for item_in in payload.items:
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

    # Создаем запись заказа в статусе pending
    new_order = Order(
        user_id=current_user.id if current_user else None,
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
        status="pending",
        items=order_items_to_create,
    )
    db.add(new_order)
    await db.flush()

    # Генерируем платежную ссылку СБП через ЮKassa / Т-Кассу
    payment_id, payment_url = await sbp_service.create_sbp_payment(
        order_id=new_order.id,
        total_amount=total_amount,
        description=f"Заказ #{new_order.id} в бутике Ulaanbaatar Cashmere",
        customer_phone=payload.customer_phone,
    )
    new_order.payment_id = payment_id
    new_order.payment_url = payment_url

    await db.commit()

    # Перезагружаем заказ со всеми позициями для ответа фронтенду
    stmt = (
        select(Order)
        .where(Order.id == new_order.id)
        .options(selectinload(Order.items))
    )
    created_order = (await db.execute(stmt)).scalar_one()

    logger.info(
        f"Заказ #{created_order.id} успешно создан на сумму {total_amount} ₽. "
        f"Ссылка СБП: {payment_url}"
    )
    return OrderOut.model_validate(created_order)


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
) -> List[OrderOut]:
    """
    Возвращает список всех заказов авторизованного пользователя со статусами оплаты и составом.
    """
    logger.debug(f"Запрос истории заказов для пользователя ID={current_user.id}")
    stmt = (
        select(Order)
        .where(Order.user_id == current_user.id)
        .options(selectinload(Order.items))
        .order_by(Order.created_at.desc())
    )
    orders = (await db.execute(stmt)).scalars().all()
    return [OrderOut.model_validate(o) for o in orders]


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
) -> OrderOut:
    """
    Используется страницей успешной оплаты на фронтенде для проверки того,
    перешел ли заказ в статус `paid` после оплаты по QR-коду СБП.
    """
    stmt = (
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.items))
    )
    order = (await db.execute(stmt)).scalar_one_or_none()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Заказ #{order_id} не найден.",
        )
    return OrderOut.model_validate(order)
