"""
Pydantic v2 схемы для регистрации, авторизации (JWT) и профиля пользователя (`app/schemas/user.py`).
"""

from datetime import datetime
from typing import Optional
from pydantic import (
    AliasChoices, BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator,
)

from app.core.validators import normalize_phone, validate_password_strength


class UserRegisterIn(BaseModel):
    """Схема входных данных при регистрации нового покупателя."""
    email: EmailStr = Field(..., description="Электронная почта пользователя")
    phone: Optional[str] = Field(
        None,
        max_length=25,
        description="Номер телефона (например, +79991234567)",
    )
    full_name: str = Field(
        ..., min_length=2, max_length=150, description="Имя и фамилия покупателя"
    )
    password: str = Field(..., max_length=100, description="Пароль: от 8 символов, буквы и цифры")
    default_city: Optional[str] = Field("Москва", description="Город доставки по умолчанию")

    @field_validator("email")
    @classmethod
    def _email_lower(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("phone")
    @classmethod
    def _phone_norm(cls, v: Optional[str]) -> Optional[str]:
        return normalize_phone(v) if v and v.strip() else None

    @model_validator(mode="after")
    def _check_password(self):
        validate_password_strength(self.password, str(self.email))
        return self


class UserLoginIn(BaseModel):
    """Вход по email ИЛИ номеру телефона. Старые поля `email` / `phone` тоже принимаются."""
    login: str = Field(validation_alias=AliasChoices("login", "email", "phone"), min_length=3)
    password: str = Field(min_length=1)


class UserUpdateIn(BaseModel):
    """Схема обновления профиля пользователя."""
    full_name: Optional[str] = Field(None, min_length=2, max_length=150)
    phone: Optional[str] = Field(None, max_length=25)
    default_city: Optional[str] = None
    default_delivery_address: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def _phone_norm(cls, v: Optional[str]) -> Optional[str]:
        return normalize_phone(v) if v and v.strip() else None


class UserOut(BaseModel):
    """Безопасная схема профиля пользователя (без хеша пароля)."""
    id: int
    email: EmailStr
    phone: Optional[str] = None
    full_name: str
    role: str
    is_active: bool
    default_city: Optional[str] = None
    default_delivery_address: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenPairOut(BaseModel):
    """Ответ при успешной авторизации или регистрации (Access + Refresh токены)."""
    access_token: str = Field(..., description="JWT Access-токен для заголовка Authorization: Bearer")
    refresh_token: str = Field(..., description="JWT Refresh-токен для продления сессии")
    token_type: str = "bearer"
    user: UserOut


class TokenRefreshIn(BaseModel):
    """Запрос на обновление Access-токена по Refresh-токену."""
    refresh_token: str


class LogoutIn(BaseModel):
    """Выход: refresh-токен можно не передавать, если он лежит в cookie."""
    refresh_token: Optional[str] = None


class SessionOut(BaseModel):
    """Активная сессия (устройство) пользователя."""
    jti: str
    user_agent: Optional[str] = None
    ip: Optional[str] = None
    created_at: datetime
    expires_at: datetime

    model_config = ConfigDict(from_attributes=True)
