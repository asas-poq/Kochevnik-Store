from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ConflictError, ForbiddenError, UnauthorizedError
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.core.validators import normalize_phone
from app.models import User, UserSession
from app.schemas.user import UserRegisterIn, UserUpdateIn

logger = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def register(db: AsyncSession, payload: UserRegisterIn) -> User:
    if (await db.execute(select(User.id).where(User.email == payload.email))).first():
        raise ConflictError("Этот email уже зарегистрирован. Войдите в аккаунт.")
    if payload.phone and (await db.execute(select(User.id).where(User.phone == payload.phone))).first():
        raise ConflictError("Этот номер телефона уже зарегистрирован. Войдите в аккаунт.")

    user = User(
        email=payload.email,
        phone=payload.phone,
        full_name=payload.full_name,
        hashed_password=get_password_hash(payload.password),
        default_city=payload.default_city,
        role="customer",
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        # Два одинаковых запроса прошли проверки выше одновременно
        await db.rollback()
        raise ConflictError("Пользователь с таким email или телефоном уже зарегистрирован.") from None
    logger.info("Пользователь зарегистрирован", extra={"user_id": user.id})
    return user


async def authenticate(db: AsyncSession, login: str, password: str) -> User:
    login = login.strip()
    if "@" in login:
        condition = User.email == login.lower()
    else:
        try:
            condition = User.phone == normalize_phone(login)
        except ValueError:
            raise UnauthorizedError("Неверный логин или пароль.") from None

    user = (await db.execute(select(User).where(condition))).scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_password):
        logger.warning("Неудачный вход")
        raise UnauthorizedError("Неверный логин или пароль.")
    if not user.is_active:
        raise ForbiddenError("Учётная запись деактивирована.")
    return user


async def open_session(db: AsyncSession, user: User, user_agent: str | None, ip: str | None) -> tuple[str, str]:
    """Создаёт сессию и возвращает пару access и refresh."""
    sid, refresh_jti = uuid4().hex, uuid4().hex
    db.add(
        UserSession(
            jti=sid,
            refresh_jti=refresh_jti,
            user_id=user.id,
            user_agent=(user_agent or "")[:255],
            ip=ip,
            expires_at=_now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    await db.commit()
    return (
        create_access_token(user.id, sid, user.role),
        create_refresh_token(user.id, sid, refresh_jti),
    )


async def refresh(db: AsyncSession, refresh_token: str) -> tuple[User, str, str]:
    """Ротация refresh. Повторное предъявление старого токена закрывает всю сессию."""
    invalid = UnauthorizedError("Невалидный или просроченный refresh-токен.")
    decoded = decode_token(refresh_token)
    if not decoded or decoded.get("type") != "refresh" or not decoded.get("sid"):
        raise invalid

    session = (
        await db.execute(select(UserSession).where(UserSession.jti == decoded["sid"]))
    ).scalar_one_or_none()
    if not session or session.revoked_at is not None or session.expires_at < _now():
        raise invalid

    if session.refresh_jti != decoded.get("jti"):
        session.revoked_at = _now()
        await db.commit()
        logger.warning("Повторное использование refresh-токена, сессия закрыта", extra={"sid": session.jti})
        raise invalid

    user = await db.get(User, int(decoded["sub"]))
    if not user or not user.is_active:
        raise invalid

    new_jti = uuid4().hex
    session.refresh_jti = new_jti
    await db.commit()
    return (
        user,
        create_access_token(user.id, session.jti, user.role),
        create_refresh_token(user.id, session.jti, new_jti),
    )


async def logout(db: AsyncSession, refresh_token: str | None) -> None:
    decoded = decode_token(refresh_token) if refresh_token else None
    if decoded and decoded.get("sid"):
        await db.execute(
            update(UserSession)
            .where(UserSession.jti == decoded["sid"], UserSession.revoked_at.is_(None))
            .values(revoked_at=_now())
        )
        await db.commit()


async def logout_all(db: AsyncSession, user: User) -> None:
    await db.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    await db.commit()


async def active_sessions(db: AsyncSession, user: User) -> list[UserSession]:
    rows = await db.execute(
        select(UserSession)
        .where(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > _now(),
        )
        .order_by(UserSession.created_at.desc())
    )
    return list(rows.scalars())


async def update_profile(db: AsyncSession, user: User, payload: UserUpdateIn) -> User:
    data = payload.model_dump(exclude_unset=True)
    phone = data.get("phone")
    if phone and (
        await db.execute(select(User.id).where(User.phone == phone, User.id != user.id))
    ).first():
        raise ConflictError("Этот номер телефона уже используется.")

    for field, value in data.items():
        setattr(user, field, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError("Этот номер телефона уже используется.") from None
    return user
