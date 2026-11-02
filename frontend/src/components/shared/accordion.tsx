"use client";

import { useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

interface AccordionItem {
  title: string;
  content: ReactNode;
}

// Раскрывающиеся блоки (описание, состав, параметры). Открыт может быть один блок.
export function Accordion({
  items,
  defaultOpen = 0,
}: {
  items: AccordionItem[];
  defaultOpen?: number | null;
}) {
  const [open, setOpen] = useState<number | null>(defaultOpen);

  return (
    <div className="flex flex-col gap-3">
      {items.map((item, i) => {
        const isOpen = open === i;
        return (
          <div key={item.title} className="rounded-xl bg-brand-section">
            <button
              type="button"
              onClick={() => setOpen(isOpen ? null : i)}
              aria-expanded={isOpen}
              className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left"
            >
              <span className="font-accent text-lg font-medium text-brand-ink">
                {item.title}
              </span>
              <ChevronDown
                className={cn(
                  "size-5 shrink-0 text-brand-muted transition-transform",
                  isOpen && "rotate-180",
                )}
              />
            </button>
            {isOpen ? (
              <div className="px-5 pb-5 text-sm leading-relaxed text-brand-muted">
                {item.content}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
