import type { Metadata } from "next";
import { Suspense } from "react";
import { CatalogView } from "@/components/catalog/catalog-view";
import { ShopShell } from "@/components/layout/shop-shell";
import { PageSkeleton } from "@/components/shared/page-skeleton";

export const metadata: Metadata = { title: "Каталог" };

export default function CatalogPage() {
  return (
    <ShopShell>
      {/* Suspense нужен, потому что каталог читает параметры из адреса (?category=…) */}
      <Suspense fallback={<PageSkeleton />}>
        <CatalogView />
      </Suspense>
    </ShopShell>
  );
}
