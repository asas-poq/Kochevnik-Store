from sqlalchemy import update

from app.db.session import AsyncSessionLocal
from app.models import Product
from tests.conftest import auth_headers, create_product, create_user

CATALOG = "/api/v1/products/catalog"


async def test_filters_and_facets(client, db):
    await create_product(db, slug="a", price=5000, color="Серый", sizes={"S": 1, "M": 0})
    await create_product(db, slug="b", price=9000, color="Белый", sizes={"M": 2})
    await create_product(db, slug="hidden", price=7000, status="draft")

    everything = (await client.get(CATALOG)).json()
    assert everything["total"] == 2

    grey = (await client.get(CATALOG, params={"color": "серый"})).json()
    assert [p["slug"] for p in grey["items"]] == ["a"]
    # Фасет цвета считается без фильтра по цвету, иначе второй цвет пропал бы
    assert {c["name"] for c in grey["available_filters"]["colors"]} == {"Серый", "Белый"}

    in_m = (await client.get(CATALOG, params={"size": "M"})).json()
    assert [p["slug"] for p in in_m["items"]] == ["b"]

    cheap = (await client.get(CATALOG, params={"max_price": 6000})).json()
    assert cheap["total"] == 1


async def test_min_price_above_max_price_is_422(client):
    resp = await client.get(CATALOG, params={"min_price": 10, "max_price": 5})

    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


async def test_catalog_cache_is_reset_by_product_update(client, db):
    admin = await create_user(db, role="admin")
    product = await create_product(db, slug="a", price=5000)
    first = (await client.get(CATALOG)).json()["items"][0]["current_price"]

    # Прямой апдейт мимо API не сбрасывает версию кэша, ответ остаётся прежним
    async with AsyncSessionLocal() as s:
        await s.execute(update(Product).where(Product.id == product.id).values(current_price=6000))
        await s.commit()
    stale = (await client.get(CATALOG)).json()["items"][0]["current_price"]

    resp = await client.patch(
        f"/api/v1/products/{product.id}", json={"current_price": 7000}, headers=await auth_headers(admin)
    )
    fresh = (await client.get(CATALOG)).json()["items"][0]["current_price"]

    assert (first, stale) == (5000, 5000)
    assert resp.status_code == 200
    assert fresh == 7000


async def test_liked_flag_is_per_user_even_with_shared_cache(client, db):
    user = await create_user(db)
    product = await create_product(db)
    headers = await auth_headers(user)
    await client.get(CATALOG)

    await client.post(f"/api/v1/interactions/products/{product.id}/like", headers=headers)

    anonymous = (await client.get(CATALOG)).json()["items"][0]
    mine = (await client.get(CATALOG, headers=headers)).json()["items"][0]
    assert anonymous["is_liked_by_me"] is False
    assert mine["is_liked_by_me"] is True


async def test_old_price_must_exceed_price_on_update(client, db):
    admin = await create_user(db, role="admin")
    product = await create_product(db, price=5000)

    resp = await client.patch(
        f"/api/v1/products/{product.id}", json={"old_price": 4000}, headers=await auth_headers(admin)
    )

    assert resp.status_code == 422


async def test_product_write_requires_admin(client, db):
    user = await create_user(db)
    product = await create_product(db)

    resp = await client.patch(
        f"/api/v1/products/{product.id}", json={"current_price": 1}, headers=await auth_headers(user)
    )

    assert resp.status_code == 403
    assert resp.json() == {"detail": "Недостаточно прав. Нужна роль администратора.", "code": "forbidden"}