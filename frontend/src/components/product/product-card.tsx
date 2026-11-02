"use client";

import Link from "next/link";
import { Heart } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { useInView } from "@/hooks/use-in-view";
import { useToggleLike } from "@/hooks/use-interactions";
import { useProduct } from "@/hooks/use-products";
import { cn, formatPrice, getDiscount } from "@/lib/utils";
import type { Schema } from "@/types";

type ProductCardData = Schema<"ProductCardOut">;

// Плашка в левом верхнем углу: «ХИТ», «НОВИНКА» или скидка «-20%»
export type ProductBadge = "hit" | "new" | "sale";

interface ProductCardProps {
  product: ProductCardData;
  badge?: ProductBadge;
}

const FALLBACK_HEX = "#D8CFC4";

// Цвет товара и все доступные цвета.
// Список оттенков приходит только в полной карточке товара, поэтому подгружаем её,
// когда карточка попала в зону видимости (запрос кешируется).
function CardColors({ product }: { product: ProductCardData }) {
  const [ref, inView] = useInView<HTMLDivElement>();
  const { data } = useProduct(inView ? product.slug : undefined);

  const colorName = product.color ?? data?.color ?? null;
  const variants = (data?.color_variants ?? []).filter(
    (v) => v.sibling_slug !== product.slug,
  );

  return (
    <div
      ref={ref}
      className="mt-3 flex items-center justify-between gap-3 text-xs text-brand-muted"
    >
      <span className="truncate">
        {colorName ? `Цвет: ${colorName}` : "Цвет не указан"}
      </span>
      <span className="pointer-events-auto relative z-[2] flex shrink-0 items-center gap-1.5">
        <span
          title={colorName ?? "Цвет"}
          className="size-4 rounded-full ring-2 ring-brand-ink/70 ring-offset-1 ring-offset-brand-surface"
          style={{ backgroundColor: product.color_hex ?? FALLBACK_HEX }}
        />
        {variants.map((v) =>
          v.in_catalog ? (
            <Link
              key={v.sibling_slug}
              href={`/product/${v.sibling_slug}`}
              title={v.color ?? "Другой цвет"}
              aria-label={`Цвет: ${v.color ?? "другой"}`}
              className="size-4 rounded-full border border-black/10 transition-transform hover:scale-125"
              style={{ backgroundColor: v.color_hex ?? FALLBACK_HEX }}
            />
          ) : (
            <span
              key={v.sibling_slug}
              title={v.color ?? "Другой цвет"}
              className="size-4 rounded-full border border-black/10 opacity-60"
              style={{ backgroundColor: v.color_hex ?? FALLBACK_HEX }}
            />
          ),
        )}
      </span>
    </div>
  );
}

export function ProductCard({ product, badge }: ProductCardProps) {
  const { toggle, pendingProductId } = useToggleLike();
  const liked = Boolean(product.is_liked_by_me);
  const image = product.images?.[0]?.url;
  const discount = getDiscount(product);

  const badgeText =
    badge === "hit"
      ? "ХИТ"
      : badge === "new"
        ? "НОВИНКА"
        : badge === "sale" && discount
          ? `-${discount.percent}%`
          : null;

  return (
    <div className="group relative rounded-2xl bg-brand-surface p-3 shadow-[0_2px_14px_rgba(57,46,33,0.06)] transition-shadow hover:shadow-[0_6px_22px_rgba(57,46,33,0.1)] sm:p-4">
      {/* Ссылка на всю карточку (лежит под остальными элементами) */}
      <Link
        href={`/product/${product.slug}`}
        aria-label={product.name}
        className="absolute inset-0 z-[1] rounded-2xl"
      />

      <div className="pointer-events-none relative">
        <div className="relative aspect-[3/4] overflow-hidden rounded-xl bg-brand-sand">
          {image ? (
            // Обычный <img>: адрес картинок приходит с бэкенда
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={image}
              alt={product.name}
              loading="lazy"
              className="size-full object-cover transition-transform duration-500 group-hover:scale-[1.03]"
            />
          ) : null}
          {!product.in_stock ? (
            <div className="absolute inset-x-0 bottom-0 bg-brand-ink/70 py-1.5 text-center text-xs font-medium tracking-wide text-brand-cream">
              Нет в наличии
            </div>
          ) : null}
        </div>
        {badgeText ? (
          <span
            className={cn(
              "absolute left-3 top-3 rounded-full px-2.5 py-1 text-xs font-semibold tracking-[0.05em] text-brand-surface",
              badge === "new" ? "bg-brand-green" : "bg-brand-faint",
            )}
          >
            {badgeText}
          </span>
        ) : null}
      </div>

      <div className="pointer-events-none">
        <h3 className="mt-4 line-clamp-2 min-h-[2.9rem] font-accent text-[15px] font-medium leading-[1.55] text-brand-ink">
          {product.name}
        </h3>

        <div className="mt-3 flex flex-wrap items-baseline gap-x-2">
          <span className="text-lg font-semibold text-brand-ink sm:text-xl">
            {formatPrice(product.current_price)}
          </span>
          {discount ? (
            <>
              <span className="text-sm tracking-[0.01em] text-brand-subtle line-through">
                {formatPrice(discount.oldPrice)}
              </span>
              <span className="text-xs font-medium tracking-[0.04em] text-brand-accent">
                -{discount.percent}%
              </span>
            </>
          ) : null}
        </div>
      </div>

      <CardColors product={product} />

      <button
        type="button"
        onClick={() => toggle(product.id)}
        disabled={pendingProductId === product.id}
        aria-pressed={liked}
        aria-label={liked ? "Убрать из избранного" : "Добавить в избранное"}
        className="absolute right-6 top-6 z-[2] grid size-9 place-items-center rounded-full bg-brand-surface/85 [@media(pointer:coarse)]:size-11 backdrop-blur transition hover:bg-brand-surface disabled:opacity-60 sm:right-7 sm:top-7"
      >
        <Heart
          className={cn(
            "size-[18px]",
            liked ? "fill-brand-red text-brand-red" : "text-brand-ink-2",
          )}
        />
      </button>
    </div>
  );
}

// Скелетон карточки (пока товары грузятся)
export function ProductCardSkeleton() {
  return (
    <div className="rounded-2xl bg-brand-surface p-3 shadow-[0_2px_14px_rgba(57,46,33,0.06)] sm:p-4">
      <Skeleton className="aspect-[3/4] w-full rounded-xl bg-brand-sand" />
      <Skeleton className="mt-4 h-4 w-11/12 bg-brand-sand" />
      <Skeleton className="mt-2 h-4 w-2/3 bg-brand-sand" />
      <Skeleton className="mt-4 h-6 w-1/2 bg-brand-sand" />
      <Skeleton className="mt-3 h-4 w-3/4 bg-brand-sand" />
    </div>
  );
}
