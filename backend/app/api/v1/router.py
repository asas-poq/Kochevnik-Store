"""
Главный агрегирующий роутер API версии v1 (`app/api/v1/router.py`).
Объединяет все тематические роутеры магазина в единый префикс `/api/v1`.
"""

from fastapi import APIRouter

from app.api.v1 import (
    auth,
    categories,
    interactions,
    orders,
    parser_sync,
    products,
    webhooks,
)

api_v1_router = APIRouter()

# Подключаем все модули эндпоинтов с понятными тегами для Swagger UI (/docs)
api_v1_router.include_router(auth.router)
api_v1_router.include_router(categories.router)
api_v1_router.include_router(products.router)
api_v1_router.include_router(interactions.router)
api_v1_router.include_router(orders.router)
api_v1_router.include_router(webhooks.router)
api_v1_router.include_router(parser_sync.router)
