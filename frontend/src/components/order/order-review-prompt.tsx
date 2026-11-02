"use client";

import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, MessageSquare, Send } from "lucide-react";
import { ReviewForm } from "@/components/product/reviews-section";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useMyReviews } from "@/hooks/use-interactions";
import { SUPPORT_TELEGRAM } from "@/lib/constants";
import { btnOutline, btnPrimary } from "@/lib/styles";
import type { Schema } from "@/types";

// После оплаты просим оставить отзыв о товарах или написать в поддержку
const PAID_STATUSES = ["paid", "shipped", "completed"];

function SupportLink({ className }: { className?: string }) {
  return (
    <a
      href={SUPPORT_TELEGRAM.url}
      target="_blank"
      rel="noopener noreferrer"
      className={className}
    >
      <Send className="size-4" />
      Написать в поддержку {SUPPORT_TELEGRAM.handle}
    </a>
  );
}

export function OrderReviewPrompt({ order }: { order: Schema<"OrderOut"> }) {
  const reviewable = PAID_STATUSES.includes(order.status);
  const myReviews = useMyReviews({ limit: 100 });
  const [formFor, setFormFor] = useState<number | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  const reviewedIds = useMemo(
    () => new Set((myReviews.data ?? []).map((r) => r.product_id)),
    [myReviews.data],
  );

  // Уникальные товары заказа (один товар в разных размерах считаем один раз)
  const products = useMemo(() => {
    const map = new Map<number, { product_id: number; name: string }>();
    for (const item of order.items ?? []) {
      if (!map.has(item.product_id)) {
        map.set(item.product_id, { product_id: item.product_id, name: item.product_name });
      }
    }
    return [...map.values()];
  }, [order.items]);

  const pendingCount = products.filter((p) => !reviewedIds.has(p.product_id)).length;
  const storageKey = `kochevnik-review-prompt-${order.id}`;

  // Один раз для каждого заказа показываем окно с просьбой об отзыве
  useEffect(() => {
    if (!reviewable || myReviews.isLoading || pendingCount === 0) return;
    try {
      if (!localStorage.getItem(storageKey)) setDialogOpen(true);
    } catch {
      // localStorage недоступен: просто не показываем окно
    }
  }, [reviewable, myReviews.isLoading, pendingCount, storageKey]);

  const closeDialog = () => {
    setDialogOpen(false);
    try {
      localStorage.setItem(storageKey, "1");
    } catch {
      // ничего страшного
    }
  };

  if (!reviewable) return null;

  const allDone = pendingCount === 0 && !myReviews.isLoading;

  return (
    <>
      <section
        id="order-review"
        className="mt-6 rounded-2xl border-2 border-brand-accent/40 bg-brand-section p-5 md:p-6"
      >
        <div className="flex items-start gap-4">
          <div className="grid size-11 shrink-0 place-items-center rounded-full bg-brand-sand text-brand-accent">
            {allDone ? <CheckCircle2 className="size-5" /> : <MessageSquare className="size-5" />}
          </div>
          <div className="flex-1">
            <h2 className="font-accent text-xl font-medium text-brand-ink">
              {allDone ? "Спасибо за отзывы!" : "Расскажите о покупке"}
            </h2>
            <p className="mt-1 text-sm leading-relaxed text-brand-muted">
              {allDone
                ? "Ваши отзывы помогают другим покупателям. Если с заказом что-то не так, мы на связи."
                : "Оплата получена. Оставьте отзыв о товарах из заказа, это очень поможет другим покупателям. Если что-то пошло не так, напишите в поддержку."}
            </p>

            <ul className="mt-4 divide-y divide-brand-line">
              {products.map((p) => {
                const done = reviewedIds.has(p.product_id);
                return (
                  <li key={p.product_id} className="py-3">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <span className="text-sm font-medium text-brand-ink">{p.name}</span>
                      {done ? (
                        <span className="flex items-center gap-1.5 text-sm text-status-paid-fg">
                          <CheckCircle2 className="size-4" /> Отзыв отправлен
                        </span>
                      ) : (
                        <button
                          type="button"
                          onClick={() => setFormFor(formFor === p.product_id ? null : p.product_id)}
                          className={btnOutline}
                        >
                          {formFor === p.product_id ? "Свернуть" : "Оставить отзыв"}
                        </button>
                      )}
                    </div>
                    {formFor === p.product_id && !done ? (
                      <ReviewForm productId={p.product_id} onDone={() => setFormFor(null)} />
                    ) : null}
                  </li>
                );
              })}
            </ul>

            <div className="mt-4">
              <SupportLink className={btnPrimary} />
            </div>
          </div>
        </div>
      </section>

      <Dialog open={dialogOpen} onOpenChange={(open) => !open && closeDialog()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Как вам заказ № {order.id}?</DialogTitle>
            <DialogDescription>
              Оставьте отзыв о товарах или напишите в поддержку, если что-то пошло не так.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <button type="button" onClick={closeDialog} className={btnOutline}>
              Позже
            </button>
            <SupportLink className={btnOutline} />
            <button
              type="button"
              onClick={() => {
                closeDialog();
                document.getElementById("order-review")?.scrollIntoView({ behavior: "smooth", block: "center" });
              }}
              className={btnPrimary}
            >
              Оставить отзыв
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
