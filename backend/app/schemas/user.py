"""
Pydantic v2 схемы для регистрации, авторизации (JWT) и профиля пользователя (`app/schemas/user.py`).
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRegisterIn(BaseModel):
    """Схема входных данных при регистрации нового покупателя."""
    email: EmailStr = Field(..., description="Электронная почта пользователя")
    phone: Optional[str] = Field(
        None,
        min_length=10,
        max_length=20,
        description="Номер телефона (например, +79991234567)",
    )
    full_name: str = Field(
        ..., min_length=2, max_length=150, description="Имя и фамилия покупателя"
    )
    password: str = Field(
        ..., min_length=6, max_length=100, description="Пароль (минимум 6 символов)"
    )
    default_city: Optional[str] = Field("Москва", description="Город доставки по умолчанию")


class UserLoginIn(BaseModel):
    """Схема для входа по email и паролю."""
    email: EmailStr
    password: str


class UserUpdateIn(BaseModel):
    """Схема обновления профиля пользователя."""
    full_name: Optional[str] = Field(None, min_length=2, max_length=150)
    phone: Optional[str] = Field(None, min_length=10, max_length=20)
    default_city: Optional[str] = None
    default_delivery_address: Optional[str] = None


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
