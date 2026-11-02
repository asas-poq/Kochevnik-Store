import type { Metadata } from "next";
import { CartView } from "@/components/cart/cart-view";
import { ShopShell } from "@/components/layout/shop-shell";

export const metadata: Metadata = { title: "Корзина" };

export default function CartPage() {
  return (
    <ShopShell>
      <CartView />
    </ShopShell>
  );
}
