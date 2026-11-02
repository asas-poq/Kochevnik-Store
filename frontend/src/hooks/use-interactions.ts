import { useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import { useAuth } from "@/hooks/use-auth";
import type { ReviewSort, Schema } from "@/types";

type Review = Schema<"ReviewOut">;
type MyReview = Schema<"MyReviewOut">;

/* ------------------------------ Лайки ------------------------------ */

// Проходит по любым данным в кеше и обновляет сердечко у нужного товара.
// Так лайк мгновенно меняется и в каталоге, и на главной, и в карточке товара.
function patchLike<T>(
  data: T,
  productId: number,
  isLiked: boolean,
  likesCount: number,
): T {
  if (Array.isArray(data)) {
    return data.map((item) =>
      patchLike(item, productId, isLiked, likesCount),
    ) as unknown as T;
  }
  if (data && typeof data === "object") {
    const source = data as Record<string, unknown>;
    const result: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(source)) {
      result[key] = patchLike(value, productId, isLiked, likesCount);
    }
    if (source.id === productId && "is_liked_by_me" in source) {
      result.is_liked_by_me = isLiked;
      result.likes_count = likesCount;
    }
    return result as T;
  }
  return data;
}

// Переключатель лайка. Если пользователь не вошёл, предлагает войти.
export function useToggleLike() {
  const qc = useQueryClient();
  const router = useRouter();
  const { isAuthenticated } = useAuth();

  const mutation = useMutation({
    mutationFn: async (productId: number) =>
      (
        await api.post<Schema<"LikeToggleOut">>(
          `/api/v1/interactions/products/${productId}/like`,
        )
      ).data,
    onSuccess: (res) => {
      qc.setQueriesData({ queryKey: qk.products }, (old: unknown) =>
        old ? patchLike(old, res.product_id, res.is_liked, res.likes_count) : old,
      );
      qc.invalidateQueries({ queryKey: qk.likes });
    },
  });

  const { mutate } = mutation;
  const toggle = useCallback(
    (productId: number) => {
      if (!isAuthenticated) {
        toast("Войдите, чтобы добавлять товары в избранное", {
          action: { label: "Войти", onClick: () => router.push("/login") },
        });
        return;
      }
      mutate(productId);
    },
    [isAuthenticated, mutate, router],
  );

  return {
    toggle,
    isPending: mutation.isPending,
    pendingProductId: mutation.isPending ? mutation.variables : undefined,
  };
}

// Избранное текущего пользователя
export function useMyLikes(params: { limit?: number; offset?: number } = {}) {
  const { isAuthenticated, hasHydrated } = useAuth();
  return useQuery({
    queryKey: qk.myLikes(params),
    enabled: hasHydrated && isAuthenticated,
    queryFn: async () =>
      (
        await api.get<Schema<"ProductCardOut">[]>(
          "/api/v1/interactions/my-likes",
          { params },
        )
      ).data,
  });
}

/* ----------------------------- Отзывы ----------------------------- */

export interface ReviewsParams {
  limit?: number;
  offset?: number;
  sort?: ReviewSort;
  rating?: number;
  only_verified?: boolean;
}

// Отзывы одним списком (с limit/offset)
export function useReviews(productId: number | undefined, params: ReviewsParams = {}) {
  return useQuery({
    queryKey: qk.productReviews(productId ?? 0, params),
    enabled: Boolean(productId),
    queryFn: async () =>
      (
        await api.get<Review[]>(
          `/api/v1/interactions/products/${productId}/reviews`,
          { params: cleanReviewParams(params) },
        )
      ).data,
  });
}

// Отзывы с кнопкой «Показать ещё»
export function useInfiniteReviews(
  productId: number | undefined,
  params: Omit<ReviewsParams, "offset"> & { limit?: number } = {},
) {
  const limit = params.limit ?? 3;
  return useInfiniteQuery({
    queryKey: qk.productReviews(productId ?? 0, { ...params, limit, infinite: true }),
    enabled: Boolean(productId),
    initialPageParam: 0,
    queryFn: async ({ pageParam }) =>
      (
        await api.get<Review[]>(
          `/api/v1/interactions/products/${productId}/reviews`,
          { params: cleanReviewParams({ ...params, limit, offset: pageParam }) },
        )
      ).data,
    getNextPageParam: (lastPage, allPages) =>
      lastPage.length < limit
        ? undefined
        : allPages.reduce((sum, page) => sum + page.length, 0),
  });
}

