"""
Скрипт наполнения базы данных (`scripts/seed_from_parser.py`).
Загружает весь JSON-дамп вашего парсера (`data/parsed_dump.json`) в базу данных,
а также создает:
1. Учетную запись Администратора (`admin@ubcashmere.ru` / пароль `Admin123!`)
2. Тестового Покупателя (`anna@example.com` / пароль `Customer123!`)
3. Несколько демонстрационных лайков и отзывов к кашемировым пуловерам и палантинам.

Запуск из корня проекта:
    python3 -m scripts.seed_from_parser
"""

import asyncio
import sys
from pathlib import Path

# Добавляем корневую директорию проекта в sys.path для корректного импорта пакета app
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import select
from app.core.logging import get_logger, setup_logging
from app.core.security import get_password_hash
from app.db.base import Base
from app.db.session import AsyncSessionLocal, engine
from app.models.interactions import ProductLike, ProductReview
from app.models.user import User
from app.services.tasks import import_parser_dump_task, recalculate_product_stats_task

setup_logging()
logger = get_logger("seed_script")


async def seed_users_and_interactions() -> None:
    """
    Создает демонстрационного администратора, покупателя, лайки и отзывы,
    чтобы все ручки API можно было сразу протестировать через Swagger (/docs).
    """
    async with AsyncSessionLocal() as db:
        # 1. Проверяем / создаем Администратора
        admin_q = await db.execute(
            select(User).where(User.email == "admin@ubcashmere.ru")
        )
        admin = admin_q.scalar_one_or_none()
        if not admin:
            admin = User(
                email="admin@ubcashmere.ru",
                phone="+79990000001",
                full_name="Администратор Ulaanbaatar",
                hashed_password=get_password_hash("Admin123!"),
                role="admin",
                default_city="Москва",
                default_delivery_address="Шоурум Ulaanbaatar, Москва",
            )
            db.add(admin)
            logger.info("Создан аккаунт администратора: admin@ubcashmere.ru (пароль: Admin123!)")

        # 2. Проверяем / создаем Покупателя
        cust_q = await db.execute(
            select(User).where(User.email == "anna@example.com")
        )
        customer = cust_q.scalar_one_or_none()
        if not customer:
            customer = User(
                email="anna@example.com",
                phone="+79991112233",
                full_name="Анна Морозова",
                hashed_password=get_password_hash("Customer123!"),
                role="customer",
                default_city="Москва",
                default_delivery_address="ПВЗ СДЭК MSK142, ул. Тверская, д. 12",
            )
            db.add(customer)
            logger.info("Создан тестовый аккаунт покупателя: anna@example.com (пароль: Customer123!)")

        await db.flush()

        # 3. Добавляем демо-лайки и отзывы к первым товарам из парсера
        existing_reviews = (await db.execute(select(ProductReview))).scalars().all()
        if not existing_reviews and customer:
            demo_likes = [
                ProductLike(user_id=customer.id, product_id=1),
                ProductLike(user_id=customer.id, product_id=2),
                ProductLike(user_id=customer.id, product_id=4),
            ]
            db.add_all(demo_likes)

            demo_reviews = [
                ProductReview(
                    product_id=1,
                    user_id=customer.id,
                    rating=5,
                    comment_text=(
                        "Невероятно нежный голубой палантин! Настоящий монгольский кашемир, "
                        "очень легкий как облако и при этом прекрасно согревает."
                    ),
                    advantages="100% натуральный кашемир, тонкая ажурная вязка, благородный оттенок",
                    disadvantages="Нет",
                    is_verified_purchase=True,
                    is_approved=True,
                    admin_reply="Благодарим вас за теплый отзыв, Анна! Носите с удовольствием.",
                ),
                ProductReview(
                    product_id=2,
                    user_id=customer.id,
                    rating=5,
                    comment_text=(
                        "Молочный пуловер сел идеально на размер 44-46. После деликатной стирки "
                        "стал еще мягче, совсем не пилингуется."
                    ),
                    advantages="Мягкость, идеальная посадка свободного кроя, цвет #FAF8F5",
                    disadvantages="Не обнаружено",
                    is_verified_purchase=True,
                    is_approved=True,
                ),
            ]
            db.add_all(demo_reviews)
            await db.commit()
            logger.info("Добавлены демонстрационные лайки и отзывы к товарам #1, #2, #4")

            # Обновляем счетчики товаров
            for pid in (1, 2, 4):
                await recalculate_product_stats_task(pid)
        else:
            await db.commit()


async def main() -> None:
    """Главная точка входа скрипта сидирования."""
    logger.info("=== Старт инициализации БД и загрузки данных парсера ===")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    dump_file = ROOT_DIR / "data" / "parsed_dump.json"
    stats = await import_parser_dump_task(str(dump_file))
    logger.info(f"Статистика импорта парсера: {stats}")

    await seed_users_and_interactions()
    await engine.dispose()
    logger.info("=== Наполнение базы данных успешно завершено! ===")


if __name__ == "__main__":
    asyncio.run(main())
