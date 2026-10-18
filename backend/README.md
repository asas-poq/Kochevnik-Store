# Ulaanbaatar Cashmere & Leather — Асинхронный Бэкенд на FastAPI

Полноценный, готовый к запуску асинхронный бэкенд интернет-магазина монгольского кашемира, пуха яка, верблюжьей шерсти и кожаных изделий **Ulaanbaatar** (`ubcashmere.ru`).

Построен на **Python 3.11 + FastAPI + SQLAlchemy 2.0 (Async) + Pydantic v2 + SQLAdmin**, полностью повторяет и расширяет структуру базы данных вашего парсера, включает **авторизацию (JWT)**, **лайки (Избранное)**, **комментарии и отзывы с оценками**, **чекаут с транзакционной блокировкой остатков (`SELECT ... FOR UPDATE`)**, **оплату по СБП (ЮKassa / Т-Касса)** и **Telegram-уведомления владельцу**.

## Архитектура проекта

| Директория / Файл | Назначение |
| :--- | :--- |
| `app/main.py` | Точка входа FastAPI, `lifespan`, Middleware трассировки `X-Request-ID`, подключение `/admin` и `/api/v1` |
| `app/core/config.py` | Типизированные настройки окружения через `pydantic-settings` |
| `app/core/logging.py` | Профессиональный структурный логгер (`logger`) с ротацией файлов и привязкой `request_id` |
| `app/core/security.py` | Хэширование паролей (`bcrypt`) и выпуск/проверка JWT-токенов (`access` и `refresh`) |
| `app/db/session.py` | Асинхронный движок `create_async_engine`, `async_sessionmaker` и зависимость `get_db` |
| `app/models/catalog.py` | Все таблицы парсера: `sources`, `categories`, `crawl_queue`, `products`, `price_history`, `product_images`, `product_materials`, `product_color_links`, `product_sizes`, `product_attributes` |
| `app/models/user.py` | Таблица пользователей и администраторов (`users`) |
| `app/models/interactions.py` | Таблицы лайков/избранного (`product_likes`) и древовидных отзывов/комментариев (`product_reviews`) |
| `app/models/order.py` | Таблицы заказов (`orders`) и позиций заказа (`order_items`) с доставкой СДЭК/Почта/Шоурум и СБП |
| `app/api/deps.py` | Переиспользуемые зависимости `Depends`: `DBSessionDep`, `CurrentUserDep`, `OptionalUserDep`, `AdminUserDep`, `ProductFilterDep` |
| `app/api/v1/` | Роутеры: `auth.py`, `categories.py`, `products.py`, `interactions.py`, `orders.py`, `webhooks.py`, `parser_sync.py` |
| `app/services/` | Асинхронные сервисы: `s3.py` (S3/MinIO фото), `payment_sbp.py` (ЮKassa СБП), `telegram.py` (Telegram-бот), `tasks.py` (`BackgroundTasks`) |
| `app/admin/views.py` | Готовая админ-панель `sqladmin` по адресу `/admin` для всех 14 таблиц |
| `data/parsed_dump.json` | Полный JSON-дамп вашего парсера (2 категории, 11 спарсенных товаров, 102 фото, материалы, связи цветов, 193 ссылки в очереди `crawl_queue`) |
| `scripts/seed_from_parser.py` | Скрипт первичного импорта всех данных парсера и создания тестовых аккаунтов |

## Быстрый старт

### Вариант 1: Запуск в Docker (PostgreSQL + Redis + MinIO + FastAPI)
```bash
cp .env.example .env
docker compose up --build -d
```

### Вариант 2: Локальный запуск без Docker (например, на SQLite или локальном PostgreSQL)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Для быстрого теста без поднятия PostgreSQL можно указать SQLite:
export DATABASE_URL="sqlite+aiosqlite:///./ubcashmere.db"

# Загружаем данные парсера и тестовых пользователей:
python3 -m scripts.seed_from_parser

# Запускаем сервер разработки:
uvicorn app.main:app --reload --port 8000
```

После запуска откройте:
- **Интерактивная документация Swagger UI**: `http://localhost:8000/docs`
- **Админ-панель управления товарами и заказами (SQLAdmin)**: `http://localhost:8000/admin`

