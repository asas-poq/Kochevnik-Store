"use client";

import { useState } from "react";
import { Play, RefreshCw, Search } from "lucide-react";
import {
  EmptyRow,
  JsonBlock,
  KeyValueList,
  PageHeader,
  Panel,
  Spinner,
  TableWrap,
  tdClass,
  thClass,
} from "@/components/admin/admin-ui";
import { ErrorState } from "@/components/shared/error-state";
import {
  useParserDiscover,
  useParserPreview,
  useParserQueue,
  useParserQueueStats,
  useParserScrape,
  useParserStatus,
} from "@/hooks/use-admin";
import { adminBtn, adminBtnOutline, adminInput } from "@/lib/styles";
import { formatDateTime } from "@/lib/utils";

export function ParserAdmin() {
  const [auto, setAuto] = useState(false);
  const refetchInterval = auto ? 5000 : false;

  const status = useParserStatus({ refetchInterval });
  const stats = useParserQueueStats({ refetchInterval });

  const [queueFilter, setQueueFilter] = useState("");
  const queue = useParserQueue({ status_filter: queueFilter || undefined, limit: 50 });

  const discover = useParserDiscover();
  const scrape = useParserScrape();
  const preview = useParserPreview();

  const [limit, setLimit] = useState("20");
  const [retryErrors, setRetryErrors] = useState(false);
  const [previewUrl, setPreviewUrl] = useState("");
  const [saveHtml, setSaveHtml] = useState(false);

  const statusKeys = Object.keys(stats.data ?? {});

  return (
    <div>
      <PageHeader
        title="Парсер"
        description="Сбор товаров с сайта-источника: статус, очередь, запуск и проверка страницы."
        actions={
          <>
            <label className="flex cursor-pointer items-center gap-2 text-sm">
              <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} className="size-4" />
              Обновлять каждые 5 секунд
            </label>
            <button
              type="button"
              onClick={() => {
                status.refetch();
                stats.refetch();
                queue.refetch();
              }}
              className={adminBtnOutline}
            >
              <RefreshCw className="size-4" /> Обновить
            </button>
          </>
        }
      />

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel title="Статус парсера">
          {status.isLoading ? (
            <Spinner />
          ) : status.isError ? (
            <ErrorState onRetry={() => status.refetch()} />
          ) : (
            <KeyValueList data={status.data ?? {}} />
          )}
        </Panel>
        <Panel title="Статистика очереди">
          {stats.isLoading ? (
            <Spinner />
          ) : stats.isError ? (
            <ErrorState onRetry={() => stats.refetch()} />
          ) : (
            <KeyValueList data={stats.data ?? {}} />
          )}
        </Panel>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <Panel title="Найти новые товары">
          <p className="mb-3 text-sm text-muted-foreground">
            Собирает ссылки на товары с сайта-источника и кладёт их в очередь. Работает в фоне.
          </p>
          <button type="button" disabled={discover.isPending} onClick={() => discover.mutate()} className={adminBtn}>
            <Search className="size-4" /> {discover.isPending ? "Запускаем…" : "Запустить поиск"}
          </button>
          {discover.data ? <div className="mt-3"><JsonBlock value={discover.data} /></div> : null}
        </Panel>

        <Panel title="Собрать данные товаров">
          <p className="mb-3 text-sm text-muted-foreground">Берёт товары из очереди и загружает их данные. Работает в фоне.</p>
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-sm">
              Сколько:
              <input value={limit} onChange={(e) => setLimit(e.target.value)} inputMode="numeric" className={`${adminInput} w-24`} />
            </label>
            <label className="flex cursor-pointer items-center gap-2 text-sm">
              <input type="checkbox" checked={retryErrors} onChange={(e) => setRetryErrors(e.target.checked)} className="size-4" />
              Повторить ошибки
            </label>
            <button
              type="button"
              disabled={scrape.isPending}
              onClick={() => {
                const n = Number(limit);
                scrape.mutate({ limit: Number.isInteger(n) && n > 0 ? n : undefined, retry_errors: retryErrors });
              }}
              className={adminBtn}
            >
              <Play className="size-4" /> {scrape.isPending ? "Запускаем…" : "Запустить сбор"}
            </button>
          </div>
          {scrape.data ? <div className="mt-3"><JsonBlock value={scrape.data} /></div> : null}
        </Panel>
      </div>

      <Panel title="Проверка страницы (preview)" className="mt-5">
        <p className="mb-3 text-sm text-muted-foreground">
          Разбирает одну страницу и показывает результат, ничего не записывая в базу. Может занять до пары минут.
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (previewUrl.trim()) preview.mutate({ url: previewUrl.trim(), save_html: saveHtml });
          }}
          className="flex flex-wrap items-center gap-3"
        >
          <input
            value={previewUrl}
            onChange={(e) => setPreviewUrl(e.target.value)}
            placeholder="https://…"
            className={`${adminInput} max-w-xl flex-1`}
          />
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <input type="checkbox" checked={saveHtml} onChange={(e) => setSaveHtml(e.target.checked)} className="size-4" />
            Сохранить HTML
          </label>
          <button type="submit" disabled={preview.isPending || !previewUrl.trim()} className={adminBtn}>
            {preview.isPending ? "Разбираем…" : "Проверить"}
          </button>
        </form>
        {preview.isPending ? <div className="mt-4"><Spinner /></div> : null}
        {preview.data !== undefined ? <div className="mt-4"><JsonBlock value={preview.data} /></div> : null}
      </Panel>

      <div className="mt-5">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-base font-semibold">Очередь</h2>
          <select value={queueFilter} onChange={(e) => setQueueFilter(e.target.value)} aria-label="Фильтр очереди" className={`${adminInput} w-56`}>
            <option value="">Все статусы</option>
            {statusKeys.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
        </div>
        <TableWrap>
          <thead>
            <tr>
              <th className={thClass}>ID</th>
              <th className={thClass}>Адрес</th>
              <th className={thClass}>Статус</th>
              <th className={thClass}>Ошибка</th>
              <th className={thClass}>Обновлено</th>
            </tr>
          </thead>
          <tbody>
            {queue.isLoading ? (
              <tr>
                <td colSpan={5} className="px-4 py-10 text-center">
                  <Spinner />
                </td>
              </tr>
            ) : (queue.data ?? []).length === 0 ? (
              <EmptyRow colSpan={5} text="Очередь пуста" />
            ) : (
              (queue.data ?? []).map((item) => (
                <tr key={item.id}>
                  <td className={tdClass}>{item.id}</td>
                  <td className={`${tdClass} max-w-md break-all`}>
                    <a href={item.url} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                      {item.url}
                    </a>
                  </td>
                  <td className={tdClass}>{item.status}</td>
                  <td className={`${tdClass} max-w-xs break-words text-destructive`}>{item.error ?? ""}</td>
                  <td className={tdClass}>{formatDateTime(item.updated_at)}</td>
                </tr>
              ))
            )}
          </tbody>
        </TableWrap>
      </div>
    </div>
  );
}
