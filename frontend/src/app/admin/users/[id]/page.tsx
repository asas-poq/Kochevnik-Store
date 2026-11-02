import { Suspense } from "react";
import { UserDetail } from "@/components/admin/user-detail";
import { Skeleton } from "@/components/ui/skeleton";

async function UserContent({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <UserDetail userId={Number(id)} />;
}

export default function AdminUserPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <Suspense fallback={<Skeleton className="h-64 w-full" />}>
      <UserContent params={params} />
    </Suspense>
  );
}

// Эти страницы открываются только после входа, поэтому проверку мгновенной навигации отключаем
export const instant = false;