## Тестовые учетные записи (создаются скриптом `seed_from_parser.py`)
- **Администратор магазина**: `admin@ubcashmere.ru` / пароль: `Admin123!`
- **Покупатель**: `anna@example.com` / пароль: `Customer123!`


## Лайки и отзывы (`/api/v1/interactions`)

| Метод | Путь | Доступ | Описание |
| --- | --- | --- | --- |
| POST | `/products/{id}/like` | авторизован | Поставить/убрать лайк |
| GET | `/my-likes?limit&offset` | авторизован | Моё избранное |
| GET | `/products/{id}/reviews?limit&offset&sort&rating&only_verified` | все | Отзывы товара |
| GET | `/products/{id}/reviews/summary` | все | Средняя оценка и распределение по звёздам |
| POST | `/products/{id}/reviews` | авторизован, **купил и получил товар** | Отзыв (403 без доставленного заказа, 409 при дубле) или ответ (`parent_id`) |
| GET | `/my-reviews?limit&offset` | авторизован | Мои отзывы с данными товара |
| PATCH | `/reviews/{id}` | автор | Редактировать свой отзыв |
| DELETE | `/reviews/{id}` | автор / админ | Удалить отзыв (вместе с ответами) |
| PATCH | `/reviews/{id}/admin-reply` | админ | Официальный ответ бутика |
| GET | `/admin/reviews/pending` | админ | Отзывы на модерации |
| POST | `/admin/reviews/{id}/approve` | админ | Одобрить |
| POST | `/admin/reviews/{id}/reject` | админ | Отклонить (удалить) |
| GET | `/admin/users/{user_id}/reviews` | админ | Все отзывы пользователя |

Премодерация включается флагом `REVIEWS_PREMODERATION = True` в `app/api/v1/interactions.py`.

### Миграция существующей БД (один раз)

`create_all` не меняет существующие таблицы, поэтому после обновления кода выполните:

```bash
python -m scripts.migrate_reviews_v2
```


## Заказы и оплата (`/api/v1/orders`, `/api/v1/payments`)

| Метод | Путь | Доступ | Описание |
| --- | --- | --- | --- |
| POST | `/orders` | **авторизован** | Создать заказ, резерв остатков, ссылка СБП. В ответе `payment_expires_at` |
| GET | `/orders/my?limit&offset&status` | авторизован | История заказов |
| GET | `/orders/{id}` | владелец / админ | Проверка заказа по ID (чужой — 404) |
| POST | `/orders/{id}/cancel` | владелец / админ | Отменить неоплаченный заказ |
| POST | `/orders/{id}/check-payment` | владелец / админ | Сверить оплату со шлюзом |
| GET | `/orders/admin/list?status&q&user_id` | админ | Все заказы |
| GET | `/orders/admin/users/{user_id}` | админ | Все заказы пользователя по его ID |
| PATCH | `/orders/admin/{id}/status` | админ | `paid → shipped → completed` |
| POST | `/payments/webhook` | шлюз | Вебхук оплаты (защищён, идемпотентен) |
| POST | `/payments/telegram/test` | админ | Тестовое сообщение в личку и группу + причина ошибки по каждому чату |
| POST | `/payments/telegram/webhook` | Telegram | Нажатия кнопок (только режим `TELEGRAM_UPDATES_MODE=webhook`) |
| GET | `/payments/sandbox/checkout/{id}` | **только песочница** | Тестовая страница «банка» |
| POST | `/payments/sandbox/orders/{id}/simulate?outcome=succeeded\|canceled` | **только песочница** | Имитация оплаты / отмены |

Статусы: `pending → paid → shipped → completed`, а также `pending → cancelled`.
Неоплаченный заказ автоматически отменяется через `ORDER_PAYMENT_TTL_MINUTES` (по умолчанию 30 мин.),
остатки возвращаются на склад.

### Как протестировать оплату (песочница)

Тестовая оплата работает, пока `YOOKASSA_SHOP_ID` начинается с `test_` и `ENVIRONMENT` не `production`.

1. Зарегистрируйтесь и войдите, затем `POST /api/v1/orders` — в ответе `payment_url`.
2. Откройте `payment_url` в браузере → страница «Тестовая оплата СБП» → **«Оплатить по СБП»**.
   (или через Swagger: `POST /api/v1/payments/sandbox/orders/{id}/simulate?outcome=succeeded`)
