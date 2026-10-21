from fastapi import APIRouter

from app.api.v1 import auth, categories, interactions, orders, parser_sync, products, webhooks

api_v1_router = APIRouter()
for module in (auth, categories, products, interactions, orders, webhooks, parser_sync):
    api_v1_router.include_router(module.router)
