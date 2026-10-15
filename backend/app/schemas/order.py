"""
Pydantic v2 схемы для оформления заказа (Чекаут), позиций корзины и оплаты по СБП (`app/schemas/order.py`).
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class OrderItemCreateIn(BaseModel):
    """Позиция корзины, передаваемая с фронтенда при оформлении заказа."""
    product_id: int = Field(..., description="ID товара из таблицы products")
    variant_id: Optional[int] = Field(
        None,
        description="ID конкретного размера из таблицы product_sizes (если не указан, берется по полю size)",
    )
    size: str = Field("ONE SIZE", description="Выбранный размер (S, M, L, ONE SIZE)")
    quantity: int = Field(1, ge=1, le=20, description="Количество единиц товара")


class OrderCreateIn(BaseModel):
    """
    Запрос на создание заказа (`POST /api/v1/orders`).
    Включает контактные данные покупателя, выбранный способ доставки и список товаров.
    """
    customer_name: str = Field(..., min_length=2, max_length=150, description="ФИО получателя")
    customer_phone: str = Field(..., min_length=10, max_length=32, description="Телефон для СДЭК и связи")
    customer_email: Optional[EmailStr] = Field(None, description="Email для отправки электронного чека")
    delivery_method: Literal[
        "cdek_pvz", "cdek_courier", "russian_post", "showroom_pickup"
    ] = Field(
        "cdek_pvz",
        description="Способ доставки: СДЭК ПВЗ, СДЭК Курьер, Почта России или Самовывоз из шоурума (Москва/СПб)",
    )
    delivery_city: str = Field("Москва", description="Город доставки")
    delivery_address: str = Field(
        ..., min_length=4, max_length=500, description="Адрес ПВЗ СДЭК, домашний адрес или адрес шоурума"
    )
    cdek_pvz_code: Optional[str] = Field(None, description="Код пункта выдачи СДЭК (например, MSK142)")
    customer_comment: Optional[str] = Field(None, max_length=1000, description="Комментарий к заказу")
    items: List[OrderItemCreateIn] = Field(
        ..., min_length=1, description="Список выбранных товаров из корзины"
    )


class OrderItemOut(BaseModel):
    """Товарная позиция в созданном заказе."""
    id: int
    product_id: int
    variant_id: Optional[int] = None
    product_name: str
    product_slug: str
    color: Optional[str] = None
    size: str
    quantity: int
    unit_price: int
    subtotal: int

    model_config = ConfigDict(from_attributes=True)


class OrderOut(BaseModel):
    """Полная информация о заказе и платежной ссылке СБП."""
    id: int
    user_id: Optional[int] = None
    customer_name: str
    customer_phone: str
    customer_email: Optional[str] = None
    delivery_method: str
    delivery_city: str
    delivery_address: str
    cdek_pvz_code: Optional[str] = None
    customer_comment: Optional[str] = None
    items_total: int
    delivery_cost: int
    total_amount: int
    currency: str
    status: str
    payment_id: Optional[str] = None
    payment_url: Optional[str] = Field(
        None, description="Платежная ссылка СБП (QR-код) для мгновенной оплаты заказа"
    )
    created_at: datetime
    paid_at: Optional[datetime] = None
    items: List[OrderItemOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class SBPWebhookPayload(BaseModel):
    """
    Универсальная схема входящего вебхука от платежного шлюза (ЮKassa / Т-Касса)
    на эндпоинт `POST /api/v1/payments/webhook`.
    """
    event: str = Field(
        ..., description="Тип события, например 'payment.succeeded' или 'payment.canceled'"
    )
    payment_id: str = Field(..., description="Уникальный ID транзакции в платежной системе")
    order_id: int = Field(..., description="Внутренний номер заказа в нашем магазине")
    amount: Optional[int] = Field(None, description="Сумма платежа в рублях")
    secret_signature: Optional[str] = Field(
        None, description="Подпись или секретный ключ для проверки подлинности вебхука"
    )
    raw_object: Optional[Dict[str, Any]] = Field(default_factory=dict)
