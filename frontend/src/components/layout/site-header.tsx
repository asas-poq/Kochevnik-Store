"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Heart, Menu, Search, ShoppingBag, User } from "lucide-react";
import { CartSheet } from "@/components/cart/cart-sheet";
import { Logo } from "@/components/layout/logo";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { useAuth } from "@/hooks/use-auth";
import { useMyLikes } from "@/hooks/use-interactions";
import { NAV_LINKS } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { useCartStore } from "@/stores/cart-store";

// Кружок с числом на иконке (избранное, корзина)
function CountBadge({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <span className="absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center rounded-full bg-brand-ink px-1 text-[10px] font-semibold leading-none text-brand-surface">
      {count > 99 ? "99+" : count}
    </span>
  );
}

function IconLink({
  href,
  label,
  children,
}: {
  href: string;
  label: string;
  children: ReactNode;
}) {
  return (
    <Link
      href={href}
      aria-label={label}
      className="relative grid size-11 place-items-center sm:size-10 rounded-full text-brand-ink transition-colors hover:bg-brand-sand"
    >
      {children}
    </Link>
  );
}

// Поле поиска: по Enter открывает каталог с поисковым запросом
function SearchForm({
  className,
  onDone,
}: {
  className?: string;
  onDone?: () => void;
}) {
  const router = useRouter();
  const [value, setValue] = useState("");

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const q = value.trim();
    router.push(q ? `/catalog?search=${encodeURIComponent(q)}` : "/catalog");
    onDone?.();
  };

  return (
    <form onSubmit={handleSubmit} role="search" className={cn("relative", className)}>
      <Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-brand-subtle" />
      <input
        type="search"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Поиск..."
        aria-label="Поиск по каталогу"
        className="h-10 w-full rounded-full bg-white/80 pl-10 dark:bg-brand-sand pr-4 text-sm tracking-[0.01em] text-brand-ink outline-none placeholder:text-brand-subtle focus:ring-2 focus:ring-brand-accent/30"
      />
    </form>
  );
}

export function SiteHeader() {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const { isAuthenticated, hasHydrated } = useAuth();

  // Количество штук в корзине (показываем только когда данные из localStorage уже прочитаны)
  const cartCount = useCartStore((s) =>
    s.hasHydrated ? s.items.reduce((n, i) => n + i.quantity, 0) : 0,
  );

  const openCart = useCartStore((s) => s.open);

  // Количество избранного (запрос только для вошедших пользователей)
  const likes = useMyLikes({ limit: 100 });
  const likesCount = isAuthenticated ? (likes.data?.length ?? 0) : 0;

  const accountHref = hasHydrated && isAuthenticated ? "/profile" : "/login";
  const likesHref = hasHydrated && isAuthenticated ? "/profile/likes" : "/login";

  return (
    <header className="sticky top-0 z-40 pt-[env(safe-area-inset-top)] border-b border-brand-line/60 bg-header/90 backdrop-blur">
      <div className="container-page flex h-16 items-center gap-3 md:h-20">
        {/* Бургер-меню на телефоне */}
        <button
          type="button"
          onClick={() => setMenuOpen(true)}
          aria-label="Открыть меню"
          className="-ml-2 grid size-11 place-items-center sm:size-10 rounded-full text-brand-ink hover:bg-brand-sand lg:hidden"
        >
          <Menu className="size-6" />
        </button>

        <Logo />

        {/* Меню по центру (на компьютере) */}
        <nav className="mx-auto hidden items-center gap-10 lg:flex" aria-label="Основное меню">
          {NAV_LINKS.map((link) => {
            const active =
              link.href === "/catalog" && pathname.startsWith("/catalog");
            return (
              <Link
                key={link.label}
                href={link.href}
                className={cn(
                  "text-[15px] font-medium tracking-[0.02em] text-brand-ink-2 transition-colors hover:text-brand-accent",
                  active && "text-brand-accent",
                )}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-1 lg:ml-0">
          <SearchForm className="mr-2 hidden w-44 md:block xl:w-60" />
          <ThemeToggle className="hidden md:grid" />
          <IconLink href={likesHref} label="Избранное">
            <Heart className="size-[22px]" />
            <CountBadge count={likesCount} />
          </IconLink>
          <button
            type="button"
            onClick={openCart}
            aria-label="Открыть корзину"
            className="relative grid size-11 place-items-center sm:size-10 rounded-full text-brand-ink transition-colors hover:bg-brand-sand"
          >
            <ShoppingBag className="size-[22px]" />
            <CountBadge count={cartCount} />
          </button>
          {/* На узких телефонах иконка профиля есть в выезжающем меню */}
          <span className="hidden sm:block">
            <IconLink
              href={accountHref}
              label={isAuthenticated ? "Личный кабинет" : "Войти"}
            >
              <User className="size-[22px]" />
            </IconLink>
          </span>
        </div>
      </div>

      <CartSheet />

      {/* Выезжающее меню для телефона */}
      <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
        <SheetContent side="left" className="bg-brand-bg p-0 pb-[env(safe-area-inset-bottom)]">
          <SheetHeader className="border-b border-brand-line p-5">
            <SheetTitle className="font-logo text-base tracking-[0.2em] text-brand-ink">
              KOCHEVNIK
            </SheetTitle>
          </SheetHeader>
          <div className="flex flex-col gap-6 p-5">
            <SearchForm onDone={() => setMenuOpen(false)} />
            <ThemeToggle variant="row" className="-mb-6 md:hidden" />
            <nav className="flex flex-col" aria-label="Меню">
              {NAV_LINKS.map((link) => (
                <Link
                  key={link.label}
                  href={link.href}
                  onClick={() => setMenuOpen(false)}
                  className="border-b border-brand-line/70 py-3.5 text-base font-medium text-brand-ink-2"
                >
                  {link.label}
                </Link>
              ))}
              <Link
                href={accountHref}
                onClick={() => setMenuOpen(false)}
                className="border-b border-brand-line/70 py-3.5 text-base font-medium text-brand-ink-2"
              >
                {isAuthenticated ? "Личный кабинет" : "Войти или зарегистрироваться"}
              </Link>
            </nav>
          </div>
        </SheetContent>
      </Sheet>
    </header>
  );
}
