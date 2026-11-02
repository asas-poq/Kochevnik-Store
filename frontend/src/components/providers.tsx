"use client";

import { useEffect, useState } from "react";
import {
  MutationCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { ThemeProvider, useTheme } from "next-themes";
import { Toaster, toast } from "sonner";
import { ApiError, getErrorMessage } from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";
import { useCartStore } from "@/stores/cart-store";

// Уведомления подстраиваются под светлую/тёмную тему
function ThemedToaster() {
  const { resolvedTheme } = useTheme();
  return (
    <Toaster
      theme={resolvedTheme === "dark" ? "dark" : "light"}
      position="top-center"
      closeButton
      richColors
    />
  );
}

export function Providers({ children }: { children: React.ReactNode }) {
  // Клиент react-query создаём один раз на всё время жизни страницы
  const [queryClient] = useState(
    () =>
      new QueryClient({
        // Любая ошибка при отправке данных (мутации) сразу показывается тостом
        mutationCache: new MutationCache({
          onError: (error) => {
            toast.error(getErrorMessage(error));
          },
        }),
        defaultOptions: {
          queries: {
            staleTime: 60_000, // данные считаем свежими 1 минуту
            refetchOnWindowFocus: false,
            // Ошибки 4xx (нет доступа, не найдено) повторять бессмысленно
            retry: (failureCount, error) => {
              if (
                error instanceof ApiError &&
                error.status >= 400 &&
                error.status < 500
              ) {
                return false;
              }
              return failureCount < 2;
            },
          },
        },
      }),
  );

  // Достаём сохранённые вход и корзину из localStorage уже в браузере
  // (так HTML с сервера и первый кадр в браузере совпадают)
  useEffect(() => {
    useAuthStore.persist.rehydrate();
    useCartStore.persist.rehydrate();
  }, []);

  return (
    <ThemeProvider
      attribute="class"
      defaultTheme="system" // сам выбирает светлую или тёмную, как настроено в телефоне или компьютере
      enableSystem
      disableTransitionOnChange
    >
      <QueryClientProvider client={queryClient}>
        {children}
        <ThemedToaster />
      </QueryClientProvider>
    </ThemeProvider>
  );
}
