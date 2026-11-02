import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { Schema } from "@/types";

type User = Schema<"UserOut">;
type TokenPair = Schema<"TokenPairOut">;

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: User | null;
  // true, когда данные из localStorage уже прочитаны (нужно, чтобы не мигала кнопка «Войти»)
  hasHydrated: boolean;

  // Сохранить результат входа/регистрации/обновления токена
  setSession: (pair: TokenPair) => void;
  // Обновить только данные пользователя (например, после правки профиля)
  setUser: (user: User) => void;
  // Выйти: стереть токены и пользователя
  logout: () => void;
  setHasHydrated: (value: boolean) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      hasHydrated: false,

      setSession: (pair) =>
        set({
          accessToken: pair.access_token,
          refreshToken: pair.refresh_token,
          user: pair.user,
        }),
      setUser: (user) => set({ user }),
      logout: () => set({ accessToken: null, refreshToken: null, user: null }),
      setHasHydrated: (value) => set({ hasHydrated: value }),
    }),
    {
      name: "kochevnik-auth", // ключ в localStorage
      version: 1,
      storage: createJSONStorage(() => localStorage),
      // Читаем localStorage вручную в providers.tsx, уже после загрузки страницы
      skipHydration: true,
      // В localStorage кладём только данные, а не функции и флаг hasHydrated
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        user: state.user,
      }),
      onRehydrateStorage: () => (state) => {
        state?.setHasHydrated(true);
      },
    },
  ),
);

// Удобные проверки для компонентов
export const selectIsAuthenticated = (s: AuthState) => Boolean(s.accessToken);
export const selectIsAdmin = (s: AuthState) => s.user?.role === "admin";
