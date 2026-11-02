import type { CatalogSort, DeliveryMethod, OrderStatus, ReviewSort } from "@/types";

/* ----------------------- Статусы заказа ----------------------- */

export const ORDER_STATUS_LABELS: Record<OrderStatus, string> = {
  pending: "Ожидает оплаты",
  paid: "Оплачен",
  shipped: "Отправлен",
  completed: "Выполнен",
  cancelled: "Отменён",
};

// Цвета бейджей статусов (цвета заданы в globals.css)
export const ORDER_STATUS_CLASSES: Record<OrderStatus, string> = {
  pending: "bg-status-pending-bg text-status-pending-fg",
  paid: "bg-status-paid-bg text-status-paid-fg",
  shipped: "bg-status-shipped-bg text-status-shipped-fg",
  completed: "bg-status-completed-bg text-status-completed-fg",
  cancelled: "bg-status-cancelled-bg text-status-cancelled-fg",
};

export const ORDER_STATUSES: OrderStatus[] = [
  "pending",
  "paid",
  "shipped",
  "completed",
  "cancelled",
];

/* ----------------------- Доставка ----------------------- */

export const DELIVERY_METHOD_LABELS: Record<DeliveryMethod, string> = {
  cdek_courier: "Курьер СДЭК",
  cdek_pvz: "Пункт выдачи СДЭК",
  russian_post: "Почта России",
  showroom_pickup: "Самовывоз из шоурума",
};

// Заказ дороже этой суммы доставляется бесплатно (текст из макета).
// Итоговую стоимость доставки всегда считает бэкенд (поле delivery_cost заказа).
export const FREE_DELIVERY_THRESHOLD = 40_000;

/* ----------------------- Сортировки ----------------------- */

export const CATALOG_SORT_OPTIONS: { value: CatalogSort; label: string }[] = [
  { value: "popular", label: "По популярности" },
  { value: "newest", label: "Сначала новинки" },
  { value: "price_asc", label: "Сначала дешёвые" },
  { value: "price_desc", label: "Сначала дорогие" },
  { value: "rating_desc", label: "По рейтингу" },
  { value: "discount", label: "По размеру скидки" },
];

export const REVIEW_SORT_OPTIONS: { value: ReviewSort; label: string }[] = [
  { value: "newest", label: "Сначала новые" },
  { value: "oldest", label: "Сначала старые" },
  { value: "rating_desc", label: "Сначала с высокой оценкой" },
  { value: "rating_asc", label: "Сначала с низкой оценкой" },
];

/* ----------------------- Навигация и контакты ----------------------- */

export const NAV_LINKS = [
  { label: "Каталог", href: "/catalog" },
  { label: "О бренде", href: "/#about" },
  { label: "Материалы", href: "/catalog" },
  { label: "Доставка", href: "/#delivery" },
];

// Ссылки на соцсети: замените "#" на свои адреса
export const SOCIAL_LINKS = [
  { label: "Telegram", href: "#" },
  { label: "Pinterest", href: "#" },
  { label: "Max", href: "#" },
];

export const CONTACTS = {
  github: "github",
  githubUrl: "https://github.com/asas-poq",
  phone: "+7 (800) 777-00-67",
  phoneHref: "tel:+78007770067",
  hours: "10:00–20:00",
};

// Поддержка в Telegram (ссылка открывается в приложении Telegram)
export const SUPPORT_TELEGRAM = {
  handle: "@Aaaaaafjs",
  url: "https://t.me/Aaaaaafjs",
};
