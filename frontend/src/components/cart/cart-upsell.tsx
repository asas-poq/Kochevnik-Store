"use client";

import { useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, Plus } from "lucide-react";
import { toast } from "sonner";
import { useRecommendations } from "@/hooks/use-products";
import { formatPrice } from "@/lib/utils";
import { toCartItem, useCartStore } from "@/stores/cart-store";
import type { Schema } from "@/types";

type ProductCard = Schema<"ProductCardOut">;

// «Дополните свой заказ»: лента товаров с кнопкой «+»
export function CartUpsell() {
  const router = useRouter();
  const scrollerRef = useRef<HTMLDivElement>(null);
  const items = useCartStore((s) => s.items);
  const addItem = useCartStore((s) => s.addItem);
  const { data } = useRecommendations({ limit: 12 });

  const inCart = new Set(items.map((i) => i.productId));
  const list = [...(data?.popular ?? []), ...(data?.new_arrivals ?? []), ...(data?.on_sale ?? [])]
    .filter((p, i, arr) => arr.findIndex((x) => x.id === p.id) === i)
    .filter((p) => !inCart.has(p.id) && p.in_stock)
    .slice(0, 10);

  if (list.length === 0) return null;

  const scrollBy = (dir: 1 | -1) => {
    const el = scrollerRef.current;
    if (el) el.scrollBy({ left: dir * el.clientWidth * 0.9, behavior: "smooth" });
  };

  const quickAdd = (product: ProductCard) => {
    const available = (product.sizes ?? []).filter((s) => s.stock > 0);
    // Если размер один, добавляем сразу. Иначе пользователь выберет размер на странице товара.
    if (available.length === 1) {
      addItem(toCartItem(product, available[0]), 1);
      toast.success("Товар добавлен в корзину");
    } else {
      router.push(`/product/${product.slug}`);
    }
  };

  return (
    <section className="mt-16 md:mt-24">
      <div className="flex items-center justify-between gap-4">
        <h2 className="font-accent text-3xl font-normal text-brand-ink md:text-4xl">
          Дополните свой заказ
        </h2>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => scrollBy(-1)}
            aria-label="Назад"
            className="grid size-10 place-items-center rounded-full text-brand-ink transition hover:bg-brand-sand"
          >
            <ArrowLeft className="size-5" />
          </button>
          <button
            type="button"
            onClick={() => scrollBy(1)}
            aria-label="Вперёд"
            className="grid size-10 place-items-center rounded-full text-brand-ink transition hover:bg-brand-sand"
          >
            <ArrowRight className="size-5" />
          </button>
        </div>
      </div>

      <div
        ref={scrollerRef}
        className="no-scrollbar mt-8 flex snap-x snap-mandatory gap-4 overflow-x-auto py-2 lg:gap-6"
      >
        {list.map((p) => (
          <div
            key={p.id}
            className="relative shrink-0 basis-[calc(50%-8px)] snap-start rounded-2xl bg-brand-surface p-3 shadow-[0_2px_14px_rgba(57,46,33,0.06)] sm:basis-[calc(33.333%-11px)] lg:basis-[calc(25%-18px)] lg:p-4"
          >
            <Link href={`/product/${p.slug}`} className="block">
              <div className="aspect-square overflow-hidden rounded-xl bg-brand-sand">
                {p.images?.[0]?.url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={p.images[0].url} alt={p.name} loading="lazy" className="size-full object-cover" />
                ) : null}
              </div>
              <h3 className="mt-4 line-clamp-1 font-accent text-lg font-medium text-brand-ink">
                {p.name}
              </h3>
              <p className="mt-1 line-clamp-2 min-h-10 text-sm text-brand-muted">
                {p.composition ?? p.color ?? ""}
              </p>
            </Link>
            <div className="mt-3 flex items-center justify-between">
              <span className="text-lg font-semibold text-brand-ink">{formatPrice(p.current_price)}</span>
              <button
                type="button"
                onClick={() => quickAdd(p)}
                aria-label="Добавить в корзину"
                className="grid size-8 place-items-center rounded-full bg-brand-sand text-brand-ink transition hover:bg-brand-ink hover:text-brand-surface"
              >
                <Plus className="size-4" />
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
