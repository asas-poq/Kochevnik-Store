from datetime import datetime

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.core.validators import normalize_phone, validate_password_strength


class UserRegisterIn(BaseModel):
    email: EmailStr
    phone: str | None = Field(None, max_length=25, description="Любой формат, сохраняется как +79991234567")
    full_name: str = Field(min_length=2, max_length=150)
    password: str = Field(max_length=100, description="От 8 символов, буквы и цифры")
    default_city: str | None = "Москва"

    @field_validator("email")
    @classmethod
    def _email_lower(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("phone")
    @classmethod
    def _phone_norm(cls, v: str | None) -> str | None:
        return normalize_phone(v) if v and v.strip() else None

    @model_validator(mode="after")
    def _check_password(self) -> "UserRegisterIn":
        validate_password_strength(self.password, str(self.email))
        return self


class UserLoginIn(BaseModel):
    login: str = Field(
        validation_alias=AliasChoices("login", "email", "phone"),
        min_length=3,
        description="Email или телефон. Поля email и phone тоже принимаются",
    )
    password: str = Field(min_length=1)


class UserUpdateIn(BaseModel):
    full_name: str | None = Field(None, min_length=2, max_length=150)
    phone: str | None = Field(None, max_length=25)
    default_city: str | None = None
    default_delivery_address: str | None = None

    @field_validator("phone")
    @classmethod
    def _phone_norm(cls, v: str | None) -> str | None:
        return normalize_phone(v) if v and v.strip() else None


class UserOut(BaseModel):
    id: int
    email: EmailStr
    phone: str | None = None
    full_name: str
    role: str
    is_active: bool
    default_city: str | None = None
    default_delivery_address: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenPairOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class TokenRefreshIn(BaseModel):
    refresh_token: str


class LogoutIn(BaseModel):
    refresh_token: str | None = Field(None, description="Если не передан, берётся из cookie")


class SessionOut(BaseModel):
    jti: str
    user_agent: str | None = None
    ip: str | None = None
    created_at: datetime
    expires_at: datetime

    model_config = ConfigDict(from_attributes=True)
