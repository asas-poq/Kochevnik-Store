"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ArrowUpDown, SearchX, SlidersHorizontal } from "lucide-react";
import {
  CatalogFilters,
  type CatalogFiltersState,
} from "@/components/catalog/catalog-filters";
import { ProductCard, ProductCardSkeleton } from "@/components/product/product-card";
import { Breadcrumbs } from "@/components/shared/breadcrumbs";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useCategories } from "@/hooks/use-categories";
import { useInfiniteCatalog } from "@/hooks/use-products";
import { findCategoryBySlug, findCategoryPath } from "@/lib/categories";
import { CATALOG_SORT_OPTIONS } from "@/lib/constants";
import { btnOutline, btnSquare } from "@/lib/styles";
import { cn } from "@/lib/utils";
import type { CatalogSort } from "@/types";

const PER_PAGE = 12;
const SORT_VALUES = CATALOG_SORT_OPTIONS.map((o) => o.value);

// Адрес страницы → фильтры
function parseFilters(sp: URLSearchParams): CatalogFiltersState {
  const num = (key: string) => {
    const raw = sp.get(key);
    if (raw === null || raw === "") return undefined;
    const n = Number(raw);
    return Number.isFinite(n) ? n : undefined;
  };
  const sort = sp.get("sort") as CatalogSort | null;
  return {
    category: sp.getAll("category"),
    material: sp.getAll("material"),
    color: sp.getAll("color"),
    size: sp.getAll("size"),
    min_price: num("min_price"),
    max_price: num("max_price"),
    search: sp.get("search") ?? undefined,
    only_in_stock: sp.get("only_in_stock") === "true",
    on_sale: sp.get("on_sale") === "true",
    sort: sort && SORT_VALUES.includes(sort) ? sort : "popular",
  };
}

// Фильтры → адрес страницы
function toQueryString(filters: CatalogFiltersState): string {
  const sp = new URLSearchParams();
  for (const key of ["category", "material", "color", "size"] as const) {
    for (const value of filters[key] ?? []) sp.append(key, value);
  }
  if (filters.min_price !== undefined && filters.min_price !== null) sp.set("min_price", String(filters.min_price));
  if (filters.max_price !== undefined && filters.max_price !== null) sp.set("max_price", String(filters.max_price));
  if (filters.search) sp.set("search", filters.search);
  if (filters.only_in_stock) sp.set("only_in_stock", "true");
  if (filters.on_sale) sp.set("on_sale", "true");
  if (filters.sort && filters.sort !== "popular") sp.set("sort", filters.sort);
  return sp.toString();
}

