import { Suspense } from "react";
import { AdminShell } from "@/components/admin/admin-shell";

// Отдельный каркас админки (без шапки и подвала магазина)
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={null}>
      <AdminShell>{children}</AdminShell>
    </Suspense>
  );
}
