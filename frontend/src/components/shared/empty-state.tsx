import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  icon?: ReactNode; // иконка из lucide-react
  title: string;
  description?: string;
  action?: ReactNode; // кнопка или ссылка
  className?: string;
}

// Пустое состояние: «Корзина пуста», «Ничего не найдено» и т. д.
export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-2xl bg-brand-section px-6 py-14 text-center",
        className,
      )}
    >
      {icon ? (
        <div className="grid size-14 place-items-center rounded-full bg-brand-sand text-brand-muted [&>svg]:size-6">
          {icon}
        </div>
      ) : null}
      <h3 className="font-accent text-xl font-medium text-brand-ink">{title}</h3>
      {description ? (
        <p className="max-w-md text-sm leading-relaxed text-brand-muted">
          {description}
        </p>
      ) : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
