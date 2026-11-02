import Link from "next/link";
import { cn } from "@/lib/utils";

// Логотип: значок «X» и надпись KOCHEVNIK
export function Logo({ className }: { className?: string }) {
  return (
    <Link
      href="/"
      aria-label="Kochevnik — на главную"
      className={cn("flex items-center gap-2.5 text-brand-ink", className)}
    >
      <svg
        viewBox="0 0 24 28"
        className="h-6 w-5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        aria-hidden
      >
        <path d="M3 2 21 26M21 2 3 26" />
      </svg>
      <span className="font-logo text-[13px] tracking-[0.18em] sm:text-[15px] sm:tracking-[0.22em]">KOCHEVNIK</span>
    </Link>
  );
}
