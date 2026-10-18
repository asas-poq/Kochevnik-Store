"""
Модуль конфигурации приложения (Pydantic Settings).
Отвечает за чтение переменных окружения из файла .env и предоставление
строго типизированных настроек во все слои приложения через зависимость или синглтон.
"""

from functools import lru_cache
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Главный класс настроек бэкенда Ulaanbaatar Cashmere.
    Все поля валидируются при старте приложения.
    """

    # --- Основные параметры проекта ---
    PROJECT_NAME: str = "Ulaanbaatar Cashmere & Leather API"
    VERSION: str = "1.0.0"
    DEBUG: bool = True
    ENVIRONMENT: str = "development"
    API_V1_STR: str = "/api/v1"

    # Разрешенные источники CORS (для фронтенда на React / Next.js / Vite)
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "https://ubcashmere.ru",
    ]

    # --- База данных (SQLAlchemy 2.0 Async) ---
    POSTGRES_USER: str = "ubcashmere"
    POSTGRES_PASSWORD: str = "ubcashmere_secret"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "ubcashmere_db"
    DATABASE_URL: Optional[str] = None

    @property
    def async_database_url(self) -> str:
        """
        Формирует строку подключения к БД.
        Если DATABASE_URL указан явно — возвращает его, иначе собирает DSN для asyncpg.
        """
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # --- Авторизация и JWT-токены ---
    SECRET_KEY: str = "super_secret_cashmere_jwt_key_change_in_production_2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # --- Облачное хранилище фото S3 / MinIO ---
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_PUBLIC_BASE_URL: str = "https://cdn.ubcashmere.ru"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin123"
    S3_BUCKET_NAME: str = "ubcashmere-media"
    S3_REGION: str = "ru-central1"

    # --- Платежная система СБП (ЮKassa / Т-Касса) ---
    PAYMENT_PROVIDER: str = "yookassa"  # 'yookassa' или 'tkassa'
    YOOKASSA_SHOP_ID: str = "test_shop_id"
    YOOKASSA_SECRET_KEY: str = "test_secret_key"
    PAYMENT_WEBHOOK_SECRET: str = "sbp_webhook_secret_2026"
    PAYMENT_RETURN_URL: str = "https://ubcashmere.ru/checkout/success"
    # Публичный адрес самого бэкенда (нужен для ссылки на тестовую страницу оплаты в песочнице)
    PUBLIC_BASE_URL: str = "http://localhost:8000"
    # Сколько минут ждём оплату: после этого неоплаченный заказ отменяется, остатки возвращаются
    ORDER_PAYMENT_TTL_MINUTES: int = 30

    @property
    def payments_sandbox_mode(self) -> bool:
        """True, если используются тестовые ключи (`YOOKASSA_SHOP_ID` начинается с `test_`)."""
        return self.YOOKASSA_SHOP_ID.startswith("test_")

    @property
    def sandbox_payments_enabled(self) -> bool:
        """Тестовая оплата доступна только в песочнице и никогда — при ENVIRONMENT=production."""
        return self.payments_sandbox_mode and self.ENVIRONMENT.lower() != "production"

    # --- Уведомления владельцу в Telegram ---
    TELEGRAM_BOT_TOKEN: str = ""
    # Личный чат владельца (положительное число). Только этот чат получает кнопки управления заказом
    TELEGRAM_OWNER_CHAT_ID: str = ""
    # Группа сотрудников (отрицательное число, например -1001234567890): получает статусы заказов
    TELEGRAM_STAFF_CHAT_ID: str = ""
    # Дополнительные Telegram user ID через запятую, которым тоже разрешено нажимать кнопки
    TELEGRAM_ADMIN_USER_IDS: str = ""
    # Как бот получает нажатия кнопок: polling (локально, без домена), webhook (прод, нужен HTTPS) или off
    TELEGRAM_UPDATES_MODE: str = "polling"
    # Секрет для вебхука Telegram (заголовок X-Telegram-Bot-Api-Secret-Token), нужен для режима webhook
    TELEGRAM_WEBHOOK_SECRET: str = ""

    @property
    def telegram_approver_ids(self) -> set:
        """Telegram user ID, которым разрешено нажимать кнопки управления заказом."""
        ids = set()
        if self.TELEGRAM_OWNER_CHAT_ID.strip():
            ids.add(self.TELEGRAM_OWNER_CHAT_ID.strip())
        ids.update(x.strip() for x in self.TELEGRAM_ADMIN_USER_IDS.split(",") if x.strip())
        return ids

    # --- Параметры логирования ---
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/backend.log"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """
    Кэшированная функция получения настроек.
    Может использоваться как напрямую, так и через FastAPI Depends(get_settings).
    """
    return Settings()


# Глобальный экземпляр настроек для удобного импорта
settings = get_settings()