3. `GET /api/v1/orders/{id}` (под тем же пользователем) — статус стал `paid`; в логе/Telegram — уведомление с пометкой «ТЕСТОВАЯ ОПЛАТА».
4. Админ: `PATCH /api/v1/orders/admin/{id}/status` — сначала `{"status": "shipped"}`, затем `{"status": "completed"}` (доставлен). **Только после `completed`** покупатель может оставить отзыв на этот товар.
5. Проверка отмены: `outcome=canceled` (или `POST /orders/{id}/cancel`) — статус `cancelled`, остатки вернулись.

Ручная имитация вебхука (песочница): `POST /api/v1/payments/webhook` с заголовком
`X-Webhook-Secret: <PAYMENT_WEBHOOK_SECRET>` и телом
`{"event": "payment.succeeded", "order_id": 1, "payment_id": "<payment_id из заказа>", "amount": 1200}`.

В боевом режиме вебхук не принимается «на слово»: статус и сумма перепроверяются запросом к API ЮKassa.

## Telegram: уведомления и кнопки управления заказом

После оплаты бот отправляет карточку заказа (состав, сумма, доставка, клиент и **ID клиента**):

| Куда | Что приходит |
| --- | --- |
| Личка владельца (`TELEGRAM_OWNER_CHAT_ID`) | Карточка + кнопка **«🚚 Подтвердить и передать в доставку»** |
| Группа (`TELEGRAM_STAFF_CHAT_ID`) | Та же карточка со статусом **«🆕 НОВЫЙ ОПЛАЧЕННЫЙ ЗАКАЗ — 🔴 ожидает отправки»**, без кнопок |

Что происходит дальше:

1. Нажатие кнопки → заказ `shipped`. В личке сообщение обновляется и получает кнопку **«✅ Заказ вручён клиенту»**.
   В группе сообщение «не отправлено» **удаляется** и заменяется на **«📦 ЗАКАЗ ОТПРАВЛЕН — 🟡 передан в доставку»** (с пометкой, кто отметил).
2. Вторая кнопка → заказ `completed`, в группе **«✅ ЗАКАЗ ВРУЧЁН — 🟢 завершён»**. Только после этого покупатель может оставить отзыв.
3. Если статус сменили через админ-API (`PATCH /orders/admin/{id}/status`), сообщения в Telegram обновляются так же.

Кто может нажимать: только Telegram-пользователь из `TELEGRAM_OWNER_CHAT_ID` (и `TELEGRAM_ADMIN_USER_IDS`).
Кнопок в группе нет, а нажатие чужого пользователя отклоняется. Повторное нажатие безопасно: статус не откатывается.

Настройка:

1. Личка: напишите боту `/start`, ID возьмите из `https://api.telegram.org/bot<TOKEN>/getUpdates` (`chat.id`, положительный).
2. Группа: создайте группу, добавьте бота, напишите `/start@имя_бота`, ID возьмите из `getUpdates` (`chat.id`, отрицательный, обычно `-100...`).
3. В `.env`: `TELEGRAM_OWNER_CHAT_ID`, `TELEGRAM_STAFF_CHAT_ID`, перезапустите сервер, проверьте `POST /payments/telegram/test`.

Приём нажатий кнопок:

- `TELEGRAM_UPDATES_MODE=polling` (по умолчанию) — бот сам опрашивает Telegram, работает локально без домена.
  **Один токен нельзя опрашивать из двух мест** (в том числе не открывайте `getUpdates` в браузере, пока сервер запущен).
- `TELEGRAM_UPDATES_MODE=webhook` — для продакшена. Задайте `TELEGRAM_WEBHOOK_SECRET` и один раз зарегистрируйте вебхук:
  ```bash
  curl "https://api.telegram.org/bot<TOKEN>/setWebhook" \
    -d "url=https://ВАШ_ДОМЕН/api/v1/payments/telegram/webhook" \
    -d "secret_token=<TELEGRAM_WEBHOOK_SECRET>" \
    -d 'allowed_updates=["callback_query"]'
  ```

Сообщения запоминаются в новой таблице `order_telegram_messages` (создаётся автоматически, миграция не нужна).