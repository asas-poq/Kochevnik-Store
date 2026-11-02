// Готовые наборы классов Tailwind, чтобы кнопки и поля везде выглядели одинаково.

/* ---------------- Магазин ---------------- */
export const btnPrimary =
  "inline-flex h-11 items-center justify-center gap-2 rounded-full bg-brand-ink px-7 text-sm font-medium tracking-[0.04em] text-brand-surface transition-colors hover:bg-brand-accent-dark disabled:pointer-events-none disabled:opacity-50";

export const btnOutline =
  "inline-flex h-11 items-center justify-center gap-2 rounded-full border border-brand-ink px-7 text-sm font-medium tracking-[0.04em] text-brand-ink transition-colors hover:bg-brand-ink hover:text-brand-surface disabled:pointer-events-none disabled:opacity-50";

// Прямоугольная кнопка «ПОКАЗАТЬ ЕЩЁ» из макета
export const btnSquare =
  "inline-flex h-12 items-center justify-center border border-brand-ink px-8 text-xs font-semibold uppercase tracking-[0.12em] text-brand-ink transition-colors hover:bg-brand-ink hover:text-brand-surface disabled:pointer-events-none disabled:opacity-50";

export const inputClass =
  "h-11 w-full rounded-xl border border-transparent bg-brand-sand/70 px-4 text-[15px] text-brand-ink outline-none transition placeholder:text-brand-subtle focus:border-brand-accent/40 focus:bg-brand-surface focus:ring-2 focus:ring-brand-accent/20";

export const textareaClass =
  "min-h-24 w-full rounded-xl border border-transparent bg-brand-sand/70 px-4 py-3 text-[15px] text-brand-ink outline-none transition placeholder:text-brand-subtle focus:border-brand-accent/40 focus:bg-brand-surface focus:ring-2 focus:ring-brand-accent/20";

export const labelClass =
  "mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.1em] text-brand-muted";

export const cardClass =
  "rounded-2xl bg-brand-section p-5 shadow-[0_2px_14px_rgba(57,46,33,0.06)] md:p-6";

export const pageTitleClass =
  "font-accent text-4xl font-normal leading-tight text-brand-ink md:text-5xl";

/* ---------------- Админка (холодная тема) ---------------- */
export const adminBtn =
  "inline-flex h-9 items-center justify-center gap-1.5 rounded-md bg-primary px-3.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:pointer-events-none disabled:opacity-50";

export const adminBtnOutline =
  "inline-flex h-9 items-center justify-center gap-1.5 rounded-md border border-input bg-card px-3.5 text-sm font-medium text-foreground transition-colors hover:bg-accent disabled:pointer-events-none disabled:opacity-50";

export const adminBtnDanger =
  "inline-flex h-9 items-center justify-center gap-1.5 rounded-md bg-destructive px-3.5 text-sm font-medium text-white transition-colors hover:bg-destructive/90 disabled:pointer-events-none disabled:opacity-50";

export const adminInput =
  "h-9 w-full rounded-md border border-input bg-card px-3 text-sm text-foreground outline-none transition placeholder:text-muted-foreground focus:border-ring focus:ring-2 focus:ring-ring/20";

export const adminTextarea =
  "min-h-20 w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground outline-none transition placeholder:text-muted-foreground focus:border-ring focus:ring-2 focus:ring-ring/20";

export const adminLabel = "mb-1 block text-xs font-medium text-muted-foreground";
