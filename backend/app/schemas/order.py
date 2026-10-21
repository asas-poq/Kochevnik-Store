from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class OrderItemCreateIn(BaseModel):
    product_id: int
    variant_id: int | None = Field(None, description="Id размера. Если не указан, ищем по полю size")
    size: str = "ONE SIZE"
    quantity: int = Field(1, ge=1, le=20)


class OrderCreateIn(BaseModel):
    customer_name: str = Field(min_length=2, max_length=150)
    customer_phone: str = Field(min_length=10, max_length=32)
    customer_email: EmailStr | None = None
    delivery_method: Literal["cdek_pvz", "cdek_courier", "russian_post", "showroom_pickup"] = "cdek_pvz"
    delivery_city: str = "Москва"
    delivery_address: str = Field(min_length=4, max_length=500, description="Адрес, ПВЗ или шоурум")
    cdek_pvz_code: str | None = None
    customer_comment: str | None = Field(None, max_length=1000)
    items: list[OrderItemCreateIn] = Field(min_length=1)


class OrderItemOut(BaseModel):
    id: int
    product_id: int
    variant_id: int | None = None
    product_name: str
    product_slug: str
    color: str | None = None
    size: str
    quantity: int
    unit_price: int
    subtotal: int

    model_config = ConfigDict(from_attributes=True)


class OrderOut(BaseModel):
    id: int
    user_id: int | None = None
    customer_name: str
    customer_phone: str
    customer_email: str | None = None
    delivery_method: str
    delivery_city: str
    delivery_address: str
    cdek_pvz_code: str | None = None
    customer_comment: str | None = None
    items_total: int
    delivery_cost: int
    total_amount: int
    currency: str
    status: str
    payment_id: str | None = None
    payment_url: str | None = Field(None, description="Ссылка на оплату по СБП")
    created_at: datetime
    paid_at: datetime | None = None
    payment_expires_at: datetime | None = Field(None, description="Только для pending")
    items: list[OrderItemOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class AdminOrderStatusIn(BaseModel):
    status: Literal["shipped", "completed"]


class SandboxPaymentOut(BaseModel):
    order_id: int
    outcome: str
    order_status: str
    result: str
    message: str


class SBPWebhookPayload(BaseModel):
    """Принимает плоский формат песочницы и нативный формат ЮKassa (поле object)."""

    event: str
    payment_id: str | None = None
    order_id: int | None = None
    amount: int | None = None
    secret_signature: str | None = Field(None, description="Секрет в теле, если нельзя передать заголовок")
    yk_object: dict[str, Any] | None = Field(None, alias="object")

    model_config = ConfigDict(populate_by_name=True)

    def normalized(self) -> tuple[str | None, int | None, int | None]:
        obj = self.yk_object or {}
        payment_id = self.payment_id or obj.get("id")

        order_id = self.order_id
        if order_id is None:
            try:
                order_id = int((obj.get("metadata") or {}).get("order_id"))
            except (TypeError, ValueError):
                order_id = None

        amount = self.amount
        if amount is None and isinstance(obj.get("amount"), dict):
            try:
                amount = int(float(obj["amount"]["value"]))
            except (KeyError, TypeError, ValueError):
                amount = None
        return payment_id, order_id, amount
