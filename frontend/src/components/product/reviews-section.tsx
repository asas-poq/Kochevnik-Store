"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BadgeCheck } from "lucide-react";
import { Stars, StarInput } from "@/components/shared/stars";
import { FormField } from "@/components/shared/form-field";
import { useAuth } from "@/hooks/use-auth";
import {
  useCreateReview,
  useInfiniteReviews,
  useReviewSummary,
} from "@/hooks/use-interactions";
import { REVIEW_SORT_OPTIONS } from "@/lib/constants";
import { btnOutline, btnPrimary, btnSquare, inputClass, textareaClass } from "@/lib/styles";
import { formatDate, formatRating, getInitials, pluralize } from "@/lib/utils";
import type { ReviewSort, Schema } from "@/types";

function ReviewCard({ review }: { review: Schema<"ReviewOut"> }) {
  const name = review.user?.full_name ?? "Покупатель";
  return (
    <article className="mb-5 break-inside-avoid rounded-xl bg-brand-section p-6">
      <div className="flex items-center justify-between gap-3">
        <Stars value={review.rating ?? 0} />
        <time className="text-xs font-medium tracking-[0.04em] text-brand-muted">
          {formatDate(review.created_at)}
        </time>
      </div>
      <p className="mt-4 whitespace-pre-line text-[15px] leading-relaxed text-brand-ink-2">
        «{review.comment_text}»
      </p>
      {review.advantages ? (
        <p className="mt-3 text-sm text-brand-muted">
          <span className="font-semibold text-brand-ink-2">Достоинства: </span>
          {review.advantages}
        </p>
      ) : null}
      {review.disadvantages ? (
        <p className="mt-1 text-sm text-brand-muted">
          <span className="font-semibold text-brand-ink-2">Недостатки: </span>
          {review.disadvantages}
        </p>
      ) : null}
      {review.admin_reply ? (
        <div className="mt-4 rounded-lg bg-brand-surface p-3 text-sm text-brand-ink-2">
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-brand-accent">
            Ответ магазина
          </p>
          {review.admin_reply}
        </div>
      ) : null}
      <div className="mt-5 flex items-center gap-3">
        <span className="grid size-9 place-items-center rounded-full bg-brand-sand text-xs font-semibold text-brand-muted">
          {getInitials(name)}
        </span>
        <div>
          <p className="text-sm font-semibold text-brand-ink">{name}</p>
          {review.is_verified_purchase ? (
            <p className="flex items-center gap-1 text-xs text-brand-muted">
              <BadgeCheck className="size-3.5 text-brand-green" />
              Проверенный покупатель
            </p>
          ) : null}
        </div>
      </div>
    </article>
  );
}

export function ReviewForm({ productId, onDone }: { productId: number; onDone: () => void }) {
  const create = useCreateReview(productId);
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState("");
  const [advantages, setAdvantages] = useState("");
  const [disadvantages, setDisadvantages] = useState("");
  const [error, setError] = useState("");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (comment.trim().length < 3) {
      setError("Напишите хотя бы пару слов об изделии");
      return;
    }
    setError("");
    create.mutate(
      {
        rating,
        comment_text: comment.trim(),
        advantages: advantages.trim() || null,
        disadvantages: disadvantages.trim() || null,
      },
      { onSuccess: onDone },
    );
  };

  return (
    <form onSubmit={submit} className="mx-auto mt-8 max-w-2xl rounded-2xl bg-brand-section p-6 md:p-8">
      <h3 className="font-accent text-2xl font-normal text-brand-ink">Ваш отзыв</h3>
      <div className="mt-4">
        <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.1em] text-brand-muted">Оценка</p>
        <StarInput value={rating} onChange={setRating} />
      </div>
      <FormField label="Отзыв" required error={error} className="mt-5">
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          className={textareaClass}
          placeholder="Расскажите, как вам изделие: ткань, посадка, ощущения"
        />
      </FormField>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <FormField label="Достоинства">
          <input value={advantages} onChange={(e) => setAdvantages(e.target.value)} className={inputClass} />
        </FormField>
        <FormField label="Недостатки">
          <input value={disadvantages} onChange={(e) => setDisadvantages(e.target.value)} className={inputClass} />
        </FormField>
      </div>
      <div className="mt-6 flex flex-wrap gap-3">
        <button type="submit" disabled={create.isPending} className={btnPrimary}>
          {create.isPending ? "Отправляем…" : "Отправить отзыв"}
        </button>
        <button type="button" onClick={onDone} className={btnOutline}>
          Отмена
        </button>
      </div>
    </form>
  );
}

