"""
Роутер регистрации, авторизации (JWT) и управления профилем (`app/api/v1/auth.py`).
Каждая ручка снабжена подробными комментариями на русском языке и структурным логированием.
"""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import or_, select

from app.api.deps import CurrentUserDep, DBSessionDep
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.models.user import User
from app.schemas.user import (
    TokenPairOut,
    TokenRefreshIn,
    UserLoginIn,
    UserOut,
    UserRegisterIn,
    UserUpdateIn,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["1. Авторизация и Профиль"])


# ==============================================================================
# РУЧКА 1: Регистрация нового покупателя
# ==============================================================================
@router.post(
    "/register",
    response_model=TokenPairOut,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация нового пользователя",
)
async def register_user(
    payload: UserRegisterIn,
    db: DBSessionDep,
) -> TokenPairOut:
    """
    Регистрирует нового покупателя в магазине монгольского кашемира:
    1. Проверяет уникальность `email` и `phone` в базе данных.
    2. Безопасно хеширует пароль с помощью `bcrypt`.
    3. Создает запись в таблице `users` и сразу возвращает пару JWT-токенов (`access` + `refresh`),
       чтобы пользователь автоматически вошел в аккаунт после регистрации.
    """
    logger.info(f"Запрос на регистрацию нового пользователя: email={payload.email}")

    # Проверяем, не занят ли email или телефон
    conditions = [User.email == payload.email.lower()]
    if payload.phone:
        conditions.append(User.phone == payload.phone)

    existing_q = await db.execute(select(User).where(or_(*conditions)))
    existing_user = existing_q.scalar_one_or_none()
    if existing_user:
        logger.warning(f"Отказ в регистрации: пользователь {payload.email} уже существует")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Пользователь с таким email или телефоном уже зарегистрирован.",
        )

    # Создаем нового пользователя
    new_user = User(
        email=payload.email.lower(),
        phone=payload.phone,
        full_name=payload.full_name,
        hashed_password=get_password_hash(payload.password),
        default_city=payload.default_city,
        role="customer",
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    logger.info(f"Успешно зарегистрирован новый пользователь ID={new_user.id} ({new_user.email})")

    # Генерируем JWT-токены
    access_token = create_access_token(
        subject=new_user.id, extra_claims={"role": new_user.role}
    )
    refresh_token = create_refresh_token(subject=new_user.id)

    return TokenPairOut(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserOut.model_validate(new_user),
    )


# ==============================================================================
# РУЧКА 2: Вход в аккаунт (Логин по email и паролю)
# ==============================================================================
@router.post(
    "/login",
    response_model=TokenPairOut,
    summary="Вход в аккаунт и получение JWT-токенов",
)
async def login_user(
    payload: UserLoginIn,
    db: DBSessionDep,
) -> TokenPairOut:
    """
    Аутентифицирует пользователя по `email` и `password`:
    - Проверяет существование учетной записи и корректность пароля.
    - Возвращает свежую пару `access_token` и `refresh_token` вместе с данными профиля.
    """
    logger.info(f"Попытка входа в аккаунт: email={payload.email}")

    result = await db.execute(
        select(User).where(User.email == payload.email.lower())
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password):
        logger.warning(f"Неудачная попытка входа для email={payload.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль.",
        )

    if not user.is_active:
        logger.warning(f"Попытка входа заблокированного пользователя ID={user.id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ваша учетная запись деактивирована.",
        )

    access_token = create_access_token(
        subject=user.id, extra_claims={"role": user.role}
    )
    refresh_token = create_refresh_token(subject=user.id)
    logger.info(f"Пользователь ID={user.id} ({user.email}) успешно вошел в систему")

    return TokenPairOut(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserOut.model_validate(user),
    )


# ==============================================================================
# РУЧКА 3: Обновление Access-токена по Refresh-токену
# ==============================================================================
@router.post(
    "/refresh",
    response_model=TokenPairOut,
    summary="Обновление пары JWT-токенов по refresh_token",
)
async def refresh_access_token(
    payload: TokenRefreshIn,
    db: DBSessionDep,
) -> TokenPairOut:
    """
    Принимает действующий `refresh_token` и выдает новую пару `access_token` + `refresh_token`
    без необходимости повторного ввода пароля на фронтенде.
    """
    decoded = decode_token(payload.refresh_token)
    if not decoded or decoded.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный или просроченный refresh-токен.",
        )

    user_id = int(decoded["sub"])
    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден или неактивен.",
        )

    logger.debug(f"Обновление JWT-токенов для пользователя ID={user.id}")
    return TokenPairOut(
        access_token=create_access_token(subject=user.id, extra_claims={"role": user.role}),
        refresh_token=create_refresh_token(subject=user.id),
        user=UserOut.model_validate(user),
    )


# ==============================================================================
# РУЧКА 4: Получение профиля текущего пользователя
# ==============================================================================
@router.get(
    "/me",
    response_model=UserOut,
    summary="Получить профиль текущего авторизованного пользователя",
)
async def get_my_profile(
    current_user: CurrentUserDep,
) -> UserOut:
    """
    Возвращает данные профиля текущего пользователя, извлеченного через зависимость `Depends(get_current_user)`.
    """
    logger.debug(f"Запрос профиля пользователя ID={current_user.id}")
    return UserOut.model_validate(current_user)


# ==============================================================================
# РУЧКА 5: Редактирование профиля и адреса доставки по умолчанию
# ==============================================================================
@router.patch(
    "/me",
    response_model=UserOut,
    summary="Обновить имя, телефон или адрес доставки ПВЗ по умолчанию",
)
async def update_my_profile(
    payload: UserUpdateIn,
    current_user: CurrentUserDep,
    db: DBSessionDep,
) -> UserOut:
    """
    Позволяет покупателю обновить свои контактные данные и сохранить любимый ПВЗ СДЭК,
    чтобы при следующем оформлении заказа поля заполнялись автоматически.
    """
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(current_user, field, value)

    await db.commit()
    await db.refresh(current_user)
    logger.info(f"Профиль пользователя ID={current_user.id} успешно обновлен: {list(update_data.keys())}")
    return UserOut.model_validate(current_user)
