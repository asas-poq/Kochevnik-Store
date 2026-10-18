"""
Роутер обработки банковских вебхуков оплаты по СБП (`app/api/v1/webhooks.py`).
Когда покупатель оплачивает заказ по QR-коду СБП в приложении своего банка,
платежный шлюз (ЮKassa / Т-Касса) присылает POST-запрос на `/api/v1/payments/webhook`.
Бэкенд переводит заказ в статус `paid` и в фоне отправляет уведомление владельцу в Telegram.

Безопасность вебхука:
- Песочница (`YOOKASSA_SHOP_ID=test_*`): секрет `PAYMENT_WEBHOOK_SECRET` обязателен
  (заголовок `X-Webhook-Secret` или поле `secret_signature`).
- Боевой режим: статус и сумма платежа перепроверяются запросом к API шлюза
  (вебхуку на слово не верим, подделать его нельзя).
- Всегда: `payment_id` должен совпадать с платежом заказа, сумма — с суммой заказа.

Тестовая оплата (только песочница и не production):
- `GET  /payments/sandbox/checkout/{order_id}` — страница «банка» с кнопками «Оплатить / Отменить»;
- `POST /payments/sandbox/orders/{order_id}/simulate?outcome=succeeded|canceled` — то же самое API-вызовом.
"""

import hmac
from typing import Dict, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import AdminUserDep, DBSessionDep
from app.core.config import settings
from app.core.logging import get_logger
from app.models.order import Order, OrderStatus
from app.schemas.order import SandboxPaymentOut, SBPWebhookPayload
from app.services.orders import apply_payment_result, schedule_payment_notifications
from app.services.payment_sbp import (
    PaymentGatewayError,
    SBPPaymentService,
    get_sbp_service,
)
from app.services.telegram import TelegramNotificationService, get_telegram_service

logger = get_logger(__name__)

router = APIRouter(prefix="/payments", tags=["6. Вебхуки оплаты СБП и Telegram"])


async def _load_order_for_update(db: DBSessionDep, *, order_id: Optional[int], payment_id: Optional[str]):
    cond = Order.id == order_id if order_id is not None else Order.payment_id == payment_id
    stmt = (
        select(Order)
        .where(cond)
        .options(selectinload(Order.items))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


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
    x_webhook_secret: Optional[str] = Header(None),
    sbp_service: SBPPaymentService = Depends(get_sbp_service),
    telegram: TelegramNotificationService = Depends(get_telegram_service),
) -> Dict[str, str]:
    """
    Принимает уведомление платежного шлюза ЮKassa / Т-Касса:
    1. Проверяет подлинность (секрет в песочнице / перепроверка у шлюза в бою).
    2. Находит заказ по `order_id` (или `payment_id`) и сверяет `payment_id` и сумму.
    3. `payment.succeeded` → заказ `paid`, фиксируется `paid_at`, владельцу уходит
       уведомление в Telegram (в фоне).
    4. `payment.canceled` → заказ `cancelled`, остатки возвращаются на склад.
    Повторные вебхуки безопасны (идемпотентность по статусу заказа). Если оплата пришла по уже
    отменённому заказу — остатки автоматически не списываются, владелец получает предупреждение.
    """
    payment_id, order_id, amount = payload.normalized()
    logger.info(
        f"Получен вебхук СБП: event='{payload.event}', order_id={order_id}, payment_id='{payment_id}'"
    )

    if order_id is None and not payment_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не указан ни order_id, ни payment_id.",
        )

    # --- 1. Подлинность вебхука ---
    if sbp_service.is_sandbox:
        provided = x_webhook_secret or payload.secret_signature or ""
        if not hmac.compare_digest(provided, settings.PAYMENT_WEBHOOK_SECRET):
            logger.warning("Вебхук СБП отклонён: неверный секрет.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверная подпись вебхука."
            )
        succeeded = payload.event == "payment.succeeded"
        if payload.event not in ("payment.succeeded", "payment.canceled"):
            logger.info(f"Неизвестный тип события вебхука: {payload.event}")
            return {"status": "ignored", "event": payload.event}
    else:
        if not payment_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Не указан payment_id."
            )
        try:
            gateway = await sbp_service.fetch_payment(payment_id)
        except PaymentGatewayError:
            # 503 — шлюз повторит доставку вебхука позже
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Не удалось подтвердить платёж у шлюза.",
            )
        if gateway["status"] not in ("succeeded", "canceled"):
            return {"status": "ignored", "event": str(gateway["status"])}
        succeeded = gateway["status"] == "succeeded"
        amount = gateway["amount"]  # источник истины — шлюз

    # --- 2. Заказ и сверка платежа ---
    order = await _load_order_for_update(db, order_id=order_id, payment_id=payment_id)
    if not order:
        logger.error(f"Вебхук СБП: заказ не найден (order_id={order_id}, payment_id={payment_id})")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден."
        )

    if payment_id and order.payment_id and order.payment_id != payment_id:
        logger.error(
            f"Вебхук СБП: payment_id='{payment_id}' не совпадает с платежом заказа #{order.id} "
            f"('{order.payment_id}')"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Платёж не относится к этому заказу."
        )

    # --- 3. Применяем результат (идемпотентно) ---
    result = await apply_payment_result(db, order, succeeded, paid_amount=amount)
    schedule_payment_notifications(background_tasks, telegram, order, result)

    if result == "amount_mismatch":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Сумма платежа не совпадает с заказом."
        )
    return {"status": result, "order_id": str(order.id)}


