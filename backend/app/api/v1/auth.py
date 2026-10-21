from fastapi import APIRouter, Depends, Request, Response, status

from app.api.deps import CurrentUserDep, DBSessionDep
from app.core.config import settings
from app.core.ratelimit import rate_limit
from app.models import User
from app.schemas.common import ErrorOut
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
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["1. Авторизация и профиль"])

limited = Depends(rate_limit("auth", settings.RATE_AUTH_PER_MIN))
RATE_LIMITED = {429: {"model": ErrorOut, "description": "Слишком много запросов"}}


def _set_cookies(response: Response, access: str, refresh: str) -> None:
    secure = settings.ENVIRONMENT != "development"
    response.set_cookie(
        "access_token", access, httponly=True, secure=secure, samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60, path="/",
    )
    response.set_cookie(
        "refresh_token", refresh, httponly=True, secure=secure, samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400, path="/",
    )


def _clear_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")


def _tokens(user: User, access: str, refresh: str, response: Response) -> TokenPairOut:
    _set_cookies(response, access, refresh)
    return TokenPairOut(access_token=access, refresh_token=refresh, user=UserOut.model_validate(user))


@router.post(
    "/register",
    response_model=TokenPairOut,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация с автоматическим входом",
    dependencies=[limited],
    responses={409: {"model": ErrorOut, "description": "Email или телефон уже заняты"}, **RATE_LIMITED},
)
async def register(payload: UserRegisterIn, request: Request, response: Response, db: DBSessionDep) -> TokenPairOut:
    user = await auth_service.register(db, payload)
    access, refresh = await auth_service.open_session(
        db, user, request.headers.get("user-agent"), request.client.host if request.client else None
    )
    return _tokens(user, access, refresh, response)


@router.post(
    "/login",
    response_model=TokenPairOut,
    summary="Вход по email или телефону",
    dependencies=[limited],
    responses={401: {"model": ErrorOut, "description": "Неверный логин или пароль"}, **RATE_LIMITED},
)
async def login(payload: UserLoginIn, request: Request, response: Response, db: DBSessionDep) -> TokenPairOut:
    user = await auth_service.authenticate(db, payload.login, payload.password)
    access, refresh = await auth_service.open_session(
        db, user, request.headers.get("user-agent"), request.client.host if request.client else None
    )
    return _tokens(user, access, refresh, response)


@router.post(
    "/refresh",
    response_model=TokenPairOut,
    summary="Обновить пару токенов",
    dependencies=[limited],
    responses={401: {"model": ErrorOut, "description": "Токен невалиден или уже использован"}, **RATE_LIMITED},
)
async def refresh(payload: TokenRefreshIn, response: Response, db: DBSessionDep) -> TokenPairOut:
    """Каждый refresh одноразовый. Повторное предъявление старого закрывает сессию."""
    user, access, new_refresh = await auth_service.refresh(db, payload.refresh_token)
    return _tokens(user, access, new_refresh, response)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Выход из текущей сессии")
async def logout(request: Request, db: DBSessionDep, payload: LogoutIn | None = None) -> Response:
    """Работает и с истёкшим access. Всегда отвечает 204."""
    token = (payload.refresh_token if payload else None) or request.cookies.get("refresh_token")
    await auth_service.logout(db, token)
    out = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_cookies(out)
    return out


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT, summary="Выйти со всех устройств")
async def logout_all(user: CurrentUserDep, db: DBSessionDep) -> Response:
    await auth_service.logout_all(db, user)
    out = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_cookies(out)
    return out


@router.get("/sessions", response_model=list[SessionOut], summary="Активные сессии")
async def sessions(user: CurrentUserDep, db: DBSessionDep) -> list[SessionOut]:
    return [SessionOut.model_validate(s) for s in await auth_service.active_sessions(db, user)]


@router.get("/me", response_model=UserOut, summary="Профиль")
async def get_me(user: CurrentUserDep) -> UserOut:
    return UserOut.model_validate(user)


@router.patch(
    "/me",
    response_model=UserOut,
    summary="Обновить имя, телефон или адрес",
    responses={409: {"model": ErrorOut, "description": "Телефон занят"}},
)
async def update_me(payload: UserUpdateIn, user: CurrentUserDep, db: DBSessionDep) -> UserOut:
    return UserOut.model_validate(await auth_service.update_profile(db, user, payload))
