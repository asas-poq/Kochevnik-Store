from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_VALUES = {"super_secret_cashmere_jwt_key_change_in_production_2026", "change-me"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="ignore"
    )

    PROJECT_NAME: str = "Ulaanbaatar Cashmere & Leather API"
    VERSION: str = "2.0.0"
    ENVIRONMENT: str = "development"
    API_V1_STR: str = "/api/v1"
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "https://ubcashmere.ru",
    ]

    POSTGRES_USER: str = "ubcashmere"
    POSTGRES_PASSWORD: str = "ubcashmere_secret"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "ubcashmere_db"
    DATABASE_URL: str | None = None

    REDIS_URL: str = "redis://localhost:6379/0"
    CATALOG_CACHE_TTL: int = 60
    REVIEWS_CACHE_TTL: int = 120
    CATEGORIES_CACHE_TTL: int = 300

    SECRET_KEY: str = "change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    RATE_AUTH_PER_MIN: int = 10
    RATE_REVIEWS_PER_MIN: int = 10
    RATE_PARSER_PER_MIN: int = 6
    RATE_WEBHOOK_PER_MIN: int = 120

    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_PUBLIC_BASE_URL: str = "https://cdn.ubcashmere.ru"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin123"
    S3_BUCKET_NAME: str = "ubcashmere-media"
    S3_REGION: str = "ru-central1"
    MAX_IMAGE_MB: int = 10
    MAX_FILES_PER_REQUEST: int = 10
    MAX_IMAGES_PER_PRODUCT: int = 20

    PAYMENT_PROVIDER: str = "yookassa"
    YOOKASSA_SHOP_ID: str = "test_shop_id"
    YOOKASSA_SECRET_KEY: str = "test_secret_key"
    PAYMENT_WEBHOOK_SECRET: str = "change-me"
    PAYMENT_RETURN_URL: str = "https://ubcashmere.ru/checkout/success"
    PUBLIC_BASE_URL: str = "http://localhost:8000"
    ORDER_PAYMENT_TTL_MINUTES: int = 30
    FREE_DELIVERY_THRESHOLD_RUB: int = 15000
    DELIVERY_COST_RUB: int = 490
    REVIEWS_PREMODERATION: bool = False

    POPULARITY_WINDOW_DAYS: int = 90
    POPULARITY_W_SOLD: int = 5
    POPULARITY_W_LIKES: int = 2
    POPULARITY_W_REVIEWS: int = 3
    POPULARITY_W_RATING: int = 2

    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_OWNER_CHAT_ID: str = ""
    TELEGRAM_STAFF_CHAT_ID: str = ""
    TELEGRAM_ADMIN_USER_IDS: str = ""
    TELEGRAM_UPDATES_MODE: str = "polling"
    TELEGRAM_WEBHOOK_SECRET: str = ""

    PARSER_BASE_URL: str = "https://ubcashmere.ru"
    PARSER_SOURCE_NAME: str = "ubcashmere"
    PARSER_DELAY_SECONDS: float = 1.5
    PARSER_HTTP_TIMEOUT: float = 30
    PARSER_RETRIES: int = 3
    PARSER_USER_AGENT: str = "Mozilla/5.0 (compatible; PriceResearchBot/1.0; +contact: replace-with-your-email)"
    PARSER_DATA_DIR: str = "data/parser"
    PARSER_LOCK_TTL_SECONDS: int = 4 * 3600
    PARSER_DEFAULT_STOCK: int = 5

    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/backend.log"
    LOG_JSON: bool = False
    METRICS_ENABLED: bool = True
    METRICS_TOKEN: str = ""

    @model_validator(mode="after")
    def _check_production(self) -> "Settings":
        if not self.is_production:
            return self
        problems = []
        if self.SECRET_KEY in INSECURE_VALUES or len(self.SECRET_KEY) < 32:
            problems.append("SECRET_KEY: задайте случайную строку от 32 символов")
        if self.PAYMENT_WEBHOOK_SECRET in INSECURE_VALUES or self.PAYMENT_WEBHOOK_SECRET.startswith(
            "sbp_webhook_secret"
        ):
            problems.append("PAYMENT_WEBHOOK_SECRET: остался значением по умолчанию")
        if self.payments_sandbox_mode:
            problems.append("YOOKASSA_SHOP_ID: тестовые ключи test_* в production")
        if problems:
            raise ValueError("Небезопасные настройки production: " + "; ".join(problems))
        return self

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def async_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def payments_sandbox_mode(self) -> bool:
        return self.YOOKASSA_SHOP_ID.startswith("test_")

    @property
    def sandbox_payments_enabled(self) -> bool:
        return self.payments_sandbox_mode and not self.is_production

    @property
    def s3_local_fallback(self) -> bool:
        return self.ENVIRONMENT.lower() in {"development", "test"}

    @property
    def telegram_approver_ids(self) -> set[str]:
        ids = {x.strip() for x in self.TELEGRAM_ADMIN_USER_IDS.split(",") if x.strip()}
        if self.TELEGRAM_OWNER_CHAT_ID.strip():
            ids.add(self.TELEGRAM_OWNER_CHAT_ID.strip())
        return ids


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
