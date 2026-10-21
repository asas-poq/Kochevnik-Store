from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.errors import ConflictError
from app.db.session import AsyncSessionLocal
from app.db.types import utc_now
from app.models import Order, ProductSize
from app.schemas.order import OrderCreateIn
from app.services import orders
from app.services.payment_sbp import SBPPaymentService
from tests.conftest import create_product, create_user, order_body

gateway = SBPPaymentService()


async def stock_of(db, product_id: int, size: str = "M") -> int:
    row = await db.execute(
        select(ProductSize.stock).where(ProductSize.product_id == product_id, ProductSize.size == size)
    )
    return row.scalar_one()


async def place(db, cache, user, product, quantity=1, **extra):
    payload = OrderCreateIn.model_validate(order_body(product.id, quantity=quantity, **extra))
    return await orders.create_order(db, cache, user, payload, gateway)


async def test_order_reserves_stock_and_adds_delivery(db, cache):
    user = await create_user(db)
    product = await create_product(db, price=5000, sizes={"M": 3})

    order = await place(db, cache, user, product, quantity=2)

    assert order.status == "pending"
    assert (order.items_total, order.delivery_cost, order.total_amount) == (10000, 490, 10490)
    assert order.payment_url and order.payment_id
    assert await stock_of(db, product.id) == 1


async def test_delivery_is_free_over_threshold_and_for_pickup(db, cache):
    user = await create_user(db)
    expensive = await create_product(db, slug="a", price=16000)
    cheap = await create_product(db, slug="b", price=1000)

    assert (await place(db, cache, user, expensive)).delivery_cost == 0
    pickup = await place(db, cache, user, cheap, delivery_method="showroom_pickup")
    assert pickup.delivery_cost == 0


async def test_cannot_order_more_than_in_stock(db, cache):
    user = await create_user(db)
    product = await create_product(db, sizes={"M": 1})

    with pytest.raises(ConflictError):
        await place(db, cache, user, product, quantity=2)
    assert await stock_of(db, product.id) == 1


async def test_cancel_returns_stock(db, cache):
    user = await create_user(db)
    product = await create_product(db, sizes={"M": 3})
    order = await place(db, cache, user, product, quantity=2)

    await orders.cancel_my_order(db, cache, user, order.id)

    assert await stock_of(db, product.id) == 3
    with pytest.raises(ConflictError):
        await orders.cancel_my_order(db, cache, user, order.id)


async def test_expired_orders_are_cancelled_and_fresh_ones_are_not(db, cache):
    user = await create_user(db)
    product = await create_product(db, sizes={"M": 5})
    old = await place(db, cache, user, product)
    fresh = await place(db, cache, user, product)
    old_row = await db.get(Order, old.id)
    old_row.created_at = utc_now() - timedelta(hours=2)
    await db.commit()

    assert await orders.cancel_expired_pending_orders(AsyncSessionLocal) == 1

    async with AsyncSessionLocal() as check:
        assert (await check.get(Order, old.id)).status == "cancelled"
        assert (await check.get(Order, fresh.id)).status == "pending"
        assert await stock_of(check, product.id) == 4


async def test_payment_result_is_idempotent(db, cache):
    user = await create_user(db)
    product = await create_product(db)
    order = await place(db, cache, user, product)

    assert await orders.apply_payment_result(db, order, True, order.total_amount) == "paid"
    paid_at = order.paid_at
    assert await orders.apply_payment_result(db, order, True, order.total_amount) == "already_paid"
    assert order.paid_at == paid_at


async def test_wrong_amount_does_not_mark_paid(db, cache):
    user = await create_user(db)
    order = await place(db, cache, user, await create_product(db))

    assert await orders.apply_payment_result(db, order, True, paid_amount=1) == "amount_mismatch"
    assert order.status == "pending"


async def test_payment_after_cancel_needs_manual_review(db, cache):
    user = await create_user(db)
    product = await create_product(db, sizes={"M": 3})
    order = await place(db, cache, user, product)
    await orders.cancel_my_order(db, cache, user, order.id)

    result = await orders.apply_payment_result(db, order, True, order.total_amount)

    assert result == "paid_after_cancel"
    assert order.status == "cancelled"
    assert await stock_of(db, product.id) == 3
