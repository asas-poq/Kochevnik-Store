import type { ReactNode } from "react";
import { labelClass } from "@/lib/styles";
import { cn } from "@/lib/utils";

// Подпись + поле + текст ошибки под ним
export function FormField({
  label,
  error,
  hint,
  required,
  className,
  children,
}: {
  label: string;
  error?: string;
  hint?: string;
  required?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cn("min-w-0", className)}>
      <label className={labelClass}>
        {label}
        {required ? " *" : ""}
      </label>
      {children}
      {error ? <p className="mt-1 text-xs text-brand-red">{error}</p> : null}
      {!error && hint ? <p className="mt-1 text-xs text-brand-subtle">{hint}</p> : null}
    </div>
  );
}
