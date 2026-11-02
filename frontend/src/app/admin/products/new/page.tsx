import type { Metadata } from "next";
import { PageHeader } from "@/components/admin/admin-ui";
import { ProductForm } from "@/components/admin/product-form";

export const metadata: Metadata = { title: "Админка: новый товар" };

export default function AdminNewProductPage() {
  return (
    <div>
      <PageHeader title="Новый товар" description="Заполните данные и загрузите фото." />
      <ProductForm />
    </div>
  );
}

// Эти страницы открываются только после входа, поэтому проверку мгновенной навигации отключаем
export const instant = false;