export function CatalogView() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [filtersOpen, setFiltersOpen] = useState(false);

  const filters = useMemo(
    () => parseFilters(new URLSearchParams(searchParams.toString())),
    [searchParams],
  );

  const goTo = (next: CatalogFiltersState) => {
    const qs = toQueryString(next);
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };
  const update = (patch: Partial<CatalogFiltersState>) => goTo({ ...filters, ...patch });
  const reset = () => goTo({ sort: filters.sort });

  const { data: tree } = useCategories();
  const query = useInfiniteCatalog({ ...filters, per_page: PER_PAGE });

  const pages = query.data?.pages ?? [];
  const items = pages.flatMap((p) => p.items);
  const total = pages[pages.length - 1]?.total ?? 0;
  const facets = pages[0]?.available_filters;

  // Заголовок и «хлебные крошки»
  const selectedSlug = filters.category?.[0];
  const path = selectedSlug ? findCategoryPath(tree, selectedSlug) : [];
  const current = path[path.length - 1] ?? (selectedSlug ? findCategoryBySlug(tree, selectedSlug) : null);
  const title = filters.search
    ? `Поиск: «${filters.search}»`
    : current
      ? current.name
      : "Каталог";

  const crumbs = [
    { label: "Главная", href: "/" },
    { label: "Каталог", href: current ? "/catalog" : undefined },
    ...path.map((c, i) => ({
      label: c.name,
      href: i === path.length - 1 ? undefined : `/catalog?category=${encodeURIComponent(c.slug)}`,
    })),
  ];

  // Быстрые кнопки подкатегорий: дети выбранной категории или «соседи», если выбран лист
  const chipsParent = current?.children?.length ? current : (path[path.length - 2] ?? null);
  const chips = chipsParent?.children ?? [];

  const filterPanel = (
    <CatalogFilters filters={filters} update={update} reset={reset} facets={facets} tree={tree} />
  );

  return (
    <div className="pb-16">
      <div className="container-page pt-6 md:pt-8">
        <Breadcrumbs items={crumbs} />
        <h1 className="mt-4 text-3xl font-extrabold uppercase leading-tight tracking-[-0.01em] text-brand-ink md:text-[40px]">
          {title}
        </h1>

        {chips.length > 0 ? (
          <div className="mt-6 flex flex-wrap gap-3">
            {chips.map((c) => {
              const active = selectedSlug === c.slug;
              return (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => update({ category: [c.slug] })}
                  className={cn(
                    "h-11 border px-5 text-sm text-brand-ink transition-colors",
                    active
                      ? "border-2 border-brand-ink bg-brand-surface font-medium"
                      : "border-brand-line-strong bg-transparent hover:border-brand-ink",
                  )}
                >
                  {c.name}
                </button>
              );
            })}
          </div>
        ) : null}
      </div>

      <div className="mt-8 bg-brand-section/60 py-6 md:py-8">
        <div className="container-page grid gap-8 lg:grid-cols-[260px_1fr] lg:gap-10">
          {/* Боковая панель на компьютере */}
          <aside className="hidden lg:block">{filterPanel}</aside>

          <div>
            {/* Панель «Фильтры / Сортировка» */}
            <div className="mb-6 flex items-center justify-between gap-4">
              <button
                type="button"
                onClick={() => setFiltersOpen(true)}
                className="flex items-center gap-2 text-sm font-medium text-brand-ink lg:pointer-events-none"
              >
                Фильтры
                <SlidersHorizontal className="size-4" />
              </button>

              <label className="flex items-center gap-2 text-sm font-medium text-brand-ink">
                <span className="hidden sm:inline">Сортировка</span>
                <ArrowUpDown className="size-4" />
                <select
                  value={filters.sort ?? "popular"}
                  onChange={(e) => update({ sort: e.target.value as CatalogSort })}
                  aria-label="Сортировка"
                  className="max-w-44 cursor-pointer bg-transparent text-sm text-brand-ink-2 outline-none"
                >
                  {CATALOG_SORT_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            {query.isError ? (
              <ErrorState onRetry={() => query.refetch()} />
            ) : query.isLoading ? (
              <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-3 xl:gap-6">
                {Array.from({ length: 6 }, (_, i) => (
                  <ProductCardSkeleton key={i} />
                ))}
              </div>
            ) : items.length === 0 ? (
              <EmptyState
                icon={<SearchX />}
                title="Ничего не найдено"
                description="Попробуйте изменить фильтры или поисковый запрос."
                action={
                  <button type="button" onClick={reset} className={btnOutline}>
                    Сбросить фильтры
                  </button>
                }
              />
            ) : (
              <>
                <div
                  className={cn(
                    "grid grid-cols-2 gap-3 transition-opacity sm:gap-4 xl:grid-cols-3 xl:gap-6",
                    query.isPlaceholderData && "opacity-60",
                  )}
                >
                  {items.map((p) => (
                    <ProductCard key={p.id} product={p} />
                  ))}
                </div>

                <div className="mt-10 flex flex-col items-center gap-4">
                  <p className="text-xs text-brand-muted">
                    Показано {items.length} из {total} моделей
                  </p>
                  <div className="h-0.5 w-56 bg-brand-line">
                    <div
                      className="h-full bg-brand-ink transition-all"
                      style={{ width: `${total ? Math.min(100, (items.length / total) * 100) : 0}%` }}
                    />
                  </div>
                  {query.hasNextPage ? (
                    <button
                      type="button"
                      onClick={() => query.fetchNextPage()}
                      disabled={query.isFetchingNextPage}
                      className={btnSquare}
                    >
                      {query.isFetchingNextPage ? "Загрузка…" : "Показать ещё"}
                    </button>
                  ) : (
                    <Link href="/" className="text-sm text-brand-muted underline underline-offset-4">
                      На главную
                    </Link>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Фильтры на телефоне */}
      <Sheet open={filtersOpen} onOpenChange={setFiltersOpen}>
        <SheetContent side="left" className="bg-brand-bg p-0">
          <SheetHeader className="border-b border-brand-line p-5">
            <SheetTitle className="font-accent text-xl font-medium text-brand-ink">Фильтры</SheetTitle>
          </SheetHeader>
          <div className="flex-1 overflow-y-auto px-5 pb-6">{filterPanel}</div>
          <div className="border-t border-brand-line p-4">
            <button
              type="button"
              onClick={() => setFiltersOpen(false)}
              className="h-11 w-full rounded-full bg-brand-ink text-sm font-medium text-brand-surface"
            >
              Показать {total ? `${total} ` : ""}товаров
            </button>
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
