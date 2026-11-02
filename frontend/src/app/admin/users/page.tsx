import type { Metadata } from "next";
import { UsersAdmin } from "@/components/admin/users-admin";

export const metadata: Metadata = { title: "Админка: пользователи" };

export default function AdminUsersPage() {
  return <UsersAdmin />;
}

// Эти страницы открываются только после входа, поэтому проверку мгновенной навигации отключаем
export const instant = false;