export function ReviewsSection({ productId }: { productId: number }) {
  const { isAuthenticated } = useAuth();
  const pathname = usePathname();
  const [sort, setSort] = useState<ReviewSort>("newest");
  const [formOpen, setFormOpen] = useState(false);

  const summary = useReviewSummary(productId);
  const reviews = useInfiniteReviews(productId, { limit: 6, sort });
  const list = reviews.data?.pages.flat() ?? [];

  const avg = summary.data?.average_rating ?? 0;
  const total = summary.data?.total_reviews ?? 0;
  const distribution = summary.data?.distribution ?? {};

  return (
    <section className="container-page py-12 md:py-20">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-brand-muted">Отзывы</p>
          <h2 className="mt-1 font-accent text-3xl font-normal text-brand-ink md:text-4xl">
            Впечатления ценителей
          </h2>
          <p className="mt-2 text-base text-brand-muted">
            Реальный опыт носки и тактильные ощущения покупателей марки KOCHEVNIK
          </p>
        </div>

        <div className="flex items-center gap-4 rounded-xl bg-brand-section px-6 py-4">
          <span className="text-5xl font-light leading-none text-brand-ink">
            {total > 0 ? formatRating(avg) : "—"}
          </span>
          <div>
            <Stars value={avg} />
            <p className="mt-1 text-xs font-semibold uppercase tracking-[0.04em] text-brand-muted">
              {total} {pluralize(total, "отзыв", "отзыва", "отзывов")}
            </p>
          </div>
        </div>
      </div>

      {total > 0 ? (
        <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-col gap-1.5 text-xs text-brand-muted">
            {[5, 4, 3, 2, 1].map((star) => {
              const count = distribution[String(star)] ?? 0;
              return (
                <div key={star} className="flex items-center gap-2">
                  <span className="w-3">{star}</span>
                  <span className="h-1.5 w-40 overflow-hidden rounded-full bg-brand-sand">
                    <span
                      className="block h-full rounded-full bg-brand-accent"
                      style={{ width: `${total ? (count / total) * 100 : 0}%` }}
                    />
                  </span>
                  <span>{count}</span>
                </div>
              );
            })}
          </div>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as ReviewSort)}
            aria-label="Сортировка отзывов"
            className="h-10 rounded-full border border-brand-line-strong bg-transparent px-4 text-sm text-brand-ink-2 outline-none"
          >
            {REVIEW_SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      ) : null}

      <div className="mt-8">
        {reviews.isLoading ? (
          <div className="grid gap-5 md:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-56 animate-pulse rounded-xl bg-brand-sand" />
            ))}
          </div>
        ) : list.length === 0 ? (
          <div className="rounded-xl bg-brand-section px-6 py-12 text-center">
            <p className="font-accent text-xl font-medium text-brand-ink">Пока нет отзывов</p>
            <p className="mt-1 text-sm text-brand-muted">Станьте первым, кто поделится впечатлениями.</p>
          </div>
        ) : (
          <div className="columns-1 gap-5 md:columns-2 lg:columns-3">
            {list.map((r) => (
              <ReviewCard key={r.id} review={r} />
            ))}
          </div>
        )}
      </div>

      <div className="mt-6 flex flex-wrap justify-center gap-4">
        {reviews.hasNextPage ? (
          <button
            type="button"
            onClick={() => reviews.fetchNextPage()}
            disabled={reviews.isFetchingNextPage}
            className={btnSquare}
          >
            {reviews.isFetchingNextPage ? "Загрузка…" : "Показать ещё"}
          </button>
        ) : null}
        {isAuthenticated ? (
          !formOpen ? (
            <button type="button" onClick={() => setFormOpen(true)} className={btnSquare}>
              Написать отзыв
            </button>
          ) : null
        ) : (
          <Link href={`/login?next=${encodeURIComponent(pathname)}`} className="text-sm text-brand-muted underline underline-offset-4">
            Войдите, чтобы оставить отзыв
          </Link>
        )}
      </div>

      {formOpen ? <ReviewForm productId={productId} onDone={() => setFormOpen(false)} /> : null}
    </section>
  );
}
