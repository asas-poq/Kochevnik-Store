"""
Сервис интеграции платежной системы СБП — ЮKassa / Т-Касса (`app/services/payment_sbp.py`).
Отвечает за создание платежа СБП (QR-код), проверку его статуса у шлюза
и за песочницу (тестовые ключи `test_*`), в которой оплату можно имитировать локально.
"""

import uuid
from typing import Dict, Tuple

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class PaymentGatewayError(Exception):
    """Шлюз недоступен или вернул ошибку. Заказ при этом НЕ должен оставаться «висеть»."""


class SBPPaymentService:
    """
    Сервис работы с платежами СБП (Система Быстрых Платежей).
    - Боевой режим: обращается к API ЮKassa (`https://api.yookassa.ru/v3/payments`).
    - Песочница (`YOOKASSA_SHOP_ID` начинается с `test_`): шлюз не вызывается, а ссылка оплаты
      ведёт на локальную тестовую страницу `/api/v1/payments/sandbox/checkout/{order_id}`,
      где можно нажать «Оплатить» или «Отменить».
    """

    YOOKASSA_API_URL = "https://api.yookassa.ru/v3/payments"

    @property
    def is_sandbox(self) -> bool:
        return settings.payments_sandbox_mode

    async def create_sbp_payment(
        self, order_id: int, total_amount: int, description: str, customer_phone: str
    ) -> Tuple[str, str]:
        """
        Создает платеж СБП для заказа `order_id` на сумму `total_amount` ₽.
        Возвращает `(payment_id, payment_url)`. При сбое шлюза бросает `PaymentGatewayError`.
        """
        logger.info(
            f"Инициализация платежа СБП для заказа #{order_id} на сумму {total_amount} ₽ "
            f"(провайдер: {settings.PAYMENT_PROVIDER}, sandbox={self.is_sandbox})"
        )

        if self.is_sandbox:
            payment_id = f"sbp_test_{uuid.uuid4().hex[:16]}"
            payment_url = (
                f"{settings.PUBLIC_BASE_URL.rstrip('/')}{settings.API_V1_STR}"
                f"/payments/sandbox/checkout/{order_id}"
            )
            logger.info(
                f"[SANDBOX СБП] Тестовая страница оплаты заказа #{order_id}: {payment_url}"
            )
            return payment_id, payment_url

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
                    # Один и тот же ключ на заказ: повторный запрос не создаст второй платёж
                    headers={"Idempotence-Key": f"order-{order_id}"},
                    auth=(settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY),
                )
                response.raise_for_status()
                data = response.json()
                logger.info(f"Платеж СБП создан в ЮKassa: payment_id={data['id']}")
                return data["id"], data["confirmation"]["confirmation_url"]
        except Exception as exc:
            logger.error(f"Ошибка создания платежа в ЮKassa для заказа #{order_id}: {exc}")
            raise PaymentGatewayError(str(exc)) from exc

    async def fetch_payment(self, payment_id: str) -> Dict:
        """
        Запрашивает у шлюза актуальный статус платежа (источник истины для вебхука).
        Возвращает `{"status": "succeeded|canceled|pending|waiting_for_capture", "amount": int}`.
        """
        if self.is_sandbox:
            raise PaymentGatewayError("В песочнице нет внешнего шлюза для проверки платежа")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.YOOKASSA_API_URL}/{payment_id}",
                    auth=(settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY),
                )
                response.raise_for_status()
                data = response.json()
                return {
                    "status": data.get("status"),
                    "amount": int(float(data["amount"]["value"])),
                }
        except Exception as exc:
            logger.error(f"Ошибка проверки платежа {payment_id} в ЮKassa: {exc}")
            raise PaymentGatewayError(str(exc)) from exc


sbp_payment_service = SBPPaymentService()


def get_sbp_service() -> SBPPaymentService:
    """Зависимость FastAPI (`Depends(get_sbp_service)`) для сервиса оплаты СБП."""
    return sbp_payment_service