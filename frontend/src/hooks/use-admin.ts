import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cleanParams } from "@/lib/params";
import { qk } from "@/lib/query-keys";
import { useAuth } from "@/hooks/use-auth";
import type { Schema } from "@/types";

// Ответы парсера в openapi описаны просто как «объект», поэтому тип свободный
export type LooseObject = Record<string, unknown>;

type RefetchOption = { refetchInterval?: number | false };

/* ------------------------------ Парсер ------------------------------ */

export function useParserStatus(options: RefetchOption = {}) {
  const { isAdmin, hasHydrated } = useAuth();
  return useQuery({
    queryKey: qk.parserStatus,
    enabled: hasHydrated && isAdmin,
    refetchInterval: options.refetchInterval ?? false,
    queryFn: async () =>
      (await api.get<LooseObject>("/api/v1/parser/status")).data,
  });
}

export function useParserQueueStats(options: RefetchOption = {}) {
  const { isAdmin, hasHydrated } = useAuth();
  return useQuery({
    queryKey: qk.parserQueueStats,
    enabled: hasHydrated && isAdmin,
    refetchInterval: options.refetchInterval ?? false,
    queryFn: async () =>
      (await api.get<LooseObject>("/api/v1/parser/queue/stats")).data,
  });
}

export function useParserQueue(
  params: { status_filter?: string; limit?: number } = {},
) {
  const { isAdmin, hasHydrated } = useAuth();
  return useQuery({
    queryKey: qk.parserQueue(params),
    enabled: hasHydrated && isAdmin,
    queryFn: async () =>
      (
        await api.get<Schema<"CrawlQueueItemOut">[]>("/api/v1/parser/queue", {
          params: cleanParams(params),
        })
      ).data,
  });
}

// Найти новые ссылки на товары (запускается в фоне)
export function useParserDiscover() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () =>
      (await api.post<LooseObject>("/api/v1/parser/discover")).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["parser"] });
      toast.success("Поиск новых товаров запущен");
    },
  });
}

// Собрать данные товаров из очереди (запускается в фоне)
export function useParserScrape() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (params: { limit?: number; retry_errors?: boolean } = {}) =>
      (
        await api.post<LooseObject>("/api/v1/parser/scrape", null, {
          params: cleanParams(params),
        })
      ).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["parser"] });
      toast.success("Сбор данных запущен");
    },
  });
}

// Разобрать одну страницу без записи в базу (может занять до пары минут)
export function useParserPreview() {
  return useMutation({
    mutationFn: async (params: { url: string; save_html?: boolean }) =>
      (
        await api.get<unknown>("/api/v1/parser/preview", {
          params: cleanParams(params),
          timeout: 120_000,
        })
      ).data,
  });
}

/* ------------------------------ Система ------------------------------ */

// Состояние сервера (/health)
export function useHealth(options: RefetchOption = {}) {
  return useQuery({
    queryKey: qk.health,
    refetchInterval: options.refetchInterval ?? false,
    retry: false,
    queryFn: async () => (await api.get<unknown>("/health")).data,
  });
}

// Проверка Telegram-уведомлений (отправляет тестовое сообщение)
export function useTelegramTest() {
  return useMutation({
    mutationFn: async () =>
      (await api.post<LooseObject>("/api/v1/payments/telegram/test")).data,
    onSuccess: () => {
      toast.success("Тестовое сообщение отправлено в Telegram");
    },
  });
}

// Тестовая оплата: работает только при тестовых ключах платёжной системы
export function useSimulatePayment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: {
      orderId: number;
      outcome: "succeeded" | "canceled";
    }) =>
      (
        await api.post<Schema<"SandboxPaymentOut">>(
          `/api/v1/payments/sandbox/orders/${vars.orderId}/simulate`,
          null,
          { params: { outcome: vars.outcome } },
        )
      ).data,
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: qk.orders });
      toast.success(res.message);
    },
  });
}
