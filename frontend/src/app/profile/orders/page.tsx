import type { Metadata } from "next";
import { OrdersList } from "@/components/profile/orders-list";

export const metadata: Metadata = { title: "Мои заказы" };

export default function ProfileOrdersPage() {
  return <OrdersList />;
}

// Эти страницы открываются только после входа, поэтому проверку мгновенной навигации отключаем
export const instant = false;
