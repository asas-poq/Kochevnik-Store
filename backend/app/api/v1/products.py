from typing import Literal

from fastapi import APIRouter, Depends, File, Query, UploadFile, status

from app.api.deps import AdminUserDep, DBSessionDep, OptionalUserDep, ProductFilterDep
from app.core.cache import CacheDep
from app.schemas.catalog import (
    ImageReorderIn,
    PaginatedProductsOut,
    ProductCreateIn,
    ProductDetailOut,
    ProductImageOut,
    ProductUpdateIn,
    RecommendationsOut,
)
from app.schemas.common import ErrorOut
from app.services import catalog, products
from app.services.s3 import S3StorageService, get_s3_service

router = APIRouter(prefix="/products", tags=["3. Каталог и карточка товара"])

ADMIN_ERRORS = {
    401: {"model": ErrorOut, "description": "Нет токена"},
    403: {"model": ErrorOut, "description": "Нужна роль admin"},
    404: {"model": ErrorOut, "description": "Товар не найден"},
}


@router.get("", response_model=RecommendationsOut, summary="Рекомендации для главной")
async def recommendations(
    db: DBSessionDep,
    cache: CacheDep,
    user: OptionalUserDep,
    limit: int = Query(8, ge=1, le=24, description="Товаров в каждой секции"),
    category: str | None = Query(None, description="Slug категории, включая вложенные"),
    season: Literal["winter", "spring", "summer", "autumn"] | None = Query(
        None, description="По умолчанию определяется по месяцу"
    ),
) -> RecommendationsOut:
    """Секции popular, seasonal, new_arrivals и on_sale. Только активные товары в наличии.
    Ответ кэшируется на минуту, личный флаг is_liked_by_me дописывается поверх."""
    return await catalog.recommendations(db, cache, user, limit=limit, category=category, season=season)


@router.get(
    "/catalog",
    response_model=PaginatedProductsOut,
    summary="Каталог с фильтрами, поиском и сортировкой",
    responses={401: {"model": ErrorOut, "description": "only_liked без авторизации"}},
)
async def list_catalog(filters: ProductFilterDep, db: DBSessionDep, cache: CacheDep, user: OptionalUserDep) -> PaginatedProductsOut:
    """Значения внутри одного фильтра работают как ИЛИ, разные фильтры как И. size и only_in_stock
    учитывают только размеры с остатком. В available_filters счётчики посчитаны под текущую выборку."""
    return await catalog.list_catalog(db, cache, filters, user)


@router.get(
    "/{slug}",
    response_model=ProductDetailOut,
    summary="Карточка товара",
    responses={404: {"model": ErrorOut, "description": "Товар не найден или скрыт"}},
)
async def get_product(slug: str, db: DBSessionDep, user: OptionalUserDep) -> ProductDetailOut:
    """Черновики и архив отдаются только администратору."""
    return await catalog.get_product_detail(db, slug=slug, viewer=user)


@router.post(
    "",
    response_model=ProductDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать товар (админ)",
    responses={409: {"model": ErrorOut, "description": "Такой slug уже есть"}, **ADMIN_ERRORS},
)
async def create_product(payload: ProductCreateIn, db: DBSessionDep, cache: CacheDep, admin: AdminUserDep) -> ProductDetailOut:
    return await products.create_product(db, cache, admin, payload)


@router.patch(
    "/{product_id}",
    response_model=ProductDetailOut,
    summary="Изменить товар (админ)",
    responses=ADMIN_ERRORS,
)
async def update_product(
    product_id: int, payload: ProductUpdateIn, db: DBSessionDep, cache: CacheDep, admin: AdminUserDep
) -> ProductDetailOut:
    """Меняются только переданные поля. Смена цены пишет запись в историю.
    sizes_stock сливается, размер с остатком 0 остаётся, на него могут ссылаться заказы.
    materials, sibling_slugs и attributes заменяются целиком."""
    return await products.update_product(db, cache, admin, product_id, payload)


@router.post(
    "/{product_id}/images",
    response_model=list[ProductImageOut],
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить фото (админ)",
    responses={413: {"model": ErrorOut, "description": "Файл слишком большой"},
               415: {"model": ErrorOut, "description": "Не JPEG, PNG или WebP"}, **ADMIN_ERRORS},
)
async def upload_images(
    product_id: int,
    db: DBSessionDep,
    cache: CacheDep,
    admin: AdminUserDep,
    file: UploadFile | None = File(None, description="Одно фото, удобно проверять в Swagger"),
    files: list[UploadFile] | None = File(None, description="Несколько фото, поле повторяется"),
    s3: S3StorageService = Depends(get_s3_service),
) -> list[ProductImageOut]:
    """Фото добавляются в конец галереи. Если хоть один файл не прошёл проверку, не сохраняется ни один."""
    uploads = ([file] if file else []) + list(files or [])
    created = await products.add_images(db, cache, s3, admin, product_id, uploads)
    return [ProductImageOut.model_validate(i) for i in created]


@router.put(
    "/{product_id}/images/order",
    response_model=list[ProductImageOut],
    summary="Порядок фото (админ)",
    responses=ADMIN_ERRORS,
)
async def reorder_images(
    product_id: int, payload: ImageReorderIn, db: DBSessionDep, cache: CacheDep, admin: AdminUserDep
) -> list[ProductImageOut]:
    """Нужны id всех фото товара. Первое в списке становится главным."""
    images = await products.reorder_images(db, cache, product_id, payload)
    return [ProductImageOut.model_validate(i) for i in images]


@router.delete(
    "/{product_id}/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить фото (админ)",
    responses=ADMIN_ERRORS,
)
async def delete_image(product_id: int, image_id: int, db: DBSessionDep, cache: CacheDep, admin: AdminUserDep) -> None:
    await products.delete_image(db, cache, product_id, image_id)