function cleanReviewParams(params: ReviewsParams) {
  const result: Record<string, unknown> = {};
  if (params.limit !== undefined) result.limit = params.limit;
  if (params.offset !== undefined) result.offset = params.offset;
  if (params.sort) result.sort = params.sort;
  if (params.rating) result.rating = params.rating;
  if (params.only_verified) result.only_verified = true;
  return result;
}

// Средняя оценка и распределение по звёздам
export function useReviewSummary(productId: number | undefined) {
  return useQuery({
    queryKey: qk.reviewSummary(productId ?? 0),
    enabled: Boolean(productId),
    queryFn: async () =>
      (
        await api.get<Schema<"ReviewSummaryOut">>(
          `/api/v1/interactions/products/${productId}/reviews/summary`,
        )
      ).data,
  });
}

// Оставить отзыв (попадает на модерацию)
export function useCreateReview(productId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: Schema<"ReviewCreateIn">) =>
      (
        await api.post<Review>(
          `/api/v1/interactions/products/${productId}/reviews`,
          payload,
        )
      ).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.reviews });
      toast.success("Спасибо! Отзыв появится после проверки модератором");
    },
  });
}

export function useUpdateReview() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: { reviewId: number; data: Schema<"ReviewUpdateIn"> }) =>
      (
        await api.patch<Review>(
          `/api/v1/interactions/reviews/${vars.reviewId}`,
          vars.data,
        )
      ).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.reviews });
      toast.success("Отзыв обновлён");
    },
  });
}

export function useDeleteReview() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (reviewId: number) => {
      await api.delete(`/api/v1/interactions/reviews/${reviewId}`);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.reviews });
      qc.invalidateQueries({ queryKey: qk.products });
      toast.success("Отзыв удалён");
    },
  });
}

// Мои отзывы (профиль)
export function useMyReviews(params: { limit?: number; offset?: number } = {}) {
  const { isAuthenticated, hasHydrated } = useAuth();
  return useQuery({
    queryKey: qk.myReviews(params),
    enabled: hasHydrated && isAuthenticated,
    queryFn: async () =>
      (await api.get<MyReview[]>("/api/v1/interactions/my-reviews", { params }))
        .data,
  });
}

/* ------------------------ Админка: модерация ------------------------ */

export function usePendingReviews(params: { limit?: number; offset?: number } = {}) {
  const { isAdmin, hasHydrated } = useAuth();
  return useQuery({
    queryKey: qk.pendingReviews(params),
    enabled: hasHydrated && isAdmin,
    queryFn: async () =>
      (
        await api.get<Review[]>("/api/v1/interactions/admin/reviews/pending", {
          params,
        })
      ).data,
  });
}

export function useApproveReview() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (reviewId: number) =>
      (
        await api.post<Review>(
          `/api/v1/interactions/admin/reviews/${reviewId}/approve`,
        )
      ).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.reviews });
      qc.invalidateQueries({ queryKey: qk.products });
      toast.success("Отзыв одобрен");
    },
  });
}

export function useRejectReview() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (reviewId: number) => {
      await api.post(`/api/v1/interactions/admin/reviews/${reviewId}/reject`);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.reviews });
      toast.success("Отзыв отклонён");
    },
  });
}

// Ответ магазина на отзыв
export function useReplyToReview() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: { reviewId: number; adminReply: string }) =>
      (
        await api.patch<Review>(
          `/api/v1/interactions/reviews/${vars.reviewId}/admin-reply`,
          { admin_reply: vars.adminReply },
        )
      ).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.reviews });
      toast.success("Ответ сохранён");
    },
  });
}

// Отзывы конкретного пользователя (страница пользователя в админке)
export function useUserReviews(
  userId: number | undefined,
  params: { limit?: number; offset?: number } = {},
) {
  const { isAdmin, hasHydrated } = useAuth();
  return useQuery({
    queryKey: qk.userReviews(userId ?? 0, params),
    enabled: hasHydrated && isAdmin && Boolean(userId),
    queryFn: async () =>
      (
        await api.get<MyReview[]>(
          `/api/v1/interactions/admin/users/${userId}/reviews`,
          { params },
        )
      ).data,
  });
}
