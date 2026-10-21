import uuid

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

YOOKASSA_API_URL = "https://api.yookassa.ru/v3/payments"


class PaymentGatewayError(Exception):
    pass


class SBPPaymentService:
    """Платежи СБП через ЮKassa. С ключами test_* шлюз не вызывается, оплата имитируется
    на локальной странице /payments/sandbox/checkout/{order_id}."""

    @property
    def is_sandbox(self) -> bool:
        return settings.payments_sandbox_mode

    async def create_sbp_payment(
        self, order_id: int, total_amount: int, description: str, customer_phone: str
    ) -> tuple[str, str]:
        if self.is_sandbox:
            url = (
                f"{settings.PUBLIC_BASE_URL.rstrip('/')}{settings.API_V1_STR}"
                f"/payments/sandbox/checkout/{order_id}"
            )
            return f"sbp_test_{uuid.uuid4().hex[:16]}", url

        payload = {
            "amount": {"value": f"{total_amount}.00", "currency": "RUB"},
            "payment_method_data": {"type": "sbp"},
            "confirmation": {
                "type": "redirect",
                "return_url": f"{settings.PAYMENT_RETURN_URL}?order_id={order_id}",
            },
            "capture": True,
            "description": description,
            "metadata": {"order_id": order_id, "customer_phone": customer_phone},
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    YOOKASSA_API_URL,
                    json=payload,
                    # Один ключ на заказ: повторный запрос не создаст второй платёж
                    headers={"Idempotence-Key": f"order-{order_id}"},
                    auth=(settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY),
                )
                response.raise_for_status()
                data = response.json()
            return data["id"], data["confirmation"]["confirmation_url"]
        except Exception as exc:
            logger.error("ЮKassa не создала платёж", extra={"order_id": order_id, "error": str(exc)})
            raise PaymentGatewayError(str(exc)) from exc

    async def fetch_payment(self, payment_id: str) -> dict:
        """Статус платежа у шлюза: succeeded, canceled, pending или waiting_for_capture."""
        if self.is_sandbox:
            raise PaymentGatewayError("В песочнице нет внешнего шлюза")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{YOOKASSA_API_URL}/{payment_id}",
                    auth=(settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY),
                )
                response.raise_for_status()
                data = response.json()
            return {"status": data.get("status"), "amount": int(float(data["amount"]["value"]))}
        except Exception as exc:
            logger.error("ЮKassa не отдала платёж", extra={"payment_id": payment_id, "error": str(exc)})
            raise PaymentGatewayError(str(exc)) from exc


sbp_payment_service = SBPPaymentService()


def get_sbp_service() -> SBPPaymentService:
    return sbp_payment_service
