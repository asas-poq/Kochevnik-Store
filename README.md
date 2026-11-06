# Kochevnik Store

Интернет-магазин монгольского кашемира и кожи. В репозитории два приложения: API на FastAPI и витрина с админкой на Next.js. Всё поднимается одной командой через Docker Compose.

## Что умеет магазин

Каталог с фильтрами по категории, материалу, цвету, размеру и цене, поиск и сортировка по популярности или скидке. Карточка товара с фото, составом, остатками по размерам и отзывами. Лайки, корзина, оформление заказа и оплата через СБП. Платежи идут через ЮKassa, пока в тестовом режиме. В личном кабинете заказы, избранное и свои отзывы.

Для владельца есть админка. В ней редактор товаров, заказы, пользователи, модерация отзывов, запуск парсера и состояние сервисов. Новые заказы приходят в Telegram, а статус можно менять кнопками прямо в чате.

Заказ сразу резервирует остаток на складе. Если за 30 минут его не оплатили, воркер отменяет заказ и возвращает товар.

## Как всё устроено

```
браузер → nginx :80
            ├─ /api, /media, /docs, /sqladmin → api (FastAPI) → PostgreSQL, Redis
            └─ всё остальное                  → frontend (Next.js)

worker (ARQ) берёт задачи из Redis: парсер, отмена неоплаченных заказов, Telegram
prometheus собирает метрики api, grafana их рисует
```

Браузер видит один адрес, поэтому CORS при локальном запуске не мешает.

Бэкенд: Python 3.11, FastAPI, SQLAlchemy 2.0 async, Alembic, PostgreSQL 16, Redis 7, ARQ, SQLAdmin.
Фронтенд: Next.js 16, React 19, TypeScript, Tailwind 4, shadcn/ui, zustand, TanStack Query.
Мониторинг: Prometheus и Grafana.

## Запуск

Нужен Docker с Compose версии 2.23 или новее.

```
git clone https://github.com/asas-poq/Kochevnik-Store.git
cd Kochevnik-Store

cp backend/.env.example backend/.env

docker compose up -d --build
docker compose run --rm worker python -m scripts.seed_from_parser
```

Первая сборка идёт несколько минут, потом всё быстрее. Миграции базы применяются сами, перед запуском API.

Последняя команда создаёт двух демо-пользователей:

| Роль | Почта | Пароль |
|---|---|---|
| Администратор | admin@ubcashmere.ru | Admin123! |
| Покупатель | anna@example.com | Customer123! |

все данные о товарах импортируются с`backend/data/parsed_dump.json` 
## Куда заходить

| Что | Адрес |
|---|---|
| Магазин | http://localhost |
| Админка магазина | http://localhost/admin |
| Документация API | http://localhost/docs |
| Панель базы (SQLAdmin) | http://localhost/sqladmin |
| Grafana | http://localhost:3001 (логин admin, пароль из `GRAFANA_PASSWORD`) |
| Prometheus | http://localhost:9090 |

Оплата работает в песочнице. После оформления заказа откроется тестовая страница оплаты. Без токена Telegram-бота уведомления просто пишутся в лог воркера.

Остановить всё можно командой `docker compose down`. Чтобы заодно стереть базу и загруженные файлы, добавь `-v`.

## Если что-то не заводится

Порт 80 занят. В `docker-compose.yml` замени `"80:80"` на `"8080:80"`, в `.env` поставь `SITE_URL=http://localhost:8080` и пересобери фронт командой `docker compose up -d --build frontend`.

Поменял адрес в `.env`, а на сайте всё по-старому. Переменные `NEXT_PUBLIC_*` вшиваются во фронт при сборке, поэтому после правки нужна пересборка фронта.

Поменял пароль базы после первого запуска, и API не может подключиться. Postgres запоминает пароль в томе. Выполни `docker compose down -v` и запусти заново, данные при этом пропадут.

В `/health` написано, что S3 недоступен. В Docker-режиме отдельного хранилища нет, и загруженные в админке фото сохраняются в локальную папку `media`. На работу магазина это не влияет.

## Перед выкладкой в интернет

В режиме `development` открыта ручка, которой можно «оплатить» любой заказ. Поэтому в таком виде демку выкладывать нельзя. Что нужно сделать:

- поставить `ENVIRONMENT=production` в `backend/.env`. С этого момента ручки песочницы исчезают, а слабые секреты не дают серверу запуститься
- задать свои `SECRET_KEY` и `PAYMENT_WEBHOOK_SECRET`, например командой `openssl rand -hex 32`
- подставить боевые ключи ЮKassa
- сменить `POSTGRES_PASSWORD` и `GRAFANA_PASSWORD`
- поставить перед nginx HTTPS и при желании закрыть `/docs`

## Что где лежит

```
backend/     API, миграции, тесты, воркер, парсер
frontend/    Next.js приложение
docker-compose.yml
Makefile     короткие команды: make up, make seed, make test
```

Подробности в [backend/README.md](backend/README.md) и [frontend/README.md](frontend/README.md).

## О парсере

Парсер читает публичный каталог ubcashmere.ru, чтобы наполнить магазин демо-данными.

## Документация API и nginx

Через nginx наружу открыты `/docs` (Swagger) и `/openapi.json` (описание всех ручек API). Для локального запуска и демо это удобно, документацию может открыть кто угодно без входа. Сами защищённые ручки при этом по-прежнему требуют токен.

Для настоящего магазина документацию лучше закрыть. Это делается в `docker-compose.yml`, в блоке `configs`, в конфиге nginx. Там есть две строки:

```
location /docs         { proxy_pass http://api; }
location /openapi.json { proxy_pass http://api; }
```

Чтобы закрыть документацию совсем, замени их на:

```
location /docs         { return 404; }
location /openapi.json { return 404; }
```

Если она нужна только тебе, открой её с одного адреса:

```
location /docs {
  allow 203.0.113.10;   # твой IP
  deny all;
  proxy_pass http://api;
}
location /openapi.json {
  allow 203.0.113.10;
  deny all;
  proxy_pass http://api;
}
```

После правки перезапусти nginx командой `docker compose up -d --force-recreate nginx`. Swagger и `openapi.json` работают вместе, поэтому закрывать нужно обе строки сразу. Если закрыть только `openapi.json`, страница `/docs` откроется пустой. Фронтенд на эти адреса не ходит, у него своя копия `openapi.json` в папке `frontend`, так что сайт от этого не пострадает.

Таким же способом можно закрыть и `/sqladmin`. Вход туда и так только по паролю админа, но в боевом режиме лишний открытый вход не нужен.