"""
Сервис отправки уведомлений владельцу магазина в Telegram (`app/services/telegram.py`).
Формирует красивое сообщение о новом оплаченном заказе со списком товаров,
размерами, суммой и адресом доставки (СДЭК / Почта России / Шоурум).
"""

import httpx
from app.core.config import settings
from app.core.logging import get_logger
from app.models.order import Order

logger = get_logger(__name__)


class TelegramNotificationService:
    """
    Асинхронный клиент Telegram Bot API для мгновенного оповещения владельца бутика
    о новых заказах и оплатах по СБП.
    """

    DELIVERY_LABELS = {
        "cdek_pvz": "СДЭК (Пункт выдачи)",
        "cdek_courier": "СДЭК (Курьер до двери)",
        "russian_post": "Почта России",
        "showroom_pickup": "Самовывоз из шоурума",
    }

    def format_paid_order_message(self, order: Order) -> str:
        """
        Формирует текст уведомления в точности по стандарту из дорожной карты:
        «🎉 Новый оплаченный заказ #104! Свитер кашемировый (Бежевый, размер M) — 18 500 ₽. Доставка: СДЭК, Москва...»
        """
        items_lines = []
        for item in order.items:
            color_str = f"{item.color}, " if item.color else ""
            price_formatted = f"{item.subtotal:,}".replace(",", " ")
            items_lines.append(
                f"• {item.product_name} ({color_str}размер {item.size}) x{item.quantity} — {price_formatted} ₽"
            )

        items_block = "\n".join(items_lines)
        total_formatted = f"{order.total_amount:,}".replace(",", " ")
        delivery_label = self.DELIVERY_LABELS.get(
            order.delivery_method, order.delivery_method
        )

        message = (
            f"🎉 <b>Новый оплаченный заказ #{order.id}!</b>\n\n"
            f"<b>Состав заказа:</b>\n{items_block}\n\n"
            f"💰 <b>Итого оплачено (СБП):</b> {total_formatted} ₽\n"
            f"🚚 <b>Доставка:</b> {delivery_label}, {order.delivery_city}, {order.delivery_address}\n"
            f"👤 <b>Клиент:</b> {order.customer_name} ({order.customer_phone})"
        )
        if order.customer_comment:
            message += f"\n💬 <b>Комментарий:</b> {order.customer_comment}"
        return message

    async def send_order_paid_alert(self, order: Order) -> bool:
        """
        Отправляет сообщение о новом оплаченном заказе в Telegram владельцу магазина.
        Вызывается асинхронно через `BackgroundTasks`, чтобы не задерживать ответ вебхука.
        """
        text = self.format_paid_order_message(order)

        # Если токен бота еще не настроен в .env, логируем полное сообщение в консоль/файл
        if (
            not settings.TELEGRAM_BOT_TOKEN
            or "test_bot_token" in settings.TELEGRAM_BOT_TOKEN
        ):
            logger.info(
                f"[TELEGRAM УВЕДОМЛЕНИЕ ВЛАДЕЛЬЦУ (Демо-режим)]:\n{text}"
            )
            return True

        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": settings.TELEGRAM_OWNER_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        }

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                logger.info(
                    f"Уведомление в Telegram по заказу #{order.id} успешно доставлено владельцу."
                )
                return True
        except Exception as exc:
            logger.error(
                f"Не удалось отправить уведомление в Telegram по заказу #{order.id}: {exc}"
            )
            return False


telegram_service = TelegramNotificationService()


def get_telegram_service() -> TelegramNotificationService:
    """Зависимость FastAPI (`Depends(get_telegram_service)`)."""
    return telegram_service
