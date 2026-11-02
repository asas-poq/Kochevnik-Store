"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, CreditCard, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { OrderReviewPrompt } from "@/components/order/order-review-prompt";
import { OrderStatusBadge } from "@/components/shared/order-status-badge";
import { PageSkeleton } from "@/components/shared/page-skeleton";
import { Stepper } from "@/components/shared/stepper";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useCancelOrder, useCheckPayment, useOrder } from "@/hooks/use-orders";
import { useRequireAuth } from "@/hooks/use-require-auth";
import { api, ApiError } from "@/lib/api";
import { DELIVERY_METHOD_LABELS } from "@/lib/constants";
import { qk } from "@/lib/query-keys";
import { btnOutline, btnPrimary, cardClass, pageTitleClass } from "@/lib/styles";
import { formatDateTime, formatPrice } from "@/lib/utils";
import type { DeliveryMethod, Schema } from "@/types";

export function OrderView({ orderId }: { orderId: number }) {
  const gate = useRequireAuth();
  const qc = useQueryClient();
  const valid = Number.isFinite(orderId) && orderId > 0;
  const { data: order, isLoading, isError, error, refetch } = useOrder(valid ? orderId : undefined);
  const cancel = useCancelOrder();
  const check = useCheckPayment();
  const [confirmOpen, setConfirmOpen] = useState(false);

  // Пока заказ ждёт оплаты, каждые 6 секунд спрашиваем платёжную систему
  const status = order?.status;
  useEffect(() => {
    if (!valid || status !== "pending") return;
    const timer = setInterval(async () => {
      try {
        const { data } = await api.post<Schema<"OrderOut">>(`/api/v1/orders/${orderId}/check-payment`);
        qc.setQueryData(qk.order(orderId), data);
        if (data.status !== "pending") qc.invalidateQueries({ queryKey: qk.orders });
      } catch {
        // молча пробуем в следующий раз
      }
    }, 6000);
    return () => clearInterval(timer);
  }, [valid, status, orderId, qc]);

  // Уведомление, когда оплата прошла
  const prevStatus = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (prevStatus.current === "pending" && status === "paid") {
      toast.success("Оплата получена. Спасибо за заказ!");
    }
    prevStatus.current = status;
  }, [status]);

  if (gate !== "ok") return <PageSkeleton />;

  if (!valid || (isError && error instanceof ApiError && (error.status === 404 || error.status === 403))) {
    return (
      <div className="container-page py-16">
        <EmptyState
          title="Заказ не найден"
          description="Проверьте ссылку или откройте список своих заказов."
          action={
            <Link href="/profile/orders" className={btnPrimary}>
              Мои заказы
            </Link>
          }
        />
      </div>
    );
  }
  if (isError) {
    return (
      <div className="container-page py-16">
        <ErrorState onRetry={() => refetch()} />
      </div>
    );
  }
  if (isLoading || !order) return <PageSkeleton />;

  const method = order.delivery_method as DeliveryMethod;
  const isPending = order.status === "pending";

  return (
    <div className="container-page py-10 md:py-16">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className={pageTitleClass}>Заказ № {order.id}</h1>
          <p className="mt-2 text-sm text-brand-muted">от {formatDateTime(order.created_at)}</p>
        </div>
        <Stepper current={3} />
      </div>

      {/* Статус */}
      <div className={`${cardClass} mt-8 flex flex-wrap items-center justify-between gap-4`}>
        <div className="flex items-center gap-3">
          <OrderStatusBadge status={order.status} className="px-4 py-1.5 text-sm" />
          {order.status === "paid" ? (
            <span className="flex items-center gap-1.5 text-sm text-status-paid-fg">
              <CheckCircle2 className="size-4" /> Оплата получена
              {order.paid_at ? `, ${formatDateTime(order.paid_at)}` : ""}
            </span>
          ) : null}
          {isPending && order.payment_expires_at ? (
            <span className="text-sm text-brand-muted">Оплатить до {formatDateTime(order.payment_expires_at)}</span>
          ) : null}
        </div>

        {isPending ? (
          <div className="flex flex-wrap gap-3">
            {order.payment_url ? (
              <a href={order.payment_url} className={btnPrimary}>
                <CreditCard className="size-4" />
                Оплатить через СБП
              </a>
            ) : null}
            <button
              type="button"
              disabled={check.isPending}
              onClick={() =>
                check.mutate(order.id, {
                  onSuccess: (o) =>
                    o.status === "pending" && toast.info("Оплата пока не поступила. Мы проверим ещё раз."),
                })
              }
              className={btnOutline}
            >
              <RefreshCw className={check.isPending ? "size-4 animate-spin" : "size-4"} />
              Проверить оплату
            </button>
            <button type="button" onClick={() => setConfirmOpen(true)} className={btnOutline}>
              Отменить заказ
            </button>
          </div>
        ) : null}
      </div>

      <OrderReviewPrompt order={order} />

      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_380px] lg:items-start">
        <section className={cardClass}>
          <h2 className="font-accent text-xl font-normal text-brand-ink">Состав заказа</h2>
          <ul className="mt-4 divide-y divide-brand-line">
            {(order.items ?? []).map((item) => (
              <li key={item.id} className="flex items-start justify-between gap-4 py-4">
                <div>
                  <Link
                    href={`/product/${item.product_slug}`}
                    className="font-medium text-brand-ink hover:text-brand-accent"
                  >
                    {item.product_name}
                  </Link>
                  <p className="mt-1 text-sm text-brand-muted">
                    {item.color ?? "Цвет не указан"} • {item.size} • {item.quantity} шт.
                  </p>
                </div>
                <div className="text-right">
                  <p className="font-semibold text-brand-ink">{formatPrice(item.subtotal)}</p>
                  {item.quantity > 1 ? (
                    <p className="text-xs text-brand-subtle">{formatPrice(item.unit_price)} за шт.</p>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        </section>

        <div className="flex flex-col gap-6">
          <section className={cardClass}>
            <h2 className="font-accent text-xl font-normal text-brand-ink">Получение</h2>
            <dl className="mt-4 space-y-3 text-sm">
              {[
                ["Получатель", order.customer_name],
                ["Телефон", order.customer_phone],
                ["Почта", order.customer_email],
                ["Способ", DELIVERY_METHOD_LABELS[method] ?? order.delivery_method],
                ["Город", order.delivery_city],
                ["Адрес", order.delivery_address],
                ["Код ПВЗ", order.cdek_pvz_code],
                ["Комментарий", order.customer_comment],
              ]
                .filter(([, value]) => Boolean(value))
                .map(([label, value]) => (
                  <div key={label} className="flex justify-between gap-4">
                    <dt className="text-brand-muted">{label}</dt>
                    <dd className="text-right text-brand-ink">{value}</dd>
                  </div>
                ))}
            </dl>
          </section>

          <section className={cardClass}>
            <dl className="space-y-3 text-sm text-brand-muted">
              <div className="flex justify-between">
                <dt>Товары</dt>
                <dd className="text-brand-ink">{formatPrice(order.items_total)}</dd>
              </div>
              <div className="flex justify-between">
                <dt>Доставка</dt>
                <dd className="text-brand-ink">
                  {order.delivery_cost > 0 ? formatPrice(order.delivery_cost) : "Бесплатно"}
                </dd>
              </div>
              <div className="flex items-end justify-between border-t border-brand-line pt-4">
                <dt className="text-brand-ink">Итого</dt>
                <dd className="text-3xl font-semibold text-brand-ink">{formatPrice(order.total_amount)}</dd>
              </div>
            </dl>
          </section>
        </div>
      </div>

      <Link href="/profile/orders" className="mt-8 inline-block text-sm text-brand-muted underline underline-offset-4">
        Все мои заказы
      </Link>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Отменить заказ № {order.id}?</DialogTitle>
            <DialogDescription>
              Заказ будет отменён, а оплатить его по этой ссылке уже не получится.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <button type="button" onClick={() => setConfirmOpen(false)} className={btnOutline}>
              Не отменять
            </button>
            <button
              type="button"
              disabled={cancel.isPending}
              onClick={() => cancel.mutate(order.id, { onSuccess: () => setConfirmOpen(false) })}
              className={btnPrimary}
            >
              {cancel.isPending ? "Отменяем…" : "Да, отменить"}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
