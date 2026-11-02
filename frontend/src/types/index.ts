import type { components, paths } from "./api";

// Достаёт тип по имени из openapi: Schema<"UserOut">, Schema<"ProductCardOut"> и т. д.
export type Schema<K extends keyof components["schemas"]> =
  components["schemas"][K];

// Статус заказа: pending | paid | shipped | completed | cancelled
export type OrderStatus = Schema<"OrderStatus">;

// Сортировка отзывов: newest | oldest | rating_desc | rating_asc
export type ReviewSort = Schema<"ReviewSort">;

// Все параметры запроса каталога (category, material, color, size, цена, поиск, сортировка, страница)
export type CatalogQuery = NonNullable<
  paths["/api/v1/products/catalog"]["get"]["parameters"]["query"]
>;

// Варианты сортировки каталога: popular | newest | price_asc | price_desc | rating_desc | discount
export type CatalogSort = NonNullable<CatalogQuery["sort"]>;

// Способ доставки: cdek_pvz | cdek_courier | russian_post | showroom_pickup
export type DeliveryMethod = NonNullable<
  Schema<"OrderCreateIn">["delivery_method"]
>;

// Время года для подборки на главной
export type Season = Schema<"RecommendationsOut">["season"];

export type { components, operations, paths } from "./api";
