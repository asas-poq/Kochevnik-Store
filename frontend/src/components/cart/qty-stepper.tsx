"use client";

import { Minus, Plus } from "lucide-react";
import { cn } from "@/lib/utils";

// Кнопки «− 1 +» для количества. max — сколько всего есть на складе.
export function QtyStepper({
  value,
  max,
  onChange,
  className,
}: {
  value: number;
  max?: number;
  onChange: (next: number) => void;
  className?: string;
}) {
  const canMinus = value > 1;
  const canPlus = max ? value < max : true;
  return (
    <div
      className={cn(
        "inline-flex items-center rounded-xl bg-brand-surface px-1 shadow-[0_1px_6px_rgba(57,46,33,0.06)]",
        className,
      )}
    >
      <button
        type="button"
        onClick={() => onChange(value - 1)}
        disabled={!canMinus}
        aria-label="Уменьшить количество"
        className="grid size-9 place-items-center text-brand-ink disabled:text-brand-faint [@media(pointer:coarse)]:size-11"
      >
        <Minus className="size-4" />
      </button>
      <span className="w-8 text-center text-sm font-medium text-brand-ink">{value}</span>
      <button
        type="button"
        onClick={() => onChange(value + 1)}
        disabled={!canPlus}
        aria-label="Увеличить количество"
        className="grid size-9 place-items-center text-brand-ink disabled:text-brand-faint [@media(pointer:coarse)]:size-11"
      >
        <Plus className="size-4" />
      </button>
    </div>
  );
}
