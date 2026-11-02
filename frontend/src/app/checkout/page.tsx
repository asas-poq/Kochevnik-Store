import type { Metadata } from "next";
import { CheckoutView } from "@/components/checkout/checkout-view";
import { ShopShell } from "@/components/layout/shop-shell";

export const metadata: Metadata = { title: "Оформление заказа" };

export default function CheckoutPage() {
  return (
    <ShopShell>
      <CheckoutView />
    </ShopShell>
  );
}
