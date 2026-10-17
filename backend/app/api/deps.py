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
from typing import Annotated, Literal, Optional
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


class ProductFilterParams:
    """
    Класс-зависимость (`Depends(ProductFilterParams)`) для удобной и чистой фильтрации
    товаров в каталоге `GET /api/v1/products`.
    Собирает все query-параметры фильтрации, поиска, сортировки и пагинации в один объект.
    """

    def __init__(
        self,
        category: Optional[str] = Query(
            None,
            description="Фильтр по slug категории (например: zhenskaia-odezhda-iz-kashemira-i-pukha-iaka-i-shersti-verbliuda или kozhanye-izdeliia-iz-mongolii)",
        ),
        material: Optional[str] = Query(
            None,
            description="Фильтр по материалу (например: кашемир, пух яка, верблюжья шерсть, кожа)",
        ),
        color: Optional[str] = Query(
            None,
            description="Фильтр по цвету (например: Бежевый, Молочный, Капучино, Серый, Голубой)",
        ),
        size: Optional[str] = Query(
            None,
            description="Фильтр по наличию размера на складе (например: S, M, L, ONE SIZE)",
        ),
        min_price: Optional[int] = Query(
            None, ge=0, description="Минимальная цена в рублях"
        ),
        max_price: Optional[int] = Query(
            None, ge=0, description="Максимальная цена в рублях"
        ),
        search: Optional[str] = Query(
            None,
            description="Поисковый запрос по названию товара, артикулу или составу",
        ),
        only_in_stock: bool = Query(
            False, description="Показывать только товары в наличии на складе"
        ),
        only_liked: bool = Query(
            False,
            description="Показывать только товары из «Избранного» текущего пользователя",
        ),
        sort: Literal[
            "price_asc", "price_desc", "newest", "popular", "rating_desc"
        ] = Query(
            "popular",
            description="Сортировка: price_asc (дешевле), price_desc (дороже), newest (новинки), popular (по лайкам), rating_desc (по рейтингу)",
        ),
        page: int = Query(1, ge=1, description="Номер страницы каталога"),
        per_page: int = Query(
            12, ge=1, le=100, description="Количество товаров на одной странице"
        ),
    ) -> None:
        self.category = category
        self.material = material
        self.color = color
        self.size = size
        self.min_price = min_price
        self.max_price = max_price
        self.search = search
        self.only_in_stock = only_in_stock
        self.only_liked = only_liked
        self.sort = sort
        self.page = page
        self.per_page = per_page


# Удобные типизированные алиасы для сигнатур эндпоинтов
OptionalUserDep = Annotated[Optional[User], Depends(get_optional_user)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
AdminUserDep = Annotated[User, Depends(get_current_admin)]
ProductFilterDep = Annotated[ProductFilterParams, Depends(ProductFilterParams)]
