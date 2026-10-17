"""
Pydantic v2 схемы для каталога товаров, категорий, истории цен и данных парсера (`app/schemas/catalog.py`).
Обеспечивают строгую валидацию входных и выходных данных API и красивую документацию в Swagger UI.
"""

import re
from datetime import datetime
from typing import Dict, List, Literal, Optional
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)


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
    Облегченная карточка товара для сеток каталога и рекомендаций.
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

    @computed_field(description="Есть ли хотя бы один размер в наличии")  # type: ignore[prop-decorator]
    @property
    def in_stock(self) -> bool:
        return any(size.stock > 0 for size in self.sizes)

    @computed_field(description="Скидка в процентах (0, если скидки нет)")  # type: ignore[prop-decorator]
    @property
    def discount_percent(self) -> int:
        if self.old_price and self.old_price > self.current_price:
            return round((self.old_price - self.current_price) * 100 / self.old_price)
        return 0

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


class FacetColorOut(BaseModel):
    """Цвет в панели фильтров: название, HEX для кружочка и сколько товаров под текущую выборку."""
    name: str
    hex: str = "#D8CFC4"
    count: int


class FacetOptionOut(BaseModel):
    """Значение фильтра (материал, размер) и количество подходящих товаров."""
    name: str
    count: int


class PriceRangeOut(BaseModel):
    min: int = 0
    max: int = 0


class CatalogFacetsOut(BaseModel):
    """
    Доступные значения фильтров ПОД ТЕКУЩУЮ ВЫБОРКУ.
    Счётчики каждой группы считаются с учётом всех остальных активных фильтров,
    но без фильтра самой группы — так фронтенд может показывать «Серый (4)»
    и не прячет выбранные значения.
    """
    colors: List[FacetColorOut] = Field(default_factory=list)
    materials: List[FacetOptionOut] = Field(default_factory=list)
    sizes: List[FacetOptionOut] = Field(default_factory=list)
    price_range: PriceRangeOut = Field(default_factory=PriceRangeOut)


class PaginatedProductsOut(BaseModel):
    """Ответ каталога (`GET /api/v1/products/catalog`) с пагинацией и фасетами фильтров."""
    total: int = Field(..., description="Общее количество найденных товаров под фильтр")
    page: int = Field(..., description="Текущая страница")
    per_page: int = Field(..., description="Количество товаров на странице")
    total_pages: int = Field(..., description="Всего страниц")
    items: List[ProductCardOut] = Field(..., description="Список карточек товаров")
    available_filters: CatalogFacetsOut = Field(
        default_factory=CatalogFacetsOut,
        description="Доступные значения фильтров с количеством товаров",
    )


class RecommendationsOut(BaseModel):
    """
    Витрина рекомендаций (`GET /api/v1/products`).
    Секции независимы: один товар может попасть в несколько (например, популярный и сезонный).
    В рекомендации попадают только товары, которые есть в наличии.
    """
    season: Literal["winter", "spring", "summer", "autumn"]
    season_label: str = Field(..., description="Название сезона на русском: «Осень»")
    popular: List[ProductCardOut] = Field(default_factory=list, description="Хиты: продажи, лайки, отзывы, рейтинг")
    seasonal: List[ProductCardOut] = Field(default_factory=list, description="Подборка под текущий сезон")
    new_arrivals: List[ProductCardOut] = Field(default_factory=list, description="Новинки")
    on_sale: List[ProductCardOut] = Field(default_factory=list, description="Товары со скидкой")


# ==============================================================================
# Создание / обновление товара администратором
# ==============================================================================
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _check_slug(value: str) -> str:
    value = value.strip().lower()
    if not _SLUG_RE.match(value):
        raise ValueError("Slug: только латиница, цифры и дефисы, например `sviter-kashemir-molochnyi`.")
    return value


def _check_hex(value: Optional[str]) -> Optional[str]:
    if value is not None and not _HEX_RE.match(value):
        raise ValueError("HEX-цвет должен быть в формате #RRGGBB, например #D8CFC4.")
    return value


def _normalize_sizes(value: Dict[str, int]) -> Dict[str, int]:
    result: Dict[str, int] = {}
    for raw_name, qty in value.items():
        name = raw_name.strip().upper()
        if not name:
            raise ValueError("Название размера не может быть пустым.")
        if name in result:
            raise ValueError(f"Размер «{name}» указан дважды.")
        if qty < 0:
            raise ValueError(f"Остаток для размера «{name}» не может быть отрицательным.")
        result[name] = qty
    return result


def _check_materials(value: List[ProductMaterialOut]) -> List[ProductMaterialOut]:
    for item in value:
        if not 0 < item.percent <= 100:
            raise ValueError(f"Процент материала «{item.material}» должен быть от 0 до 100.")
    return value


def _check_prices(current: Optional[int], old: Optional[int]) -> None:
    if current is not None and old is not None and old <= current:
        raise ValueError("Старая цена должна быть больше текущей (иначе это не скидка). Оставьте old_price пустым.")


