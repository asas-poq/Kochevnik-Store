"""
Бизнес-логика заказов (`app/services/orders.py`).

Единое место для всего, что меняет статус заказа и склад:
- машина состояний (`pending → paid → shipped → completed`, `pending → cancelled`);
- возврат остатков на склад при отмене;
- применение результата платежа (используется и вебхуком, и тестовой оплатой в песочнице);
- автоотмена неоплаченных заказов по таймауту (`ORDER_PAYMENT_TTL_MINUTES`).
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Set, Tuple

from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.models.catalog import ProductSize
from app.models.order import Order, OrderStatus
from app.services.telegram import TelegramNotificationService

logger = get_logger(__name__)

S = OrderStatus

# Допустимые переходы статусов: всё остальное — ошибка (защита от гонок и повторных вебхуков)
ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
    S.PENDING.value: {S.PAID.value, S.CANCELLED.value},
    S.PAID.value: {S.SHIPPED.value},
    S.SHIPPED.value: {S.COMPLETED.value},
    S.COMPLETED.value: set(),
    S.CANCELLED.value: set(),
}

# Статусы, при которых заказ уже оплачен
PAID_STATUSES = {S.PAID.value, S.SHIPPED.value, S.COMPLETED.value}


class InvalidOrderTransition(Exception):
    """Недопустимая смена статуса заказа."""


def ensure_transition(order: Order, target: str) -> None:
    if target not in ALLOWED_TRANSITIONS.get(order.status, set()):
        raise InvalidOrderTransition(
            f"Нельзя перевести заказ #{order.id} из статуса '{order.status}' в '{target}'."
        )


def payment_expires_at(order: Order) -> Optional[datetime]:
    """До какого времени можно оплатить заказ (только для `pending`)."""
    if order.status != S.PENDING.value or order.created_at is None:
        return None
    created = order.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return created + timedelta(minutes=settings.ORDER_PAYMENT_TTL_MINUTES)


# ==============================================================================
# Срок оплаты, склад и смена статусов (commit делает вызывающий код)
# ==============================================================================
async def restore_stock(db: AsyncSession, order: Order) -> None:
    """Возвращает на склад зарезервированные позиции заказа (строки блокируются по порядку ID)."""
    for item in sorted(order.items, key=lambda i: i.variant_id or 0):
        if item.variant_id:
            size_row = await db.get(ProductSize, item.variant_id, with_for_update=True)
            if size_row:
                size_row.stock += item.quantity


async def cancel_order(db: AsyncSession, order: Order, reason: str) -> None:
    """`pending → cancelled` + возврат остатков. Бросает `InvalidOrderTransition`."""
    ensure_transition(order, S.CANCELLED.value)
    order.status = S.CANCELLED.value
    await restore_stock(db, order)
    logger.warning(f"Заказ #{order.id} отменён ({reason}), остатки возвращены на склад.")


async def apply_payment_result(
    db: AsyncSession,
    order: Order,
    succeeded: bool,
    paid_amount: Optional[int] = None,
) -> str:
    """
    Применяет результат платежа к заказу (идемпотентно) и делает commit.
    Заказ должен быть загружен с `selectinload(Order.items)` и желательно `FOR UPDATE`.

    Возвращает код результата:
    `paid`, `already_paid`, `paid_after_cancel`, `amount_mismatch`,
    `cancelled`, `already_cancelled`, `ignored`.
    """
    if succeeded:
        if order.status in PAID_STATUSES:
            return "already_paid"
        if order.status == S.CANCELLED.value:
            # Заказ уже отменён (например, по таймауту), остаток возвращён — автоматически
            # оплатить нельзя, нужен ручной разбор: подтвердить или вернуть деньги.
            logger.error(f"Оплата пришла по ОТМЕНЁННОМУ заказу #{order.id}!")
            return "paid_after_cancel"
        if paid_amount is not None and paid_amount != order.total_amount:
            logger.error(
                f"Сумма платежа {paid_amount} ₽ не совпадает с суммой заказа #{order.id} "
                f"({order.total_amount} ₽)"
            )
            return "amount_mismatch"
        ensure_transition(order, S.PAID.value)
        order.status = S.PAID.value
        order.paid_at = datetime.now(timezone.utc)
        await db.commit()
        logger.info(f"Заказ #{order.id} переведён в статус 'paid'.")
        return "paid"

    if order.status == S.CANCELLED.value:
        return "already_cancelled"
    if order.status != S.PENDING.value:
        logger.warning(f"Отмена платежа для заказа #{order.id} в статусе '{order.status}' проигнорирована.")
        return "ignored"
    await cancel_order(db, order, "платёж отменён")
    await db.commit()
    return "cancelled"


async def advance_order_status(
    db: AsyncSession, order_id: int, target: str
) -> Tuple[Optional[Order], str]:
    """
    Переводит оплаченный заказ дальше (`paid → shipped → completed`) с блокировкой строки.
    Возвращает `(заказ, код)`: `ok`, `not_found` или `invalid` (переход невозможен — например,
    заказ уже отправлен). Используется кнопками в Telegram.
    """
    order = (
        await db.execute(
            select(Order)
            .where(Order.id == order_id)
            .options(selectinload(Order.items))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if not order:
        return None, "not_found"
    try:
        ensure_transition(order, target)
    except InvalidOrderTransition:
        return order, "invalid"
    order.status = target
    await db.commit()
    logger.info(f"Заказ #{order.id} переведён в статус '{target}'.")
    return order, "ok"


def schedule_payment_notifications(
    background_tasks: BackgroundTasks,
    telegram: TelegramNotificationService,
    order: Order,
    result: str,
) -> None:
    """Ставит в фон нужное уведомление владельцу в Telegram по результату платежа."""
    if result == "paid":
        background_tasks.add_task(telegram.send_order_paid_alert, order)
    elif result == "paid_after_cancel":
        background_tasks.add_task(
            telegram.send_alert,
            f"⚠️ <b>Оплата пришла по отменённому заказу #{order.id}</b> "
            f"({order.total_amount} ₽). Остатки уже возвращены на склад — "
            f"подтвердите заказ вручную или сделайте возврат.",
            order.id,
        )
    elif result == "amount_mismatch":
        background_tasks.add_task(
            telegram.send_alert,
            f"⚠️ <b>Сумма платежа не совпала с заказом #{order.id}</b> "
            f"(ожидалось {order.total_amount} ₽). Заказ НЕ отмечен оплаченным.",
            order.id,
        )


# ==============================================================================
# Автоотмена неоплаченных заказов
# ==============================================================================
async def cancel_expired_pending_orders() -> int:
    """Отменяет `pending`-заказы старше TTL и возвращает остатки. Возвращает число отмен."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.ORDER_PAYMENT_TTL_MINUTES)
    cancelled = 0
    async with AsyncSessionLocal() as db:
        ids = (
            (
                await db.execute(
                    select(Order.id).where(
                        Order.status == S.PENDING.value, Order.created_at < cutoff
                    )
                )
            )
            .scalars()
            .all()
        )
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
            if order and order.status == S.PENDING.value:
                await cancel_order(db, order, f"не оплачен за {settings.ORDER_PAYMENT_TTL_MINUTES} мин.")
                await db.commit()
                cancelled += 1
    return cancelled


async def expire_orders_loop(interval_seconds: int = 60) -> None:
    """Фоновый цикл автоотмены (запускается в `lifespan`)."""
    logger.info(
        f"Запущена автоотмена неоплаченных заказов (TTL={settings.ORDER_PAYMENT_TTL_MINUTES} мин.)"
    )
    while True:
        try:
            count = await cancel_expired_pending_orders()
            if count:
                logger.info(f"Автоотмена: отменено неоплаченных заказов — {count}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(f"Ошибка автоотмены заказов: {exc}")
        await asyncio.sleep(interval_seconds)


