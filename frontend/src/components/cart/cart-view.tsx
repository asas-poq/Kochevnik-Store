"use client";

import Link from "next/link";
import { ArrowLeft, ArrowRight, Heart, ShieldCheck, ShoppingBag, Trash2, Undo2, Lock } from "lucide-react";
import { CartUpsell } from "@/components/cart/cart-upsell";
import { QtyStepper } from "@/components/cart/qty-stepper";
import { EmptyState } from "@/components/shared/empty-state";
import { Stepper } from "@/components/shared/stepper";
import { useLikedIds } from "@/hooks/use-liked-ids";
import { useToggleLike } from "@/hooks/use-interactions";
import { btnPrimary, pageTitleClass } from "@/lib/styles";
import { cn, formatPrice, pluralize } from "@/lib/utils";
import { useCartStore, useCartTotals } from "@/stores/cart-store";

export function CartView() {
  const hasHydrated = useCartStore((s) => s.hasHydrated);
  const items = useCartStore((s) => s.items);
  const setQuantity = useCartStore((s) => s.setQuantity);
  const removeItem = useCartStore((s) => s.removeItem);
  const clear = useCartStore((s) => s.clear);
  const totals = useCartTotals();
  const likedIds = useLikedIds();
  const { toggle } = useToggleLike();

  return (
    <div className="container-page py-10 md:py-16">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <h1 className={pageTitleClass}>Корзина</h1>
        <Stepper current={1} />
      </div>

      {!hasHydrated ? (
        <div className="mt-10 h-64 animate-pulse rounded-2xl bg-brand-sand" />
      ) : items.length === 0 ? (
        <div className="mt-10">
          <EmptyState
            icon={<ShoppingBag />}
            title="Ваша корзина пуста"
            description="Выберите что-нибудь в каталоге: кашемир, пух яка, кожа."
            action={
              <Link href="/catalog" className={btnPrimary}>
                Перейти в каталог
              </Link>
            }
          />
        </div>
      ) : (
        <>
          <div className="mt-10 grid gap-8 lg:grid-cols-[1fr_380px] lg:items-start">
            <div>
              {/* Заголовки колонок (только на компьютере) */}
              <div className="hidden grid-cols-[1fr_130px_140px_90px] gap-4 px-6 pb-4 text-[11px] font-semibold uppercase tracking-[0.1em] text-brand-muted md:grid">
                <span>Товар и характеристики</span>
                <span>Количество</span>
                <span>Стоимость</span>
                <span>Действия</span>
              </div>

              <ul className="flex flex-col gap-4">
                {items.map((item) => {
                  const liked = likedIds.has(item.productId);
                  const percent = item.oldPrice
                    ? Math.round((1 - item.price / item.oldPrice) * 100)
                    : 0;
                  return (
                    <li
                      key={item.key}
                      className="grid gap-4 rounded-2xl bg-brand-section p-4 shadow-[0_2px_14px_rgba(57,46,33,0.05)] md:grid-cols-[1fr_130px_140px_90px] md:items-center md:px-6"
                    >
                      <div className="flex gap-4">
                        <Link
                          href={`/product/${item.slug}`}
                          className="relative h-28 w-24 shrink-0 overflow-hidden rounded-lg bg-brand-sand"
                        >
                          {item.imageUrl ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img src={item.imageUrl} alt={item.name} className="size-full object-cover" />
                          ) : null}
                          {percent > 0 ? (
                            <span className="absolute left-1.5 top-1.5 rounded bg-brand-surface/90 px-1.5 py-0.5 text-[10px] font-semibold text-status-cancelled-fg">
                              -{percent}%
                            </span>
                          ) : null}
                        </Link>
                        <div className="min-w-0">
                          {item.article ? (
                            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-brand-muted">
                              Арт. {item.article}
                            </p>
                          ) : null}
                          <Link
                            href={`/product/${item.slug}`}
                            className="mt-1 block font-accent text-lg font-medium leading-snug text-brand-ink hover:text-brand-accent"
                          >
                            {item.name}
                          </Link>
                          <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-brand-muted">
                            <span className="flex items-center gap-2">
                              <span
                                className="size-3.5 rounded-full border border-black/10"
                                style={{ backgroundColor: item.colorHex ?? "#D8CFC4" }}
                              />
                              {item.color ?? "Цвет не указан"}
                            </span>
                            <span className="text-brand-faint">•</span>
                            <span>{item.size}</span>
                          </p>
                        </div>
                      </div>

                      <QtyStepper
                        value={item.quantity}
                        max={item.maxStock}
                        onChange={(q) => setQuantity(item.key, q)}
                        className="w-fit"
                      />

                      <div>
                        <div className="text-xl font-semibold text-brand-ink">
                          {formatPrice(item.price * item.quantity)}
                        </div>
                        {item.oldPrice ? (
                          <div className="text-sm text-brand-subtle line-through">
                            {formatPrice(item.oldPrice * item.quantity)}
                          </div>
                        ) : null}
                      </div>

                      <div className="flex items-center gap-3 text-brand-ink-2">
                        <button
                          type="button"
                          onClick={() => toggle(item.productId)}
                          aria-label={liked ? "Убрать из избранного" : "В избранное"}
                          aria-pressed={liked}
                        >
                          <Heart
                            className={cn(
                              "size-5",
                              liked && "fill-brand-red text-brand-red",
                            )}
                          />
                        </button>
                        <button
                          type="button"
                          onClick={() => removeItem(item.key)}
                          aria-label="Удалить из корзины"
                          className="transition-colors hover:text-brand-red"
                        >
                          <Trash2 className="size-5" />
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>

              <div className="mt-6 flex items-center justify-between text-xs font-semibold uppercase tracking-[0.1em] text-brand-ink-2">
                <Link href="/catalog" className="flex items-center gap-2 hover:text-brand-accent">
                  <ArrowLeft className="size-4" />
                  Продолжить покупки
                </Link>
                <button
                  type="button"
                  onClick={clear}
                  className="flex items-center gap-2 hover:text-brand-red"
                >
                  <Trash2 className="size-4" />
                  Очистить корзину
                </button>
              </div>
            </div>

            {/* Детали заказа */}
            <aside className="rounded-2xl bg-brand-section p-6 shadow-[0_4px_24px_rgba(57,46,33,0.08)] lg:sticky lg:top-28">
              <h2 className="font-accent text-2xl font-normal text-brand-ink">Детали заказа</h2>

              <dl className="mt-6 space-y-4 text-[15px] text-brand-muted">
                <div className="flex justify-between">
                  <dt>
                    Товары ({totals.count} {pluralize(totals.count, "шт.", "шт.", "шт.")})
                  </dt>
                  <dd className="font-medium text-brand-ink">{formatPrice(totals.gross)}</dd>
                </div>
                {totals.discount > 0 ? (
                  <div className="flex items-center justify-between">
                    <dt className="flex items-center gap-2">
                      Скидка по акции
                      <span className="rounded bg-status-cancelled-bg px-1.5 py-0.5 text-[11px] font-semibold text-status-cancelled-fg">
                        -{totals.discountPercent}%
                      </span>
                    </dt>
                    <dd className="font-medium text-brand-red">−{formatPrice(totals.discount)}</dd>
                  </div>
                ) : null}
                <div className="flex justify-between">
                  <dt>
                    Доставка
                    <span className="block text-[11px] font-semibold uppercase tracking-[0.06em] text-brand-accent">
                      СДЭК · стоимость на следующем шаге
                    </span>
                  </dt>
                  <dd className="text-right text-sm text-brand-muted">Рассчитаем при оформлении</dd>
                </div>
              </dl>

              <div className="mt-6 border-t border-brand-line pt-6">
                <div className="flex items-end justify-between gap-3">
                  <span className="text-lg text-brand-ink">Итого к оплате</span>
                  <span className="text-3xl font-semibold text-brand-ink">{formatPrice(totals.total)}</span>
                </div>
                <p className="mt-1 text-right text-[11px] font-semibold uppercase tracking-[0.06em] text-brand-muted">
                  НДС включён в стоимость
                </p>
              </div>

              <Link href="/checkout" className={`${btnPrimary} mt-6 h-14 w-full rounded-xl uppercase`}>
                Перейти к оформлению
                <ArrowRight className="size-4" />
              </Link>

              <ul className="mt-6 space-y-3 text-sm text-brand-ink-2">
                <li className="flex items-center gap-3">
                  <ShieldCheck className="size-4 text-brand-accent" />
                  100% аутентичный сертифицированный пух
                </li>
                <li className="flex items-center gap-3">
                  <Undo2 className="size-4 text-brand-accent" />
                  14 дней на безусловный лёгкий возврат
                </li>
                <li className="flex items-center gap-3">
                  <Lock className="size-4 text-brand-accent" />
                  Безопасная оплата
                </li>
              </ul>
            </aside>
          </div>

          <CartUpsell />
        </>
      )}
    </div>
  );
}
