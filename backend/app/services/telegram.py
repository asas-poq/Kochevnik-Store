"""
Сервис Telegram-уведомлений и управления заказами (`app/services/telegram.py`).

Как это работает
----------------
1. Заказ оплачен → бот шлёт сообщение:
   - в ЛИЧНЫЙ чат владельца (`TELEGRAM_OWNER_CHAT_ID`) — с кнопкой
     «🚚 Подтвердить и передать в доставку»;
   - в ГРУППУ сотрудников (`TELEGRAM_STAFF_CHAT_ID`) — без кнопок, с понятным статусом
     «🆕 НОВЫЙ ОПЛАЧЕННЫЙ ЗАКАЗ — ожидает отправки».
2. Владелец нажимает кнопку → заказ получает статус `shipped` (у клиента в заказе «передан в
   доставку»), сообщение в личке обновляется (кнопка меняется на «✅ Заказ вручён клиенту»),
   а сообщение в группе УДАЛЯЕТСЯ и заменяется новым «📦 ОТПРАВЛЕН».
3. Вторая кнопка → `completed` («вручён»). После этого покупатель может оставить отзыв.

Безопасность кнопок
-------------------
Кнопки есть только в личном сообщении владельца. Нажатие принимается, только если его сделал
Telegram-пользователь из `TELEGRAM_OWNER_CHAT_ID` / `TELEGRAM_ADMIN_USER_IDS`: никакой отдельной
авторизации не нужно, Telegram сам гарантирует, кто нажал. Повторное нажатие безвредно:
статус не откатывается (машина состояний), а устаревшая кнопка исчезает.

Получение нажатий (`TELEGRAM_UPDATES_MODE`)
-------------------------------------------
- `polling` — бот сам опрашивает Telegram (работает локально, без домена и HTTPS);
- `webhook` — Telegram шлёт на `/api/v1/payments/telegram/webhook` (нужен публичный HTTPS);
- `off` — кнопки не обрабатываются.
"""

import asyncio
import re
from html import escape as esc
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.models.order import Order, OrderStatus
from app.models.telegram_message import OrderTelegramMessage

logger = get_logger(__name__)

CALLBACK_RE = re.compile(r"ord:(ship|done):(\d+)")

# Заголовки сообщений по стадиям заказа: единый, легко узнаваемый вид для группы
STAGES = {
    OrderStatus.PAID.value: ("🆕", "НОВЫЙ ОПЛАЧЕННЫЙ ЗАКАЗ", "🔴", "ожидает отправки"),
    OrderStatus.SHIPPED.value: ("📦", "ЗАКАЗ ОТПРАВЛЕН", "🟡", "передан в доставку"),
    OrderStatus.COMPLETED.value: ("✅", "ЗАКАЗ ВРУЧЁН КЛИЕНТУ", "🟢", "завершён"),
}


