from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from app.api.deps import AdminUserDep, CurrentUserDep, DBSessionDep
from app.core.cache import CacheDep
from app.models import Order, OrderStatus
from app.schemas.common import ErrorOut
from app.schemas.order import AdminOrderStatusIn, OrderCreateIn, OrderOut
from app.services import orders, payments
from app.services.payment_sbp import SBPPaymentService, get_sbp_service
from app.services.telegram import TelegramService, get_telegram_service

router = APIRouter(prefix="/orders", tags=["5. Заказы и доставка"])

NOT_FOUND = {404: {"model": ErrorOut, "description": "Заказ не найден или чужой"}}


def to_out(order: Order) -> OrderOut:
    out = OrderOut.model_validate(order)
    out.payment_expires_at = orders.payment_expires_at(order)
    return out


@router.post(
    "",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать заказ и получить ссылку СБП",
    responses={
        400: {"model": ErrorOut, "description": "Такого размера у товара нет"},
        404: {"model": ErrorOut, "description": "Товар не найден или снят с продажи"},
        409: {"model": ErrorOut, "description": "Не хватает остатка"},
        502: {"model": ErrorOut, "description": "Платёжный шлюз недоступен, заказ отменён"},
    },
)
async def create_order(
    payload: OrderCreateIn,
    db: DBSessionDep,
    cache: CacheDep,
    user: CurrentUserDep,
    gateway: SBPPaymentService = Depends(get_sbp_service),
) -> OrderOut:
    """Одинаковые позиции объединяются. Остаток резервируется сразу, неоплаченный заказ отменяется
    через ORDER_PAYMENT_TTL_MINUTES. Доставка бесплатна от FREE_DELIVERY_THRESHOLD_RUB и при самовывозе."""
    return to_out(await orders.create_order(db, cache, user, payload, gateway))


@router.get("/my", response_model=list[OrderOut], summary="Мои заказы")
async def my_orders(
    user: CurrentUserDep,
    db: DBSessionDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status_filter: OrderStatus | None = Query(None, alias="status"),
) -> list[OrderOut]:
    rows = await orders.list_orders(db, user_id=user.id, status=status_filter, limit=limit, offset=offset)
    return [to_out(o) for o in rows]


@router.get("/admin/list", response_model=list[OrderOut], summary="Все заказы (админ)")
async def admin_list(
    admin: AdminUserDep,
    db: DBSessionDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status_filter: OrderStatus | None = Query(None, alias="status"),
    user_id: int | None = None,
    q: str | None = Query(None, min_length=2, description="Имя, телефон или id платежа"),
) -> list[OrderOut]:
    rows = await orders.list_orders(db, user_id=user_id, status=status_filter, q=q, limit=limit, offset=offset)
    return [to_out(o) for o in rows]


@router.get("/admin/users/{user_id}", response_model=list[OrderOut], summary="Заказы пользователя (админ)")
async def admin_user_orders(
    user_id: int,
    admin: AdminUserDep,
    db: DBSessionDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status_filter: OrderStatus | None = Query(None, alias="status"),
) -> list[OrderOut]:
    rows = await orders.list_orders(db, user_id=user_id, status=status_filter, limit=limit, offset=offset)
    return [to_out(o) for o in rows]


@router.patch(
    "/admin/{order_id}/status",
    response_model=OrderOut,
    summary="Передать в доставку или отметить врученным (админ)",
    responses={409: {"model": ErrorOut, "description": "Переход из текущего статуса невозможен"}, **NOT_FOUND},
)
async def admin_update_status(
    order_id: int,
    payload: AdminOrderStatusIn,
    background: BackgroundTasks,
    admin: AdminUserDep,
    db: DBSessionDep,
    telegram: TelegramService = Depends(get_telegram_service),
) -> OrderOut:
    """Допустимы переходы paid, shipped, completed. После completed покупатель может оставить отзыв."""
    order = await orders.advance_order_status(db, order_id, payload.status)
    background.add_task(telegram.sync_order_status, order_id, f"админ ID={admin.id}")
    return to_out(order)


@router.get("/{order_id}", response_model=OrderOut, summary="Заказ по номеру", responses=NOT_FOUND)
async def get_order(order_id: int, db: DBSessionDep, user: CurrentUserDep) -> OrderOut:
    """Доступен владельцу и администратору. Чужой заказ отвечает 404."""
    return to_out(await orders.get_accessible_order(db, order_id, user))


@router.post(
    "/{order_id}/cancel",
    response_model=OrderOut,
    summary="Отменить неоплаченный заказ",
    responses={409: {"model": ErrorOut, "description": "Заказ уже не pending"}, **NOT_FOUND},
)
async def cancel_order(order_id: int, db: DBSessionDep, cache: CacheDep, user: CurrentUserDep) -> OrderOut:
    return to_out(await orders.cancel_my_order(db, cache, user, order_id))


@router.post(
    "/{order_id}/check-payment",
    response_model=OrderOut,
    summary="Сверить оплату со шлюзом",
    responses={502: {"model": ErrorOut, "description": "Шлюз недоступен"}, **NOT_FOUND},
)
async def check_payment(
    order_id: int,
    background: BackgroundTasks,
    db: DBSessionDep,
    cache: CacheDep,
    user: CurrentUserDep,
    gateway: SBPPaymentService = Depends(get_sbp_service),
    telegram: TelegramService = Depends(get_telegram_service),
) -> OrderOut:
    """На случай потерянного вебхука. В песочнице внешнего шлюза нет, возвращается текущее состояние."""
    return to_out(await payments.check_payment(db, cache, gateway, telegram, background, user, order_id))
