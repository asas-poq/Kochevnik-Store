import { Suspense } from "react";
import { ShopShell } from "@/components/layout/shop-shell";
import { OrderView } from "@/components/order/order-view";
import { PageSkeleton } from "@/components/shared/page-skeleton";

async function OrderContent({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <OrderView orderId={Number(id)} />;
}

export default function OrderPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <ShopShell>
      <Suspense fallback={<PageSkeleton />}>
        <OrderContent params={params} />
      </Suspense>
    </ShopShell>
  );
}
