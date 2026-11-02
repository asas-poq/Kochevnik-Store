"use client";

import { useEffect, useState } from "react";
import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { cn } from "@/lib/utils";

type Mode = "system" | "light" | "dark";
const NAMES: Record<Mode, string> = { system: "Авто", light: "Светлая", dark: "Тёмная" };
const NEXT: Record<Mode, Mode> = { system: "light", light: "dark", dark: "system" };

// Переключатель темы: Авто (как в телефоне) → Светлая → Тёмная → Авто.
// Выбор запоминается в браузере.
// variant="icon": круглая иконка в шапке; "row": строка в мобильном меню; "admin": кнопка в админке.
export function ThemeToggle({
  variant = "icon",
  className,
}: {
  variant?: "icon" | "row" | "admin";
  className?: string;
}) {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);

  // До загрузки страницы режим неизвестен, показываем «Авто»
  const mode: Mode = mounted && (theme === "light" || theme === "dark") ? theme : "system";
  const Icon = mode === "dark" ? Moon : mode === "light" ? Sun : Monitor;
  const label = `Тема: ${NAMES[mode]}. Нажмите, чтобы переключить`;
  const toggle = () => setTheme(NEXT[mode]);

  if (variant === "row") {
    return (
      <button
        type="button"
        onClick={toggle}
        aria-label={label}
        className={cn(
          "flex items-center gap-3 border-b border-brand-line/70 py-3.5 text-left text-base font-medium text-brand-ink-2",
          className,
        )}
      >
        <Icon className="size-5" />
        Тема: {NAMES[mode]}
      </button>
    );
  }

  if (variant === "admin") {
    return (
      <button
        type="button"
        onClick={toggle}
        aria-label={label}
        title={label}
        className={cn(
          "grid size-9 place-items-center rounded-md border border-input text-foreground hover:bg-accent",
          className,
        )}
      >
        <Icon className="size-4" />
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={label}
      title={label}
      className={cn(
        "size-11 place-items-center rounded-full text-brand-ink transition-colors hover:bg-brand-sand sm:size-10",
        className ?? "grid",
      )}
    >
      <Icon className="size-[22px]" />
    </button>
  );
}
