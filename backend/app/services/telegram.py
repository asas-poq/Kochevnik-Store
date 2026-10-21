import asyncio
import hmac
import re
from html import escape as esc
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.models import Order, OrderStatus, OrderTelegramMessage
from app.services import orders as order_service

logger = get_logger(__name__)

CALLBACK_RE = re.compile(r"ord:(ship|done):(\d+)")

STAGES = {
    OrderStatus.PAID.value: ("НОВЫЙ ОПЛАЧЕННЫЙ ЗАКАЗ", "ожидает отправки"),
    OrderStatus.SHIPPED.value: ("ЗАКАЗ ОТПРАВЛЕН", "передан в доставку"),
    OrderStatus.COMPLETED.value: ("ЗАКАЗ ВРУЧЁН КЛИЕНТУ", "завершён"),
}
DELIVERY_LABELS = {
    "cdek_pvz": "СДЭК, пункт выдачи",
    "cdek_courier": "СДЭК, курьер",
    "russian_post": "Почта России",
    "showroom_pickup": "Самовывоз из шоурума",
}


def _money(value: int) -> str:
    return f"{value:,}".replace(",", " ")


class TelegramService:
    """Владельцу в личку уходит сообщение с кнопками, в группу сотрудников только статус.
    Кнопки нажимает только тот, чей id в TELEGRAM_OWNER_CHAT_ID или TELEGRAM_ADMIN_USER_IDS."""

    @property
    def is_demo(self) -> bool:
        token = settings.TELEGRAM_BOT_TOKEN
        return not token or "test_bot_token" in token

    @property
    def owner_chat_id(self) -> str | None:
        return settings.TELEGRAM_OWNER_CHAT_ID.strip() or None

    @property
    def staff_chat_id(self) -> str | None:
        staff = settings.TELEGRAM_STAFF_CHAT_ID.strip()
        return staff if staff and staff != self.owner_chat_id else None

    def check_webhook_secret(self, token: str | None) -> bool:
        secret = settings.TELEGRAM_WEBHOOK_SECRET
        enabled = settings.TELEGRAM_UPDATES_MODE == "webhook" and bool(secret)
        return enabled and hmac.compare_digest(token or "", secret)

    def format_order(self, order: Order, stage: str | None = None, actor: str | None = None) -> str:
        title, label = STAGES.get(stage or order.status, STAGES[OrderStatus.PAID.value])
        lines = []
        for item in order.items:
            color = f"{esc(item.color)}, " if item.color else ""
            lines.append(
                f"- {esc(item.product_name)} ({color}размер {esc(item.size)}) "
                f"x{item.quantity}, {_money(item.subtotal)} руб."
            )
        delivery = DELIVERY_LABELS.get(order.delivery_method, order.delivery_method)
        text = [
            *(["<b>[ТЕСТОВАЯ ОПЛАТА]</b>"] if settings.payments_sandbox_mode else []),
            f"<b>{title} #{order.id}</b>",
            f"Статус: <b>{label}</b>",
            "",
            "<b>Состав заказа:</b>",
            *lines,
            "",
            f"<b>Оплачено (СБП):</b> {_money(order.total_amount)} руб.",
            f"<b>Доставка:</b> {esc(delivery)}, {esc(order.delivery_city)}, {esc(order.delivery_address)}",
            f"<b>Клиент:</b> {esc(order.customer_name)} ({esc(order.customer_phone)})",
            f"<b>ID клиента:</b> {order.user_id or '-'}",
        ]
        if order.customer_comment:
            text.append(f"<b>Комментарий:</b> {esc(order.customer_comment)}")
        if actor:
            text.append(f"\nОтметил: <b>{esc(actor)}</b>")
        return "\n".join(text)

    @staticmethod
    def keyboard(order: Order) -> dict[str, list]:
        if order.status == OrderStatus.PAID.value:
            rows = [[{"text": "Передать в доставку", "callback_data": f"ord:ship:{order.id}"}]]
        elif order.status == OrderStatus.SHIPPED.value:
            rows = [[{"text": "Заказ вручён клиенту", "callback_data": f"ord:done:{order.id}"}]]
        else:
            rows = []
        return {"inline_keyboard": rows}

    async def _call(self, method: str, payload: dict[str, Any], timeout: float = 8.0) -> tuple[bool, Any]:
        """Токен лежит в URL, поэтому ни URL, ни текст исключения в логи и ответы не попадают."""
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}"
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=payload)
        except httpx.HTTPError as exc:
            return False, f"Сетевая ошибка при обращении к Telegram: {type(exc).__name__}"
        try:
            data = resp.json()
        except ValueError:
            return False, f"Telegram вернул {resp.status_code}: {resp.text[:200]}"
        if resp.status_code == 200 and data.get("ok"):
            return True, data.get("result")
        description = data.get("description", resp.text[:200])
        migrate_to = (data.get("parameters") or {}).get("migrate_to_chat_id")
        if migrate_to:
            description += f" (новый chat_id группы: {migrate_to})"
        return False, f"Telegram вернул {resp.status_code}: {description}"

    async def _send(self, chat_id: str, text: str, markup: dict | None = None) -> tuple[bool, Any]:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if markup is not None:
            payload["reply_markup"] = markup
        ok, result = await self._call("sendMessage", payload)
        return ok, (result["message_id"] if ok else result)

    async def _edit(self, chat_id: int, message_id: int, text: str, markup: dict) -> bool:
        ok, result = await self._call(
            "editMessageText",
            {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML", "reply_markup": markup},
        )
        return ok or "message is not modified" in str(result)

    async def _answer(self, callback_id: str, text: str, alert: bool = False) -> None:
        await self._call(
            "answerCallbackQuery", {"callback_query_id": callback_id, "text": text[:190], "show_alert": alert}
        )

    async def send_alert(self, text: str, order_id: int | None = None) -> bool:
        if self.is_demo or not self.owner_chat_id:
            logger.info("Telegram в демо-режиме", extra={"text": text})
            return True
        ok, detail = await self._send(self.owner_chat_id, text)
        if not ok:
            logger.error("Telegram не принял сообщение", extra={"order_id": order_id, "detail": detail})
        return ok

    async def send_order_paid_alert(self, order: Order) -> bool:
        text = self.format_order(order, OrderStatus.PAID.value)
        if self.is_demo:
            logger.info("Telegram в демо-режиме", extra={"text": text})
            return True

        saved: list[OrderTelegramMessage] = []
        all_ok = True
        targets = [("owner", self.owner_chat_id, self.keyboard(order)), ("staff", self.staff_chat_id, None)]
        for role, chat_id, markup in targets:
            if not chat_id:
                continue
            ok, result = await self._send(chat_id, text, markup)
            if ok:
                saved.append(
                    OrderTelegramMessage(order_id=order.id, role=role, chat_id=int(chat_id), message_id=int(result))
                )
            else:
                all_ok = False
                logger.error("Telegram не принял сообщение", extra={"order_id": order.id, "role": role, "detail": result})
        if saved:
            async with AsyncSessionLocal() as db:
                db.add_all(saved)
                await db.commit()
        return all_ok

    async def notify_payment_result(self, order: Order, result: str) -> None:
        if result == "paid":
            await self.send_order_paid_alert(order)
        elif result == "paid_after_cancel":
            await self.send_alert(
                f"<b>Оплата пришла по отменённому заказу #{order.id}</b> ({order.total_amount} руб.). "
                "Остатки уже вернулись на склад. Подтвердите заказ вручную или сделайте возврат.",
                order.id,
            )
        elif result == "amount_mismatch":
            await self.send_alert(
                f"<b>Сумма платежа не совпала с заказом #{order.id}</b> "
                f"(ожидалось {order.total_amount} руб.). Заказ не отмечен оплаченным.",
                order.id,
            )

    async def sync_order_status(self, order_id: int, actor: str | None = None) -> None:
        """Личное сообщение редактируем. В группе старое удаляем и шлём новое, чтобы оно всплыло."""
        if self.is_demo:
            logger.info("Telegram в демо-режиме, статус заказа", extra={"order_id": order_id})
            return
        async with AsyncSessionLocal() as db:
            order = (
                await db.execute(select(Order).where(Order.id == order_id).options(selectinload(Order.items)))
            ).scalar_one_or_none()
            if not order or order.status not in STAGES:
                return
            text = self.format_order(order, order.status, actor)
            rows = {
                r.role: r
                for r in (
                    await db.execute(select(OrderTelegramMessage).where(OrderTelegramMessage.order_id == order_id))
                ).scalars()
            }

            if self.owner_chat_id:
                markup = self.keyboard(order)
                row = rows.get("owner")
                if not (row and await self._edit(row.chat_id, row.message_id, text, markup)):
                    ok, result = await self._send(self.owner_chat_id, text, markup)
                    if ok and row:
                        row.message_id = int(result)
                    elif ok:
                        db.add(
                            OrderTelegramMessage(
                                order_id=order_id, role="owner", chat_id=int(self.owner_chat_id), message_id=int(result)
                            )
                        )

            if self.staff_chat_id:
                row = rows.get("staff")
                ok, result = await self._send(self.staff_chat_id, text)
                if ok and row:
                    deleted, _ = await self._call("deleteMessage", {"chat_id": row.chat_id, "message_id": row.message_id})
                    if not deleted:
                        # Сообщения старше 48 часов Telegram не удаляет, поэтому хотя бы затираем статус
                        await self._edit(
                            row.chat_id, row.message_id,
                            f"Заказ #{order_id}: статус изменился, см. новое сообщение ниже.",
                            {"inline_keyboard": []},
                        )
                    row.message_id = int(result)
                elif ok:
                    db.add(
                        OrderTelegramMessage(
                            order_id=order_id, role="staff", chat_id=int(self.staff_chat_id), message_id=int(result)
                        )
                    )
                else:
                    logger.error("Telegram не принял сообщение", extra={"order_id": order_id, "role": "staff", "detail": result})
            await db.commit()

    async def handle_update(self, update: dict[str, Any]) -> None:
        callback = update.get("callback_query")
        if callback:
            await self._handle_callback(callback)

    async def _handle_callback(self, callback: dict[str, Any]) -> None:
        callback_id = callback["id"]
        user = callback.get("from") or {}
        match = CALLBACK_RE.fullmatch(callback.get("data") or "")
        if not match:
            await self._answer(callback_id, "Неизвестная команда")
            return
        if str(user.get("id")) not in settings.telegram_approver_ids:
            logger.warning("Нажатие кнопки от чужого пользователя", extra={"tg_user_id": user.get("id")})
            await self._answer(callback_id, "Нет прав управлять заказами", alert=True)
            return

        order_id = int(match.group(2))
        target = OrderStatus.SHIPPED.value if match.group(1) == "ship" else OrderStatus.COMPLETED.value
        actor = user.get("first_name") or ""
        if user.get("username"):
            actor = f"{actor} (@{user['username']})".strip()

        async with AsyncSessionLocal() as db:
            try:
                await order_service.advance_order_status(db, order_id, target)
            except order_service.InvalidOrderTransition:
                # Кнопка устарела, статус не откатываем, просто обновляем сообщения
                await self._answer(callback_id, f"Заказ #{order_id} уже в другом статусе", alert=True)
                await self.sync_order_status(order_id)
                return
            except NotFoundError:
                await self._answer(callback_id, f"Заказ #{order_id} не найден", alert=True)
                return
        await self._answer(callback_id, f"Заказ #{order_id} обновлён")
        await self.sync_order_status(order_id, actor=actor)

    async def polling_loop(self) -> None:
        """Нажатия кнопок без домена и HTTPS. Один токен нельзя опрашивать из двух процессов."""
        if self.is_demo or settings.TELEGRAM_UPDATES_MODE != "polling":
            return
        await self._call("deleteWebhook", {"drop_pending_updates": False})
        logger.info("Telegram polling запущен")
        offset: int | None = None
        while True:
            try:
                payload: dict[str, Any] = {"timeout": 25, "allowed_updates": ["callback_query"]}
                if offset is not None:
                    payload["offset"] = offset
                ok, result = await self._call("getUpdates", payload, timeout=35.0)
                if not ok:
                    logger.error("Telegram getUpdates", extra={"detail": result})
                    await asyncio.sleep(10)
                    continue
                for update in result:
                    offset = update["update_id"] + 1
                    try:
                        await self.handle_update(update)
                    except Exception:
                        logger.exception("Ошибка обработки Telegram update")
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Ошибка цикла Telegram polling")
                await asyncio.sleep(5)

    async def send_test(self) -> dict[str, object]:
        if self.is_demo:
            return {"mode": "demo", "ok": False, "detail": "TELEGRAM_BOT_TOKEN не задан"}
        chats: dict[str, dict[str, object]] = {}
        for role, chat_id in (("owner", self.owner_chat_id), ("staff", self.staff_chat_id)):
            if not chat_id:
                if role == "owner":
                    chats[role] = {"chat_id": None, "ok": False, "detail": "TELEGRAM_OWNER_CHAT_ID не задан"}
                continue
            ok, result = await self._send(chat_id, "Тест уведомлений Ulaanbaatar Cashmere: Telegram подключён.")
            chats[role] = {"chat_id": chat_id, "ok": ok, "detail": "ok" if ok else str(result)}
        return {
            "mode": "live",
            "ok": all(c["ok"] for c in chats.values()),
            "updates_mode": settings.TELEGRAM_UPDATES_MODE,
            "detail": "; ".join(f"{r}: {c['detail']}" for r, c in chats.items()),
            "chats": chats,
        }

    async def ping(self) -> str:
        if self.is_demo:
            return "off"
        ok, result = await self._call("getMe", {}, timeout=3.0)
        return "ok" if ok else str(result)


telegram_service = TelegramService()


def get_telegram_service() -> TelegramService:
    return telegram_service
