"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Heart, PackageCheck, ShoppingBag, Truck } from "lucide-react";
import { toast } from "sonner";
import { ProductCard, ProductCardSkeleton } from "@/components/product/product-card";
import { ReviewsSection } from "@/components/product/reviews-section";
import { Accordion } from "@/components/shared/accordion";
import { Breadcrumbs } from "@/components/shared/breadcrumbs";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { Stars } from "@/components/shared/stars";
import { Skeleton } from "@/components/ui/skeleton";
import { useCategories } from "@/hooks/use-categories";
import { useToggleLike } from "@/hooks/use-interactions";
import { useProduct, useRecommendations } from "@/hooks/use-products";
import { ApiError } from "@/lib/api";
import { findCategoryPath } from "@/lib/categories";
import { btnPrimary } from "@/lib/styles";
import { cn, formatPrice, formatRating, getDiscount, pluralize } from "@/lib/utils";
import { makeCartKey, toCartItem, useCartStore } from "@/stores/cart-store";
import type { Schema } from "@/types";

type Product = Schema<"ProductDetailOut">;

const FALLBACK_HEX = "#D8CFC4";

function Gallery({ product }: { product: Product }) {
  const images = useMemo(
    () => [...(product.images ?? [])].sort((a, b) => (a.position ?? 0) - (b.position ?? 0)),
    [product.images],
  );
  const [active, setActive] = useState(0);
  const current = images[Math.min(active, Math.max(images.length - 1, 0))];

  return (
    <div>
      <div className="aspect-[4/5] overflow-hidden rounded-2xl bg-brand-sand">
        {current ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={current.url} alt={product.name} className="size-full object-cover" />
        ) : (
          <div className="grid size-full place-items-center text-sm text-brand-subtle">Фото скоро появится</div>
        )}
      </div>
      {images.length > 1 ? (
        <div className="mt-3 grid grid-cols-5 gap-2 sm:gap-3">
          {images.slice(0, 10).map((img, i) => (
            <button
              key={img.id}
              type="button"
              onClick={() => setActive(i)}
              aria-label={`Фото ${i + 1}`}
              className={cn(
                "aspect-square overflow-hidden rounded-lg bg-brand-sand ring-2 ring-offset-2 ring-offset-brand-bg transition",
                i === active ? "ring-brand-ink" : "ring-transparent hover:ring-brand-line-strong",
              )}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={img.url} alt="" loading="lazy" className="size-full object-cover" />
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function Recommended({ product }: { product: Product }) {
  const { data, isLoading } = useRecommendations({
    category: product.category?.slug,
    limit: 8,
  });
  const list = [...(data?.popular ?? []), ...(data?.seasonal ?? []), ...(data?.new_arrivals ?? [])]
    .filter((p, i, arr) => p.id !== product.id && arr.findIndex((x) => x.id === p.id) === i)
    .slice(0, 4);

  if (!isLoading && list.length === 0) return null;
  return (
    <section className="container-page pb-12 md:pb-20">
      <h2 className="font-accent text-3xl font-normal text-brand-ink md:text-4xl">
        Вам также может понравиться
      </h2>
      <div className="mt-8 grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4 lg:gap-6">
        {isLoading
          ? [0, 1, 2, 3].map((i) => <ProductCardSkeleton key={i} />)
          : list.map((p) => <ProductCard key={p.id} product={p} />)}
      </div>
    </section>
  );
}

function ProductContent({ product }: { product: Product }) {
  const { data: tree } = useCategories();
  const { toggle, isPending } = useToggleLike();
  const addItem = useCartStore((s) => s.addItem);
  const openCart = useCartStore((s) => s.open);
  const cartItems = useCartStore((s) => s.items);

  const sizes = product.sizes ?? [];
  const [selected, setSelected] = useState<string | null>(null);
  const activeSize =
    sizes.find((s) => s.size === selected && s.stock > 0) ??
    sizes.find((s) => s.stock > 0) ??
    null;

  const discount = getDiscount(product);
  const liked = Boolean(product.is_liked_by_me);

  const variants = (product.color_variants ?? []).filter((v) => v.sibling_slug !== product.slug);
  const colorsCount = variants.length + 1;

  const path = findCategoryPath(tree, product.category?.slug ?? "");
  const crumbs = [
    { label: "Главная", href: "/" },
    { label: "Каталог", href: "/catalog" },
    ...path.map((c) => ({ label: c.name, href: `/catalog?category=${encodeURIComponent(c.slug)}` })),
    { label: product.name },
  ];

  const handleAdd = () => {
    if (!activeSize) {
      toast.error("Выберите размер");
      return;
    }
    const inCart = cartItems.find((i) => i.key === makeCartKey(product.id, activeSize.size));
    if (inCart && inCart.quantity >= activeSize.stock) {
      toast.error("Больше этого товара в наличии нет");
      openCart();
      return;
    }
    addItem(toCartItem(product, activeSize), 1);
    toast.success("Добавлено в корзину");
    openCart();
  };

  const materials = product.materials ?? [];
  const attributes = product.attributes ?? [];

  return (
    <>
      <div className="container-page py-6 md:py-8">
        <Breadcrumbs items={crumbs} uppercase />
      </div>

      <div className="container-page grid gap-8 lg:grid-cols-[1.25fr_1fr] lg:gap-12">
        <Gallery product={product} />

        <div>
          <h1 className="font-accent text-3xl font-normal leading-tight text-brand-ink md:text-[40px]">
            {product.name}
          </h1>

          <div className="mt-3 flex items-center gap-2 text-sm text-brand-muted">
            <Stars value={product.rating_avg ?? 0} />
            <span className="font-semibold text-brand-ink-2">{formatRating(product.rating_avg ?? 0)}</span>
            <span>
              ({product.reviews_count ?? 0}{" "}
              {pluralize(product.reviews_count ?? 0, "отзыв", "отзыва", "отзывов")})
            </span>
          </div>

          <div className="mt-5 flex items-center justify-between gap-3 rounded-xl bg-brand-section px-5 py-5">
            <div className="flex flex-wrap items-baseline gap-x-3">
              <span className="text-3xl font-semibold text-brand-ink">{formatPrice(product.current_price)}</span>
              {discount ? (
                <span className="text-base text-brand-subtle line-through">{formatPrice(discount.oldPrice)}</span>
              ) : null}
            </div>
            {discount ? (
              <span className="rounded bg-brand-green px-2.5 py-1 text-[11px] font-semibold tracking-[0.03em] text-white">
                Экономия {formatPrice(discount.saving)}
              </span>
            ) : null}
          </div>

          {/* Цвет */}
          <div className="mt-6">
            <div className="flex items-center justify-between text-sm text-brand-muted">
              <span>
                Цвет: <span className="text-brand-ink-2">{product.color ?? "не указан"}</span>
              </span>
              <span className="text-xs tracking-[0.04em]">
                {colorsCount} {pluralize(colorsCount, "оттенок", "оттенка", "оттенков")}
              </span>
            </div>
            <div className="mt-3 flex flex-wrap gap-3">
              <span
                title={product.color ?? "Текущий цвет"}
                className="size-10 rounded-full ring-2 ring-brand-ink ring-offset-2 ring-offset-brand-bg"
                style={{ backgroundColor: product.color_hex ?? FALLBACK_HEX }}
              />
              {variants.map((v) =>
                v.in_catalog ? (
                  <Link
                    key={v.sibling_slug}
                    href={`/product/${v.sibling_slug}`}
                    title={v.color ?? "Другой цвет"}
                    aria-label={`Цвет: ${v.color ?? "другой"}`}
                    className="size-10 rounded-full border border-black/10 transition-transform hover:scale-110"
                    style={{ backgroundColor: v.color_hex ?? FALLBACK_HEX }}
                  />
                ) : (
                  <span
                    key={v.sibling_slug}
                    title={`${v.color ?? "Другой цвет"} (нет в каталоге)`}
                    className="size-10 rounded-full border border-black/10 opacity-50"
                    style={{ backgroundColor: v.color_hex ?? FALLBACK_HEX }}
                  />
                ),
              )}
            </div>
          </div>

          {/* Размер */}
          <div className="mt-6">
            <p className="text-sm text-brand-muted">Размер</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {sizes.length === 0 ? (
                <span className="text-sm text-brand-subtle">Размеры не указаны</span>
              ) : (
                sizes.map((s) => {
                  const isActive = activeSize?.size === s.size;
                  const out = s.stock <= 0;
                  return (
                    <button
                      key={s.id}
                      type="button"
                      disabled={out}
                      onClick={() => setSelected(s.size)}
                      className={cn(
                        "h-11 min-w-16 rounded-lg px-4 text-sm font-medium transition-colors",
                        isActive
                          ? "bg-brand-ink text-brand-surface"
                          : "bg-brand-sand text-brand-ink-2 hover:bg-brand-line",
                        out && "cursor-not-allowed text-brand-faint line-through hover:bg-brand-sand",
                      )}
                    >
                      {s.size}
                    </button>
                  );
                })
              )}
            </div>
            <p className="mt-3 text-sm text-brand-muted">
              {!product.in_stock || !activeSize ? (
                "Нет в наличии"
              ) : activeSize.stock <= 5 ? (
                <>
                  Осталось всего <b className="text-brand-ink">{activeSize.stock} шт.</b> в этом оттенке
                </>
              ) : (
                "В наличии"
              )}
            </p>
          </div>

          <div className="mt-6 flex gap-3">
            <button
              type="button"
              onClick={handleAdd}
              disabled={!product.in_stock || !activeSize}
              className={cn(btnPrimary, "h-14 flex-1 rounded-lg uppercase")}
            >
              <ShoppingBag className="size-4" />
              Добавить в корзину
            </button>
            <button
              type="button"
              onClick={() => toggle(product.id)}
              disabled={isPending}
              aria-pressed={liked}
              aria-label={liked ? "Убрать из избранного" : "Добавить в избранное"}
              className="grid size-14 place-items-center rounded-lg bg-brand-sand transition-colors hover:bg-brand-line"
            >
              <Heart className={cn("size-5", liked ? "fill-brand-red text-brand-red" : "text-brand-ink")} />
            </button>
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <div className="flex gap-3 rounded-xl bg-brand-section p-4 text-xs leading-relaxed text-brand-muted">
              <Truck className="size-5 shrink-0 text-brand-accent" />
              <p>
                <b className="text-brand-ink-2">Экспресс-доставка</b>
                <br />
                по Москве и Петербургу, от 2 дней
              </p>
            </div>
            <div className="flex gap-3 rounded-xl bg-brand-section p-4 text-xs leading-relaxed text-brand-muted">
              <PackageCheck className="size-5 shrink-0 text-brand-accent" />
              <p>
                <b className="text-brand-ink-2">Возврат</b>
                <br />
                14 дней на лёгкий возврат курьером
              </p>
            </div>
          </div>

          <div className="mt-6">
            <Accordion
              items={[
                {
                  title: "Описание и свойства сырья",
                  content: (
                    <div className="space-y-3">
                      <p className="whitespace-pre-line">{product.description ?? "Описание скоро появится."}</p>
                      {attributes.length > 0 ? (
                        <ul className="grid gap-x-6 gap-y-1.5 text-xs sm:grid-cols-2">
                          {attributes.map((a) => (
                            <li key={a.attr_key}>
                              • <b className="font-semibold text-brand-ink-2">{a.attr_key}:</b> {a.attr_value}
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  ),
                },
                {
                  title: "Состав и бережный уход",
                  content: (
                    <div className="space-y-3">
                      {product.composition ? <p>{product.composition}</p> : null}
                      {materials.length > 0 ? (
                        <ul className="space-y-1">
                          {materials.map((m) => (
                            <li key={m.material}>
                              • {m.material}
                              {m.percent ? ` — ${m.percent}%` : ""}
                            </li>
                          ))}
                        </ul>
                      ) : null}
                      {product.care_text ? <p className="whitespace-pre-line">{product.care_text}</p> : null}
                      {!product.composition && materials.length === 0 && !product.care_text ? (
                        <p>Информация уточняется.</p>
                      ) : null}
                    </div>
                  ),
                },
                {
                  title: "Параметры и мерки изделия",
                  content: (
                    <div className="space-y-3">
                      {product.measurements ? <p className="whitespace-pre-line">{product.measurements}</p> : null}
                      {product.density_yarn ? <p>Плотность пряжи: {product.density_yarn}</p> : null}
                      {sizes.some((s) => s.measurements_cm) ? (
                        <ul className="space-y-1">
                          {sizes
                            .filter((s) => s.measurements_cm)
                            .map((s) => (
                              <li key={s.id}>
                                • <b className="text-brand-ink-2">{s.size}:</b> {s.measurements_cm}
                              </li>
                            ))}
                        </ul>
                      ) : null}
                      {product.article ? <p>Артикул: {product.article}</p> : null}
                      {!product.measurements && !product.density_yarn && !sizes.some((s) => s.measurements_cm) ? (
                        <p>Мерки уточняются.</p>
                      ) : null}
                    </div>
                  ),
                },
              ]}
            />
          </div>
        </div>
      </div>

      <ReviewsSection productId={product.id} />
      <Recommended product={product} />
    </>
  );
}

export function ProductView({ slug }: { slug: string }) {
  const { data: product, isLoading, isError, error, refetch } = useProduct(slug);

  if (isLoading) {
    return (
      <div className="container-page py-10">
        <div className="grid gap-8 lg:grid-cols-[1.25fr_1fr]">
          <Skeleton className="aspect-[4/5] bg-brand-sand" />
          <div className="space-y-4">
            <Skeleton className="h-10 w-3/4 bg-brand-sand" />
            <Skeleton className="h-6 w-1/3 bg-brand-sand" />
            <Skeleton className="h-24 bg-brand-sand" />
            <Skeleton className="h-12 bg-brand-sand" />
            <Skeleton className="h-14 bg-brand-sand" />
          </div>
        </div>
      </div>
    );
  }

  if (isError || !product) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <div className="container-page py-16">
        {notFound ? (
          <EmptyState
            title="Товар не найден"
            description="Возможно, он снят с продажи или ссылка устарела."
            action={
              <Link href="/catalog" className={btnPrimary}>
                В каталог
              </Link>
            }
          />
        ) : (
          <ErrorState onRetry={() => refetch()} />
        )}
      </div>
    );
  }

  return <ProductContent product={product} />;
}
