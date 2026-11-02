import axios, {
  type AxiosError,
  type InternalAxiosRequestConfig,
} from "axios";
import { toast } from "sonner";
import { useAuthStore } from "@/stores/auth-store";
import type { Schema } from "@/types";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/* ---------------------------- Ошибки API ---------------------------- */

// Ошибка с кодом и текстом от бэкенда ({detail, code})
export class ApiError extends Error {
  status: number; // HTTP-статус (0 — сервер вообще не ответил)
  code: string; // машинный код ошибки от бэкенда

  constructor(message: string, status: number, code: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

// Превращает любую ошибку (axios, сеть, обычный Error) в ApiError
export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;

  if (axios.isAxiosError(error)) {
    // Ответа нет — проблемы с сетью или сервер выключен
    if (!error.response) {
      return new ApiError(
        "Не удалось связаться с сервером. Проверьте интернет и попробуйте ещё раз.",
        0,
        "network_error",
      );
    }

    const { status, data } = error.response;
    const body = data as
      | { detail?: unknown; code?: unknown }
      | null
      | undefined;
    const detail = body?.detail;

    // Обычная ошибка бэкенда: { detail: "текст", code: "some_code" }
    if (typeof detail === "string" && detail) {
      const code = typeof body?.code === "string" ? body.code : "unknown";
      return new ApiError(detail, status, code);
    }

    // Ошибка проверки данных (422): detail — список проблем по полям
    if (Array.isArray(detail)) {
      const text = detail
        .map((item) =>
          typeof item?.msg === "string" ? item.msg : "Некорректные данные",
        )
        .join("; ");
      return new ApiError(
        text || "Проверьте правильность введённых данных",
        status,
        "validation_error",
      );
    }

    return new ApiError(`Ошибка сервера (${status})`, status, "unknown");
  }

  return new ApiError(
    error instanceof Error ? error.message : "Неизвестная ошибка",
    0,
    "unknown",
  );
}

// Текст ошибки для показа пользователю
export function getErrorMessage(error: unknown): string {
  return toApiError(error).message;
}

// Показать ошибку красным уведомлением sonner
export function showApiError(error: unknown) {
  toast.error(getErrorMessage(error));
}

/* ---------------------------- Axios-клиент --------------------------- */

export const api = axios.create({
  baseURL: API_URL,
  timeout: 20_000,
  headers: { Accept: "application/json" },
  // Массивы в параметрах отправляем как ?color=a&color=b (так ждёт FastAPI)
  paramsSerializer: { indexes: null },
});

// Адреса авторизации: для них не нужно пытаться обновлять токен
const AUTH_URLS = ["/auth/login", "/auth/register", "/auth/refresh"];
const isAuthUrl = (url?: string) =>
  Boolean(url && AUTH_URLS.some((part) => url.includes(part)));

// 1) Перед каждым запросом добавляем токен
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token && !config.headers.Authorization) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Обновление токена. Если уже идёт — все ждут один и тот же запрос.
let refreshPromise: Promise<string | null> | null = null;

function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      const { refreshToken, setSession, logout } = useAuthStore.getState();
      if (!refreshToken) return null;
      try {
        // Используем «голый» axios без перехватчиков, чтобы не зациклиться
        const { data } = await axios.post<Schema<"TokenPairOut">>(
          `${API_URL}/api/v1/auth/refresh`,
          { refresh_token: refreshToken },
        );
        setSession(data);
        return data.access_token;
      } catch {
        // Refresh-токен тоже не подошёл — разлогиниваем
        logout();
        return null;
      } finally {
        refreshPromise = null;
      }
    })();
  }
  return refreshPromise;
}

type RetriableConfig = InternalAxiosRequestConfig & { _retried?: boolean };

// 2) После ответа: на 401 обновляем токен и повторяем запрос один раз
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as RetriableConfig | undefined;

    if (
      error.response?.status === 401 &&
      original &&
      !original._retried &&
      !isAuthUrl(original.url)
    ) {
      original._retried = true;
      const newToken = await refreshAccessToken();
      if (newToken) {
        original.headers.Authorization = `Bearer ${newToken}`;
        return api(original);
      }
    }

    // Все остальные ошибки превращаем в понятный ApiError
    return Promise.reject(toApiError(error));
  },
);
