"""
Роутер регистрации, авторизации (JWT), сессий и профиля (`app/api/v1/auth.py`).

- email и телефон проверяются на уникальность отдельно, с понятными ошибками (409);
- пароль проверяется в схеме (длина, буквы+цифры, не популярный);
- вход по email ИЛИ по номеру телефона;
- регистрация сразу авторизует (токены в теле ответа + httpOnly-cookie);
- каждая выдача токенов создаёт сессию в БД -> работают /logout, /logout-all, /sessions;
- refresh с ротацией и защитой от повторного использования токена.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUserDep, DBSessionDep
from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.core.validators import normalize_phone
from app.models.session import UserSession
from app.models.user import User
from app.schemas.user import (
    LogoutIn,
    SessionOut,
    TokenPairOut,
    TokenRefreshIn,
    UserLoginIn,
    UserOut,
    UserRegisterIn,
    UserUpdateIn,
)

from datetime import datetime, timezone

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _as_utc(dt: datetime) -> datetime:
    """Гарантирует, что datetime имеет timezone.utc (актуально для SQLite)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["1. Авторизация и Профиль"])


# ==============================================================================
# Вспомогательные функции
# ==============================================================================
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    """Дублируем токены в httpOnly-cookie: фронту не нужно вручную хранить токен."""
    secure = settings.ENVIRONMENT != "development"
    response.set_cookie(
        "access_token", access, httponly=True, secure=secure, samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60, path="/",
    )
    response.set_cookie(
        "refresh_token", refresh, httponly=True, secure=secure, samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400, path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")


async def _issue_tokens(
    db: DBSessionDep, user: User, request: Request, response: Response
) -> TokenPairOut:
    """Создаёт сессию в БД и выдаёт пару токенов, привязанных к ней."""
    sid = uuid4().hex
    refresh_jti = uuid4().hex
    db.add(
        UserSession(
            jti=sid,
            refresh_jti=refresh_jti,
            user_id=user.id,
            user_agent=(request.headers.get("user-agent") or "")[:255],
            ip=request.client.host if request.client else None,
            expires_at=_now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    await db.commit()

    access = create_access_token(subject=user.id, extra_claims={"role": user.role}, session_id=sid)
    refresh = create_refresh_token(subject=user.id, session_id=sid, jti=refresh_jti)
    _set_auth_cookies(response, access, refresh)
    return TokenPairOut(
        access_token=access, refresh_token=refresh, user=UserOut.model_validate(user)
    )


# ==============================================================================
# РУЧКА 1: Регистрация (сразу выполняет вход)
# ==============================================================================
@router.post(
    "/register",
    response_model=TokenPairOut,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация нового пользователя (с автоматическим входом)",
)
async def register_user(
    payload: UserRegisterIn, request: Request, response: Response, db: DBSessionDep
) -> TokenPairOut:
    email = payload.email
    phone = payload.phone  # уже нормализован схемой
    logger.info(f"Запрос на регистрацию: email={email}")

    if (await db.execute(select(User.id).where(User.email == email))).first():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Этот email уже зарегистрирован. Войдите в аккаунт.",
        )
    if phone and (await db.execute(select(User.id).where(User.phone == phone))).first():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Этот номер телефона уже зарегистрирован. Войдите в аккаунт.",
        )

    new_user = User(
        email=email,
        phone=phone,
        full_name=payload.full_name,
        hashed_password=get_password_hash(payload.password),
        default_city=payload.default_city,
        role="customer",
    )
    db.add(new_user)
    try:
        await db.commit()
    except IntegrityError:
        # два запроса одновременно — сработал уникальный индекс в БД
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Пользователь с таким email или телефоном уже зарегистрирован.",
        )
    await db.refresh(new_user)

    logger.info(f"Зарегистрирован пользователь ID={new_user.id} ({new_user.email})")
    return await _issue_tokens(db, new_user, request, response)


# ==============================================================================
# РУЧКА 2: Вход по email ИЛИ телефону
# ==============================================================================
@router.post("/login", response_model=TokenPairOut, summary="Вход по email или номеру телефона")
async def login_user(
    payload: UserLoginIn, request: Request, response: Response, db: DBSessionDep
) -> TokenPairOut:
    login = payload.login.strip()
    if "@" in login:
        condition = User.email == login.lower()
    else:
        try:
            condition = User.phone == normalize_phone(login)
        except ValueError:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Неверный логин или пароль.")

    user = (await db.execute(select(User).where(condition))).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        logger.warning(f"Неудачная попытка входа: login={login}")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Неверный логин или пароль.")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Ваша учетная запись деактивирована.")

    logger.info(f"Пользователь ID={user.id} вошёл в систему")
    return await _issue_tokens(db, user, request, response)


