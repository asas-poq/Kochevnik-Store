"use client";

import { useState } from "react";
import Link from "next/link";
import { Package } from "lucide-react";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { OrderStatusBadge } from "@/components/shared/order-status-badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useMyOrders } from "@/hooks/use-orders";
import { ORDER_STATUS_LABELS, ORDER_STATUSES } from "@/lib/constants";
import { btnPrimary, btnSquare } from "@/lib/styles";
import { cn, formatDateTime, formatPrice } from "@/lib/utils";
import type { OrderStatus } from "@/types";

const PAGE = 10;

export function OrdersList() {
  const [status, setStatus] = useState<OrderStatus | undefined>(undefined);
  const [limit, setLimit] = useState(PAGE);
  const { data, isLoading, isError, refetch, isFetching } = useMyOrders({ limit, status });

  const orders = data ?? [];

  return (
    <div>
      <h2 className="font-accent text-2xl font-normal text-brand-ink">Мои заказы</h2>

      <div className="mt-5 flex flex-wrap gap-2">
        {[undefined, ...ORDER_STATUSES].map((s) => (
          <button
            key={s ?? "all"}
            type="button"
            onClick={() => {
              setStatus(s);
              setLimit(PAGE);
            }}
            className={cn(
              "rounded-full px-4 py-1.5 text-sm transition-colors",
              status === s ? "bg-brand-ink text-brand-surface" : "bg-brand-section text-brand-ink-2 hover:bg-brand-sand",
            )}
          >
            {s ? ORDER_STATUS_LABELS[s] : "Все"}
          </button>
        ))}
      </div>

      <div className="mt-6 flex flex-col gap-4">
        {isError ? (
          <ErrorState onRetry={() => refetch()} />
        ) : isLoading ? (
          [0, 1, 2].map((i) => <Skeleton key={i} className="h-32 rounded-2xl bg-brand-sand" />)
        ) : orders.length === 0 ? (
          <EmptyState
            icon={<Package />}
            title="Заказов пока нет"
            description="Когда вы оформите заказ, он появится здесь."
            action={
              <Link href="/catalog" className={btnPrimary}>
                Перейти в каталог
              </Link>
            }
          />
        ) : (
          orders.map((o) => {
            const first = (o.items ?? []).slice(0, 2).map((i) => i.product_name);
            const more = (o.items ?? []).length - first.length;
            return (
              <Link
                key={o.id}
                href={`/order/${o.id}`}
                className="rounded-2xl bg-brand-section p-5 shadow-[0_2px_14px_rgba(57,46,33,0.05)] transition-shadow hover:shadow-[0_6px_22px_rgba(57,46,33,0.1)]"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="font-semibold text-brand-ink">Заказ № {o.id}</p>
                    <p className="text-xs text-brand-muted">{formatDateTime(o.created_at)}</p>
                  </div>
                  <OrderStatusBadge status={o.status} />
                </div>
                <p className="mt-3 line-clamp-2 text-sm text-brand-muted">
                  {first.join(", ")}
                  {more > 0 ? ` и ещё ${more}` : ""}
                </p>
                <p className="mt-3 text-xl font-semibold text-brand-ink">{formatPrice(o.total_amount)}</p>
              </Link>
            );
          })
        )}
      </div>

      {orders.length >= limit ? (
        <div className="mt-6 flex justify-center">
          <button type="button" disabled={isFetching} onClick={() => setLimit(limit + PAGE)} className={btnSquare}>
            {isFetching ? "Загрузка…" : "Показать ещё"}
          </button>
        </div>
      ) : null}
    </div>
  );
}
