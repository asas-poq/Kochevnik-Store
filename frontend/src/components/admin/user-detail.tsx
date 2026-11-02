"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { AdminOrdersTable } from "@/components/admin/admin-orders-table";
import { PageHeader, Panel, Spinner } from "@/components/admin/admin-ui";
import { ErrorState } from "@/components/shared/error-state";
import { Stars } from "@/components/shared/stars";
import { useUserOrders } from "@/hooks/use-orders";
import { useUserReviews } from "@/hooks/use-interactions";
import { cn, formatDateTime } from "@/lib/utils";

export function UserDetail({ userId }: { userId: number }) {
  const [tab, setTab] = useState<"orders" | "reviews">("orders");
  const orders = useUserOrders(userId, { limit: 100 });
  const reviews = useUserReviews(userId, { limit: 100 });

  return (
    <div>
      <Link href="/admin/users" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> Все пользователи
      </Link>
      <PageHeader
        title={`Пользователь № ${userId}`}
        description={orders.data?.[0] ? `${orders.data[0].customer_name} · ${orders.data[0].customer_phone}` : undefined}
      />

      <div className="mb-4 flex gap-2">
        {(
          [
            ["orders", `Заказы${orders.data ? ` (${orders.data.length})` : ""}`],
            ["reviews", `Отзывы${reviews.data ? ` (${reviews.data.length})` : ""}`],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={cn(
              "rounded-md px-4 py-2 text-sm font-medium transition-colors",
              tab === key ? "bg-primary text-primary-foreground" : "border border-input bg-card hover:bg-accent",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "orders" ? (
        orders.isError ? (
          <ErrorState onRetry={() => orders.refetch()} />
        ) : (
          <AdminOrdersTable orders={orders.data ?? []} loading={orders.isLoading} />
        )
      ) : reviews.isError ? (
        <ErrorState onRetry={() => reviews.refetch()} />
      ) : reviews.isLoading ? (
        <div className="py-10 text-center">
          <Spinner />
        </div>
      ) : (reviews.data ?? []).length === 0 ? (
        <Panel>
          <p className="py-6 text-center text-sm text-muted-foreground">Отзывов нет</p>
        </Panel>
      ) : (
        <div className="flex flex-col gap-3">
          {(reviews.data ?? []).map((r) => (
            <Panel key={r.id}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Link href={`/product/${r.product_slug}`} className="font-medium hover:underline">
                  {r.product_name}
                </Link>
                <span
                  className={cn(
                    "rounded-full px-2.5 py-0.5 text-xs font-medium",
                    r.is_approved ? "bg-status-paid-bg text-status-paid-fg" : "bg-status-pending-bg text-status-pending-fg",
                  )}
                >
                  {r.is_approved ? "Опубликован" : "На модерации"}
                </span>
              </div>
              <div className="mt-2 flex items-center gap-3">
                <Stars value={r.rating ?? 0} />
                <span className="text-xs text-muted-foreground">{formatDateTime(r.created_at)}</span>
              </div>
              <p className="mt-2 whitespace-pre-line text-sm">{r.comment_text}</p>
            </Panel>
          ))}
        </div>
      )}
    </div>
  );
}
