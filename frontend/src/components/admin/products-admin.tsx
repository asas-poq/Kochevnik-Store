"use client";

import { useState } from "react";
import Link from "next/link";
import { ExternalLink, Pencil, Plus, Search } from "lucide-react";
import { EmptyRow, PageHeader, Spinner, TableWrap, tdClass, thClass } from "@/components/admin/admin-ui";
import { ErrorState } from "@/components/shared/error-state";
import { useCatalog } from "@/hooks/use-products";
import { adminBtn, adminBtnOutline, adminInput } from "@/lib/styles";
import { formatPrice } from "@/lib/utils";
import { PaginationBar } from "@/components/admin/admin-ui";

const PER_PAGE = 20;

export function ProductsAdmin() {
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  const { data, isLoading, isError, refetch } = useCatalog({
    page,
    per_page: PER_PAGE,
    search: search || undefined,
    sort: "newest",
  });
  const items = data?.items ?? [];

  return (
    <div>
      <PageHeader
        title="Товары"
        description="Создание и редактирование товаров, загрузка фото."
        actions={
          <Link href="/admin/products/new" className={adminBtn}>
            <Plus className="size-4" /> Создать товар
          </Link>
        }
      />

      <form
        onSubmit={(e) => {
          e.preventDefault();
          setPage(1);
          setSearch(searchInput.trim());
        }}
        className="mb-4 flex gap-2"
      >
        <input
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder="Поиск по названию или артикулу"
          className={`${adminInput} max-w-sm`}
        />
        <button type="submit" className={adminBtn}>
          <Search className="size-4" /> Найти
        </button>
      </form>

      {isError ? (
        <ErrorState onRetry={() => refetch()} />
      ) : (
        <>
          <TableWrap>
            <thead>
              <tr>
                <th className={thClass}>Фото</th>
                <th className={thClass}>Название</th>
                <th className={thClass}>Артикул</th>
                <th className={thClass}>Цвет</th>
                <th className={thClass}>Цена</th>
                <th className={thClass}>Наличие</th>
                <th className={thClass}>Действия</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={7} className="px-4 py-10 text-center">
                    <Spinner />
                  </td>
                </tr>
              ) : items.length === 0 ? (
                <EmptyRow colSpan={7} text="Товаров не найдено" />
              ) : (
                items.map((p) => (
                  <tr key={p.id}>
                    <td className={tdClass}>
                      <div className="size-12 overflow-hidden rounded-md bg-muted">
                        {p.images?.[0]?.url ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={p.images[0].url} alt="" className="size-full object-cover" />
                        ) : null}
                      </div>
                    </td>
                    <td className={tdClass}>
                      <p className="font-medium">{p.name}</p>
                      <p className="text-xs text-muted-foreground">{p.slug}</p>
                    </td>
                    <td className={tdClass}>{p.article ?? "—"}</td>
                    <td className={tdClass}>
                      <span className="flex items-center gap-2">
                        <span
                          className="size-3.5 rounded-full border border-black/10"
                          style={{ backgroundColor: p.color_hex ?? "#d8cfc4" }}
                        />
                        {p.color ?? "—"}
                      </span>
                    </td>
                    <td className={tdClass}>{formatPrice(p.current_price)}</td>
                    <td className={tdClass}>{p.in_stock ? "В наличии" : "Нет"}</td>
                    <td className={tdClass}>
                      <div className="flex gap-2">
                        <Link href={`/admin/products/${p.slug}`} className={adminBtnOutline}>
                          <Pencil className="size-4" /> Изменить
                        </Link>
                        <Link href={`/product/${p.slug}`} target="_blank" className={adminBtnOutline} aria-label="Открыть на сайте">
                          <ExternalLink className="size-4" />
                        </Link>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </TableWrap>
          <PaginationBar page={page - 1} hasNext={page < (data?.total_pages ?? 1)} onPage={(p) => setPage(p + 1)} />
        </>
      )}
    </div>
  );
}
