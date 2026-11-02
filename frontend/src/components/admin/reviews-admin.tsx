"use client";

import { useState } from "react";
import Link from "next/link";
import { Check, X } from "lucide-react";
import { PageHeader, PaginationBar, Panel, Spinner } from "@/components/admin/admin-ui";
import { ErrorState } from "@/components/shared/error-state";
import { Stars } from "@/components/shared/stars";
import {
  useApproveReview,
  usePendingReviews,
  useRejectReview,
  useReplyToReview,
} from "@/hooks/use-interactions";
import { adminBtn, adminBtnDanger, adminBtnOutline, adminTextarea } from "@/lib/styles";
import { formatDateTime } from "@/lib/utils";
import type { Schema } from "@/types";

const PAGE_SIZE = 20;

function ReviewItem({ review }: { review: Schema<"ReviewOut"> }) {
  const approve = useApproveReview();
  const reject = useRejectReview();
  const reply = useReplyToReview();
  const [text, setText] = useState(review.admin_reply ?? "");
  const busy = approve.isPending || reject.isPending;

  return (
    <Panel>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-3">
            <Stars value={review.rating ?? 0} />
            <span className="text-xs text-muted-foreground">{formatDateTime(review.created_at)}</span>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            {review.user?.full_name ?? "Покупатель"} ·{" "}
            <Link href={`/admin/users/${review.user_id}`} className="text-primary hover:underline">
              пользователь #{review.user_id}
            </Link>{" "}
            · товар #{review.product_id}
            {review.is_verified_purchase ? " · покупал" : ""}
          </p>
        </div>
        <div className="flex gap-2">
          <button type="button" disabled={busy} onClick={() => approve.mutate(review.id)} className={adminBtn}>
            <Check className="size-4" /> Одобрить
          </button>
          <button type="button" disabled={busy} onClick={() => reject.mutate(review.id)} className={adminBtnDanger}>
            <X className="size-4" /> Отклонить
          </button>
        </div>
      </div>

      <p className="mt-3 whitespace-pre-line text-sm text-foreground">{review.comment_text}</p>
      {review.advantages ? (
        <p className="mt-2 text-sm text-muted-foreground">
          <b className="text-foreground">Достоинства:</b> {review.advantages}
        </p>
      ) : null}
      {review.disadvantages ? (
        <p className="mt-1 text-sm text-muted-foreground">
          <b className="text-foreground">Недостатки:</b> {review.disadvantages}
        </p>
      ) : null}

      <div className="mt-4 border-t border-border pt-4">
        <label className="mb-1 block text-xs font-medium text-muted-foreground">Ответ магазина</label>
        <textarea value={text} onChange={(e) => setText(e.target.value)} className={adminTextarea} placeholder="Ответ покупателю (необязательно)" />
        <div className="mt-2">
          <button
            type="button"
            disabled={reply.isPending || text.trim().length === 0}
            onClick={() => reply.mutate({ reviewId: review.id, adminReply: text.trim() })}
            className={adminBtnOutline}
          >
            Сохранить ответ
          </button>
        </div>
      </div>
    </Panel>
  );
}

export function ReviewsAdmin() {
  const [page, setPage] = useState(0);
  const { data, isLoading, isError, refetch } = usePendingReviews({ limit: PAGE_SIZE, offset: page * PAGE_SIZE });
  const list = data ?? [];

  return (
    <div>
      <PageHeader title="Модерация отзывов" description="Новые отзывы ждут проверки. Одобренные появятся на странице товара." />
      {isError ? (
        <ErrorState onRetry={() => refetch()} />
      ) : isLoading ? (
        <div className="py-10 text-center">
          <Spinner />
        </div>
      ) : list.length === 0 ? (
        <Panel>
          <p className="py-6 text-center text-sm text-muted-foreground">Очередь пуста: все отзывы проверены.</p>
        </Panel>
      ) : (
        <div className="flex flex-col gap-4">
          {list.map((r) => (
            <ReviewItem key={r.id} review={r} />
          ))}
          <PaginationBar page={page} hasNext={list.length === PAGE_SIZE} onPage={setPage} />
        </div>
      )}
    </div>
  );
}
