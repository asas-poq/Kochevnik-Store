import type { Metadata } from "next";
import { Suspense } from "react";
import { RegisterForm } from "@/components/auth/register-form";
import { ShopShell } from "@/components/layout/shop-shell";
import { PageSkeleton } from "@/components/shared/page-skeleton";

export const metadata: Metadata = { title: "Регистрация" };

export default function RegisterPage() {
  return (
    <ShopShell>
      <Suspense fallback={<PageSkeleton />}>
        <RegisterForm />
      </Suspense>
    </ShopShell>
  );
}
