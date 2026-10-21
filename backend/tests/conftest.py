import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ.update(
    {
        "DATABASE_URL": f"sqlite+aiosqlite:///{_tmp}/test.db",
        "ENVIRONMENT": "test",
        "LOG_FILE": "",
        "SECRET_KEY": "test-secret-key-test-secret-key-12345",
        "PAYMENT_WEBHOOK_SECRET": "test-webhook-secret",
        "TELEGRAM_BOT_TOKEN": "",
        "RATE_AUTH_PER_MIN": "1000",
        "RATE_REVIEWS_PER_MIN": "1000",
        "RATE_PARSER_PER_MIN": "1000",
        "RATE_WEBHOOK_PER_MIN": "1000",
    }
)

import httpx  # noqa: E402
import pytest_asyncio  # noqa: E402
from fakeredis import FakeAsyncRedis  # noqa: E402

from app.core.cache import Cache  # noqa: E402
from app.core.queue import get_arq  # noqa: E402
from app.core.redis import get_redis  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Product, ProductSize, Source, User  # noqa: E402
from app.services import auth as auth_service  # noqa: E402


class FakeArq:
    def __init__(self) -> None:
        self.jobs: list[tuple] = []

    async def enqueue_job(self, name: str, *args):  # type: ignore[no-untyped-def]
        self.jobs.append((name, args))
        return object()


@pytest_asyncio.fixture(autouse=True)
async def _database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def redis():
    client = FakeAsyncRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def cache(redis):
    return Cache(redis)


@pytest_asyncio.fixture
async def arq():
    return FakeArq()


@pytest_asyncio.fixture
async def db():
    async with AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(redis, arq):
    app.dependency_overrides[get_redis] = lambda: redis
    app.dependency_overrides[get_arq] = lambda: arq
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def create_user(db, email="buyer@example.com", role="customer", phone=None) -> User:
    user = User(email=email, phone=phone, full_name="Тест Тестов", hashed_password="x", role=role)
    db.add(user)
    await db.commit()
    return user


async def auth_headers(user: User) -> dict[str, str]:
    async with AsyncSessionLocal() as session:
        access, _ = await auth_service.open_session(session, user, "pytest", "127.0.0.1")
    return {"Authorization": f"Bearer {access}"}


async def create_product(
    db, slug="sviter-molochnyi", price=10000, sizes=None, status="active", **fields
) -> Product:
    if await db.get(Source, 1) is None:
        db.add(Source(id=1, name="test", base_url="https://example.test"))
        await db.flush()
    product = Product(
        source_id=1, slug=slug, name=fields.pop("name", f"Свитер {slug}"), current_price=price,
        status=status, color=fields.pop("color", "Молочный"), **fields,
    )
    db.add(product)
    await db.flush()
    for size, stock in (sizes or {"M": 3}).items():
        db.add(ProductSize(product_id=product.id, size=size, stock=stock))
    await db.commit()
    return product


def order_body(product_id: int, size="M", quantity=1, **extra) -> dict:
    return {
        "customer_name": "Анна Морозова",
        "customer_phone": "+79991234567",
        "delivery_address": "Москва, ул. Тверская, 1",
        "items": [{"product_id": product_id, "size": size, "quantity": quantity}],
        **extra,
    }
