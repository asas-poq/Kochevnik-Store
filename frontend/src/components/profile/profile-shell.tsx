"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Heart, LogOut, MessageSquare, Package, ShieldCheck, User } from "lucide-react";
import { PageSkeleton } from "@/components/shared/page-skeleton";
import { useAuth, useLogout, useMe } from "@/hooks/use-auth";
import { useRequireAuth } from "@/hooks/use-require-auth";
import { cn } from "@/lib/utils";

const TABS = [
  { href: "/profile", label: "Профиль", icon: User },
  { href: "/profile/orders", label: "Заказы", icon: Package },
  { href: "/profile/likes", label: "Избранное", icon: Heart },
  { href: "/profile/reviews", label: "Отзывы", icon: MessageSquare },
];

// Каркас личного кабинета: меню слева и содержимое справа
export function ProfileShell({ children }: { children: React.ReactNode }) {
  const gate = useRequireAuth();
  const pathname = usePathname();
  const router = useRouter();
  const { user, isAdmin } = useAuth();
  const logout = useLogout();
  useMe(); // обновляем данные профиля (в том числе роль)

  if (gate !== "ok") return <PageSkeleton />;

  return (
    <div className="container-page py-10 md:py-14">
      <h1 className="font-accent text-4xl font-normal text-brand-ink md:text-5xl">Личный кабинет</h1>
      <p className="mt-2 text-brand-muted">{user?.full_name}</p>

      <div className="mt-8 grid gap-8 lg:grid-cols-[240px_1fr]">
        <nav className="flex gap-2 overflow-x-auto lg:flex-col lg:overflow-visible" aria-label="Разделы кабинета">
          {TABS.map(({ href, label, icon: Icon }) => {
            const active = href === "/profile" ? pathname === "/profile" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex shrink-0 items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium transition-colors",
                  active ? "bg-brand-ink text-brand-surface" : "bg-brand-section text-brand-ink-2 hover:bg-brand-sand",
                )}
              >
                <Icon className="size-4" />
                {label}
              </Link>
            );
          })}
          {isAdmin ? (
            <Link
              href="/admin"
              className="flex shrink-0 items-center gap-3 rounded-xl bg-brand-section px-4 py-3 text-sm font-medium text-brand-accent hover:bg-brand-sand"
            >
              <ShieldCheck className="size-4" />
              Админка
            </Link>
          ) : null}
          <button
            type="button"
            disabled={logout.isPending}
            onClick={() => logout.mutate(undefined, { onSuccess: () => router.push("/") })}
            className="flex shrink-0 items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium text-brand-muted transition-colors hover:bg-brand-section hover:text-brand-red"
          >
            <LogOut className="size-4" />
            Выйти
          </button>
        </nav>

        <div className="min-w-0">{children}</div>
      </div>
    </div>
  );
}
