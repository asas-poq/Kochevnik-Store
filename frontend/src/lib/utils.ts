export { cn } from "cn";

// Неразрывный пробел: число и «₽» не разъедутся по разным строкам
const NBSP = "\u00A0";

// Цена в рублях: 12500 → "12 500 ₽", 99.5 → "99,50 ₽"
export function formatPrice(
  value: number | string | null | undefined,
): string {
  if (value === null || value === undefined || value === "") return "—";
  const amount = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(amount)) return "—";

  // Копейки показываем, только если они есть
  const hasKopecks = Math.round(amount * 100) % 100 !== 0;
  const formatted = new Intl.NumberFormat("ru-RU", {
    minimumFractionDigits: hasKopecks ? 2 : 0,
    maximumFractionDigits: hasKopecks ? 2 : 0,
  }).format(amount);

  // Intl ставит узкий пробел — заменяем на обычный неразрывный
  return `${formatted.replace(/[\u00A0\u202F]/g, NBSP)}${NBSP}₽`;
}

// Дата: "26 октября 2026"
export function formatDate(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const date = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(date);
}

// Дата и время: "26 октября 2026, 15:40"
export function formatDateTime(
  value: string | Date | null | undefined,
): string {
  if (!value) return "—";
  const date = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

// Склонение: pluralize(3, "товар", "товара", "товаров") → "товара"
export function pluralize(
  count: number,
  one: string,
  few: string,
  many: string,
): string {
  const n = Math.abs(count) % 100;
  const last = n % 10;
  if (n > 10 && n < 20) return many;
  if (last > 1 && last < 5) return few;
  if (last === 1) return one;
  return many;
}

// Скидка товара. Возвращает null, если скидки нет или данные «мусорные»
// (например, старая цена в миллионы рублей и скидка -100%).
export function getDiscount(product: {
  current_price: number;
  old_price?: number | null;
}): { oldPrice: number; percent: number; saving: number } | null {
  const old = product.old_price;
  const current = product.current_price;
  if (!old || !current || old <= current) return null;
  const percent = Math.round((1 - current / old) * 100);
  if (percent < 1 || percent > 90) return null;
  return { oldPrice: old, percent, saving: old - current };
}

// Инициалы для кружка с аватаром: "Екатерина Борисова" → "ЕБ"
export function getInitials(name: string | null | undefined): string {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/).slice(0, 2);
  return parts.map((p) => p[0]?.toUpperCase() ?? "").join("") || "?";
}

// Рейтинг с запятой: 4.9 → "4,9"
export function formatRating(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return value.toFixed(1).replace(".", ",");
}

// Безопасный адрес для перехода после входа (только внутри сайта)
export function safeNextPath(next: string | null | undefined, fallback = "/profile"): string {
  if (!next || !next.startsWith("/") || next.startsWith("//")) return fallback;
  return next;
}
