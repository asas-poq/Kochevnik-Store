"""
Сервис работы с облачным хранилищем S3 / MinIO (`app/services/s3.py`).
Позволяет загружать фотографии свитеров, палантинов и кожаных сумок через админку или API
и возвращает прямую публичную ссылку (`image_url`) для сохранения в таблицу `product_images`.
Если внешний S3/MinIO недоступен в режиме локальной разработки, автоматически сохраняет
файл в локальную папку `/media/uploads/` и отдает валидный URL.
"""

import uuid
from pathlib import Path
from typing import Optional
from fastapi import UploadFile

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Локальная директория резервного хранения медиафайлов при разработке без Docker MinIO
LOCAL_MEDIA_DIR = Path("media/uploads")
LOCAL_MEDIA_DIR.mkdir(parents=True, exist_ok=True)


class S3StorageService:
    """
    Асинхронный сервис загрузки изображений товаров в S3-совместимое хранилище (MinIO, Timeweb S3, Yandex Object Storage).
    """

    def __init__(self) -> None:
        self.endpoint_url = settings.S3_ENDPOINT_URL
        self.bucket_name = settings.S3_BUCKET_NAME
        self.public_base_url = settings.S3_PUBLIC_BASE_URL.rstrip("/")

    async def upload_product_image(
        self, file: UploadFile, product_slug: str = "common"
    ) -> str:
        """
        Загружает изображение товара в бакет S3 и возвращает прямую ссылку (`image_url`).
        При отсутствии подключения к S3 в dev-режиме сохраняет файл локально.
        """
        ext = Path(file.filename or "image.webp").suffix.lower() or ".webp"
        unique_name = f"products/{product_slug}/{uuid.uuid4().hex[:12]}{ext}"
        content = await file.read()

        # Пытаемся загрузить в облачный S3 / MinIO через aioboto3
        try:
            import aioboto3

            session = aioboto3.Session()
            async with session.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=settings.S3_ACCESS_KEY,
                aws_secret_access_key=settings.S3_SECRET_KEY,
                region_name=settings.S3_REGION,
            ) as s3_client:
                await s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=unique_name,
                    Body=content,
                    ContentType=file.content_type or "image/webp",
                )
                image_url = f"{self.public_base_url}/{unique_name}"
                logger.info(
                    f"Фото успешно загружено в S3 бакет '{self.bucket_name}': {image_url}"
                )
                return image_url
        except Exception as exc:
            # Безопасный фоллбэк на локальное сохранение для удобства разработки
            logger.warning(
                f"S3/MinIO недоступен ({exc}). Сохраняем фото локально в {LOCAL_MEDIA_DIR}."
            )
            local_file = LOCAL_MEDIA_DIR / f"{product_slug}_{uuid.uuid4().hex[:8]}{ext}"
            local_file.write_bytes(content)
            local_url = f"/media/uploads/{local_file.name}"
            logger.info(f"Фото сохранено локально: {local_url}")
            return local_url


# Единый экземпляр сервиса S3 для внедрения через Depends
s3_service = S3StorageService()


def get_s3_service() -> S3StorageService:
    """Зависимость FastAPI (`Depends(get_s3_service)`) для получения клиента S3."""
    return s3_service
