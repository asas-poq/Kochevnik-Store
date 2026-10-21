from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, UnauthorizedError, UnprocessableError
from app.core.security import decode_token
from app.db.session import get_db
from app.models import User, UserSession

bearer_scheme = HTTPBearer(auto_error=False)

DBSessionDep = Annotated[AsyncSession, Depends(get_db)]


async def get_optional_user(
    request: Request,
    db: DBSessionDep,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> User | None:
    """Токен из заголовка Authorization, а если его нет, из cookie access_token."""
    token = credentials.credentials if credentials else request.cookies.get("access_token")
    payload = decode_token(token) if token else None
    if not payload or payload.get("type") != "access":
        return None
    user_id, sid = payload.get("sub"), payload.get("sid")
    if not sid or not str(user_id).isdigit():
        return None

    alive = await db.execute(
        select(UserSession.id).where(
            UserSession.jti == sid,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > datetime.now(timezone.utc),
        )
    )
    if alive.scalar_one_or_none() is None:
        return None
    user = await db.get(User, int(user_id))
    return user if user and user.is_active else None


async def get_current_user(user: Annotated[User | None, Depends(get_optional_user)]) -> User:
    if not user:
        raise UnauthorizedError("Требуется авторизация. Передайте заголовок Authorization: Bearer <token>")
    return user


async def get_current_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not user.is_admin:
        raise ForbiddenError("Недостаточно прав. Нужна роль администратора.")
    return user


OptionalUserDep = Annotated[User | None, Depends(get_optional_user)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
AdminUserDep = Annotated[User, Depends(get_current_admin)]


def _split_values(values: list[str] | None) -> list[str]:
    """Принимает color=A&color=B и color=A,B. Дубли без учёта регистра убирает."""
    result: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        for part in raw.split(","):
            part = part.strip()
            if part and part.lower() not in seen:
                seen.add(part.lower())
                result.append(part)
    return result


class ProductFilterParams:
    """Значения внутри одного фильтра работают как ИЛИ, разные фильтры как И."""

    def __init__(
        self,
        category: list[str] | None = Query(None, description="Slug категории, включая вложенные"),
        material: list[str] | None = Query(None, description="Кашемир, пух яка, верблюжья шерсть, кожа"),
        color: list[str] | None = Query(None),
        size: list[str] | None = Query(None, description="Только размеры с остатком"),
        min_price: int | None = Query(None, ge=0),
        max_price: int | None = Query(None, ge=0),
        search: str | None = Query(None, max_length=100, description="Все слова должны встретиться"),
        only_in_stock: bool = Query(False),
        on_sale: bool = Query(False),
        only_liked: bool = Query(False, description="Нужна авторизация"),
        sort: Literal["popular", "newest", "price_asc", "price_desc", "rating_desc", "discount"] = Query(
            "popular"
        ),
        page: int = Query(1, ge=1),
        per_page: int = Query(12, ge=1, le=100),
    ) -> None:
        if min_price is not None and max_price is not None and min_price > max_price:
            raise UnprocessableError("min_price не может быть больше max_price.")
        self.category = _split_values(category)
        self.material = _split_values(material)
        self.color = _split_values(color)
        self.size = _split_values(size)
        self.min_price = min_price
        self.max_price = max_price
        self.search = (search or "").strip() or None
        self.only_in_stock = only_in_stock
        self.on_sale = on_sale
        self.only_liked = only_liked
        self.sort = sort
        self.page = page
        self.per_page = per_page


ProductFilterDep = Annotated[ProductFilterParams, Depends(ProductFilterParams)]
