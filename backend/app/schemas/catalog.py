"""
Pydantic v2 схемы для каталога товаров, категорий, истории цен и данных парсера (`app/schemas/catalog.py`).
Обеспечивают строгую валидацию входных и выходных данных API и красивую документацию в Swagger UI.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


# ==============================================================================
# 1. Схемы Категорий (`categories`)
# ==============================================================================
class CategoryBase(BaseModel):
    """Базовые поля категории товара."""
    slug: str = Field(..., description="Уникальный ЧПУ-идентификатор категории (slug)")
    name: str = Field(..., description="Название категории на русском языке")
    url: Optional[str] = Field(None, description="Оригинальный URL категории из парсера")
    parent_id: Optional[int] = Field(None, description="ID родительской категории (если есть)")


class CategoryOut(CategoryBase):
    """Схема ответа API для одной категории."""
    id: int
    source_id: int = 1

    model_config = ConfigDict(from_attributes=True)


class CategoryTreeOut(CategoryOut):
    """Древовидная схема категории со списком дочерних подкатегорий и количеством товаров."""
    products_count: int = Field(0, description="Количество активных товаров в категории")
    children: List["CategoryTreeOut"] = Field(
        default_factory=list, description="Вложенные подкатегории"
    )

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# 2. Дочерние элементы карточки товара (фото, материалы, размеры, цвета, история цен)
# ==============================================================================
class ProductImageOut(BaseModel):
    """Схема фотографии товара."""
    id: int
    position: int = Field(0, description="Порядковый номер фото в галерее (0 — главное фото)")
    url: str = Field(..., description="Прямая ссылка на фото в S3 или CDN")

    model_config = ConfigDict(from_attributes=True)


class ProductMaterialOut(BaseModel):
    """Схема материала состава изделия."""
    material: str = Field(..., description="Название волокна/материала (кашемир, пух яка, кожа)")
    percent: float = Field(100.0, description="Процентное содержание в составе (0..100)")

    model_config = ConfigDict(from_attributes=True)


class ProductSizeOut(BaseModel):
    """Схема доступного размера и складского остатка (`variant`)."""
    id: int = Field(..., description="ID варианта размера (`variant_id` для добавления в корзину)")
    size: str = Field(..., description="Размер изделия (S, M, L, XL, ONE SIZE)")
    stock: int = Field(..., description="Доступный остаток на складе (шт.)")
    sku: Optional[str] = Field(None, description="Артикул конкретного размера (SKU)")
    measurements_cm: Optional[str] = Field(
        None, description="Обмеры изделия в данном размере (в см)"
    )

    model_config = ConfigDict(from_attributes=True)


class ProductAttributeOut(BaseModel):
    """Дополнительная характеристика товара (Плотность/нить, Посадка, Сезон)."""
    attr_key: str
    attr_value: str

    model_config = ConfigDict(from_attributes=True)


class PriceHistoryOut(BaseModel):
    """Запись из истории изменения цены товара (`price_history`)."""
    id: int
    price: int = Field(..., description="Актуальная цена в рублях")
    old_price: Optional[int] = Field(None, description="Старая цена до скидки в рублях")
    currency: str = "RUB"
    scraped_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SiblingColorVariantOut(BaseModel):
    """
    Информация о соседнем цвете этой же модели товара (из таблицы `product_color_links`).
    Используется на фронтенде для отрисовки кружочков переключения цвета.
    """
    sibling_slug: str = Field(..., description="Slug карточки товара в другом цвете")
    color: Optional[str] = Field(None, description="Название цвета (например: Капучино, Молочный)")
    color_hex: Optional[str] = Field("#D8CFC4", description="HEX-код кружочка цвета для UI")
    in_catalog: bool = Field(
        False,
        description="True, если этот цвет уже спарсен и активен в БД; False, если еще в очереди crawl_queue",
    )
    preview_image: Optional[str] = Field(None, description="Главное фото соседнего цвета")
    price: Optional[int] = Field(None, description="Цена товара в этом цвете")


# ==============================================================================
# 3. Схемы Товара для Каталога (краткая) и Детальной карточки (полная)
# ==============================================================================
class ProductCardOut(BaseModel):
    """
    Облегченная карточка товара для сетки каталога (`GET /api/v1/products`).
    Отдает ровно те данные, которые нужны для рендера превью-карточки в каталоге.
    """
    id: int
    slug: str
    article: Optional[str] = None
    name: str
    brand: Optional[str] = "Ulaanbaatar"
    category_id: Optional[int] = None
    color: Optional[str] = None
    color_hex: Optional[str] = "#D8CFC4"
    composition: Optional[str] = None
    current_price: int
    old_price: Optional[int] = None
    currency: str = "RUB"
    likes_count: int = 0
    reviews_count: int = 0
    rating_avg: float = 0.0
    is_liked_by_me: bool = Field(
        False, description="Поставил ли текущий авторизованный пользователь лайк этому товару"
    )
    images: List[ProductImageOut] = Field(default_factory=list)
    sizes: List[ProductSizeOut] = Field(default_factory=list)
    materials: List[ProductMaterialOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ProductDetailOut(ProductCardOut):
    """
    Полная детальная схема карточки товара (`GET /api/v1/products/{slug}`).
    Включает уход, обмеры, плотность нити, соседние цвета (`color_variants`),
    историю цен и дополнительные атрибуты.
    """
    url: Optional[str] = None
    color_group: Optional[str] = None
    density_yarn: Optional[str] = None
    care_text: Optional[str] = None
    measurements: Optional[str] = None
    description: Optional[str] = None
    status: str = "active"
    first_seen: datetime
    last_seen: datetime
    category: Optional[CategoryOut] = None
    attributes: List[ProductAttributeOut] = Field(default_factory=list)
    color_variants: List[SiblingColorVariantOut] = Field(
        default_factory=list,
        description="Список всех доступных цветов данной модели для переключения в UI",
    )
    price_history: List[PriceHistoryOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class PaginatedProductsOut(BaseModel):
    """Ответ каталога с пагинацией и метаданными доступных фильтров."""
    total: int = Field(..., description="Общее количество найденных товаров под фильтр")
    page: int = Field(..., description="Текущая страница")
    per_page: int = Field(..., description="Количество товаров на странице")
    total_pages: int = Field(..., description="Всего страниц")
    items: List[ProductCardOut] = Field(..., description="Список карточек товаров")
    available_filters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Доступные значения фильтров (цвета, материалы, диапазон цен, размеры)",
    )


class ProductCreateUpdateIn(BaseModel):
    """Схема для создания или обновления товара администратором через API."""
    slug: str
    name: str
    article: Optional[str] = None
    brand: str = "Ulaanbaatar"
    category_id: Optional[int] = None
    color: Optional[str] = None
    color_hex: Optional[str] = "#D8CFC4"
    color_group: Optional[str] = None
    composition: Optional[str] = "100% кашемир"
    density_yarn: Optional[str] = "2-ply (26/2 Nm)"
    care_text: Optional[str] = (
        "Ручная стирка при температуре до 30°C специальными средствами для кашемира. "
        "Сушить в расправленном виде на горизонтальной поверхности."
    )
    measurements: Optional[str] = None
    description: Optional[str] = None
    current_price: int = Field(..., gt=0)
    old_price: Optional[int] = None
    image_urls: List[str] = Field(default_factory=list)
    sizes_stock: Dict[str, int] = Field(
        default_factory=lambda: {"S": 3, "M": 5, "L": 4},
        description="Словарь размеров и остатков на складе, например {'S': 3, 'M': 5, 'L': 2}",
    )
    materials: List[ProductMaterialOut] = Field(default_factory=list)
    sibling_slugs: List[str] = Field(default_factory=list)


class CrawlQueueItemOut(BaseModel):
    """Элемент очереди парсера (`crawl_queue`)."""
    id: int
    source_id: int
    url: str
    status: str
    error: Optional[str] = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
