"use client";

import Link from "next/link";
import { Heart } from "lucide-react";
import { ProductCard, ProductCardSkeleton } from "@/components/product/product-card";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { useMyLikes } from "@/hooks/use-interactions";
import { btnPrimary } from "@/lib/styles";

export function LikesView() {
  const { data, isLoading, isError, refetch } = useMyLikes({ limit: 100 });
  const list = data ?? [];

  return (
    <div>
      <h2 className="font-accent text-2xl font-normal text-brand-ink">Избранное</h2>
      <div className="mt-6">
        {isError ? (
          <ErrorState onRetry={() => refetch()} />
        ) : isLoading ? (
          <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <ProductCardSkeleton key={i} />
            ))}
          </div>
        ) : list.length === 0 ? (
          <EmptyState
            icon={<Heart />}
            title="В избранном пока пусто"
            description="Нажимайте на сердечко у товаров, которые вам понравились, и они появятся здесь."
            action={
              <Link href="/catalog" className={btnPrimary}>
                Перейти в каталог
              </Link>
            }
          />
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-3 xl:gap-6">
            {list.map((p) => (
              <ProductCard key={p.id} product={p} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
