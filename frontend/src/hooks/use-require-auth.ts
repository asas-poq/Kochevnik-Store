import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/hooks/use-auth";

export type AuthGateStatus = "loading" | "ok" | "forbidden";

// Защита страниц: если пользователь не вошёл, отправляет на /login и после входа возвращает назад.
// adminOnly: страница только для role=admin.
export function useRequireAuth(options: { adminOnly?: boolean } = {}): AuthGateStatus {
  const { isAuthenticated, isAdmin, hasHydrated } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (hasHydrated && !isAuthenticated) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [hasHydrated, isAuthenticated, pathname, router]);

  if (!hasHydrated || !isAuthenticated) return "loading";
  if (options.adminOnly && !isAdmin) return "forbidden";
  return "ok";
}

// Список id товаров, которые пользователь добавил в избранное (для сердечек)
