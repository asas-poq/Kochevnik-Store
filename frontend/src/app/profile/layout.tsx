import { Suspense } from "react";
import { ShopShell } from "@/components/layout/shop-shell";
import { ProfileShell } from "@/components/profile/profile-shell";
import { PageSkeleton } from "@/components/shared/page-skeleton";

// Все страницы /profile/* получают шапку, подвал и меню кабинета
export default function ProfileLayout({ children }: { children: React.ReactNode }) {
  return (
    <ShopShell>
      <Suspense fallback={<PageSkeleton />}>
        <ProfileShell>{children}</ProfileShell>
      </Suspense>
    </ShopShell>
  );
}
