import { ORDER_STATUS_CLASSES, ORDER_STATUS_LABELS } from "@/lib/constants";
import { cn } from "@/lib/utils";
import type { OrderStatus } from "@/types";

// Цветной бейдж статуса заказа
export function OrderStatusBadge({
  status,
  className,
}: {
  status: string;
  className?: string;
}) {
  const known = status in ORDER_STATUS_LABELS;
  return (
    <span
      className={cn(
        "inline-flex items-center whitespace-nowrap rounded-full px-3 py-1 text-xs font-medium",
        known ? ORDER_STATUS_CLASSES[status as OrderStatus] : "bg-muted text-muted-foreground",
        className,
      )}
    >
      {known ? ORDER_STATUS_LABELS[status as OrderStatus] : status}
    </span>
  );
}
