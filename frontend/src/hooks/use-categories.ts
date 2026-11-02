import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import type { Schema } from "@/types";

// Дерево категорий (меняется редко, поэтому кешируем на 10 минут)
export function useCategories() {
  return useQuery({
    queryKey: qk.categories,
    staleTime: 10 * 60_000,
    queryFn: async () =>
      (await api.get<Schema<"CategoryTreeOut">[]>("/api/v1/categories")).data,
  });
}

// Одна категория со своими подкатегориями
export function useCategory(slug: string | undefined) {
  return useQuery({
    queryKey: qk.category(slug ?? ""),
    enabled: Boolean(slug),
    staleTime: 10 * 60_000,
    queryFn: async () =>
      (
        await api.get<Schema<"CategoryTreeOut">>(
          `/api/v1/categories/${encodeURIComponent(slug as string)}`,
        )
      ).data,
  });
}
