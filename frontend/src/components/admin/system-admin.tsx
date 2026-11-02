"use client";

import { useState } from "react";
import { CheckCircle2, RefreshCw, Send, XCircle } from "lucide-react";
import { JsonBlock, PageHeader, Panel, Spinner } from "@/components/admin/admin-ui";
import { useHealth, useSimulatePayment, useTelegramTest } from "@/hooks/use-admin";
import { adminBtn, adminBtnOutline, adminInput } from "@/lib/styles";
import { API_URL } from "@/lib/api";

export function SystemAdmin() {
  const [auto, setAuto] = useState(false);
  const health = useHealth({ refetchInterval: auto ? 10000 : false });
  const telegram = useTelegramTest();
  const simulate = useSimulatePayment();

  const [orderId, setOrderId] = useState("");
  const [outcome, setOutcome] = useState<"succeeded" | "canceled">("succeeded");

  return (
    <div>
      <PageHeader title="Система" description="Состояние сервера и проверка уведомлений." />

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel
          title="Состояние сервера (/health)"
          actions={
            <button type="button" onClick={() => health.refetch()} disabled={health.isFetching} className={adminBtnOutline}>
              <RefreshCw className={health.isFetching ? "size-4 animate-spin" : "size-4"} /> Проверить
            </button>
          }
        >
          <div className="mb-3 flex items-center gap-2 text-sm">
            {health.isLoading ? (
              <Spinner />
            ) : health.isError ? (
              <>
                <XCircle className="size-5 text-destructive" />
                <span className="font-medium text-destructive">Сервер не отвечает</span>
              </>
            ) : (
              <>
                <CheckCircle2 className="size-5 text-status-paid-fg" />
                <span className="font-medium text-status-paid-fg">Сервер работает</span>
              </>
            )}
          </div>
          <p className="mb-3 text-xs text-muted-foreground">Адрес API: {API_URL}</p>
          {health.data !== undefined ? <JsonBlock value={health.data} /> : null}
          <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm">
            <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} className="size-4" />
            Проверять каждые 10 секунд
          </label>
        </Panel>

        <div className="flex flex-col gap-5">
          <Panel title="Telegram">
            <p className="mb-3 text-sm text-muted-foreground">
              Отправляет тестовое сообщение, чтобы проверить, что уведомления о заказах доходят.
            </p>
            <button type="button" disabled={telegram.isPending} onClick={() => telegram.mutate()} className={adminBtn}>
              <Send className="size-4" /> {telegram.isPending ? "Отправляем…" : "Отправить тест"}
            </button>
            {telegram.data ? <div className="mt-3"><JsonBlock value={telegram.data} /></div> : null}
          </Panel>

          <Panel title="Тестовая оплата">
            <p className="mb-3 text-sm text-muted-foreground">
              Имитирует результат оплаты заказа. Работает только при тестовых ключах платёжной системы.
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const id = Number(orderId);
                if (Number.isInteger(id) && id > 0) simulate.mutate({ orderId: id, outcome });
              }}
              className="flex flex-wrap items-center gap-2"
            >
              <input
                value={orderId}
                onChange={(e) => setOrderId(e.target.value)}
                inputMode="numeric"
                placeholder="№ заказа"
                className={`${adminInput} w-32`}
              />
              <select value={outcome} onChange={(e) => setOutcome(e.target.value as typeof outcome)} className={`${adminInput} w-44`}>
                <option value="succeeded">Оплата прошла</option>
                <option value="canceled">Оплата отменена</option>
              </select>
              <button type="submit" disabled={simulate.isPending || !orderId} className={adminBtn}>
                Применить
              </button>
            </form>
            {simulate.data ? <div className="mt-3"><JsonBlock value={simulate.data} /></div> : null}
          </Panel>
        </div>
      </div>
    </div>
  );
}
