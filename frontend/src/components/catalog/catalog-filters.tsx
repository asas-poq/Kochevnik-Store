"use client";

import { useState, type ReactNode } from "react";
import { Check, ChevronDown, ChevronUp, Minus, Plus } from "lucide-react";
import { type CategoryNode, findCategoryPath } from "@/lib/categories";
import { cn } from "@/lib/utils";
import type { CatalogQuery, Schema } from "@/types";

export type CatalogFiltersState = Omit<CatalogQuery, "page" | "per_page">;

interface CatalogFiltersProps {
  filters: CatalogFiltersState;
  update: (patch: Partial<CatalogFiltersState>) => void;
  reset: () => void;
  facets?: Schema<"CatalogFacetsOut">;
  tree?: CategoryNode[];
}

// Сворачиваемая группа фильтров («СОСТАВ ТКАНИ +»)
function FilterGroup({
  title,
  defaultOpen = false,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b border-brand-line py-4">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center justify-between text-xs font-bold uppercase tracking-[0.1em] text-brand-ink"
      >
        {title}
        {open ? <Minus className="size-3.5" /> : <Plus className="size-3.5" />}
      </button>
      {open ? <div className="mt-4">{children}</div> : null}
    </div>
  );
}

function toggleValue(list: string[] | null | undefined, value: string): string[] {
  const current = list ?? [];
  return current.includes(value) ? current.filter((v) => v !== value) : [...current, value];
}

