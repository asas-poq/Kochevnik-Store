import { Suspense } from "react";
import { ShopShell } from "@/components/layout/shop-shell";
import { ProductView } from "@/components/product/product-view";
import { PageSkeleton } from "@/components/shared/page-skeleton";

async function ProductContent({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <ProductView slug={slug} />;
}

export default function ProductPage({ params }: { params: Promise<{ slug: string }> }) {
  return (
    <ShopShell>
      <Suspense fallback={<PageSkeleton />}>
        <ProductContent params={params} />
      </Suspense>
    </ShopShell>
  );
}
