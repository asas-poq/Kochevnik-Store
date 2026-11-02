import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cleanParams } from "@/lib/params";
import { qk } from "@/lib/query-keys";
import type { CatalogQuery, Schema, Season } from "@/types";

type ProductDetail = Schema<"ProductDetailOut">;
type ProductImage = Schema<"ProductImageOut">;

/* ----------------------------- Чтение ----------------------------- */

export interface RecommendationsParams {
  limit?: number; // сколько товаров в каждой секции (1–24)
  category?: string; // slug категории
  season?: Season;
}

// Главная: popular, seasonal, new_arrivals, on_sale
export function useRecommendations(params: RecommendationsParams = {}) {
  return useQuery({
    queryKey: qk.recommendations(params),
    queryFn: async () =>
      (
        await api.get<Schema<"RecommendationsOut">>("/api/v1/products", {
          params: cleanParams(params),
        })
      ).data,
  });
}

async function fetchCatalog(filters: CatalogQuery) {
  const { data } = await api.get<Schema<"PaginatedProductsOut">>(
    "/api/v1/products/catalog",
    { params: cleanParams(filters) },
  );
  return data;
}

// Каталог с постраничной навигацией (page / per_page)
export function useCatalog(
  filters: CatalogQuery,
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: qk.catalog(filters),
    queryFn: () => fetchCatalog(filters),
    placeholderData: keepPreviousData, // пока грузится новая страница, показываем старую
    enabled: options.enabled ?? true,
  });
}

// Каталог с кнопкой «Показать ещё»: страницы подгружаются одна за другой
export function useInfiniteCatalog(filters: Omit<CatalogQuery, "page">) {
  return useInfiniteQuery({
    queryKey: qk.catalogInfinite(filters),
    initialPageParam: 1,
    queryFn: ({ pageParam }) => fetchCatalog({ ...filters, page: pageParam }),
    getNextPageParam: (last) =>
      last.page < last.total_pages ? last.page + 1 : undefined,
    placeholderData: keepPreviousData,
  });
}

// Карточка товара по slug
export function useProduct(slug: string | undefined) {
  return useQuery({
    queryKey: qk.product(slug ?? ""),
    enabled: Boolean(slug),
    queryFn: async () =>
      (
        await api.get<ProductDetail>(
          `/api/v1/products/${encodeURIComponent(slug as string)}`,
        )
      ).data,
  });
}

/* ------------------------ Админка: товары ------------------------ */

export function useCreateProduct() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: Schema<"ProductCreateIn">) =>
      (await api.post<ProductDetail>("/api/v1/products", payload)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.products });
      toast.success("Товар создан");
    },
  });
}

export function useUpdateProduct() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: {
      productId: number;
      data: Schema<"ProductUpdateIn">;
    }) =>
      (
        await api.patch<ProductDetail>(
          `/api/v1/products/${vars.productId}`,
          vars.data,
        )
      ).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.products });
      toast.success("Товар сохранён");
    },
  });
}

// Загрузка одного или нескольких фото (поле формы называется "files")
export function useUploadProductImages() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: { productId: number; files: File[] }) => {
      const form = new FormData();
      vars.files.forEach((file) => form.append("files", file));
      return (
        await api.post<ProductImage[]>(
          `/api/v1/products/${vars.productId}/images`,
          form,
          { timeout: 120_000 },
        )
      ).data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.products });
      toast.success("Фото загружены");
    },
  });
}

// Новый порядок фото: массив id в нужной последовательности
export function useReorderProductImages() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: { productId: number; imageIds: number[] }) =>
      (
        await api.put<ProductImage[]>(
          `/api/v1/products/${vars.productId}/images/order`,
          { image_ids: vars.imageIds },
        )
      ).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.products });
    },
  });
}

export function useDeleteProductImage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: { productId: number; imageId: number }) => {
      await api.delete(
        `/api/v1/products/${vars.productId}/images/${vars.imageId}`,
      );
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.products });
      toast.success("Фото удалено");
    },
  });
}
