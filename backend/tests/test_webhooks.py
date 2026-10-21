from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models import Order, PaymentEvent
from tests.conftest import auth_headers, create_product, create_user, order_body

SECRET = {"X-Webhook-Secret": "test-webhook-secret"}


async def new_order(client, db) -> dict:
    user = await create_user(db)
    product = await create_product(db, price=5000, sizes={"M": 3})
    resp = await client.post("/api/v1/orders", json=order_body(product.id), headers=await auth_headers(user))
    assert resp.status_code == 201, resp.text
    return resp.json()


def succeeded(order: dict, **extra) -> dict:
    return {"event": "payment.succeeded", "order_id": order["id"], "payment_id": order["payment_id"], **extra}


async def test_webhook_requires_secret(client, db):
    order = await new_order(client, db)

    resp = await client.post("/api/v1/payments/webhook", json=succeeded(order))

    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthorized"


async def test_webhook_pays_once_and_repeat_is_duplicate(client, db):
    order = await new_order(client, db)
    body = succeeded(order, amount=order["total_amount"])

    first = await client.post("/api/v1/payments/webhook", json=body, headers=SECRET)
    second = await client.post("/api/v1/payments/webhook", json=body, headers=SECRET)

    assert first.json()["status"] == "paid"
    assert second.json()["status"] == "duplicate"
    async with AsyncSessionLocal() as check:
        assert (await check.get(Order, order["id"])).status == "paid"
        events = (await check.execute(select(PaymentEvent))).scalars().all()
        assert len(events) == 1


async def test_webhook_rejects_foreign_payment_id(client, db):
    order = await new_order(client, db)

    resp = await client.post(
        "/api/v1/payments/webhook", json=succeeded(order, payment_id="someone-else"), headers=SECRET
    )

    assert resp.status_code == 409


async def test_amount_mismatch_is_conflict_and_order_stays_pending(client, db):
    order = await new_order(client, db)

    resp = await client.post("/api/v1/payments/webhook", json=succeeded(order, amount=1), headers=SECRET)

    assert resp.status_code == 409
    async with AsyncSessionLocal() as check:
        assert (await check.get(Order, order["id"])).status == "pending"


async def test_canceled_event_returns_stock(client, db):
    order = await new_order(client, db)
    body = {"event": "payment.canceled", "order_id": order["id"], "payment_id": order["payment_id"]}

    resp = await client.post("/api/v1/payments/webhook", json=body, headers=SECRET)

    assert resp.json()["status"] == "cancelled"


async def test_sandbox_simulate_pays_order(client, db):
    order = await new_order(client, db)

    resp = await client.post(f"/api/v1/payments/sandbox/orders/{order['id']}/simulate")

    assert resp.json()["order_status"] == "paid"
