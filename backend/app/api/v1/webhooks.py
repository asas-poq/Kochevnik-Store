from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Request
from fastapi.responses import HTMLResponse

from app.api.deps import AdminUserDep, DBSessionDep
from app.core.cache import CacheDep
from app.core.config import settings
from app.core.errors import NotFoundError, UnauthorizedError
from app.core.ratelimit import rate_limit
from app.schemas.common import ErrorOut
from app.schemas.order import SandboxPaymentOut, SBPWebhookPayload
from app.services import orders, payments
from app.services.payment_sbp import SBPPaymentService, get_sbp_service
from app.services.telegram import TelegramService, get_telegram_service

router = APIRouter(prefix="/payments", tags=["6. Платежи и Telegram"])

webhook_limit = Depends(rate_limit("webhook", settings.RATE_WEBHOOK_PER_MIN))


@router.post(
    "/webhook",
    summary="Вебхук оплаты СБП",
    dependencies=[webhook_limit],
    responses={
        401: {"model": ErrorOut, "description": "Неверный секрет (песочница)"},
        404: {"model": ErrorOut, "description": "Заказ не найден"},
        409: {"model": ErrorOut, "description": "Платёж чужой или сумма не совпала"},
        503: {"model": ErrorOut, "description": "Шлюз не подтвердил платёж, он повторит доставку"},
    },
)
async def sbp_webhook(
    payload: SBPWebhookPayload,
    background: BackgroundTasks,
    db: DBSessionDep,
    cache: CacheDep,
    x_webhook_secret: str | None = Header(None),
    gateway: SBPPaymentService = Depends(get_sbp_service),
    telegram: TelegramService = Depends(get_telegram_service),
) -> dict[str, str]:
    """Принимает плоский формат и нативный формат ЮKassa. В песочнице нужен секрет в заголовке
    X-Webhook-Secret или в поле secret_signature. В бою статус и сумма берутся у шлюза.
    Ответ status: paid, cancelled, already_paid, already_cancelled, paid_after_cancel, ignored или duplicate."""
    return await payments.process_webhook(db, cache, gateway, telegram, background, payload, x_webhook_secret)


@router.post(
    "/sandbox/orders/{order_id}/simulate",
    response_model=SandboxPaymentOut,
    summary="[тест] Имитировать оплату или отмену",
    responses={404: {"model": ErrorOut, "description": "Заказа нет или не песочница"}},
)
async def simulate(
    order_id: int,
    background: BackgroundTasks,
    db: DBSessionDep,
    cache: CacheDep,
    outcome: Literal["succeeded", "canceled"] = "succeeded",
    telegram: TelegramService = Depends(get_telegram_service),
) -> SandboxPaymentOut:
    """Проходит тот же путь, что и вебхук. Доступно только с ключами test_* и не в production."""
    return await payments.simulate_sandbox_payment(db, cache, telegram, background, order_id, outcome)


@router.get(
    "/sandbox/checkout/{order_id}",
    response_class=HTMLResponse,
    summary="[тест] Страница оплаты",
    responses={404: {"model": ErrorOut, "description": "Заказа нет или не песочница"}},
)
async def sandbox_checkout(order_id: int, db: DBSessionDep) -> HTMLResponse:
    order = await orders.load_order(db, order_id)
    if not order:
        raise NotFoundError(f"Заказ #{order_id} не найден.")
    return HTMLResponse(payments.render_checkout_page(order))


@router.post("/telegram/test", summary="Проверить связку бота и чатов (админ)")
async def telegram_test(admin: AdminUserDep, telegram: TelegramService = Depends(get_telegram_service)) -> dict:
    """В detail лежит дословный ответ Telegram, например chat not found."""
    return await telegram.send_test()


@router.post(
    "/telegram/webhook",
    summary="Вебхук Telegram с нажатиями кнопок",
    dependencies=[webhook_limit],
    responses={
        401: {"model": ErrorOut, "description": "Неверный секрет"},
        404: {"model": ErrorOut, "description": "Режим webhook выключен"},
    },
)
async def telegram_webhook(
    request: Request,
    background: BackgroundTasks,
    x_telegram_bot_api_secret_token: str | None = Header(None),
    telegram: TelegramService = Depends(get_telegram_service),
) -> dict[str, bool]:
    """Работает при TELEGRAM_UPDATES_MODE=webhook. Секрет TELEGRAM_WEBHOOK_SECRET задаётся в setWebhook.
    Права нажимать кнопки проверяются отдельно по списку из настроек."""
    if settings.TELEGRAM_UPDATES_MODE != "webhook" or not settings.TELEGRAM_WEBHOOK_SECRET:
        raise NotFoundError("Not Found")
    if not telegram.check_webhook_secret(x_telegram_bot_api_secret_token):
        raise UnauthorizedError("Неверный секрет.")
    background.add_task(telegram.handle_update, await request.json())
    return {"ok": True}