# ==============================================================================
# ПЕСОЧНИЦА: тестовая оплата (как будто покупатель оплатил / отменил в банке)
# ==============================================================================
def _require_sandbox() -> None:
    if not settings.sandbox_payments_enabled:
        # Притворяемся, что ручки нет: в боевом режиме она недоступна вообще
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


@router.post(
    "/sandbox/orders/{order_id}/simulate",
    response_model=SandboxPaymentOut,
    summary="[ТЕСТ] Имитировать оплату или отмену платежа заказа (только песочница)",
)
async def sandbox_simulate_payment(
    order_id: int,
    background_tasks: BackgroundTasks,
    db: DBSessionDep,
    outcome: Literal["succeeded", "canceled"] = "succeeded",
    telegram: TelegramNotificationService = Depends(get_telegram_service),
) -> SandboxPaymentOut:
    """
    Проходит ТОТ ЖЕ путь, что и настоящий вебхук: смена статуса, `paid_at`, возврат остатков при
    отмене, уведомление в Telegram (в демо-режиме — в лог). После вызова проверяйте
    `GET /orders/{id}`, добавляйте отзыв, переводите заказ в `shipped` и т. д.
    Доступно только при тестовых ключах (`YOOKASSA_SHOP_ID=test_*`) и `ENVIRONMENT != production`.
    """
    _require_sandbox()
    order = await _load_order_for_update(db, order_id=order_id, payment_id=None)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Заказ #{order_id} не найден."
        )

    result = await apply_payment_result(
        db, order, succeeded=outcome == "succeeded", paid_amount=order.total_amount
    )
    schedule_payment_notifications(background_tasks, telegram, order, result)

    messages = {
        "paid": "Оплата имитирована: заказ переведён в статус paid.",
        "already_paid": "Заказ уже был оплачен.",
        "paid_after_cancel": "Заказ уже отменён (например, по таймауту) — оплата не применена.",
        "cancelled": "Платёж отменён: заказ cancelled, остатки возвращены на склад.",
        "already_cancelled": "Заказ уже отменён.",
        "ignored": "Действие проигнорировано: заказ в статусе, где это невозможно.",
    }
    logger.info(f"[SANDBOX] Заказ #{order_id}: outcome={outcome}, result={result}")
    return SandboxPaymentOut(
        order_id=order_id,
        outcome=outcome,
        order_status=order.status,
        result=result,
        message=messages.get(result, result),
    )


