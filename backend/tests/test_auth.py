from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models import UserSession

REGISTER = {
    "email": "Anna@Example.com",
    "phone": "8 (999) 123-45-67",
    "full_name": "Анна Морозова",
    "password": "Zebra2026!",
}


async def test_register_login_and_me(client):
    created = await client.post("/api/v1/auth/register", json=REGISTER)
    assert created.status_code == 201
    assert created.json()["user"]["email"] == "anna@example.com"
    assert created.json()["user"]["phone"] == "+79991234567"

    login = await client.post("/api/v1/auth/login", json={"login": "+7 999 123 45 67", "password": "Zebra2026!"})
    assert login.status_code == 200
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
    assert me.json()["full_name"] == "Анна Морозова"


async def test_duplicate_email_is_conflict(client):
    await client.post("/api/v1/auth/register", json=REGISTER)

    resp = await client.post("/api/v1/auth/register", json={**REGISTER, "phone": None})

    assert resp.status_code == 409


async def test_weak_password_gives_short_error(client):
    resp = await client.post("/api/v1/auth/register", json={**REGISTER, "password": "12345678"})

    body = resp.json()
    assert resp.status_code == 422
    assert body["code"] == "validation_error"
    assert "букву" in body["detail"]
    assert body["errors"][0]["message"] == body["detail"]


async def test_reused_refresh_token_closes_the_session(client):
    tokens = (await client.post("/api/v1/auth/register", json=REGISTER)).json()
    old_refresh = tokens["refresh_token"]

    rotated = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert rotated.status_code == 200

    replay = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert replay.status_code == 401
    # После кражи закрыта вся сессия, новый refresh тоже больше не работает
    later = await client.post("/api/v1/auth/refresh", json={"refresh_token": rotated.json()["refresh_token"]})
    assert later.status_code == 401
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(UserSession.revoked_at))).scalar_one() is not None


async def test_logout_makes_access_token_useless(client):
    tokens = (await client.post("/api/v1/auth/register", json=REGISTER)).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    await client.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})

    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401
