import type { Metadata } from "next";
import { OrdersAdmin } from "@/components/admin/orders-admin";

export const metadata: Metadata = { title: "Админка: заказы" };

export default function AdminOrdersPage() {
  return <OrdersAdmin />;
}

// Эти страницы открываются только после входа, поэтому проверку мгновенной навигации отключаем
export const instant = false;
