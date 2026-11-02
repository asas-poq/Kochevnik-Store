"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity,
  LogOut,
  Menu,
  MessageSquare,
  Package,
  Radar,
  ShoppingCart,
  Store,
  Users,
} from "lucide-react";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth, useLogout, useMe } from "@/hooks/use-auth";
import { useRequireAuth } from "@/hooks/use-require-auth";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/admin/orders", label: "Заказы", icon: ShoppingCart },
  { href: "/admin/products", label: "Товары", icon: Package },
  { href: "/admin/reviews", label: "Отзывы", icon: MessageSquare },
  { href: "/admin/users", label: "Пользователи", icon: Users },
  { href: "/admin/parser", label: "Парсер", icon: Radar },
  { href: "/admin/system", label: "Система", icon: Activity },
];

function NavLinks({ pathname, onNavigate }: { pathname: string; onNavigate?: () => void }) {
  return (
    <nav className="flex flex-col gap-1" aria-label="Разделы админки">
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = pathname === href || pathname.startsWith(`${href}/`);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              active
                ? "bg-sidebar-accent text-sidebar-accent-foreground"
                : "text-sidebar-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
            )}
          >
            <Icon className="size-4" />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

// Каркас админки: боковое меню, верхняя панель, защита по роли
export function AdminShell({ children }: { children: React.ReactNode }) {
  const gate = useRequireAuth({ adminOnly: true });
  const pathname = usePathname();
  const router = useRouter();
  const { user } = useAuth();
  const logout = useLogout();
  const [menuOpen, setMenuOpen] = useState(false);
  useMe(); // обновляем роль пользователя

  // Включаем холодную тему на весь документ (чтобы окна и меню тоже были в ней)
  useEffect(() => {
    document.documentElement.classList.add("admin-theme");
    return () => document.documentElement.classList.remove("admin-theme");
  }, []);

  if (gate === "loading") {
    return (
      <div className="min-h-dvh bg-background p-8">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="mt-6 h-64 w-full" />
      </div>
    );
  }

  if (gate === "forbidden") {
    return (
      <div className="grid min-h-dvh place-items-center bg-background p-6">
        <div className="max-w-sm rounded-lg border border-border bg-card p-8 text-center">
          <h1 className="text-xl font-semibold text-foreground">Нет доступа</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Админка доступна только администраторам магазина.
          </p>
          <Link
            href="/"
            className="mt-6 inline-flex h-9 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
          >
            На сайт
          </Link>
        </div>
      </div>
    );
  }

  const brand = (
    <Link href="/admin/orders" className="flex items-center gap-2 px-3 text-sidebar-foreground">
      <span className="font-logo text-sm tracking-[0.2em] text-white">KOCHEVNIK</span>
      <span className="rounded bg-sidebar-primary/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-sidebar-primary">
        admin
      </span>
    </Link>
  );

  return (
    <div className="flex min-h-dvh bg-background text-foreground">
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col gap-6 bg-sidebar py-5 text-sidebar-foreground lg:flex">
        {brand}
        <div className="flex-1 px-3">
          <NavLinks pathname={pathname} />
        </div>
        <div className="px-3">
          <Link
            href="/"
            className="flex items-center gap-3 rounded-md px-3 py-2 text-sm text-sidebar-foreground hover:bg-sidebar-accent/60"
          >
            <Store className="size-4" /> В магазин
          </Link>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-3 border-b border-border bg-card/90 px-4 backdrop-blur md:px-8">
          <button
            type="button"
            onClick={() => setMenuOpen(true)}
            aria-label="Открыть меню"
            className="grid size-9 place-items-center rounded-md hover:bg-accent lg:hidden"
          >
            <Menu className="size-5" />
          </button>
          <span className="hidden text-sm text-muted-foreground lg:block">Панель управления</span>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <span className="hidden text-muted-foreground sm:inline">{user?.full_name}</span>
            <ThemeToggle variant="admin" />
            <button
              type="button"
              disabled={logout.isPending}
              onClick={() => logout.mutate(undefined, { onSuccess: () => router.push("/") })}
              className="flex items-center gap-1.5 rounded-md border border-input px-3 py-1.5 text-sm hover:bg-accent"
            >
              <LogOut className="size-4" /> Выйти
            </button>
          </div>
        </header>

        <main className="flex-1 p-4 md:p-8">{children}</main>
      </div>

      <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
        <SheetContent side="left" className="bg-sidebar p-0 text-sidebar-foreground">
          <SheetHeader className="p-5">
            <SheetTitle className="font-logo text-sm tracking-[0.2em] text-white">KOCHEVNIK ADMIN</SheetTitle>
          </SheetHeader>
          <div className="px-3">
            <NavLinks pathname={pathname} onNavigate={() => setMenuOpen(false)} />
            <Link
              href="/"
              onClick={() => setMenuOpen(false)}
              className="mt-4 flex items-center gap-3 rounded-md px-3 py-2 text-sm hover:bg-sidebar-accent/60"
            >
              <Store className="size-4" /> В магазин
            </Link>
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
