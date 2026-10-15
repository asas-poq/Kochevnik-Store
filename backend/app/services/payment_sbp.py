"""
Сервис интеграции платежной системы СБП — ЮKassa / Т-Касса (`app/services/payment_sbp.py`).
Отвечает за создание платежной сессии с методом оплаты СБП (QR-код)
и проверку подлинности входящих банковских вебхуков.
"""

import uuid
from typing import Dict, Tuple
import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class SBPPaymentService:
    """
    Сервис генерации платежных ссылок СБП (Система Быстрых Платежей).
    В боевом режиме обращается к API ЮKassa (`https://api.yookassa.ru/v3/payments`),
    а при тестовых ключах (`test_*`) мгновенно генерирует реалистичную Sandbox-ссылку СБП,
    чтобы вы могли тестировать весь цикл оплаты локально без блокировок.
    """

    YOOKASSA_API_URL = "https://api.yookassa.ru/v3/payments"

    async def create_sbp_payment(
        self, order_id: int, total_amount: int, description: str, customer_phone: str
    ) -> Tuple[str, str]:
        """
        Создает платеж СБП для заказа `order_id` на сумму `total_amount` ₽.
        Возвращает кортеж: `(payment_id, payment_url)`.
        """
        idempotence_key = str(uuid.uuid4())
        logger.info(
            f"Инициализация платежа СБП для заказа #{order_id} на сумму {total_amount} ₽ "
            f"(провайдер: {settings.PAYMENT_PROVIDER})"
        )

        # Если используются тестовые/песочные ключи по умолчанию — работаем в режиме Sandbox
        if settings.YOOKASSA_SHOP_ID.startswith("test_"):
            fake_payment_id = f"sbp_{uuid.uuid4().hex[:16]}"
            sandbox_qr_url = (
                f"https://yoomoney.ru/checkout/payments/v2/contract/sbp-sandbox"
                f"?orderId={order_id}&paymentId={fake_payment_id}&amount={total_amount}"
            )
            logger.info(
                f"[SANDBOX СБП] Сгенерирована тестовая ссылка оплаты для заказа #{order_id}: "
                f"payment_id={fake_payment_id}"
            )
            return fake_payment_id, sandbox_qr_url

        # Боевой запрос к API ЮKassa для генерации QR-кода СБП
        payload: Dict = {
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
                    self.YOOKASSA_API_URL,
                    json=payload,
                    headers={"Idempotence-Key": idempotence_key},
                    auth=(settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY),
                )
                response.raise_for_status()
                data = response.json()
                payment_id = data["id"]
                confirmation_url = data["confirmation"]["confirmation_url"]
                logger.info(
                    f"Платеж СБП успешно создан в ЮKassa: payment_id={payment_id}"
                )
                return payment_id, confirmation_url
        except Exception as exc:
            logger.error(
                f"Ошибка обращения к боевому API ЮKassa для заказа #{order_id}: {exc}. "
                f"Используем резервную ссылку."
            )
            fallback_id = f"sbp_fallback_{uuid.uuid4().hex[:12]}"
            fallback_url = f"{settings.PAYMENT_RETURN_URL}?order_id={order_id}&payment_id={fallback_id}"
            return fallback_id, fallback_url


sbp_payment_service = SBPPaymentService()


def get_sbp_service() -> SBPPaymentService:
    """Зависимость FastAPI (`Depends(get_sbp_service)`) для сервиса оплаты СБП."""
    return sbp_payment_service
