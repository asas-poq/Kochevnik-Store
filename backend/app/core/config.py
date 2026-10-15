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

    # --- Уведомления владельцу в Telegram ---
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_OWNER_CHAT_ID: str = ""

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
