from sqlalchemy import update

from app.db.session import AsyncSessionLocal
from app.models import Order, OrderStatus, Product
from tests.conftest import auth_headers, create_product, create_user, order_body

URL = "/api/v1/interactions/products/{}/reviews"


async def buy(client, db, user, product, completed: bool) -> None:
    resp = await client.post(
        "/api/v1/orders", json=order_body(product.id), headers=await auth_headers(user)
    )
    if completed:
        async with AsyncSessionLocal() as s:
            await s.execute(
                update(Order).where(Order.id == resp.json()["id"]).values(status=OrderStatus.COMPLETED.value)
            )
            await s.commit()


async def test_review_needs_completed_order(client, db):
    user = await create_user(db)
    product = await create_product(db)
    headers = await auth_headers(user)
    body = {"rating": 5, "comment_text": "Отличный свитер"}

    assert (await client.post(URL.format(product.id), json=body, headers=headers)).status_code == 403

    await buy(client, db, user, product, completed=False)
    assert (await client.post(URL.format(product.id), json=body, headers=headers)).status_code == 403


async def test_review_updates_rating_and_blocks_duplicates(client, db):
    user = await create_user(db)
    product = await create_product(db)
    await buy(client, db, user, product, completed=True)
    headers = await auth_headers(user)

    created = await client.post(
        URL.format(product.id), json={"rating": 4, "comment_text": "Хороший"}, headers=headers
    )
    again = await client.post(
        URL.format(product.id), json={"rating": 5, "comment_text": "Ещё раз"}, headers=headers
    )

    assert created.status_code == 201
    assert created.json()["is_verified_purchase"] is True
    assert again.status_code == 409
    async with AsyncSessionLocal() as check:
        fresh = await check.get(Product, product.id)
        assert (fresh.reviews_count, fresh.rating_avg) == (1, 4.0)


async def test_reply_does_not_change_rating_and_stranger_cannot_delete(client, db):
    author = await create_user(db, "author@example.com")
    stranger = await create_user(db, "stranger@example.com")
    admin = await create_user(db, "admin@example.com", role="admin")
    product = await create_product(db)
    await buy(client, db, author, product, completed=True)
    root = await client.post(
        URL.format(product.id),
        json={"rating": 5, "comment_text": "Отлично"},
        headers=await auth_headers(author),
    )
    root_id = root.json()["id"]

    reply = await client.post(
        URL.format(product.id),
        json={"comment_text": "Согласен", "parent_id": root_id},
        headers=await auth_headers(stranger),
    )
    assert reply.status_code == 201
    assert reply.json()["rating"] is None

    forbidden = await client.delete(
        f"/api/v1/interactions/reviews/{root_id}", headers=await auth_headers(stranger)
    )
    assert forbidden.status_code == 403
    removed = await client.delete(
        f"/api/v1/interactions/reviews/{root_id}", headers=await auth_headers(admin)
    )
    assert removed.status_code == 204

    listing = await client.get(URL.format(product.id))
    assert listing.json() == []


async def test_review_list_is_cached_until_a_write(client, db, redis):
    user = await create_user(db)
    product = await create_product(db)
    await buy(client, db, user, product, completed=True)

    assert (await client.get(URL.format(product.id))).json() == []
    await client.post(
        URL.format(product.id),
        json={"rating": 5, "comment_text": "Супер"},
        headers=await auth_headers(user),
    )

    assert len((await client.get(URL.format(product.id))).json()) == 1
