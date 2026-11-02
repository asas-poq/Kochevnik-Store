"use client";

import { TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
  className?: string;
}

// Блок ошибки загрузки с кнопкой «Повторить»
export function ErrorState({
  title = "Не удалось загрузить данные",
  message = "Проверьте соединение и попробуйте ещё раз.",
  onRetry,
  className,
}: ErrorStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-2xl bg-brand-section px-6 py-14 text-center",
        className,
      )}
    >
      <div className="grid size-14 place-items-center rounded-full bg-status-cancelled-bg text-status-cancelled-fg">
        <TriangleAlert className="size-6" />
      </div>
      <h3 className="font-accent text-xl font-medium text-brand-ink">{title}</h3>
      <p className="max-w-md text-sm leading-relaxed text-brand-muted">
        {message}
      </p>
      {onRetry ? (
        <Button
          variant="outline"
          className="mt-2 rounded-full px-6"
          onClick={onRetry}
        >
          Повторить
        </Button>
      ) : null}
    </div>
  );
}
