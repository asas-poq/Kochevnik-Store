from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.cache import Cache
from app.core.config import settings
from app.core.errors import BadGatewayError, BadRequestError, ConflictError, NotFoundError
from app.core.logging import get_logger
from app.db.utils import escape_like
from app.models import Order, OrderItem, OrderStatus, Product, ProductSize, User
from app.schemas.order import OrderCreateIn, OrderItemCreateIn
from app.services.payment_sbp import PaymentGatewayError, SBPPaymentService

logger = get_logger(__name__)

S = OrderStatus

# Всё, чего нет в таблице, это ошибка. Так повторные вебхуки и гонки не откатывают статус.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    S.PENDING.value: {S.PAID.value, S.CANCELLED.value},
    S.PAID.value: {S.SHIPPED.value},
    S.SHIPPED.value: {S.COMPLETED.value},
    S.COMPLETED.value: set(),
    S.CANCELLED.value: set(),
}
PAID_STATUSES = {S.PAID.value, S.SHIPPED.value, S.COMPLETED.value}


class InvalidOrderTransition(ConflictError):
    pass


def ensure_transition(order: Order, target: str) -> None:
    if target not in ALLOWED_TRANSITIONS.get(order.status, set()):
        raise InvalidOrderTransition(
            f"Нельзя перевести заказ #{order.id} из статуса «{order.status}» в «{target}»."
        )


def payment_expires_at(order: Order) -> datetime | None:
    if order.status != S.PENDING.value:
        return None
    return order.created_at + timedelta(minutes=settings.ORDER_PAYMENT_TTL_MINUTES)


async def load_order(db: AsyncSession, order_id: int, *, for_update: bool = False) -> Order | None:
    stmt = (
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.items))
        .execution_options(populate_existing=True)
    )
    if for_update:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_accessible_order(
    db: AsyncSession, order_id: int, user: User, *, for_update: bool = False
) -> Order:
    """Чужой заказ отдаёт 404, а не 403, чтобы нельзя было перебирать номера."""
    order = await load_order(db, order_id, for_update=for_update)
    if not order or not (user.is_admin or order.user_id == user.id):
        raise NotFoundError(f"Заказ #{order_id} не найден.")
    return order


async def create_order(
    db: AsyncSession, cache: Cache, user: User, payload: OrderCreateIn, gateway: SBPPaymentService
) -> Order:
    merged: dict[tuple[int, int, str], OrderItemCreateIn] = {}
    for item in payload.items:
        key = (item.product_id, item.variant_id or 0, item.size)
        if key in merged:
            merged[key] = merged[key].model_copy(update={"quantity": merged[key].quantity + item.quantity})
        else:
            merged[key] = item

    items_total = 0
    order_items: list[OrderItem] = []
    # Строки размеров блокируем всегда в одном порядке, иначе два заказа с общими
    # позициями ждут друг друга и получаем дедлок
    for key in sorted(merged):
        item = merged[key]
        product = await db.get(Product, item.product_id)
        if not product or product.status != "active":
            raise NotFoundError(f"Товар id={item.product_id} не найден или снят с продажи.")

        stmt = select(ProductSize).where(ProductSize.product_id == product.id).with_for_update()
        if item.variant_id:
            stmt = stmt.where(ProductSize.id == item.variant_id)
        else:
            stmt = stmt.where(ProductSize.size == item.size)
        variant = (await db.execute(stmt)).scalar_one_or_none()
        if not variant:
            raise BadRequestError(f"Размер «{item.size}» для товара «{product.name}» не найден.")
        if variant.stock < item.quantity:
            raise ConflictError(
                f"Товара «{product.name}» (размер {variant.size}) осталось {variant.stock} шт."
            )

        variant.stock -= item.quantity
        subtotal = product.current_price * item.quantity
        items_total += subtotal
        order_items.append(
            OrderItem(
                product_id=product.id,
                variant_id=variant.id,
                product_name=product.name,
                product_slug=product.slug,
                color=product.color,
                size=variant.size,
                quantity=item.quantity,
                unit_price=product.current_price,
                subtotal=subtotal,
            )
        )

    free = items_total >= settings.FREE_DELIVERY_THRESHOLD_RUB or payload.delivery_method == "showroom_pickup"
    delivery_cost = 0 if free else settings.DELIVERY_COST_RUB
    total = items_total + delivery_cost

    order = Order(
        user_id=user.id,
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
        total_amount=total,
        status=S.PENDING.value,
        items=order_items,
    )
    db.add(order)
    await db.flush()
    order_id = order.id
    await db.commit()  # запрос к шлюзу ниже идёт уже без блокировок на складе
    await cache.bump("catalog")

    try:
        payment_id, payment_url = await gateway.create_sbp_payment(
            order_id=order_id,
            total_amount=total,
            description=f"Заказ #{order_id} в бутике Ulaanbaatar Cashmere",
            customer_phone=payload.customer_phone,
        )
    except PaymentGatewayError:
        await cancel_order(db, order, "платёжный шлюз недоступен")
        await db.commit()
        await cache.bump("catalog")
        raise BadGatewayError("Платёжный сервис временно недоступен. Заказ не оформлен, попробуйте позже.") from None

    order.payment_id = payment_id
    order.payment_url = payment_url
    await db.commit()
    logger.info("Заказ создан", extra={"order_id": order_id, "total": total})
    return await load_order(db, order_id)  # type: ignore[return-value]


