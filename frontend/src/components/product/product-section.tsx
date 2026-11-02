"use client";

import { useRef } from "react";
import Link from "next/link";
import { ArrowRight, ChevronLeft, ChevronRight } from "lucide-react";
import {
  ProductCard,
  ProductCardSkeleton,
  type ProductBadge,
} from "@/components/product/product-card";
import { cn } from "@/lib/utils";
import type { Schema } from "@/types";

interface ProductSectionProps {
  eyebrow?: string; // маленькая надпись над заголовком («СВЕЖИЙ РЕЛИЗ»)
  title: string;
  subtitle?: string;
  href?: string; // ссылка справа («Весь каталог хитов →»)
  linkLabel?: string;
  products: Schema<"ProductCardOut">[];
  isLoading?: boolean;
  badge?: ProductBadge;
  layout?: "grid" | "carousel"; // сетка 4 в ряд или лента со стрелками
  skeletonCount?: number;
}

// Секция главной: заголовок + ряд карточек товаров
export function ProductSection({
  eyebrow,
  title,
  subtitle,
  href,
  linkLabel,
  products,
  isLoading = false,
  badge,
  layout = "grid",
  skeletonCount = 4,
}: ProductSectionProps) {
  const scrollerRef = useRef<HTMLDivElement>(null);

  // Пустую секцию не показываем
  if (!isLoading && products.length === 0) return null;

  const scrollBy = (direction: 1 | -1) => {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollBy({ left: direction * el.clientWidth * 0.9, behavior: "smooth" });
  };

  const cards = isLoading
    ? Array.from({ length: skeletonCount }, (_, i) => (
        <ProductCardSkeleton key={i} />
      ))
    : products.map((p) => <ProductCard key={p.id} product={p} badge={badge} />);

  return (
    <section className="container-page py-10 md:py-16">
      <div className="flex items-end justify-between gap-4">
        <div>
          {eyebrow ? (
            <div className="mb-1 flex items-center gap-2 text-xs font-semibold tracking-[0.1em] text-brand-green">
              <span className="h-px w-5 bg-brand-green" />
              {eyebrow}
            </div>
          ) : null}
          <h2 className="font-accent text-3xl font-normal leading-tight text-brand-ink md:text-4xl">
            {title}
          </h2>
          {subtitle ? (
            <p className="mt-2 max-w-2xl text-base leading-relaxed text-brand-muted">
              {subtitle}
            </p>
          ) : null}
        </div>

        {layout === "carousel" ? (
          <div className="flex shrink-0 gap-2">
            <button
              type="button"
              onClick={() => scrollBy(-1)}
              aria-label="Назад"
              className="grid size-10 place-items-center rounded-full bg-brand-sand text-brand-ink transition hover:bg-brand-line"
            >
              <ChevronLeft className="size-5" />
            </button>
            <button
              type="button"
              onClick={() => scrollBy(1)}
              aria-label="Вперёд"
              className="grid size-10 place-items-center rounded-full bg-brand-sand text-brand-ink transition hover:bg-brand-line"
            >
              <ChevronRight className="size-5" />
            </button>
          </div>
        ) : href ? (
          <Link
            href={href}
            className="hidden shrink-0 items-center gap-1.5 text-[15px] font-medium tracking-[0.02em] text-brand-ink transition-colors hover:text-brand-accent sm:flex"
          >
            {linkLabel}
            <ArrowRight className="size-4" />
          </Link>
        ) : null}
      </div>

      {layout === "carousel" ? (
        <div
          ref={scrollerRef}
          className="no-scrollbar -mx-1 mt-8 flex snap-x snap-mandatory gap-4 overflow-x-auto px-1 py-2 lg:gap-6"
        >
          {isLoading
            ? Array.from({ length: skeletonCount }, (_, i) => (
                <div key={i} className={carouselItemClass}>
                  <ProductCardSkeleton />
                </div>
              ))
            : products.map((p) => (
                <div key={p.id} className={carouselItemClass}>
                  <ProductCard product={p} badge={badge} />
                </div>
              ))}
        </div>
      ) : (
        <div className="mt-8 grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4 lg:gap-6">
          {cards}
        </div>
      )}

      {layout === "grid" && href ? (
        <Link
          href={href}
          className="mt-6 flex items-center justify-center gap-1.5 text-[15px] font-medium text-brand-ink sm:hidden"
        >
          {linkLabel}
          <ArrowRight className="size-4" />
        </Link>
      ) : null}
    </section>
  );
}

// Ширина карточки в ленте: 2 на телефоне, 3 на планшете, 4 на компьютере
const carouselItemClass = cn(
  "shrink-0 snap-start",
  "basis-[calc(50%-6px)] sm:basis-[calc(33.333%-11px)] lg:basis-[calc(25%-18px)]",
);
