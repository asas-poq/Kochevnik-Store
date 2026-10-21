import hmac
from pathlib import Path
from string import Template

from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import Cache
from app.core.config import settings
from app.core.errors import (
    BadGatewayError,
    BadRequestError,
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    UnauthorizedError,
)
from app.core.logging import get_logger
from app.models import Order, OrderStatus, PaymentEvent, User
from app.schemas.order import SandboxPaymentOut, SBPWebhookPayload
from app.services import orders
from app.services.payment_sbp import PaymentGatewayError, SBPPaymentService
from app.services.telegram import TelegramService

logger = get_logger(__name__)

CHECKOUT_TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "sandbox_checkout.html"

SANDBOX_MESSAGES = {
    "paid": "Оплата имитирована, заказ в статусе paid.",
    "already_paid": "Заказ уже был оплачен.",
    "paid_after_cancel": "Заказ уже отменён, например по таймауту. Оплата не применена.",
    "cancelled": "Платёж отменён, остатки вернулись на склад.",
    "already_cancelled": "Заказ уже отменён.",
    "ignored": "Заказ в статусе, где это действие невозможно.",
    "amount_mismatch": "Сумма платежа не совпала с заказом.",
}


async def _lock_order(db: AsyncSession, *, order_id: int | None, payment_id: str | None) -> Order | None:
    stmt = select(Order.id).where(Order.id == order_id if order_id is not None else Order.payment_id == payment_id)
    found = (await db.execute(stmt)).scalar_one_or_none()
    return await orders.load_order(db, found, for_update=True) if found else None


async def process_webhook(
    db: AsyncSession,
    cache: Cache,
    gateway: SBPPaymentService,
    telegram: TelegramService,
    background: BackgroundTasks,
    payload: SBPWebhookPayload,
    secret_header: str | None,
) -> dict[str, str]:
    """Повтор того же события отвечает duplicate и ничего не меняет. Ключ это платёж плюс событие."""
    payment_id, order_id, amount = payload.normalized()
    if order_id is None and not payment_id:
        raise BadRequestError("Не указан ни order_id, ни payment_id.")

    if gateway.is_sandbox:
        provided = secret_header or payload.secret_signature or ""
        if not hmac.compare_digest(provided, settings.PAYMENT_WEBHOOK_SECRET):
            logger.warning("Вебхук СБП отклонён: неверный секрет")
            raise UnauthorizedError("Неверная подпись вебхука.")
        if payload.event not in ("payment.succeeded", "payment.canceled"):
            return {"status": "ignored", "event": payload.event}
        succeeded = payload.event == "payment.succeeded"
    else:
        # В бою вебхуку на слово не верим, статус и сумму берём у шлюза
        if not payment_id:
            raise BadRequestError("Не указан payment_id.")
        try:
            gateway_state = await gateway.fetch_payment(payment_id)
        except PaymentGatewayError:
            raise ServiceUnavailableError("Не удалось подтвердить платёж у шлюза.") from None
        if gateway_state["status"] not in ("succeeded", "canceled"):
            return {"status": "ignored", "event": str(gateway_state["status"])}
        succeeded = gateway_state["status"] == "succeeded"
        amount = gateway_state["amount"]

    order = await _lock_order(db, order_id=order_id, payment_id=payment_id)
    if not order:
        raise NotFoundError("Заказ не найден.")
    if payment_id and order.payment_id and order.payment_id != payment_id:
        logger.error("payment_id не совпал с платежом заказа", extra={"order_id": order.id})
        raise ConflictError("Платёж не относится к этому заказу.")

    event = "payment.succeeded" if succeeded else "payment.canceled"
    key = order.payment_id or f"order-{order.id}"
    seen = await db.execute(
        select(PaymentEvent.id).where(PaymentEvent.payment_id == key, PaymentEvent.event == event)
    )
    if seen.scalar_one_or_none() is not None:
        return {"status": "duplicate", "order_id": str(order.id)}

    result = await orders.apply_payment_result(db, order, succeeded, paid_amount=amount)
    if result == "amount_mismatch":
        # Исключение ниже отбросит фоновые задачи, поэтому предупреждаем владельца сразу
        await telegram.notify_payment_result(order, result)
        raise ConflictError("Сумма платежа не совпадает с заказом.")

    db.add(PaymentEvent(payment_id=key, event=event, order_id=order.id, result=result))
    await db.commit()
    if result == "cancelled":
        await cache.bump("catalog")
    background.add_task(telegram.notify_payment_result, order, result)
    return {"status": result, "order_id": str(order.id)}


async def simulate_sandbox_payment(
    db: AsyncSession,
    cache: Cache,
    telegram: TelegramService,
    background: BackgroundTasks,
    order_id: int,
    outcome: str,
) -> SandboxPaymentOut:
    require_sandbox()
    order = await orders.load_order(db, order_id, for_update=True)
    if not order:
        raise NotFoundError(f"Заказ #{order_id} не найден.")
    result = await orders.apply_payment_result(
        db, order, succeeded=outcome == "succeeded", paid_amount=order.total_amount
    )
    await db.commit()
    if result == "cancelled":
        await cache.bump("catalog")
    background.add_task(telegram.notify_payment_result, order, result)
    return SandboxPaymentOut(
        order_id=order_id,
        outcome=outcome,
        order_status=order.status,
        result=result,
        message=SANDBOX_MESSAGES.get(result, result),
    )


async def check_payment(
    db: AsyncSession,
    cache: Cache,
    gateway: SBPPaymentService,
    telegram: TelegramService,
    background: BackgroundTasks,
    user: User,
    order_id: int,
) -> Order:
    """Для случая, когда вебхук потерялся. В песочнице шлюза нет, отдаём заказ как есть."""
    order = await orders.get_accessible_order(db, order_id, user, for_update=True)
    if order.status == OrderStatus.PENDING.value and order.payment_id and not gateway.is_sandbox:
        try:
            state = await gateway.fetch_payment(order.payment_id)
        except PaymentGatewayError:
            raise BadGatewayError("Не удалось связаться с платёжным сервисом, попробуйте позже.") from None
        if state["status"] in ("succeeded", "canceled"):
            result = await orders.apply_payment_result(
                db, order, succeeded=state["status"] == "succeeded", paid_amount=state["amount"]
            )
            await db.commit()
            if result == "cancelled":
                await cache.bump("catalog")
            background.add_task(telegram.notify_payment_result, order, result)
    return order


def require_sandbox() -> None:
    if not settings.sandbox_payments_enabled:
        # Вне песочницы делаем вид, что ручки нет
        raise NotFoundError("Not Found")


def render_checkout_page(order: Order) -> str:
    require_sandbox()
    return Template(CHECKOUT_TEMPLATE.read_text(encoding="utf-8")).substitute(
        order_id=int(order.id),
        amount=int(order.total_amount),
        order_status=order.status,
        disabled="" if order.status == OrderStatus.PENDING.value else "disabled",
        api=settings.API_V1_STR,
    )
