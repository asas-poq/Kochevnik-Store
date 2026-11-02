import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

const STEPS = ["КОРЗИНА", "ОФОРМЛЕНИЕ", "ОПЛАТА"];

// Шаги заказа: Корзина — Оформление — Оплата. current: 1, 2 или 3
export function Stepper({ current }: { current: 1 | 2 | 3 }) {
  return (
    <ol className="flex items-center gap-3 text-[11px] font-semibold tracking-[0.1em] text-brand-ink-2">
      {STEPS.map((label, i) => {
        const n = i + 1;
        const done = n < current;
        const active = n === current;
        return (
          <li key={label} className="flex items-center gap-3">
            <span className="flex items-center gap-2">
              <span
                className={cn(
                  "grid size-6 place-items-center rounded-full text-[11px]",
                  active && "bg-brand-ink text-brand-surface",
                  done && "bg-brand-sand text-brand-muted",
                  !active && !done && "bg-brand-sand text-brand-subtle",
                )}
              >
                {done ? <Check className="size-3.5" /> : n}
              </span>
              <span className={cn("hidden sm:inline", !active && "text-brand-muted")}>{label}</span>
            </span>
            {i < STEPS.length - 1 ? (
              <span className="h-px w-6 bg-brand-line-strong sm:w-12" />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
