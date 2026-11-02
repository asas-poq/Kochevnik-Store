"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";
import { EmptyRow, PageHeader, Panel, Spinner, TableWrap, tdClass, thClass } from "@/components/admin/admin-ui";
import { useAdminOrders } from "@/hooks/use-orders";
import { adminBtn, adminBtnOutline, adminInput } from "@/lib/styles";
import { formatDateTime, formatPrice } from "@/lib/utils";

// В API нет списка пользователей, поэтому здесь:
// 1) поиск по номеру пользователя, 2) список покупателей из последних заказов.
export function UsersAdmin() {
  const router = useRouter();
  const [idInput, setIdInput] = useState("");
  const { data, isLoading } = useAdminOrders({ limit: 100 });

  const customers = useMemo(() => {
    const map = new Map<number, { id: number; name: string; phone: string; orders: number; total: number; last: string }>();
    for (const o of data ?? []) {
      if (!o.user_id) continue;
      const prev = map.get(o.user_id);
      map.set(o.user_id, {
        id: o.user_id,
        name: o.customer_name,
        phone: o.customer_phone,
        orders: (prev?.orders ?? 0) + 1,
        total: (prev?.total ?? 0) + (o.status === "cancelled" ? 0 : o.total_amount),
        last: prev && prev.last > o.created_at ? prev.last : o.created_at,
      });
    }
    return [...map.values()].sort((a, b) => (a.last < b.last ? 1 : -1));
  }, [data]);

  return (
    <div>
      <PageHeader title="Пользователи" description="Откройте пользователя, чтобы посмотреть его заказы и отзывы." />

      <Panel title="Найти по номеру" className="mb-6">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const id = Number(idInput);
            if (Number.isInteger(id) && id > 0) router.push(`/admin/users/${id}`);
          }}
          className="flex gap-2"
        >
          <input
            value={idInput}
            onChange={(e) => setIdInput(e.target.value)}
            inputMode="numeric"
            placeholder="Номер пользователя, например 12"
            className={`${adminInput} max-w-xs`}
          />
          <button type="submit" className={adminBtn}>
            <Search className="size-4" /> Открыть
          </button>
        </form>
      </Panel>

      <h2 className="mb-3 text-base font-semibold">Покупатели из последних заказов</h2>
      <TableWrap>
        <thead>
          <tr>
            <th className={thClass}>№</th>
            <th className={thClass}>Имя</th>
            <th className={thClass}>Телефон</th>
            <th className={thClass}>Заказов</th>
            <th className={thClass}>Сумма</th>
            <th className={thClass}>Последний заказ</th>
            <th className={thClass} />
          </tr>
        </thead>
        <tbody>
          {isLoading ? (
            <tr>
              <td colSpan={7} className="px-4 py-10 text-center">
                <Spinner />
              </td>
            </tr>
          ) : customers.length === 0 ? (
            <EmptyRow colSpan={7} text="Пока нет заказов от зарегистрированных пользователей" />
          ) : (
            customers.map((c) => (
              <tr key={c.id}>
                <td className={tdClass}>{c.id}</td>
                <td className={tdClass}>{c.name}</td>
                <td className={tdClass}>{c.phone}</td>
                <td className={tdClass}>{c.orders}</td>
                <td className={tdClass}>{formatPrice(c.total)}</td>
                <td className={tdClass}>{formatDateTime(c.last)}</td>
                <td className={tdClass}>
                  <Link href={`/admin/users/${c.id}`} className={adminBtnOutline}>
                    Открыть
                  </Link>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </TableWrap>
    </div>
  );
}
