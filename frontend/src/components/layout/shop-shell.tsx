import { Suspense } from "react";
import { SiteFooter } from "@/components/layout/site-footer";
import { SiteHeader } from "@/components/layout/site-header";

// Общий каркас страниц магазина: шапка сверху, подвал снизу.
// Шапка завёрнута в Suspense, потому что она читает адрес страницы.
export function ShopShell({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Suspense fallback={<div className="h-16 border-b border-brand-line/60 md:h-20" />}>
        <SiteHeader />
      </Suspense>
      <main className="flex-1">{children}</main>
      <SiteFooter />
    </>
  );
}
