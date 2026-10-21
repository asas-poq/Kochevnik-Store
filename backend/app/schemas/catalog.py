import re
from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    computed_field,
    field_validator,
    model_validator,
)


class CategoryOut(BaseModel):
    id: int
    source_id: int = 1
    slug: str
    name: str
    url: str | None = None
    parent_id: int | None = None

    model_config = ConfigDict(from_attributes=True)


class CategoryTreeOut(CategoryOut):
    products_count: int = Field(0, description="Активные товары, у родителя вместе с вложенными")
    children: list["CategoryTreeOut"] = Field(default_factory=list)


class CategoryTreeList(RootModel[list[CategoryTreeOut]]):
    pass


class ProductImageOut(BaseModel):
    id: int
    position: int = Field(0, description="0 это главное фото")
    url: str

    model_config = ConfigDict(from_attributes=True)


class ProductMaterialOut(BaseModel):
    material: str
    percent: float = 100.0

    model_config = ConfigDict(from_attributes=True)


class ProductSizeOut(BaseModel):
    id: int = Field(description="Это variant_id для заказа")
    size: str
    stock: int
    sku: str | None = None
    measurements_cm: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ProductAttributeOut(BaseModel):
    attr_key: str
    attr_value: str

    model_config = ConfigDict(from_attributes=True)


class PriceHistoryOut(BaseModel):
    id: int
    price: int
    old_price: int | None = None
    currency: str = "RUB"
    scraped_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SiblingColorVariantOut(BaseModel):
    sibling_slug: str
    color: str | None = None
    color_hex: str | None = "#D8CFC4"
    in_catalog: bool = False
    preview_image: str | None = None
    price: int | None = None


class ProductCardOut(BaseModel):
    id: int
    slug: str
    article: str | None = None
    name: str
    brand: str | None = "Ulaanbaatar"
    category_id: int | None = None
    color: str | None = None
    color_hex: str | None = "#D8CFC4"
    composition: str | None = None
    current_price: int
    old_price: int | None = None
    currency: str = "RUB"
    likes_count: int = 0
    reviews_count: int = 0
    rating_avg: float = 0.0
    is_liked_by_me: bool = False
    images: list[ProductImageOut] = Field(default_factory=list)
    sizes: list[ProductSizeOut] = Field(default_factory=list)
    materials: list[ProductMaterialOut] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def in_stock(self) -> bool:
        return any(size.stock > 0 for size in self.sizes)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def discount_percent(self) -> int:
        if self.old_price and self.old_price > self.current_price:
            return round((self.old_price - self.current_price) * 100 / self.old_price)
        return 0

    model_config = ConfigDict(from_attributes=True)


class ProductDetailOut(ProductCardOut):
    url: str | None = None
    color_group: str | None = None
    density_yarn: str | None = None
    care_text: str | None = None
    measurements: str | None = None
    description: str | None = None
    status: str = "active"
    first_seen: datetime
    last_seen: datetime
    category: CategoryOut | None = None
    attributes: list[ProductAttributeOut] = Field(default_factory=list)
    color_variants: list[SiblingColorVariantOut] = Field(
        default_factory=list, description="Все цвета модели, текущий первым"
    )
    price_history: list[PriceHistoryOut] = Field(default_factory=list, description="Последние 30 записей")


class FacetColorOut(BaseModel):
    name: str
    hex: str = "#D8CFC4"
    count: int


class FacetOptionOut(BaseModel):
    name: str
    count: int


class PriceRangeOut(BaseModel):
    min: int = 0
    max: int = 0


class CatalogFacetsOut(BaseModel):
    """Счётчики группы считаются без фильтра этой же группы, чтобы выбранное значение не пропадало."""

    colors: list[FacetColorOut] = Field(default_factory=list)
    materials: list[FacetOptionOut] = Field(default_factory=list)
    sizes: list[FacetOptionOut] = Field(default_factory=list)
    price_range: PriceRangeOut = Field(default_factory=PriceRangeOut)


class PaginatedProductsOut(BaseModel):
    total: int
    page: int
    per_page: int
    total_pages: int
    items: list[ProductCardOut]
    available_filters: CatalogFacetsOut = Field(default_factory=CatalogFacetsOut)


class RecommendationsOut(BaseModel):
    season: Literal["winter", "spring", "summer", "autumn"]
    season_label: str
    popular: list[ProductCardOut] = Field(default_factory=list)
    seasonal: list[ProductCardOut] = Field(default_factory=list)
    new_arrivals: list[ProductCardOut] = Field(default_factory=list)
    on_sale: list[ProductCardOut] = Field(default_factory=list)


_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _check_hex(value: str | None) -> str | None:
    if value is not None and not _HEX_RE.match(value):
        raise ValueError("HEX-цвет должен быть в формате #RRGGBB.")
    return value


