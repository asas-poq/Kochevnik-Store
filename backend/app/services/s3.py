import uuid
from pathlib import Path

import aioboto3
from fastapi import UploadFile

from app.core.config import settings
from app.core.errors import BadGatewayError
from app.core.logging import get_logger

logger = get_logger(__name__)

LOCAL_MEDIA_DIR = Path("media/uploads")
EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


class S3StorageService:
    def _client(self):  # type: ignore[no-untyped-def]
        return aioboto3.Session().client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
        )

    async def upload_product_image(self, file: UploadFile, product_slug: str) -> str:
        """Возвращает публичный URL. Локальная папка вместо S3 только в development и test,
        иначе в проде фото тихо оказались бы на диске контейнера."""
        ext = EXTENSIONS.get(file.content_type or "", ".webp")
        key = f"products/{product_slug}/{uuid.uuid4().hex[:12]}{ext}"
        content = await file.read()
        try:
            async with self._client() as s3:
                await s3.put_object(
                    Bucket=settings.S3_BUCKET_NAME, Key=key, Body=content, ContentType=file.content_type
                )
            return f"{settings.S3_PUBLIC_BASE_URL.rstrip('/')}/{key}"
        except Exception as exc:
            if not settings.s3_local_fallback:
                logger.error("Загрузка в S3 не удалась", extra={"error": str(exc)})
                raise BadGatewayError("Хранилище фото недоступно, попробуйте позже.") from exc
            logger.warning("S3 недоступен, сохраняем фото локально", extra={"error": str(exc)})
            LOCAL_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
            path = LOCAL_MEDIA_DIR / f"{product_slug}_{uuid.uuid4().hex[:8]}{ext}"
            path.write_bytes(content)
            return f"/media/uploads/{path.name}"

    async def ping(self) -> None:
        async with self._client() as s3:
            await s3.head_bucket(Bucket=settings.S3_BUCKET_NAME)


s3_service = S3StorageService()


def get_s3_service() -> S3StorageService:
    return s3_service
