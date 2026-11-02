"use client";

import Link from "next/link";
import { ShoppingBag, X } from "lucide-react";
import { QtyStepper } from "@/components/cart/qty-stepper";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { btnOutline, btnPrimary } from "@/lib/styles";
import { formatPrice, pluralize } from "@/lib/utils";
import { useCartStore, useCartTotals } from "@/stores/cart-store";

// Боковая панель корзины (выезжает справа по клику на значок корзины)
export function CartSheet() {
  const isOpen = useCartStore((s) => s.isOpen);
  const setOpen = useCartStore((s) => s.setOpen);
  const items = useCartStore((s) => s.items);
  const setQuantity = useCartStore((s) => s.setQuantity);
  const removeItem = useCartStore((s) => s.removeItem);
  const totals = useCartTotals();

  return (
    <Sheet open={isOpen} onOpenChange={setOpen}>
      <SheetContent side="right" className="w-full bg-brand-bg p-0 sm:max-w-md">
        <SheetHeader className="border-b border-brand-line p-5">
          <SheetTitle className="font-accent text-xl font-medium text-brand-ink">
            Корзина
            {totals.count > 0 ? (
              <span className="ml-2 text-sm font-normal text-brand-muted">
                {totals.count} {pluralize(totals.count, "товар", "товара", "товаров")}
              </span>
            ) : null}
          </SheetTitle>
        </SheetHeader>

        {items.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
            <div className="grid size-14 place-items-center rounded-full bg-brand-sand text-brand-muted">
              <ShoppingBag className="size-6" />
            </div>
            <p className="font-accent text-lg font-medium text-brand-ink">Корзина пуста</p>
            <p className="text-sm text-brand-muted">
              Добавьте товары из каталога, и они появятся здесь.
            </p>
            <Link href="/catalog" onClick={() => setOpen(false)} className={`${btnPrimary} mt-2`}>
              Перейти в каталог
            </Link>
          </div>
        ) : (
          <>
            <ul className="flex-1 divide-y divide-brand-line overflow-y-auto px-5">
              {items.map((item) => (
                <li key={item.key} className="flex gap-4 py-4">
                  <Link
                    href={`/product/${item.slug}`}
                    onClick={() => setOpen(false)}
                    className="h-24 w-20 shrink-0 overflow-hidden rounded-lg bg-brand-sand"
                  >
                    {item.imageUrl ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={item.imageUrl} alt={item.name} className="size-full object-cover" />
                    ) : null}
                  </Link>
                  <div className="flex min-w-0 flex-1 flex-col">
                    <div className="flex items-start justify-between gap-2">
                      <Link
                        href={`/product/${item.slug}`}
                        onClick={() => setOpen(false)}
                        className="line-clamp-2 font-accent text-[15px] font-medium leading-snug text-brand-ink"
                      >
                        {item.name}
                      </Link>
                      <button
                        type="button"
                        onClick={() => removeItem(item.key)}
                        aria-label="Удалить из корзины"
                        className="shrink-0 text-brand-subtle transition-colors hover:text-brand-red"
                      >
                        <X className="size-4" />
                      </button>
                    </div>
                    <p className="mt-1 flex items-center gap-2 text-xs text-brand-muted">
                      <span
                        className="size-3 rounded-full border border-black/10"
                        style={{ backgroundColor: item.colorHex ?? "#D8CFC4" }}
                      />
                      {item.color ?? "Цвет не указан"} · {item.size}
                    </p>
                    <div className="mt-auto flex items-center justify-between pt-3">
                      <QtyStepper
                        value={item.quantity}
                        max={item.maxStock}
                        onChange={(q) => setQuantity(item.key, q)}
                      />
                      <div className="text-right">
                        <div className="text-[15px] font-semibold text-brand-ink">
                          {formatPrice(item.price * item.quantity)}
                        </div>
                        {item.oldPrice ? (
                          <div className="text-xs text-brand-subtle line-through">
                            {formatPrice(item.oldPrice * item.quantity)}
                          </div>
                        ) : null}
                      </div>
                    </div>
                  </div>
                </li>
              ))}
            </ul>

            <div className="border-t border-brand-line bg-brand-section p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))]">
              {totals.discount > 0 ? (
                <div className="mb-2 flex justify-between text-sm text-brand-muted">
                  <span>Скидка</span>
                  <span className="text-brand-red">−{formatPrice(totals.discount)}</span>
                </div>
              ) : null}
              <div className="flex items-end justify-between">
                <span className="text-sm text-brand-muted">Итого к оплате</span>
                <span className="text-2xl font-semibold text-brand-ink">
                  {formatPrice(totals.total)}
                </span>
              </div>
              <div className="mt-4 grid gap-2">
                <Link href="/checkout" onClick={() => setOpen(false)} className={btnPrimary}>
                  Оформить заказ
                </Link>
                <Link href="/cart" onClick={() => setOpen(false)} className={btnOutline}>
                  Открыть корзину
                </Link>
              </div>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
