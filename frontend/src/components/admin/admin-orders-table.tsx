"use client";

import { useState } from "react";
import Link from "next/link";
import { EmptyRow, TableWrap, Spinner, tdClass, thClass } from "@/components/admin/admin-ui";
import { OrderStatusBadge } from "@/components/shared/order-status-badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useAdminSetOrderStatus } from "@/hooks/use-orders";
import { DELIVERY_METHOD_LABELS } from "@/lib/constants";
import { adminBtn, adminBtnOutline } from "@/lib/styles";
import { formatDateTime, formatPrice } from "@/lib/utils";
import type { DeliveryMethod, Schema } from "@/types";

type Order = Schema<"OrderOut">;

// Какие переходы статуса разрешены: оплачен → отправлен → выполнен
const NEXT_STATUS: Record<string, { status: "shipped" | "completed"; label: string }> = {
  paid: { status: "shipped", label: "Отметить отправленным" },
  shipped: { status: "completed", label: "Отметить выполненным" },
};

function OrderDialog({ order, onClose }: { order: Order; onClose: () => void }) {
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Заказ № {order.id}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 text-sm">
          <div className="flex flex-wrap items-center gap-3">
            <OrderStatusBadge status={order.status} />
            <span className="text-muted-foreground">{formatDateTime(order.created_at)}</span>
            {order.paid_at ? <span className="text-muted-foreground">Оплачен: {formatDateTime(order.paid_at)}</span> : null}
          </div>

          <dl className="grid gap-2 sm:grid-cols-2">
            {[
              ["Клиент", order.customer_name],
              ["Телефон", order.customer_phone],
              ["Почта", order.customer_email],
              ["Доставка", DELIVERY_METHOD_LABELS[order.delivery_method as DeliveryMethod] ?? order.delivery_method],
              ["Город", order.delivery_city],
              ["Адрес", order.delivery_address],
              ["Код ПВЗ", order.cdek_pvz_code],
              ["Комментарий", order.customer_comment],
              ["ID платежа", order.payment_id],
            ]
              .filter(([, v]) => Boolean(v))
              .map(([k, v]) => (
                <div key={k}>
                  <dt className="text-xs text-muted-foreground">{k}</dt>
                  <dd className="break-words text-foreground">{v}</dd>
                </div>
              ))}
          </dl>

          <ul className="divide-y divide-border rounded-md border border-border">
            {(order.items ?? []).map((i) => (
              <li key={i.id} className="flex justify-between gap-3 p-3">
                <div>
                  <Link href={`/product/${i.product_slug}`} className="font-medium hover:underline">
                    {i.product_name}
                  </Link>
                  <p className="text-xs text-muted-foreground">
                    {i.color ?? "—"} • {i.size} • {i.quantity} × {formatPrice(i.unit_price)}
                  </p>
                </div>
                <span className="font-medium">{formatPrice(i.subtotal)}</span>
              </li>
            ))}
          </ul>

          <div className="space-y-1 text-right">
            <p className="text-muted-foreground">Товары: {formatPrice(order.items_total)}</p>
            <p className="text-muted-foreground">Доставка: {formatPrice(order.delivery_cost)}</p>
            <p className="text-lg font-semibold">Итого: {formatPrice(order.total_amount)}</p>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// Таблица заказов с действиями (используется в «Заказах» и на странице пользователя)
export function AdminOrdersTable({ orders, loading }: { orders: Order[]; loading?: boolean }) {
  const setStatus = useAdminSetOrderStatus();
  const [selected, setSelected] = useState<Order | null>(null);

  return (
    <>
      <TableWrap>
        <thead>
          <tr>
            <th className={thClass}>№</th>
            <th className={thClass}>Дата</th>
            <th className={thClass}>Клиент</th>
            <th className={thClass}>Город</th>
            <th className={thClass}>Сумма</th>
            <th className={thClass}>Статус</th>
            <th className={thClass}>Действия</th>
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr>
              <td colSpan={7} className="px-4 py-10 text-center">
                <Spinner />
              </td>
            </tr>
          ) : orders.length === 0 ? (
            <EmptyRow colSpan={7} text="Заказов не найдено" />
          ) : (
            orders.map((o) => {
              const next = NEXT_STATUS[o.status];
              return (
                <tr key={o.id}>
                  <td className={tdClass}>
                    <button type="button" onClick={() => setSelected(o)} className="font-medium text-primary hover:underline">
                      {o.id}
                    </button>
                  </td>
                  <td className={tdClass}>{formatDateTime(o.created_at)}</td>
                  <td className={tdClass}>
                    <p className="font-medium">{o.customer_name}</p>
                    <p className="text-xs text-muted-foreground">{o.customer_phone}</p>
                    {o.user_id ? (
                      <Link href={`/admin/users/${o.user_id}`} className="text-xs text-primary hover:underline">
                        пользователь #{o.user_id}
                      </Link>
                    ) : null}
                  </td>
                  <td className={tdClass}>{o.delivery_city}</td>
                  <td className={tdClass}>{formatPrice(o.total_amount)}</td>
                  <td className={tdClass}>
                    <OrderStatusBadge status={o.status} />
                  </td>
                  <td className={tdClass}>
                    <div className="flex flex-wrap gap-2">
                      <button type="button" onClick={() => setSelected(o)} className={adminBtnOutline}>
                        Подробнее
                      </button>
                      {next ? (
                        <button
                          type="button"
                          disabled={setStatus.isPending}
                          onClick={() => setStatus.mutate({ orderId: o.id, status: next.status })}
                          className={adminBtn}
                        >
                          {next.label}
                        </button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </TableWrap>
      {selected ? <OrderDialog order={selected} onClose={() => setSelected(null)} /> : null}
    </>
  );
}
