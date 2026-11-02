import { useMemo } from "react";
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import { getDiscount } from "@/lib/utils";
import type { Schema } from "@/types";

type ProductCard = Schema<"ProductCardOut">;
type ProductDetail = Schema<"ProductDetailOut">;
type ProductSize = Schema<"ProductSizeOut">;

// Одна позиция в корзине. Корзина хранится только в браузере (в API корзины нет),
// поэтому сюда копируем всё, что нужно для показа без запросов к серверу.
export interface CartItem {
  key: string; // уникальный ключ позиции: "id товара:размер"
  productId: number;
  slug: string;
  name: string;
  article: string | null;
  imageUrl: string | null;
  color: string | null;
  colorHex: string | null;
  size: string;
  price: number; // текущая цена за штуку
  oldPrice: number | null; // цена до скидки (если есть)
  quantity: number;
  maxStock: number; // сколько всего есть на складе в этом размере
}

export type NewCartItem = Omit<CartItem, "key" | "quantity">;

export const makeCartKey = (productId: number, size: string) =>
  `${productId}:${size}`;

// Собирает позицию корзины из товара и выбранного размера
export function toCartItem(
  product: ProductCard | ProductDetail,
  size: ProductSize,
): NewCartItem {
  return {
    productId: product.id,
    slug: product.slug,
    name: product.name,
    article: product.article ?? null,
    imageUrl: product.images?.[0]?.url ?? null,
    color: product.color ?? null,
    colorHex: product.color_hex ?? null,
    size: size.size,
    price: product.current_price,
    oldPrice: getDiscount(product)?.oldPrice ?? null,
    maxStock: size.stock,
  };
}

interface CartState {
  items: CartItem[];
  isOpen: boolean; // открыта ли боковая панель корзины
  hasHydrated: boolean;

  addItem: (item: NewCartItem, quantity?: number) => void;
  setQuantity: (key: string, quantity: number) => void;
  removeItem: (key: string) => void;
  clear: () => void;

  open: () => void;
  close: () => void;
  setOpen: (value: boolean) => void;
  setHasHydrated: (value: boolean) => void;
}

// Количество не должно превышать остаток на складе (если остаток известен)
const clampQuantity = (quantity: number, maxStock: number) => {
  const min = Math.max(1, quantity);
  return maxStock > 0 ? Math.min(min, maxStock) : min;
};

export const useCartStore = create<CartState>()(
  persist(
    (set) => ({
      items: [],
      isOpen: false,
      hasHydrated: false,

      addItem: (item, quantity = 1) =>
        set((state) => {
          const key = makeCartKey(item.productId, item.size);
          const existing = state.items.find((i) => i.key === key);
          if (existing) {
            return {
              items: state.items.map((i) =>
                i.key === key
                  ? {
                      ...i,
                      ...item, // обновляем цену и остаток на свежие
                      quantity: clampQuantity(
                        i.quantity + quantity,
                        item.maxStock,
                      ),
                    }
                  : i,
              ),
            };
          }
          return {
            items: [
              ...state.items,
              { ...item, key, quantity: clampQuantity(quantity, item.maxStock) },
            ],
          };
        }),

      setQuantity: (key, quantity) =>
        set((state) => ({
          items: state.items.map((i) =>
            i.key === key
              ? { ...i, quantity: clampQuantity(quantity, i.maxStock) }
              : i,
          ),
        })),

      removeItem: (key) =>
        set((state) => ({ items: state.items.filter((i) => i.key !== key) })),

      clear: () => set({ items: [] }),

      open: () => set({ isOpen: true }),
      close: () => set({ isOpen: false }),
      setOpen: (value) => set({ isOpen: value }),
      setHasHydrated: (value) => set({ hasHydrated: value }),
    }),
    {
      name: "kochevnik-cart", // ключ в localStorage
      version: 1,
      storage: createJSONStorage(() => localStorage),
      skipHydration: true, // читаем вручную в providers.tsx
      partialize: (state) => ({ items: state.items }),
      onRehydrateStorage: () => (state) => {
        state?.setHasHydrated(true);
      },
    },
  ),
);

/* ----------------------- Подсчёты ----------------------- */

export interface CartTotals {
  count: number; // всего штук
  gross: number; // сумма по ценам БЕЗ скидки (строка «Товары»)
  discount: number; // сколько сэкономили
  total: number; // итого к оплате
  discountPercent: number; // скидка в процентах от gross
}

export function getCartTotals(items: CartItem[]): CartTotals {
  let count = 0;
  let gross = 0;
  let total = 0;
  for (const item of items) {
    const base =
      item.oldPrice && item.oldPrice > item.price ? item.oldPrice : item.price;
    count += item.quantity;
    gross += base * item.quantity;
    total += item.price * item.quantity;
  }
  const discount = gross - total;
  return {
    count,
    gross,
    discount,
    total,
    discountPercent: gross > 0 ? Math.round((discount / gross) * 100) : 0,
  };
}

// Хук с итогами. useMemo нужен, чтобы объект не создавался заново при каждом рендере
export function useCartTotals(): CartTotals {
  const items = useCartStore((s) => s.items);
  return useMemo(() => getCartTotals(items), [items]);
}

// Позиции корзины → формат для POST /api/v1/orders
export function cartItemsToOrderItems(
  items: CartItem[],
): Schema<"OrderItemCreateIn">[] {
  return items.map((i) => ({
    product_id: i.productId,
    size: i.size,
    quantity: i.quantity,
  }));
}