def _normalize_sizes(value: dict[str, int]) -> dict[str, int]:
    result: dict[str, int] = {}
    for raw_name, qty in value.items():
        name = raw_name.strip().upper()
        if not name:
            raise ValueError("Название размера не может быть пустым.")
        if name in result:
            raise ValueError(f"Размер «{name}» указан дважды.")
        if qty < 0:
            raise ValueError(f"Остаток размера «{name}» не может быть отрицательным.")
        result[name] = qty
    return result


def _check_materials(value: list[ProductMaterialOut]) -> list[ProductMaterialOut]:
    for item in value:
        if not 0 < item.percent <= 100:
            raise ValueError(f"Процент материала «{item.material}» должен быть от 0 до 100.")
    return value


class ProductCreateIn(BaseModel):
    """Один цвет это одна карточка. Модель в двух цветах это две карточки с общим color_group."""

    slug: str = Field(max_length=255)
    name: str = Field(min_length=2, max_length=300)
    article: str | None = Field(None, max_length=64)
    brand: str = Field("Ulaanbaatar", max_length=120)
    category_id: int | None = None
    color: str | None = Field(None, max_length=80)
    color_hex: str | None = Field(None, description="По умолчанию берётся из справочника по названию цвета")
    color_group: str | None = Field(None, description="По умолчанию равен slug")
    composition: str | None = Field(None, max_length=255)
    density_yarn: str | None = Field(None, max_length=120)
    care_text: str | None = None
    measurements: str | None = None
    description: str | None = None
    current_price: int = Field(gt=0)
    old_price: int | None = Field(None, gt=0, description="Должна быть больше current_price")
    image_urls: list[str] = Field(default_factory=list, max_length=20)
    sizes_stock: dict[str, int] = Field(description="Например {'S': 3, 'M': 5}. Нужен минимум один размер")
    materials: list[ProductMaterialOut] = Field(default_factory=list)
    sibling_slugs: list[str] = Field(default_factory=list)
    attributes: dict[str, str] = Field(default_factory=dict, description="Например {'Сезон': 'осень-зима'}")

    @field_validator("slug")
    @classmethod
    def _v_slug(cls, v: str) -> str:
        v = v.strip().lower()
        if not _SLUG_RE.match(v):
            raise ValueError("Slug: латиница, цифры и дефисы, например sviter-kashemir-molochnyi.")
        return v

    @field_validator("color_hex")
    @classmethod
    def _v_hex(cls, v: str | None) -> str | None:
        return _check_hex(v)

    @field_validator("sizes_stock")
    @classmethod
    def _v_sizes(cls, v: dict[str, int]) -> dict[str, int]:
        if not v:
            raise ValueError("Укажите хотя бы один размер, для сумок ONE SIZE.")
        return _normalize_sizes(v)

    @field_validator("materials")
    @classmethod
    def _v_materials(cls, v: list[ProductMaterialOut]) -> list[ProductMaterialOut]:
        return _check_materials(v)

    @model_validator(mode="after")
    def _v_prices(self) -> "ProductCreateIn":
        if self.old_price is not None and self.old_price <= self.current_price:
            raise ValueError("Старая цена должна быть больше текущей. Для товара без скидки оставьте null.")
        return self


class ProductUpdateIn(BaseModel):
    """Меняются только переданные поля. sizes_stock сливается, остальные коллекции заменяются целиком."""

    name: str | None = Field(None, min_length=2, max_length=300)
    article: str | None = Field(None, max_length=64)
    brand: str | None = Field(None, max_length=120)
    category_id: int | None = None
    color: str | None = Field(None, max_length=80)
    color_hex: str | None = None
    color_group: str | None = None
    composition: str | None = Field(None, max_length=255)
    density_yarn: str | None = Field(None, max_length=120)
    care_text: str | None = None
    measurements: str | None = None
    description: str | None = None
    current_price: int | None = Field(None, gt=0)
    old_price: int | None = Field(None, gt=0)
    status: Literal["active", "draft", "archived"] | None = None
    sizes_stock: dict[str, int] | None = None
    materials: list[ProductMaterialOut] | None = None
    sibling_slugs: list[str] | None = None
    attributes: dict[str, str] | None = None

    @field_validator("color_hex")
    @classmethod
    def _v_hex(cls, v: str | None) -> str | None:
        return _check_hex(v)

    @field_validator("sizes_stock")
    @classmethod
    def _v_sizes(cls, v: dict[str, int] | None) -> dict[str, int] | None:
        return None if v is None else _normalize_sizes(v)

    @field_validator("materials")
    @classmethod
    def _v_materials(cls, v: list[ProductMaterialOut] | None) -> list[ProductMaterialOut] | None:
        return None if v is None else _check_materials(v)


class ImageReorderIn(BaseModel):
    image_ids: list[int] = Field(min_length=1, description="Id всех фото товара, первое будет главным")


class CrawlQueueItemOut(BaseModel):
    id: int
    source_id: int
    url: str
    status: str
    error: str | None = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
