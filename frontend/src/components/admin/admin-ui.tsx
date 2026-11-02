import type { ReactNode } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { adminBtnOutline } from "@/lib/styles";
import { cn } from "@/lib/utils";

// Заголовок страницы админки с кнопками справа
export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">{title}</h1>
        {description ? <p className="mt-1 text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

// Белая панель с рамкой
export function Panel({
  title,
  children,
  className,
  actions,
}: {
  title?: string;
  children: ReactNode;
  className?: string;
  actions?: ReactNode;
}) {
  return (
    <section className={cn("rounded-lg border border-border bg-card p-4 md:p-5", className)}>
      {title || actions ? (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          {title ? <h2 className="text-base font-semibold text-foreground">{title}</h2> : <span />}
          {actions}
        </div>
      ) : null}
      {children}
    </section>
  );
}

// Таблица с прокруткой по горизонтали
export function TableWrap({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-card">
      <table className="w-full min-w-[720px] border-collapse text-sm">{children}</table>
    </div>
  );
}

export const thClass =
  "bg-muted/60 px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-muted-foreground";
export const tdClass = "border-t border-border px-4 py-3 align-top text-foreground";

export function EmptyRow({ colSpan, text }: { colSpan: number; text: string }) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-4 py-10 text-center text-sm text-muted-foreground">
        {text}
      </td>
    </tr>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-block size-4 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-primary",
        className,
      )}
    />
  );
}

// «Назад / Вперёд» (API не отдаёт общее число записей, поэтому без номеров страниц)
export function PaginationBar({
  page,
  hasNext,
  onPage,
}: {
  page: number; // с нуля
  hasNext: boolean;
  onPage: (page: number) => void;
}) {
  return (
    <div className="mt-4 flex items-center justify-between text-sm text-muted-foreground">
      <span>Страница {page + 1}</span>
      <div className="flex gap-2">
        <button type="button" disabled={page === 0} onClick={() => onPage(page - 1)} className={adminBtnOutline}>
          <ChevronLeft className="size-4" /> Назад
        </button>
        <button type="button" disabled={!hasNext} onClick={() => onPage(page + 1)} className={adminBtnOutline}>
          Вперёд <ChevronRight className="size-4" />
        </button>
      </div>
    </div>
  );
}

// Красиво показывает произвольные данные (ответы парсера и /health)
export function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-96 overflow-auto rounded-md bg-muted p-3 text-xs leading-relaxed text-foreground">
      {typeof value === "string" ? value : JSON.stringify(value, null, 2)}
    </pre>
  );
}

// Список «ключ: значение» для объекта
export function KeyValueList({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data);
  if (entries.length === 0) return <p className="text-sm text-muted-foreground">Нет данных</p>;
  return (
    <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
      {entries.map(([key, value]) => (
        <div key={key} className="flex justify-between gap-3 border-b border-border/60 py-1.5">
          <dt className="text-muted-foreground">{key}</dt>
          <dd className="break-all text-right font-medium text-foreground">
            {value !== null && typeof value === "object" ? JSON.stringify(value) : String(value ?? "—")}
          </dd>
        </div>
      ))}
    </dl>
  );
}