# ==============================================================================
# РУЧКА 3: Обновление токенов (ротация refresh)
# ==============================================================================
@router.post("/refresh", response_model=TokenPairOut, summary="Обновление пары токенов")
async def refresh_access_token(
    payload: TokenRefreshIn, request: Request, response: Response, db: DBSessionDep
) -> TokenPairOut:
    invalid = HTTPException(
        status.HTTP_401_UNAUTHORIZED, detail="Невалидный или просроченный refresh-токен."
    )
    decoded = decode_token(payload.refresh_token)
    if not decoded or decoded.get("type") != "refresh" or not decoded.get("sid"):
        raise invalid

    session = (
        await db.execute(select(UserSession).where(UserSession.jti == decoded["sid"]))
    ).scalar_one_or_none()
    if not session or session.revoked_at is not None or _as_utc(session.expires_at) < _now():
        raise invalid

    # Старый (уже использованный) refresh -> считаем токен украденным, закрываем сессию
    if session.refresh_jti != decoded.get("jti"):
        session.revoked_at = _now()
        await db.commit()
        logger.warning(f"Повторное использование refresh-токена: сессия {session.jti} закрыта")
        raise invalid

    user = await db.get(User, int(decoded["sub"]))
    if not user or not user.is_active:
        raise invalid

    new_jti = uuid4().hex
    session.refresh_jti = new_jti
    await db.commit()

    access = create_access_token(subject=user.id, extra_claims={"role": user.role}, session_id=session.jti)
    refresh = create_refresh_token(subject=user.id, session_id=session.jti, jti=new_jti)
    _set_auth_cookies(response, access, refresh)
    return TokenPairOut(access_token=access, refresh_token=refresh, user=UserOut.model_validate(user))


# ==============================================================================
# РУЧКА 4: Выход (аннулирование текущей сессии)
# ==============================================================================
@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Выход: аннулировать текущую сессию",
)
async def logout(
    request: Request, db: DBSessionDep, payload: Optional[LogoutIn] = None
) -> Response:
    """
    Принимает refresh_token в теле (или берёт из cookie). Работает, даже если access уже истёк.
    Всегда отвечает 204 и чистит cookie.
    """
    token = (payload.refresh_token if payload else None) or request.cookies.get("refresh_token")
    decoded = decode_token(token) if token else None
    if decoded and decoded.get("sid"):
        await db.execute(
            update(UserSession)
            .where(UserSession.jti == decoded["sid"], UserSession.revoked_at.is_(None))
            .values(revoked_at=_now())
        )
        await db.commit()
    out = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_auth_cookies(out)
    return out


# ==============================================================================
# РУЧКА 5: Выйти со всех устройств
# ==============================================================================
@router.post(
    "/logout-all", status_code=status.HTTP_204_NO_CONTENT, summary="Выйти со всех устройств"
)
async def logout_all(current_user: CurrentUserDep, db: DBSessionDep) -> Response:
    await db.execute(
        update(UserSession)
        .where(UserSession.user_id == current_user.id, UserSession.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    await db.commit()
    logger.info(f"Пользователь ID={current_user.id} вышел со всех устройств")
    out = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_auth_cookies(out)
    return out


# ==============================================================================
# РУЧКА 6: Активные сессии
# ==============================================================================
@router.get("/sessions", response_model=list[SessionOut], summary="Активные сессии пользователя")
async def list_sessions(current_user: CurrentUserDep, db: DBSessionDep) -> list[SessionOut]:
    rows = await db.execute(
        select(UserSession)
        .where(
            UserSession.user_id == current_user.id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > _now(),
        )
        .order_by(UserSession.created_at.desc())
    )
    return [SessionOut.model_validate(s) for s in rows.scalars().all()]


# ==============================================================================
# РУЧКА 7: Профиль
# ==============================================================================
@router.get("/me", response_model=UserOut, summary="Профиль текущего пользователя")
async def get_my_profile(current_user: CurrentUserDep) -> UserOut:
    return UserOut.model_validate(current_user)


@router.patch("/me", response_model=UserOut, summary="Обновить имя, телефон или адрес доставки")
async def update_my_profile(
    payload: UserUpdateIn, current_user: CurrentUserDep, db: DBSessionDep
) -> UserOut:
    update_data = payload.model_dump(exclude_unset=True)

    new_phone = update_data.get("phone")
    if new_phone:
        busy = await db.execute(
            select(User.id).where(User.phone == new_phone, User.id != current_user.id)
        )
        if busy.first():
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Этот номер телефона уже используется.")

    for field, value in update_data.items():
        setattr(current_user, field, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Этот номер телефона уже используется.")
    await db.refresh(current_user)
    logger.info(f"Профиль ID={current_user.id} обновлён: {list(update_data.keys())}")
    return UserOut.model_validate(current_user)
