import { useMemo } from "react";
import { useMyLikes } from "@/hooks/use-interactions";

// Набор id избранных товаров. Использует тот же запрос, что и шапка сайта, поэтому лишней нагрузки нет.
export function useLikedIds(): Set<number> {
  const { data } = useMyLikes({ limit: 100 });
  return useMemo(() => new Set((data ?? []).map((p) => p.id)), [data]);
}
