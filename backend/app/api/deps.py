"""
Модуль зависимостей FastAPI (`app/api/deps.py`).
Содержит переиспользуемые зависимости (`Depends` и `Annotated`), которые внедряются
в эндпоинты (ручки) для:
1. Получения асинхронной сессии базы данных (`DBSessionDep`)
2. Извлечения и проверки текущего пользователя по JWT-токену (`CurrentUserDep`)
3. Мягкой (опциональной) авторизации для гостей витрины (`OptionalUserDep`)
4. Проверки прав администратора магазина (`AdminUserDep`)
5. Валидации параметров пагинации и фильтрации каталога (`ProductFilterParams`)
"""

from datetime import datetime, timezone
from typing import Annotated, List, Literal, Optional
from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import decode_token
from app.db.session import get_db
from app.models.session import UserSession
from app.models.user import User

logger = get_logger(__name__)

# Схема авторизации через заголовок Authorization: Bearer <token>
# auto_error=False позволяет делать ручки, доступные одновременно и гостям, и авторизованным клиентам
bearer_scheme = HTTPBearer(auto_error=False)

# Типизированный алиас зависимости сессии БД
DBSessionDep = Annotated[AsyncSession, Depends(get_db)]


async def get_optional_user(
    request: Request,
    db: DBSessionDep,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[User]:
    """
    Опциональная зависимость авторизации.
    Токен берётся из заголовка `Authorization: Bearer ...`, а если его нет —
    из httpOnly-cookie `access_token` (её ставят /login и /register).
    Дополнительно проверяется, что сессия не отозвана (выход аннулирует её).
    """
    token = credentials.credentials if credentials and credentials.credentials else None
    if not token:
        token = request.cookies.get("access_token")
    if not token:
        logger.debug("Токен не передан: нет ни заголовка Authorization, ни cookie access_token")
        return None

    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return None

    user_id_str = payload.get("sub")
    if not user_id_str or not str(user_id_str).isdigit():
        return None

    # Сессия должна существовать и быть не отозванной
    sid = payload.get("sid")
    if not sid:
        return None
    session_ok = await db.execute(
        select(UserSession.id).where(
            UserSession.jti == sid,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > datetime.now(timezone.utc),
        )
    )
    if session_ok.scalar_one_or_none() is None:
        logger.info(f"Сессия {sid} завершена или не найдена")
        return None

    user = await db.get(User, int(user_id_str))
    if not user or not user.is_active:
        return None

    return user


async def get_current_user(
    user: Optional[User] = Depends(get_optional_user),
) -> User:
    """
    Строгая зависимость авторизации (`Depends(get_current_user)`).
    Требует валидный JWT Access-токен. Если пользователь не авторизован —
    выбрасывает HTTP 401 Unauthorized.
    """
    if not user:
        logger.warning("Попытка доступа к защищенной ручке без валидного JWT-токена")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация. Передайте заголовок Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Зависимость проверки прав администратора (`Depends(get_current_admin)`).
    Разрешает доступ только пользователям с ролью `admin`.
    """
    if not current_user.is_admin:
        logger.warning(
            f"Отказ в доступе к админ-ручке для пользователя ID={current_user.id} (role={current_user.role})"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав. Требуется роль администратора магазина.",
        )
    return current_user


def _split_values(values: Optional[List[str]]) -> List[str]:
    """
    Приводит параметр фильтра к списку значений. Поддерживает оба стиля:
    `?color=Серый&color=Бежевый` и `?color=Серый,Бежевый`.
    """
    result: List[str] = []
    for raw in values or []:
        for part in raw.split(","):
            part = part.strip()
            if part and part.lower() not in {r.lower() for r in result}:
                result.append(part)
    return result


class ProductFilterParams:
    """
    Класс-зависимость (`Depends(ProductFilterParams)`) для `GET /api/v1/products/catalog`.
    Все фильтры из одной группы работают как ИЛИ (серый ИЛИ бежевый),
    разные группы объединяются через И (серый И кашемир И размер M).
    """

    def __init__(
        self,
        category: Optional[List[str]] = Query(
            None,
            description="Slug категории (можно несколько). Включает все вложенные подкатегории",
        ),
        material: Optional[List[str]] = Query(
            None, description="Материал (можно несколько): кашемир, пух яка, верблюжья шерсть, кожа"
        ),
        color: Optional[List[str]] = Query(
            None, description="Цвет (можно несколько): Бежевый, Молочный, Серый..."
        ),
        size: Optional[List[str]] = Query(
            None, description="Размер в наличии (можно несколько): S, M, L, ONE SIZE"
        ),
        min_price: Optional[int] = Query(None, ge=0, description="Минимальная цена, ₽"),
        max_price: Optional[int] = Query(None, ge=0, description="Максимальная цена, ₽"),
        search: Optional[str] = Query(
            None,
            max_length=100,
            description="Поиск по названию, артикулу, составу и цвету. Несколько слов — все должны встретиться",
        ),
        only_in_stock: bool = Query(False, description="Только товары, которые есть в наличии"),
        on_sale: bool = Query(False, description="Только товары со скидкой"),
        only_liked: bool = Query(False, description="Только избранное текущего пользователя (нужна авторизация)"),
        sort: Literal[
            "popular", "newest", "price_asc", "price_desc", "rating_desc", "discount"
        ] = Query(
            "popular",
            description=(
                "popular — хиты (продажи, лайки, отзывы), newest — новинки, price_asc/price_desc — по цене, "
                "rating_desc — по рейтингу (с поправкой на число отзывов), discount — по размеру скидки"
            ),
        ),
        page: int = Query(1, ge=1, description="Номер страницы"),
        per_page: int = Query(12, ge=1, le=100, description="Товаров на странице"),
    ) -> None:
        if min_price is not None and max_price is not None and min_price > max_price:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="min_price не может быть больше max_price.",
            )
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


# Удобные типизированные алиасы для сигнатур эндпоинтов
OptionalUserDep = Annotated[Optional[User], Depends(get_optional_user)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
AdminUserDep = Annotated[User, Depends(get_current_admin)]
ProductFilterDep = Annotated[ProductFilterParams, Depends(ProductFilterParams)]
