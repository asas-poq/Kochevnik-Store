"use client";

import { useState } from "react";
import { Search } from "lucide-react";
import { AdminOrdersTable } from "@/components/admin/admin-orders-table";
import { PageHeader, PaginationBar } from "@/components/admin/admin-ui";
import { ErrorState } from "@/components/shared/error-state";
import { useAdminOrders } from "@/hooks/use-orders";
import { ORDER_STATUS_LABELS, ORDER_STATUSES } from "@/lib/constants";
import { adminBtn, adminInput } from "@/lib/styles";
import type { OrderStatus } from "@/types";

const PAGE_SIZE = 20;

export function OrdersAdmin() {
  const [status, setStatus] = useState<OrderStatus | "">("");
  const [searchInput, setSearchInput] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);

  const { data, isLoading, isError, refetch } = useAdminOrders({
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
    status: status || undefined,
    q: q || undefined,
  });
  const orders = data ?? [];

  return (
    <div>
      <PageHeader title="Заказы" description="Все заказы магазина. Меняйте статус по мере выполнения." />

      <form
        onSubmit={(e) => {
          e.preventDefault();
          setPage(0);
          setQ(searchInput.trim());
        }}
        className="mb-4 flex flex-wrap items-center gap-2"
      >
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as OrderStatus | "");
            setPage(0);
          }}
          aria-label="Фильтр по статусу"
          className={`${adminInput} w-48`}
        >
          <option value="">Все статусы</option>
          {ORDER_STATUSES.map((s) => (
            <option key={s} value={s}>
              {ORDER_STATUS_LABELS[s]}
            </option>
          ))}
        </select>
        <input
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder="Поиск: имя, телефон, почта, номер"
          className={`${adminInput} w-full max-w-sm`}
        />
        <button type="submit" className={adminBtn}>
          <Search className="size-4" /> Найти
        </button>
      </form>

      {isError ? (
        <ErrorState onRetry={() => refetch()} />
      ) : (
        <>
          <AdminOrdersTable orders={orders} loading={isLoading} />
          <PaginationBar page={page} hasNext={orders.length === PAGE_SIZE} onPage={setPage} />
        </>
      )}
    </div>
  );
}
