import type { Metadata } from "next";
import { SystemAdmin } from "@/components/admin/system-admin";

export const metadata: Metadata = { title: "Админка: система" };

export default function AdminSystemPage() {
  return <SystemAdmin />;
}

// Эти страницы открываются только после входа, поэтому проверку мгновенной навигации отключаем
export const instant = false;