class ProductCreateIn(BaseModel):
    """
    Создание товара. ОДИН ЦВЕТ = ОДНА КАРТОЧКА: если у модели два цвета, создаются две карточки
    с одинаковым `color_group` (у каждой свои фото, остатки и slug).
    """
    slug: str = Field(..., max_length=255)
    name: str = Field(..., min_length=2, max_length=300)
    article: Optional[str] = Field(None, max_length=64)
    brand: str = Field("Ulaanbaatar", max_length=120)
    category_id: Optional[int] = None
    color: Optional[str] = Field(None, max_length=80)
    color_hex: Optional[str] = Field(None, description="Если не указан — подставится из справочника по названию цвета")
    color_group: Optional[str] = Field(
        None,
        description="Общий ключ модели для всех её цветов. Если пусто — равен slug этой карточки",
    )
    composition: Optional[str] = Field(None, max_length=255)
    density_yarn: Optional[str] = Field(None, max_length=120)
    care_text: Optional[str] = None
    measurements: Optional[str] = None
    description: Optional[str] = None
    current_price: int = Field(..., gt=0)
    old_price: Optional[int] = Field(None, gt=0)
    image_urls: List[str] = Field(default_factory=list, max_length=20)
    sizes_stock: Dict[str, int] = Field(
        ...,
        description="Размеры и остатки, например {'S': 3, 'M': 5}. Нужен минимум один размер: без него товар нельзя купить",
    )
    materials: List[ProductMaterialOut] = Field(default_factory=list)
    sibling_slugs: List[str] = Field(
        default_factory=list,
        description="Slug других цветов этой модели (необязательно, если задан общий color_group)",
    )
    attributes: Dict[str, str] = Field(
        default_factory=dict,
        description="Доп. характеристики, например {'Сезон': 'осень-зима', 'Посадка': 'свободная'}",
    )

    @field_validator("slug")
    @classmethod
    def _v_slug(cls, v: str) -> str:
        return _check_slug(v)

    @field_validator("color_hex")
    @classmethod
    def _v_hex(cls, v: Optional[str]) -> Optional[str]:
        return _check_hex(v)

    @field_validator("sizes_stock")
    @classmethod
    def _v_sizes(cls, v: Dict[str, int]) -> Dict[str, int]:
        if not v:
            raise ValueError("Укажите хотя бы один размер (для сумок — «ONE SIZE»).")
        return _normalize_sizes(v)

    @field_validator("materials")
    @classmethod
    def _v_materials(cls, v: List[ProductMaterialOut]) -> List[ProductMaterialOut]:
        return _check_materials(v)

    @model_validator(mode="after")
    def _v_prices(self):
        _check_prices(self.current_price, self.old_price)
        return self


# Обратная совместимость со старым именем схемы
ProductCreateUpdateIn = ProductCreateIn


class ProductUpdateIn(BaseModel):
    """
    Частичное обновление товара (PATCH): меняются только переданные поля.
    `slug` менять нельзя — это адрес страницы.
    `sizes_stock` — слияние (указанные размеры обновляются/добавляются, остальные не трогаются),
    `materials`, `sibling_slugs`, `attributes` — полная замена списка.
    """
    name: Optional[str] = Field(None, min_length=2, max_length=300)
    article: Optional[str] = Field(None, max_length=64)
    brand: Optional[str] = Field(None, max_length=120)
    category_id: Optional[int] = None
    color: Optional[str] = Field(None, max_length=80)
    color_hex: Optional[str] = None
    color_group: Optional[str] = None
    composition: Optional[str] = Field(None, max_length=255)
    density_yarn: Optional[str] = Field(None, max_length=120)
    care_text: Optional[str] = None
    measurements: Optional[str] = None
    description: Optional[str] = None
    current_price: Optional[int] = Field(None, gt=0)
    old_price: Optional[int] = Field(None, gt=0)
    status: Optional[Literal["active", "draft", "archived"]] = Field(
        None, description="active — виден в магазине; draft/archived — скрыт от покупателей"
    )
    sizes_stock: Optional[Dict[str, int]] = None
    materials: Optional[List[ProductMaterialOut]] = None
    sibling_slugs: Optional[List[str]] = None
    attributes: Optional[Dict[str, str]] = None

    @field_validator("color_hex")
    @classmethod
    def _v_hex(cls, v: Optional[str]) -> Optional[str]:
        return _check_hex(v)

    @field_validator("sizes_stock")
    @classmethod
    def _v_sizes(cls, v: Optional[Dict[str, int]]) -> Optional[Dict[str, int]]:
        return None if v is None else _normalize_sizes(v)

    @field_validator("materials")
    @classmethod
    def _v_materials(cls, v: Optional[List[ProductMaterialOut]]) -> Optional[List[ProductMaterialOut]]:
        return None if v is None else _check_materials(v)


class ImageReorderIn(BaseModel):
    """Новый порядок фото: список id всех фото товара. Первое в списке — главное."""
    image_ids: List[int] = Field(..., min_length=1)


class CrawlQueueItemOut(BaseModel):
    """Элемент очереди парсера (`crawl_queue`)."""
    id: int
    source_id: int
    url: str
    status: str
    error: Optional[str] = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