_CHECKOUT_PAGE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Тестовая оплата СБП — заказ #{order_id}</title>
<style>
 body{{font-family:system-ui,sans-serif;background:#f4f1ec;margin:0;display:flex;
      min-height:100vh;align-items:center;justify-content:center}}
 .card{{background:#fff;border-radius:16px;padding:32px;max-width:380px;width:92%;
       box-shadow:0 8px 30px rgba(0,0,0,.08);text-align:center}}
 .badge{{display:inline-block;background:#fff3cd;color:#7a5b00;border-radius:8px;
        padding:4px 10px;font-size:12px;margin-bottom:12px}}
 .sum{{font-size:34px;font-weight:700;margin:8px 0 4px}}
 button{{width:100%;padding:14px;border:0;border-radius:10px;font-size:16px;cursor:pointer;margin-top:10px}}
 .pay{{background:#1f8f4e;color:#fff}} .cancel{{background:#eee;color:#333}}
 button:disabled{{opacity:.5;cursor:default}} #msg{{margin-top:16px;font-size:14px;min-height:20px}}
</style></head><body><div class="card">
 <div class="badge">🧪 ТЕСТОВЫЙ РЕЖИМ — деньги не списываются</div>
 <div>Заказ #{order_id}</div>
 <div class="sum">{amount} ₽</div>
 <div style="color:#777;font-size:14px">Статус заказа: <b id="st">{order_status}</b></div>
 <button class="pay" id="pay" {disabled}>Оплатить по СБП</button>
 <button class="cancel" id="cancel" {disabled}>Отменить платёж</button>
 <div id="msg"></div>
</div>
<script>
 async function simulate(outcome){{
   document.getElementById('pay').disabled = true;
   document.getElementById('cancel').disabled = true;
   const r = await fetch('{api}/payments/sandbox/orders/{order_id}/simulate?outcome=' + outcome,
                         {{method:'POST'}});
   const d = await r.json();
   document.getElementById('msg').textContent = d.message || d.detail || 'Ошибка';
   if (d.order_status) document.getElementById('st').textContent = d.order_status;
 }}
 document.getElementById('pay').onclick = () => simulate('succeeded');
 document.getElementById('cancel').onclick = () => simulate('canceled');
</script></body></html>"""


@router.get(
    "/sandbox/checkout/{order_id}",
    response_class=HTMLResponse,
    summary="[ТЕСТ] Страница «банка» для тестовой оплаты (открывается по payment_url)",
)
async def sandbox_checkout_page(order_id: int, db: DBSessionDep) -> HTMLResponse:
    """В песочнице `payment_url` заказа ведёт сюда: нажмите «Оплатить» — и заказ станет `paid`."""
    _require_sandbox()
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Заказ #{order_id} не найден."
        )
    html = _CHECKOUT_PAGE.format(
        order_id=int(order.id),
        amount=int(order.total_amount),
        order_status=order.status,  # значение из enum статусов, не пользовательский ввод
        disabled="" if order.status == OrderStatus.PENDING.value else "disabled",
        api=settings.API_V1_STR,
    )
    return HTMLResponse(html)


# ==============================================================================
# ДИАГНОСТИКА TELEGRAM (только Администратор)
# ==============================================================================
@router.post(
    "/telegram/test",
    summary="Отправить тестовое сообщение в Telegram и показать причину ошибки (только Администратор)",
)
async def telegram_test(
    admin_user: AdminUserDep,
    telegram: TelegramNotificationService = Depends(get_telegram_service),
) -> Dict[str, object]:
    """
    Проверяет связку бота и чата. В ответе `ok` и `detail` — дословный ответ Telegram,
    например `chat not found` (неверный chat_id или бот не в чате) или
    `bot was kicked from the group chat`.
    """
    result = await telegram.send_test()
    logger.info(f"Тест Telegram от админа ID={admin_user.id}: {result}")
    return result


# ==============================================================================
# TELEGRAM WEBHOOK: нажатия кнопок (режим TELEGRAM_UPDATES_MODE=webhook, нужен HTTPS)
# ==============================================================================
@router.post(
    "/telegram/webhook",
    summary="Вебхук Telegram: нажатия кнопок управления заказом (для продакшена)",
)
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_telegram_bot_api_secret_token: Optional[str] = Header(None),
    telegram: TelegramNotificationService = Depends(get_telegram_service),
) -> Dict[str, bool]:
    """
    Telegram присылает сюда update при нажатии кнопки «Передать в доставку» / «Вручён».
    Подлинность проверяется секретом `TELEGRAM_WEBHOOK_SECRET` (заголовок
    `X-Telegram-Bot-Api-Secret-Token`, задаётся при `setWebhook`). Права проверяются отдельно:
    кнопку может нажать только пользователь из `TELEGRAM_OWNER_CHAT_ID` / `TELEGRAM_ADMIN_USER_IDS`.
    """
    if settings.TELEGRAM_UPDATES_MODE != "webhook" or not settings.TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    if not hmac.compare_digest(
        x_telegram_bot_api_secret_token or "", settings.TELEGRAM_WEBHOOK_SECRET
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный секрет.")

    update = await request.json()
    # Telegram ждёт быстрый ответ — обрабатываем нажатие в фоне
    background_tasks.add_task(telegram.handle_update, update)
    return {"ok": True}