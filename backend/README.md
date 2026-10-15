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
