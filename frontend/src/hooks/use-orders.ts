import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cleanParams } from "@/lib/params";
import { qk } from "@/lib/query-keys";
import { useAuth } from "@/hooks/use-auth";
import type { OrderStatus, Schema } from "@/types";

type Order = Schema<"OrderOut">;

export interface OrdersParams {
  limit?: number;
  offset?: number;
  status?: OrderStatus;
}

// Оформление заказа. В ответе есть payment_url — туда нужно отправить покупателя (СБП).
export function useCreateOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: Schema<"OrderCreateIn">) =>
      (await api.post<Order>("/api/v1/orders", payload)).data,
    onSuccess: (order) => {
      qc.setQueryData(qk.order(order.id), order);
      qc.invalidateQueries({ queryKey: qk.orders });
    },
  });
}

// Мои заказы
export function useMyOrders(params: OrdersParams = {}) {
  const { isAuthenticated, hasHydrated } = useAuth();
  return useQuery({
    queryKey: qk.myOrders(params),
    enabled: hasHydrated && isAuthenticated,
    queryFn: async () =>
      (
        await api.get<Order[]>("/api/v1/orders/my", {
          params: cleanParams(params),
        })
      ).data,
  });
}

// Один заказ. refetchInterval (в мс) включает автообновление, пока ждём оплату.
export function useOrder(
  orderId: number | undefined,
  options: { refetchInterval?: number | false } = {},
) {
  const { isAuthenticated, hasHydrated } = useAuth();
  return useQuery({
    queryKey: qk.order(orderId ?? 0),
    enabled: hasHydrated && isAuthenticated && Boolean(orderId),
    refetchInterval: options.refetchInterval ?? false,
    queryFn: async () =>
      (await api.get<Order>(`/api/v1/orders/${orderId}`)).data,
  });
}

// Отмена заказа
export function useCancelOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (orderId: number) =>
      (await api.post<Order>(`/api/v1/orders/${orderId}/cancel`)).data,
    onSuccess: (order) => {
      qc.setQueryData(qk.order(order.id), order);
      qc.invalidateQueries({ queryKey: qk.orders });
      toast.success("Заказ отменён");
    },
  });
}

// Проверка оплаты (опрашивает платёжную систему и обновляет статус заказа)
export function useCheckPayment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (orderId: number) =>
      (await api.post<Order>(`/api/v1/orders/${orderId}/check-payment`)).data,
    onSuccess: (order) => {
      qc.setQueryData(qk.order(order.id), order);
      qc.invalidateQueries({ queryKey: qk.orders });
    },
  });
}

/* ----------------------------- Админка ----------------------------- */

export interface AdminOrdersParams extends OrdersParams {
  user_id?: number;
  q?: string; // поиск
}

export function useAdminOrders(params: AdminOrdersParams = {}) {
  const { isAdmin, hasHydrated } = useAuth();
  return useQuery({
    queryKey: qk.adminOrders(params),
    enabled: hasHydrated && isAdmin,
    queryFn: async () =>
      (
        await api.get<Order[]>("/api/v1/orders/admin/list", {
          params: cleanParams(params),
        })
      ).data,
  });
}

// Заказы конкретного пользователя
export function useUserOrders(userId: number | undefined, params: OrdersParams = {}) {
  const { isAdmin, hasHydrated } = useAuth();
  return useQuery({
    queryKey: qk.userOrders(userId ?? 0, params),
    enabled: hasHydrated && isAdmin && Boolean(userId),
    queryFn: async () =>
      (
        await api.get<Order[]>(`/api/v1/orders/admin/users/${userId}`, {
          params: cleanParams(params),
        })
      ).data,
  });
}

// Смена статуса: бэкенд разрешает только shipped и completed
export function useAdminSetOrderStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vars: {
      orderId: number;
      status: Schema<"AdminOrderStatusIn">["status"];
    }) =>
      (
        await api.patch<Order>(`/api/v1/orders/admin/${vars.orderId}/status`, {
          status: vars.status,
        })
      ).data,
    onSuccess: (order) => {
      qc.setQueryData(qk.order(order.id), order);
      qc.invalidateQueries({ queryKey: qk.orders });
      toast.success("Статус заказа обновлён");
    },
  });
}
