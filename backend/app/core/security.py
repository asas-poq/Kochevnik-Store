"""
Модуль безопасности и криптографии (`app/core/security.py`).
Отвечает за хеширование паролей пользователей (алгоритм bcrypt)
и генерацию / проверку JWT-токенов (Access и Refresh).
"""

from datetime import datetime, timedelta, timezone
import uuid
from typing import Any, Dict, Optional, Union
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Контекст Passlib для безопасного хеширования паролей через bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Проверяет соответствие введенного пароля в открытом виде его bcrypt-хешу из БД.
    """
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as exc:
        logger.error(f"Ошибка при проверке хеша пароля: {exc}")
        return False


def get_password_hash(password: str) -> str:
    """
    Генерирует безопасный bcrypt-хеш для нового пароля пользователя.
    """
    return pwd_context.hash(password)


def create_access_token(
    subject: Union[str, int],
    extra_claims: Optional[Dict[str, Any]] = None,
    expires_delta: Optional[timedelta] = None,
    session_id: Optional[str] = None,
) -> str:
    """
    Создает короткоживущий JWT Access-токен для авторизации запросов в API.
    Поле `sub` содержит ID пользователя, поле `type` = 'access'.
    """
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode: Dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
        "iat": now,
        "type": "access",
        "sid": session_id,
    }
    if extra_claims:
        to_encode.update(extra_claims)

    encoded_jwt = jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )
    logger.debug(f"Сгенерирован access-токен для пользователя ID={subject}")
    return encoded_jwt


def create_refresh_token(
    subject: Union[str, int],
    session_id: Optional[str] = None,
    jti: Optional[str] = None,
) -> str:
    """
    Создает долгоживущий JWT Refresh-токен для обновления сессии пользователя.
    Поле `sub` содержит ID пользователя, поле `type` = 'refresh'.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode: Dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
        "iat": now,
        "type": "refresh",
        "sid": session_id,
        "jti": jti or uuid.uuid4().hex,
    }
    encoded_jwt = jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )
    logger.debug(f"Сгенерирован refresh-токен для пользователя ID={subject}")
    return encoded_jwt


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Декодирует и проверяет подпись и срок действия JWT-токена.
    Возвращает словарь с полезной нагрузкой (payload) или None в случае ошибки.
    """
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        return payload
    except JWTError as exc:
        logger.warning(f"Невалидный или просроченный JWT-токен: {exc}")
        return None
