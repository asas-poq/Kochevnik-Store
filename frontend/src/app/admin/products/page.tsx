import type { Metadata } from "next";
import { ProductsAdmin } from "@/components/admin/products-admin";

export const metadata: Metadata = { title: "Админка: товары" };

export default function AdminProductsPage() {
  return <ProductsAdmin />;
}

// Эти страницы открываются только после входа, поэтому проверку мгновенной навигации отключаем
export const instant = false;