// Боковая панель: категории + состав, цвет, размер, цена
export function CatalogFilters({ filters, update, reset, facets, tree }: CatalogFiltersProps) {
  const selectedCategory = filters.category?.[0];
  const path = selectedCategory ? findCategoryPath(tree, selectedCategory) : [];
  const root = path[0];
  const [rootOpen, setRootOpen] = useState(true);

  const [minPrice, setMinPrice] = useState(filters.min_price?.toString() ?? "");
  const [maxPrice, setMaxPrice] = useState(filters.max_price?.toString() ?? "");

  const applyPrice = () => {
    const min = minPrice.trim() === "" ? undefined : Number(minPrice);
    const max = maxPrice.trim() === "" ? undefined : Number(maxPrice);
    update({
      min_price: min !== undefined && Number.isFinite(min) ? min : undefined,
      max_price: max !== undefined && Number.isFinite(max) ? max : undefined,
    });
  };

  const activeCount =
    (filters.material?.length ?? 0) +
    (filters.color?.length ?? 0) +
    (filters.size?.length ?? 0) +
    (filters.min_price !== undefined || filters.max_price !== undefined ? 1 : 0) +
    (filters.only_in_stock ? 1 : 0) +
    (filters.on_sale ? 1 : 0);

  return (
    <div>
      {/* Категории */}
      <div className="border-b border-brand-line pb-5">
        {root ? (
          <>
            <button
              type="button"
              onClick={() => setRootOpen(!rootOpen)}
              className="flex w-full items-start justify-between gap-3 text-left text-xs font-bold uppercase leading-snug tracking-[0.08em] text-brand-ink"
            >
              {root.name}
              {rootOpen ? <ChevronUp className="mt-0.5 size-4 shrink-0" /> : <ChevronDown className="mt-0.5 size-4 shrink-0" />}
            </button>
            {rootOpen ? (
              <ul className="mt-4 flex flex-col gap-3 text-sm">
                <li>
                  <button
                    type="button"
                    onClick={() => update({ category: [root.slug] })}
                    className={cn(
                      "text-left text-brand-ink-2 hover:text-brand-accent",
                      selectedCategory === root.slug && "font-bold text-brand-ink",
                    )}
                  >
                    Смотреть все
                  </button>
                </li>
                {(root.children ?? []).map((c) => (
                  <li key={c.id}>
                    <button
                      type="button"
                      onClick={() => update({ category: [c.slug] })}
                      className={cn(
                        "text-left text-brand-ink-2 hover:text-brand-accent",
                        path.some((p) => p.slug === c.slug) && "font-bold text-brand-ink",
                      )}
                    >
                      {c.name}
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </>
        ) : (
          <>
            <p className="text-xs font-bold uppercase tracking-[0.1em] text-brand-ink">Категории</p>
            <ul className="mt-4 flex flex-col gap-3 text-sm">
              {(tree ?? []).map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => update({ category: [c.slug] })}
                    className="text-left text-brand-ink-2 hover:text-brand-accent"
                  >
                    {c.name}
                    {c.products_count ? (
                      <span className="ml-1.5 text-xs text-brand-subtle">{c.products_count}</span>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>

      <FilterGroup title="Состав ткани" defaultOpen={(filters.material?.length ?? 0) > 0}>
        <ul className="flex flex-col gap-2.5">
          {(facets?.materials ?? []).map((m) => {
            const checked = filters.material?.includes(m.name) ?? false;
            return (
              <li key={m.name}>
                <button
                  type="button"
                  onClick={() => update({ material: toggleValue(filters.material, m.name) })}
                  className="flex w-full items-center gap-3 text-left text-sm text-brand-ink-2"
                >
                  <span
                    className={cn(
                      "grid size-4 place-items-center rounded border",
                      checked ? "border-brand-ink bg-brand-ink text-brand-surface" : "border-brand-line-strong",
                    )}
                  >
                    {checked ? <Check className="size-3" /> : null}
                  </span>
                  <span className="flex-1">{m.name}</span>
                  <span className="text-xs text-brand-subtle">{m.count}</span>
                </button>
              </li>
            );
          })}
          {(facets?.materials ?? []).length === 0 ? (
            <li className="text-sm text-brand-subtle">Нет вариантов</li>
          ) : null}
        </ul>
      </FilterGroup>

      <FilterGroup title="Цвет" defaultOpen={(filters.color?.length ?? 0) > 0}>
        <ul className="flex flex-col gap-2.5">
          {(facets?.colors ?? []).map((c) => {
            const checked = filters.color?.includes(c.name) ?? false;
            return (
              <li key={c.name}>
                <button
                  type="button"
                  onClick={() => update({ color: toggleValue(filters.color, c.name) })}
                  className="flex w-full items-center gap-3 text-left text-sm text-brand-ink-2"
                >
                  <span
                    className={cn(
                      "size-5 rounded-full border border-black/10 ring-offset-2 ring-offset-brand-bg",
                      checked && "ring-2 ring-brand-ink",
                    )}
                    style={{ backgroundColor: c.hex ?? "#D8CFC4" }}
                  />
                  <span className={cn("flex-1", checked && "font-semibold text-brand-ink")}>{c.name}</span>
                  <span className="text-xs text-brand-subtle">{c.count}</span>
                </button>
              </li>
            );
          })}
          {(facets?.colors ?? []).length === 0 ? (
            <li className="text-sm text-brand-subtle">Нет вариантов</li>
          ) : null}
        </ul>
      </FilterGroup>

      <FilterGroup title="Размер" defaultOpen={(filters.size?.length ?? 0) > 0}>
        <div className="flex flex-wrap gap-2">
          {(facets?.sizes ?? []).map((s) => {
            const checked = filters.size?.includes(s.name) ?? false;
            return (
              <button
                key={s.name}
                type="button"
                onClick={() => update({ size: toggleValue(filters.size, s.name) })}
                title={`В наличии: ${s.count}`}
                className={cn(
                  "h-9 min-w-12 rounded-lg px-3 text-sm transition-colors",
                  checked
                    ? "bg-brand-ink text-brand-surface"
                    : "bg-brand-sand text-brand-ink-2 hover:bg-brand-line",
                )}
              >
                {s.name}
              </button>
            );
          })}
          {(facets?.sizes ?? []).length === 0 ? (
            <span className="text-sm text-brand-subtle">Нет вариантов</span>
          ) : null}
        </div>
      </FilterGroup>

      <FilterGroup
        title="Цена, ₽"
        defaultOpen={filters.min_price !== undefined || filters.max_price !== undefined}
      >
        <div className="flex items-center gap-2">
          <input
            type="number"
            min={0}
            inputMode="numeric"
            value={minPrice}
            onChange={(e) => setMinPrice(e.target.value)}
            onBlur={applyPrice}
            onKeyDown={(e) => e.key === "Enter" && applyPrice()}
            placeholder={facets?.price_range?.min != null ? `от ${facets.price_range.min}` : "от"}
            className="h-10 w-full rounded-lg bg-brand-sand/70 px-3 text-sm outline-none focus:ring-2 focus:ring-brand-accent/30"
          />
          <span className="text-brand-subtle">—</span>
          <input
            type="number"
            min={0}
            inputMode="numeric"
            value={maxPrice}
            onChange={(e) => setMaxPrice(e.target.value)}
            onBlur={applyPrice}
            onKeyDown={(e) => e.key === "Enter" && applyPrice()}
            placeholder={facets?.price_range?.max != null ? `до ${facets.price_range.max}` : "до"}
            className="h-10 w-full rounded-lg bg-brand-sand/70 px-3 text-sm outline-none focus:ring-2 focus:ring-brand-accent/30"
          />
        </div>
      </FilterGroup>

      <div className="space-y-3 py-5 text-sm text-brand-ink-2">
        <label className="flex cursor-pointer items-center gap-3">
          <input
            type="checkbox"
            checked={Boolean(filters.only_in_stock)}
            onChange={(e) => update({ only_in_stock: e.target.checked })}
            className="size-4 accent-brand-ink"
          />
          Только в наличии
        </label>
        <label className="flex cursor-pointer items-center gap-3">
          <input
            type="checkbox"
            checked={Boolean(filters.on_sale)}
            onChange={(e) => update({ on_sale: e.target.checked })}
            className="size-4 accent-brand-ink"
          />
          Со скидкой
        </label>
      </div>

      {activeCount > 0 || selectedCategory || filters.search ? (
        <button
          type="button"
          onClick={() => {
            setMinPrice("");
            setMaxPrice("");
            reset();
          }}
          className="text-sm text-brand-accent underline underline-offset-4 hover:text-brand-accent-dark"
        >
          Сбросить все фильтры
        </button>
      ) : null}
    </div>
  );
}
