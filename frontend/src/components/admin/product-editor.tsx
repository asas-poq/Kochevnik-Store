"use client";

import { PageHeader } from "@/components/admin/admin-ui";
import { ProductForm } from "@/components/admin/product-form";
import { ErrorState } from "@/components/shared/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useProduct } from "@/hooks/use-products";

// Страница редактирования: загружает товар и показывает форму
export function ProductEditor({ slug }: { slug: string }) {
  const { data, isLoading, isError, refetch } = useProduct(slug);

  if (isLoading) return <Skeleton className="h-96 w-full" />;
  if (isError || !data) return <ErrorState title="Товар не найден" onRetry={() => refetch()} />;

  return (
    <div>
      <PageHeader title={data.name} description={`Редактирование товара · ${data.slug}`} />
      <ProductForm key={data.id} product={data} />
    </div>
  );
}
