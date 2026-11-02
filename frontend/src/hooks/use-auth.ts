import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import {
  selectIsAdmin,
  selectIsAuthenticated,
  useAuthStore,
} from "@/stores/auth-store";
import type { Schema } from "@/types";

type TokenPair = Schema<"TokenPairOut">;
type User = Schema<"UserOut">;

// Короткий доступ к состоянию входа для компонентов:
// const { user, isAuthenticated, isAdmin, hasHydrated } = useAuth();
export function useAuth() {
  const user = useAuthStore((s) => s.user);
  const hasHydrated = useAuthStore((s) => s.hasHydrated);
  const isAuthenticated = useAuthStore(selectIsAuthenticated);
  const isAdmin = useAuthStore(selectIsAdmin);
  return { user, hasHydrated, isAuthenticated, isAdmin };
}

// Вход по email или телефону
export function useLogin() {
  const qc = useQueryClient();
  const setSession = useAuthStore((s) => s.setSession);
  return useMutation({
    mutationFn: async (payload: Schema<"UserLoginIn">) =>
      (await api.post<TokenPair>("/api/v1/auth/login", payload)).data,
    onSuccess: (pair) => {
      setSession(pair);
      qc.invalidateQueries(); // лайки и прочее личное нужно загрузить заново
      toast.success(`Добро пожаловать, ${pair.user.full_name}!`);
    },
  });
}

// Регистрация (сразу входит в аккаунт)
export function useRegister() {
  const qc = useQueryClient();
  const setSession = useAuthStore((s) => s.setSession);
  return useMutation({
    mutationFn: async (payload: Schema<"UserRegisterIn">) =>
      (await api.post<TokenPair>("/api/v1/auth/register", payload)).data,
    onSuccess: (pair) => {
      setSession(pair);
      qc.invalidateQueries();
      toast.success("Аккаунт создан. Добро пожаловать!");
    },
  });
}

// Выход с этого устройства. Даже если сервер не ответит, локально всё равно выходим.
export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const refreshToken = useAuthStore.getState().refreshToken;
      try {
        await api.post("/api/v1/auth/logout", { refresh_token: refreshToken });
      } catch {
        // игнорируем: выход на сервере не критичен
      }
    },
    onSettled: () => {
      useAuthStore.getState().logout();
      qc.clear();
      toast.success("Вы вышли из аккаунта");
    },
  });
}

// Выход со всех устройств
export function useLogoutAll() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      await api.post("/api/v1/auth/logout-all");
    },
    onSuccess: () => {
      useAuthStore.getState().logout();
      qc.clear();
      toast.success("Вы вышли со всех устройств");
    },
  });
}

// Свежие данные профиля (заодно обновляет user в сторе)
export function useMe() {
  const { isAuthenticated, hasHydrated } = useAuth();
  return useQuery({
    queryKey: qk.me,
    enabled: hasHydrated && isAuthenticated,
    queryFn: async () => {
      const { data } = await api.get<User>("/api/v1/auth/me");
      useAuthStore.getState().setUser(data);
      return data;
    },
  });
}

// Изменение профиля: имя, телефон, город, адрес по умолчанию
export function useUpdateMe() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: Schema<"UserUpdateIn">) =>
      (await api.patch<User>("/api/v1/auth/me", payload)).data,
    onSuccess: (user) => {
      useAuthStore.getState().setUser(user);
      qc.setQueryData(qk.me, user);
      toast.success("Профиль обновлён");
    },
  });
}

// Список активных входов (устройств)
export function useSessions() {
  const { isAuthenticated, hasHydrated } = useAuth();
  return useQuery({
    queryKey: qk.sessions,
    enabled: hasHydrated && isAuthenticated,
    queryFn: async () =>
      (await api.get<Schema<"SessionOut">[]>("/api/v1/auth/sessions")).data,
  });
}
