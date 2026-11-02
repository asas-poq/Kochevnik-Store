import Link from "next/link";
import { cn } from "@/lib/utils";

export interface Crumb {
  label: string;
  href?: string;
}

// «Хлебные крошки»: Главная / Каталог / Категория
export function Breadcrumbs({
  items,
  uppercase = false,
  className,
}: {
  items: Crumb[];
  uppercase?: boolean;
  className?: string;
}) {
  return (
    <nav
      aria-label="Навигация"
      className={cn(
        "flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-brand-muted",
        uppercase && "font-medium uppercase tracking-[0.08em]",
        className,
      )}
    >
      {items.map((item, i) => {
        const last = i === items.length - 1;
        return (
          <span key={`${item.label}-${i}`} className="flex items-center gap-2">
            {item.href && !last ? (
              <Link href={item.href} className="transition-colors hover:text-brand-accent">
                {item.label}
              </Link>
            ) : (
              <span className={cn(last && "text-brand-ink-2")}>{item.label}</span>
            )}
            {!last ? <span className="text-brand-faint">/</span> : null}
          </span>
        );
      })}
    </nav>
  );
}
