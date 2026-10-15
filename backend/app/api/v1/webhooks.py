"""
Роутер обработки банковских вебхуков оплаты по СБП (`app/api/v1/webhooks.py`).
Когда покупатель оплачивает заказ по QR-коду СБП в приложении своего банка,
платежный шлюз (ЮKassa / Т-Касса) присылает POST-запрос на `/api/v1/payments/webhook`.
Бэкенд переводит заказ в статус `paid` и в фоне отправляет уведомление владельцу в Telegram.
"""

from datetime import datetime, timezone
from typing import Dict
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DBSessionDep
from app.core.logging import get_logger
from app.models.catalog import ProductSize
from app.models.order import Order
from app.schemas.order import SBPWebhookPayload
from app.services.telegram import TelegramNotificationService, get_telegram_service

logger = get_logger(__name__)

router = APIRouter(prefix="/payments", tags=["6. Вебхуки оплаты СБП и Telegram"])


# ==============================================================================
# РУЧКА 1: Прием вебхука от платежной системы (POST /api/v1/payments/webhook)
# ==============================================================================
@router.post(
    "/webhook",
    summary="Вебхук подтверждения оплаты по СБП (POST /api/v1/payments/webhook)",
)
async def sbp_payment_webhook(
    payload: SBPWebhookPayload,
    background_tasks: BackgroundTasks,
    db: DBSessionDep,
    telegram: TelegramNotificationService = Depends(get_telegram_service),
) -> Dict[str, str]:
    """
    Принимает уведомление от платежного шлюза ЮKassa / Т-Касса (`POST /api/v1/payments/webhook`):
    1. Находит заказ по `order_id` или `payment_id`.
    2. Если событие `payment.succeeded`:
       - Меняет статус заказа на `paid` и фиксирует точное время оплаты `paid_at`.
       - Ставит в фоновую очередь (`BackgroundTasks`) отправку уведомления в Telegram владельцу магазина:
         *«🎉 Новый оплаченный заказ #104! Свитер кашемировый (Бежевый, размер M) — 18 500 ₽. Доставка: СДЭК, Москва...»*
    3. Если событие `payment.canceled`:
       - Переводит заказ в статус `cancelled` и автоматически возвращает зарезервированные остатки обратно на склад!
    """
    logger.info(
        f"Получен вебхук СБП: event='{payload.event}', order_id={payload.order_id}, payment_id='{payload.payment_id}'"
    )

    stmt = (
        select(Order)
        .where(Order.id == payload.order_id)
        .options(selectinload(Order.items))
        .with_for_update()
    )
    order = (await db.execute(stmt)).scalar_one_or_none()

    if not order:
        logger.error(f"Вебхук СБП: заказ #{payload.order_id} не найден в БД")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Заказ #{payload.order_id} не найден.",
        )

    # Идемпотентная проверка: если заказ уже оплачен, просто возвращаем 200 OK
    if order.status == "paid":
        logger.info(f"Заказ #{order.id} уже имеет статус 'paid'. Игнорируем дубликат вебхука.")
        return {"status": "already_paid", "order_id": str(order.id)}

    if payload.event == "payment.succeeded":
        order.status = "paid"
        order.paid_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(
            f"Заказ #{order.id} успешно переведен в статус 'paid'! "
            f"Запускаем фоновую отправку уведомления в Telegram."
        )
        # Отправляем красивое уведомление владельцу магазина в фоне
        background_tasks.add_task(telegram.send_order_paid_alert, order)
        return {"status": "paid", "order_id": str(order.id)}

    elif payload.event == "payment.canceled":
        order.status = "cancelled"
        # Возвращаем зарезервированный товар обратно на склад
        for item in order.items:
            if item.variant_id:
                size_row = await db.get(ProductSize, item.variant_id)
                if size_row:
                    size_row.stock += item.quantity
        await db.commit()
        logger.warning(
            f"Оплата заказа #{order.id} отменена. Статус изменен на 'cancelled', остатки возвращены на склад."
        )
        return {"status": "cancelled", "order_id": str(order.id)}

    logger.info(f"Неизвестный тип события вебхука: {payload.event}")
    return {"status": "ignored", "event": payload.event}