async def restore_stock(db: AsyncSession, order: Order) -> None:
    for item in sorted(order.items, key=lambda i: i.variant_id or 0):
        if item.variant_id:
            size = await db.get(ProductSize, item.variant_id, with_for_update=True)
            if size:
                size.stock += item.quantity


async def cancel_order(db: AsyncSession, order: Order, reason: str) -> None:
    """pending в cancelled с возвратом остатков. Commit на вызывающем."""
    ensure_transition(order, S.CANCELLED.value)
    order.status = S.CANCELLED.value
    await restore_stock(db, order)
    logger.warning("Заказ отменён", extra={"order_id": order.id, "reason": reason})


async def cancel_my_order(db: AsyncSession, cache: Cache, user: User, order_id: int) -> Order:
    order = await get_accessible_order(db, order_id, user, for_update=True)
    if order.status != S.PENDING.value:
        raise ConflictError(f"Заказ в статусе «{order.status}» отменить нельзя. Свяжитесь с магазином.")
    await cancel_order(db, order, "по просьбе покупателя")
    await db.commit()
    await cache.bump("catalog")
    return order


async def apply_payment_result(
    db: AsyncSession, order: Order, succeeded: bool, paid_amount: int | None = None
) -> str:
    """Применяет результат платежа и повторно безопасна. Commit на вызывающем.
    Коды: paid, already_paid, paid_after_cancel, amount_mismatch, cancelled, already_cancelled, ignored."""
    if succeeded:
        if order.status in PAID_STATUSES:
            return "already_paid"
        if order.status == S.CANCELLED.value:
            # Остаток уже вернули на склад, автоматически оплату не принимаем. Нужен ручной разбор
            logger.error("Оплата пришла по отменённому заказу", extra={"order_id": order.id})
            return "paid_after_cancel"
        if paid_amount is not None and paid_amount != order.total_amount:
            logger.error(
                "Сумма платежа не совпала с заказом",
                extra={"order_id": order.id, "paid": paid_amount, "expected": order.total_amount},
            )
            return "amount_mismatch"
        ensure_transition(order, S.PAID.value)
        order.status = S.PAID.value
        order.paid_at = datetime.now(timezone.utc)
        return "paid"

    if order.status == S.CANCELLED.value:
        return "already_cancelled"
    if order.status != S.PENDING.value:
        return "ignored"
    await cancel_order(db, order, "платёж отменён")
    return "cancelled"


async def advance_order_status(db: AsyncSession, order_id: int, target: str) -> Order:
    """paid, shipped, completed по цепочке. Используется админ-ручкой и кнопками Telegram."""
    order = await load_order(db, order_id, for_update=True)
    if not order:
        raise NotFoundError(f"Заказ #{order_id} не найден.")
    ensure_transition(order, target)
    order.status = target
    await db.commit()
    logger.info("Статус заказа изменён", extra={"order_id": order_id, "status": target})
    return order


async def list_orders(
    db: AsyncSession,
    *,
    user_id: int | None = None,
    status: OrderStatus | None = None,
    q: str | None = None,
    limit: int,
    offset: int,
) -> list[Order]:
    stmt = select(Order)
    if user_id is not None:
        stmt = stmt.where(Order.user_id == user_id)
    if status:
        stmt = stmt.where(Order.status == status.value)
    if q:
        pattern = escape_like(q)
        stmt = stmt.where(
            or_(
                Order.customer_name.ilike(pattern, escape="\\"),
                Order.customer_phone.ilike(pattern, escape="\\"),
                Order.payment_id.ilike(pattern, escape="\\"),
            )
        )
    stmt = (
        stmt.options(selectinload(Order.items))
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list((await db.execute(stmt)).scalars())


async def cancel_expired_pending_orders(session_factory: async_sessionmaker[AsyncSession]) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.ORDER_PAYMENT_TTL_MINUTES)
    cancelled = 0
    async with session_factory() as db:
        ids = (
            await db.execute(
                select(Order.id).where(Order.status == S.PENDING.value, Order.created_at < cutoff)
            )
        ).scalars().all()
        for order_id in ids:
            order = (
                await db.execute(
                    select(Order)
                    .where(Order.id == order_id)
                    .options(selectinload(Order.items))
                    .with_for_update(skip_locked=True)
                    .execution_options(populate_existing=True)
                )
            ).scalar_one_or_none()
            # Между выборкой id и блокировкой заказ могли оплатить
            if order and order.status == S.PENDING.value:
                await cancel_order(db, order, f"не оплачен за {settings.ORDER_PAYMENT_TTL_MINUTES} мин.")
                await db.commit()
                cancelled += 1
    return cancelled