class TelegramNotificationService:
    """Клиент Telegram Bot API: уведомления, кнопки управления заказом, синхронизация групп."""

    DELIVERY_LABELS = {
        "cdek_pvz": "СДЭК (Пункт выдачи)",
        "cdek_courier": "СДЭК (Курьер до двери)",
        "russian_post": "Почта России",
        "showroom_pickup": "Самовывоз из шоурума",
    }

    # ==========================================================================
    # Формат сообщения и клавиатура
    # ==========================================================================
    def format_order_message(
        self, order: Order, stage: Optional[str] = None, actor: Optional[str] = None
    ) -> str:
        """
        Текст карточки заказа. `stage` — статус заказа (paid / shipped / completed),
        `actor` — кто отметил статус (показывается после нажатия кнопки).
        """
        stage = stage or order.status
        emoji, title, dot, label = STAGES.get(stage, STAGES[OrderStatus.PAID.value])

        items_lines = []
        for item in order.items:
            color_str = f"{esc(item.color)}, " if item.color else ""
            price_formatted = f"{item.subtotal:,}".replace(",", " ")
            items_lines.append(
                f"• {esc(item.product_name)} ({color_str}размер {esc(item.size)}) "
                f"x{item.quantity} — {price_formatted} ₽"
            )
        items_block = "\n".join(items_lines)
        total_formatted = f"{order.total_amount:,}".replace(",", " ")
        delivery_label = esc(
            self.DELIVERY_LABELS.get(order.delivery_method, order.delivery_method)
        )
        test_prefix = "🧪 <b>[ТЕСТОВАЯ ОПЛАТА]</b>\n" if settings.payments_sandbox_mode else ""

        lines = [
            f"{test_prefix}{emoji} <b>{title} #{order.id}</b>",
            f"{dot} Статус: <b>{label}</b>",
            "",
            "<b>Состав заказа:</b>",
            items_block,
            "",
            f"💰 <b>Оплачено (СБП):</b> {total_formatted} ₽",
            f"🚚 <b>Доставка:</b> {delivery_label}, {esc(order.delivery_city)}, {esc(order.delivery_address)}",
            f"👤 <b>Клиент:</b> {esc(order.customer_name)} ({esc(order.customer_phone)})",
            f"🆔 <b>ID клиента:</b> {order.user_id if order.user_id else '—'}",
        ]
        if order.customer_comment:
            lines.append(f"💬 <b>Комментарий:</b> {esc(order.customer_comment)}")
        if actor:
            lines.append(f"\n🧾 Отметил: <b>{esc(actor)}</b>")
        return "\n".join(lines)

    # Обратная совместимость со старым именем
    def format_paid_order_message(self, order: Order) -> str:
        return self.format_order_message(order, OrderStatus.PAID.value)

    @staticmethod
    def build_keyboard(order: Order) -> Dict[str, List]:
        """Кнопки под сообщением владельца: следующая доступная стадия заказа."""
        if order.status == OrderStatus.PAID.value:
            rows = [[{"text": "🚚 Подтвердить и передать в доставку",
                      "callback_data": f"ord:ship:{order.id}"}]]
        elif order.status == OrderStatus.SHIPPED.value:
            rows = [[{"text": "✅ Заказ вручён клиенту",
                      "callback_data": f"ord:done:{order.id}"}]]
        else:
            rows = []
        return {"inline_keyboard": rows}

    # ==========================================================================
    # Низкоуровневые вызовы Bot API
    # ==========================================================================
    @property
    def is_demo(self) -> bool:
        """Демо-режим: токен не задан или остался заглушкой — сообщения только пишутся в лог."""
        token = settings.TELEGRAM_BOT_TOKEN
        return not token or "test_bot_token" in token

    @property
    def owner_chat_id(self) -> Optional[str]:
        return settings.TELEGRAM_OWNER_CHAT_ID.strip() or None

    @property
    def staff_chat_id(self) -> Optional[str]:
        staff = settings.TELEGRAM_STAFF_CHAT_ID.strip()
        # Если группа совпадает с личкой — не дублируем сообщения
        return staff if staff and staff != self.owner_chat_id else None

    async def _call(
        self, method: str, payload: Dict[str, Any], timeout: float = 8.0
    ) -> Tuple[bool, Any]:
        """
        Вызывает метод Bot API. Возвращает `(успех, result | текст ошибки)`.
        Токен и URL в логи и ответы НЕ попадают (в URL лежит токен бота).
        """
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}"
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=payload)
        except httpx.HTTPError as exc:
            return False, f"Сетевая ошибка при обращении к Telegram: {type(exc).__name__}"

        try:
            data = resp.json()
        except Exception:
            return False, f"Telegram вернул {resp.status_code}: {resp.text[:200]}"

        if resp.status_code == 200 and data.get("ok"):
            return True, data.get("result")

        description = data.get("description", resp.text[:200])
        migrate_to = (data.get("parameters") or {}).get("migrate_to_chat_id")
        if migrate_to:
            description += f" (новый chat_id группы: {migrate_to})"
        return False, f"Telegram вернул {resp.status_code}: {description}"

    async def _send_message(
        self, chat_id: str, text: str, reply_markup: Optional[Dict] = None
    ) -> Tuple[bool, Any]:
        payload: Dict[str, Any] = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        ok, result = await self._call("sendMessage", payload)
        return ok, (result["message_id"] if ok else result)

    async def _edit_message(
        self, chat_id: int, message_id: int, text: str, reply_markup: Dict
    ) -> Tuple[bool, str]:
        ok, result = await self._call(
            "editMessageText",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": reply_markup,
            },
        )
        if not ok and "message is not modified" in str(result):
            return True, "not modified"
        return ok, "ok" if ok else str(result)

    async def _delete_message(self, chat_id: int, message_id: int) -> bool:
        ok, _ = await self._call("deleteMessage", {"chat_id": chat_id, "message_id": message_id})
        return ok

    async def _answer_callback(self, callback_id: str, text: str, alert: bool = False) -> None:
        await self._call(
            "answerCallbackQuery",
            {"callback_query_id": callback_id, "text": text[:190], "show_alert": alert},
        )

    # ==========================================================================
    # Уведомления
    # ==========================================================================
    async def _send(self, text: str, order_id: Optional[int] = None) -> bool:
        """Простое служебное сообщение владельцу (в демо-режиме — только лог)."""
        if self.is_demo or not self.owner_chat_id:
            logger.info(f"[TELEGRAM УВЕДОМЛЕНИЕ ВЛАДЕЛЬЦУ (Демо-режим)]:\n{text}")
            return True
        ok, detail = await self._send_message(self.owner_chat_id, text)
        if not ok:
            logger.error(f"Не удалось отправить уведомление в Telegram (заказ #{order_id}): {detail}")
        return ok

    async def send_alert(self, text: str, order_id: Optional[int] = None) -> bool:
        """Служебное предупреждение владельцу (например, оплата пришла по отменённому заказу)."""
        return await self._send(text, order_id)

    async def send_order_paid_alert(self, order: Order) -> bool:
        """
        Уведомление о новом оплаченном заказе (вызывается через `BackgroundTasks`):
        владельцу — с кнопкой, в группу — со статусом. `message_id` сохраняются, чтобы потом
        редактировать/заменять сообщения при смене статуса.
        """
        try:
            text = self.format_order_message(order, OrderStatus.PAID.value)
        except Exception as exc:
            logger.error(f"Ошибка форматирования уведомления по заказу #{order.id}: {exc}")
            text = f"🆕 <b>НОВЫЙ ОПЛАЧЕННЫЙ ЗАКАЗ #{order.id}</b>\nСумма: {order.total_amount} ₽"

        if self.is_demo:
            logger.info(f"[TELEGRAM УВЕДОМЛЕНИЕ ВЛАДЕЛЬЦУ (Демо-режим)]:\n{text}")
            return True

        saved: List[OrderTelegramMessage] = []
        all_ok = True
        targets = [("owner", self.owner_chat_id, self.build_keyboard(order)),
                   ("staff", self.staff_chat_id, None)]
        for role, chat_id, markup in targets:
            if not chat_id:
                continue
            ok, result = await self._send_message(chat_id, text, markup)
            if ok:
                saved.append(OrderTelegramMessage(
                    order_id=order.id, role=role, chat_id=int(chat_id), message_id=int(result)
                ))
            else:
                all_ok = False
                logger.error(f"Telegram ({role}) заказ #{order.id}: {result}")

        if saved:
            async with AsyncSessionLocal() as db:
                db.add_all(saved)
                await db.commit()
            logger.info(f"Уведомления по заказу #{order.id} отправлены ({len(saved)} чат.).")
        return all_ok

    async def sync_order_status(self, order_id: int, actor: Optional[str] = None) -> None:
        """
        Приводит сообщения в Telegram в соответствие с текущим статусом заказа:
        - личка владельца: сообщение РЕДАКТИРУЕТСЯ (новая метка + следующая кнопка);
        - группа: старое сообщение УДАЛЯЕТСЯ, вместо него отправляется новое с актуальным статусом.
        Вызывается и после нажатия кнопки, и после смены статуса через админ-API.
        """
        async with AsyncSessionLocal() as db:
            order = (
                await db.execute(
                    select(Order).where(Order.id == order_id).options(selectinload(Order.items))
                )
            ).scalar_one_or_none()
            if not order or order.status not in STAGES:
                return

            text = self.format_order_message(order, order.status, actor)
            if self.is_demo:
                logger.info(f"[TELEGRAM (Демо-режим)] Статус заказа #{order_id}:\n{text}")
                return

            rows = {
                r.role: r
                for r in (
                    await db.execute(
                        select(OrderTelegramMessage).where(OrderTelegramMessage.order_id == order_id)
                    )
                ).scalars()
            }

            # --- Личка владельца: редактируем сообщение ---
            if self.owner_chat_id:
                markup = self.build_keyboard(order)
                row = rows.get("owner")
                edited = False
                if row:
                    edited, detail = await self._edit_message(
                        row.chat_id, row.message_id, text, markup
                    )
                    if not edited:
                        logger.warning(f"Не удалось отредактировать сообщение владельца: {detail}")
                if not edited:
                    ok, result = await self._send_message(self.owner_chat_id, text, markup)
                    if ok:
                        if row:
                            row.message_id = int(result)
                        else:
                            db.add(OrderTelegramMessage(
                                order_id=order_id, role="owner",
                                chat_id=int(self.owner_chat_id), message_id=int(result),
                            ))

            # --- Группа: удаляем старое сообщение и присылаем новое ---
            if self.staff_chat_id:
                row = rows.get("staff")
                ok, result = await self._send_message(self.staff_chat_id, text)
                if ok:
                    if row:
                        deleted = await self._delete_message(row.chat_id, row.message_id)
                        if not deleted:
                            # Нельзя удалить (например, сообщению больше 48 ч) — хотя бы
                            # перепишем старое, чтобы не висел устаревший статус
                            await self._edit_message(
                                row.chat_id, row.message_id,
                                f"↪️ Заказ #{order_id}: статус изменён, см. новое сообщение ниже.",
                                {"inline_keyboard": []},
                            )
                        row.message_id = int(result)
                    else:
                        db.add(OrderTelegramMessage(
                            order_id=order_id, role="staff",
                            chat_id=int(self.staff_chat_id), message_id=int(result),
                        ))
                else:
                    logger.error(f"Telegram (staff) заказ #{order_id}: {result}")

            await db.commit()

    # ==========================================================================
    # Нажатия кнопок
    # ==========================================================================
    async def handle_update(self, update: Dict[str, Any]) -> None:
        """Обрабатывает входящий update от Telegram (интересуют только нажатия кнопок)."""
        callback = update.get("callback_query")
        if callback:
            await self._handle_callback(callback)

    async def _handle_callback(self, callback: Dict[str, Any]) -> None:
        from app.services.orders import advance_order_status  # во избежание циклического импорта

        callback_id = callback["id"]
        from_user = callback.get("from") or {}
        match = CALLBACK_RE.fullmatch(callback.get("data") or "")
        if not match:
            await self._answer_callback(callback_id, "Неизвестная команда")
            return

        # Нажать может только владелец / доверенные пользователи
        if str(from_user.get("id")) not in settings.telegram_approver_ids:
            logger.warning(f"Telegram: отклонено нажатие от пользователя ID={from_user.get('id')}")
            await self._answer_callback(callback_id, "⛔ У вас нет прав управлять заказами", alert=True)
            return

        action, order_id = match.group(1), int(match.group(2))
        target = OrderStatus.SHIPPED.value if action == "ship" else OrderStatus.COMPLETED.value
        actor = from_user.get("first_name") or ""
        if from_user.get("username"):
            actor = f"{actor} (@{from_user['username']})".strip()

        async with AsyncSessionLocal() as db:
            order, code = await advance_order_status(db, order_id, target)

        if code == "ok":
            done = "передан в доставку" if target == OrderStatus.SHIPPED.value else "вручён клиенту"
            await self._answer_callback(callback_id, f"✅ Заказ #{order_id} {done}")
            await self.sync_order_status(order_id, actor=actor)
        elif code == "not_found":
            await self._answer_callback(callback_id, f"Заказ #{order_id} не найден", alert=True)
        else:
            # Уже отмечено ранее: статус не откатываем, просто убираем устаревшую кнопку
            await self._answer_callback(
                callback_id, f"Заказ #{order_id} уже в статусе «{order.status}»", alert=True
            )
            await self.sync_order_status(order_id)

    async def polling_loop(self) -> None:
        """
        Фоновый цикл long polling: получает нажатия кнопок без домена и HTTPS (для локальной
        разработки). Один токен бота нельзя опрашивать из двух мест одновременно.
        """
        if self.is_demo or settings.TELEGRAM_UPDATES_MODE != "polling":
            return
        await self._call("deleteWebhook", {"drop_pending_updates": False})
        logger.info("Telegram: запущен приём нажатий кнопок (polling).")
        offset: Optional[int] = None
        while True:
            try:
                payload: Dict[str, Any] = {"timeout": 25, "allowed_updates": ["callback_query"]}
                if offset is not None:
                    payload["offset"] = offset
                ok, result = await self._call("getUpdates", payload, timeout=35.0)
                if not ok:
                    hint = (
                        " (этот токен уже опрашивает другой процесс/сервер — оставьте один)"
                        if "Conflict" in str(result) else ""
                    )
                    logger.error(f"Telegram getUpdates: {result}{hint}")
                    await asyncio.sleep(10)
                    continue
                for update in result:
                    offset = update["update_id"] + 1
                    try:
                        await self.handle_update(update)
                    except Exception as exc:
                        logger.error(f"Ошибка обработки Telegram update: {exc}")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(f"Ошибка цикла Telegram polling: {exc}")
                await asyncio.sleep(5)

    # ==========================================================================
    # Диагностика
    # ==========================================================================
    async def send_test(self) -> Dict[str, object]:
        """Диагностика: тестовое сообщение в личку и в группу, с причиной ошибки по каждому чату."""
        if self.is_demo:
            return {
                "mode": "demo",
                "ok": False,
                "detail": "TELEGRAM_BOT_TOKEN не задан (или остался заглушкой). "
                "Проверьте .env и что сервер запущен из папки backend и перезапущен.",
            }
        chats: Dict[str, Dict[str, object]] = {}
        for role, chat_id in (("owner", self.owner_chat_id), ("staff", self.staff_chat_id)):
            if not chat_id:
                if role == "owner":
                    chats[role] = {"chat_id": None, "ok": False, "detail": "TELEGRAM_OWNER_CHAT_ID не задан"}
                continue
            ok, result = await self._send_message(
                chat_id, "✅ Тест уведомлений Ulaanbaatar Cashmere: Telegram подключён."
            )
            chats[role] = {"chat_id": chat_id, "ok": ok, "detail": "ok" if ok else str(result)}
        all_ok = all(c["ok"] for c in chats.values())
        return {
            "mode": "live",
            "ok": all_ok,
            "updates_mode": settings.TELEGRAM_UPDATES_MODE,
            "detail": "; ".join(f"{r}: {c['detail']}" for r, c in chats.items()),
            "chats": chats,
        }


telegram_service = TelegramNotificationService()


def get_telegram_service() -> TelegramNotificationService:
    """Зависимость FastAPI (`Depends(get_telegram_service)`)."""
    return telegram_service