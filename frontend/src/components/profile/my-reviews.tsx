"use client";

import { useState } from "react";
import Link from "next/link";
import { MessageSquare, Pencil, Trash2 } from "lucide-react";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { FormField } from "@/components/shared/form-field";
import { Stars, StarInput } from "@/components/shared/stars";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useDeleteReview, useMyReviews, useUpdateReview } from "@/hooks/use-interactions";
import { btnOutline, btnPrimary, inputClass, textareaClass } from "@/lib/styles";
import { formatDate } from "@/lib/utils";
import type { Schema } from "@/types";

type MyReview = Schema<"MyReviewOut">;

function EditDialog({ review, onClose }: { review: MyReview; onClose: () => void }) {
  const update = useUpdateReview();
  const [rating, setRating] = useState(review.rating ?? 5);
  const [text, setText] = useState(review.comment_text);
  const [adv, setAdv] = useState(review.advantages ?? "");
  const [dis, setDis] = useState(review.disadvantages ?? "");

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Редактировать отзыв</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <StarInput value={rating} onChange={setRating} />
          <FormField label="Отзыв">
            <textarea value={text} onChange={(e) => setText(e.target.value)} className={textareaClass} />
          </FormField>
          <FormField label="Достоинства">
            <input value={adv} onChange={(e) => setAdv(e.target.value)} className={inputClass} />
          </FormField>
          <FormField label="Недостатки">
            <input value={dis} onChange={(e) => setDis(e.target.value)} className={inputClass} />
          </FormField>
        </div>
        <DialogFooter>
          <button type="button" onClick={onClose} className={btnOutline}>
            Отмена
          </button>
          <button
            type="button"
            disabled={update.isPending || text.trim().length < 3}
            onClick={() =>
              update.mutate(
                {
                  reviewId: review.id,
                  data: {
                    rating,
                    comment_text: text.trim(),
                    advantages: adv.trim() || null,
                    disadvantages: dis.trim() || null,
                  },
                },
                { onSuccess: onClose },
              )
            }
            className={btnPrimary}
          >
            Сохранить
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function MyReviews() {
  const { data, isLoading, isError, refetch } = useMyReviews({ limit: 100 });
  const del = useDeleteReview();
  const [editing, setEditing] = useState<MyReview | null>(null);
  const list = data ?? [];

  return (
    <div>
      <h2 className="font-accent text-2xl font-normal text-brand-ink">Мои отзывы</h2>
      <div className="mt-6 flex flex-col gap-4">
        {isError ? (
          <ErrorState onRetry={() => refetch()} />
        ) : isLoading ? (
          [0, 1].map((i) => <Skeleton key={i} className="h-36 rounded-2xl bg-brand-sand" />)
        ) : list.length === 0 ? (
          <EmptyState
            icon={<MessageSquare />}
            title="Вы ещё не оставляли отзывов"
            description="Отзыв можно написать на странице товара."
            action={
              <Link href="/catalog" className={btnPrimary}>
                Перейти в каталог
              </Link>
            }
          />
        ) : (
          list.map((r) => (
            <article key={r.id} className="flex gap-4 rounded-2xl bg-brand-section p-5">
              <Link
                href={`/product/${r.product_slug}`}
                className="h-24 w-20 shrink-0 overflow-hidden rounded-lg bg-brand-sand"
              >
                {r.product_image_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={r.product_image_url} alt={r.product_name} className="size-full object-cover" />
                ) : null}
              </Link>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <Link href={`/product/${r.product_slug}`} className="font-medium text-brand-ink hover:text-brand-accent">
                    {r.product_name}
                  </Link>
                  <span
                    className={
                      r.is_approved
                        ? "rounded-full bg-status-paid-bg px-3 py-1 text-xs font-medium text-status-paid-fg"
                        : "rounded-full bg-status-pending-bg px-3 py-1 text-xs font-medium text-status-pending-fg"
                    }
                  >
                    {r.is_approved ? "Опубликован" : "На модерации"}
                  </span>
                </div>
                <div className="mt-2 flex items-center gap-3">
                  <Stars value={r.rating ?? 0} />
                  <span className="text-xs text-brand-muted">{formatDate(r.created_at)}</span>
                </div>
                <p className="mt-2 whitespace-pre-line text-sm text-brand-ink-2">{r.comment_text}</p>
                {r.admin_reply ? (
                  <p className="mt-3 rounded-lg bg-brand-surface p-3 text-sm text-brand-ink-2">
                    <b className="text-brand-accent">Ответ магазина: </b>
                    {r.admin_reply}
                  </p>
                ) : null}
                <div className="mt-3 flex gap-4 text-sm">
                  <button type="button" onClick={() => setEditing(r)} className="flex items-center gap-1.5 text-brand-muted hover:text-brand-ink">
                    <Pencil className="size-4" /> Изменить
                  </button>
                  <button
                    type="button"
                    disabled={del.isPending}
                    onClick={() => window.confirm("Удалить этот отзыв?") && del.mutate(r.id)}
                    className="flex items-center gap-1.5 text-brand-muted hover:text-brand-red"
                  >
                    <Trash2 className="size-4" /> Удалить
                  </button>
                </div>
              </div>
            </article>
          ))
        )}
      </div>
      {editing ? <EditDialog review={editing} onClose={() => setEditing(null)} /> : null}
    </div>
  );
}
