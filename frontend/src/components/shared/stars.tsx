import { Star } from "lucide-react";
import { cn } from "@/lib/utils";

// Показывает рейтинг звёздочками (1–5)
export function Stars({
  value,
  className,
}: {
  value: number;
  className?: string;
}) {
  const rounded = Math.round(value);
  return (
    <span className={cn("inline-flex gap-0.5", className)} aria-label={`Оценка ${value} из 5`}>
      {[1, 2, 3, 4, 5].map((i) => (
        <Star
          key={i}
          className={cn(
            "size-4",
            i <= rounded
              ? "fill-brand-accent text-brand-accent"
              : "fill-transparent text-brand-line-strong",
          )}
        />
      ))}
    </span>
  );
}

// Выбор оценки кликом (для формы отзыва)
export function StarInput({
  value,
  onChange,
}: {
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <span className="inline-flex gap-1">
      {[1, 2, 3, 4, 5].map((i) => (
        <button
          key={i}
          type="button"
          onClick={() => onChange(i)}
          aria-label={`${i} из 5`}
          className="rounded p-0.5"
        >
          <Star
            className={cn(
              "size-7 transition-colors",
              i <= value
                ? "fill-brand-accent text-brand-accent"
                : "fill-transparent text-brand-line-strong hover:text-brand-accent",
            )}
          />
        </button>
      ))}
    </span>
  );
}
