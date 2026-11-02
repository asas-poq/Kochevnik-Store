import type { Metadata } from "next";
import { Suspense } from "react";
import { LoginForm } from "@/components/auth/login-form";
import { ShopShell } from "@/components/layout/shop-shell";
import { PageSkeleton } from "@/components/shared/page-skeleton";

export const metadata: Metadata = { title: "Вход" };

export default function LoginPage() {
  return (
    <ShopShell>
      <Suspense fallback={<PageSkeleton />}>
        <LoginForm />
      </Suspense>
    </ShopShell>
  );
}
