import { Skeleton } from "@/components/ui/skeleton";

// Заглушка страницы, пока она загружается
export function PageSkeleton() {
  return (
    <div className="container-page py-10 md:py-14">
      <Skeleton className="h-10 w-1/3 bg-brand-sand" />
      <Skeleton className="mt-4 h-5 w-1/2 bg-brand-sand" />
      <div className="mt-10 grid gap-6 md:grid-cols-2">
        <Skeleton className="h-96 bg-brand-sand" />
        <Skeleton className="h-96 bg-brand-sand" />
      </div>
    </div>
  );
}
