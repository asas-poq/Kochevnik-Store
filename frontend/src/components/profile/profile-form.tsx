"use client";

import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { FormField } from "@/components/shared/form-field";
import { useAuth, useLogoutAll, useSessions, useUpdateMe } from "@/hooks/use-auth";
import { btnOutline, btnPrimary, cardClass, inputClass } from "@/lib/styles";
import { formatDateTime } from "@/lib/utils";

const schema = z.object({
  full_name: z.string().trim().min(2, "Введите имя и фамилию"),
  phone: z
    .string()
    .trim()
    .refine((v) => v === "" || /^\+?[\d\s()\-]{10,}$/.test(v), "Некорректный номер телефона"),
  default_city: z.string().trim(),
  default_delivery_address: z.string().trim(),
});
type FormValues = z.infer<typeof schema>;

export function ProfileForm() {
  const router = useRouter();
  const { user } = useAuth();
  const update = useUpdateMe();
  const sessions = useSessions();
  const logoutAll = useLogoutAll();

  const {
    register,
    handleSubmit,
    formState: { errors, isDirty },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    // values подставляет данные пользователя, как только они загрузились
    values: {
      full_name: user?.full_name ?? "",
      phone: user?.phone ?? "",
      default_city: user?.default_city ?? "",
      default_delivery_address: user?.default_delivery_address ?? "",
    },
  });

  const onSubmit = handleSubmit((v) => {
    update.mutate({
      full_name: v.full_name,
      phone: v.phone || null,
      default_city: v.default_city || null,
      default_delivery_address: v.default_delivery_address || null,
    });
  });

  return (
    <div className="flex flex-col gap-6">
      <form onSubmit={onSubmit} noValidate className={cardClass}>
        <h2 className="font-accent text-2xl font-normal text-brand-ink">Мои данные</h2>
        <div className="mt-6 grid gap-5 sm:grid-cols-2">
          <FormField label="Имя и фамилия" required error={errors.full_name?.message} className="sm:col-span-2">
            <input {...register("full_name")} className={inputClass} />
          </FormField>
          <FormField label="Электронная почта" hint="Почту изменить нельзя">
            <input value={user?.email ?? ""} readOnly disabled className={`${inputClass} opacity-70`} />
          </FormField>
          <FormField label="Телефон" error={errors.phone?.message}>
            <input {...register("phone")} type="tel" className={inputClass} />
          </FormField>
          <FormField label="Город по умолчанию">
            <input {...register("default_city")} className={inputClass} />
          </FormField>
          <FormField label="Адрес доставки по умолчанию">
            <input {...register("default_delivery_address")} className={inputClass} />
          </FormField>
        </div>
        <button type="submit" disabled={update.isPending || !isDirty} className={`${btnPrimary} mt-6`}>
          {update.isPending ? "Сохраняем…" : "Сохранить"}
        </button>
      </form>

      <section className={cardClass}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-accent text-2xl font-normal text-brand-ink">Устройства</h2>
          <button
            type="button"
            disabled={logoutAll.isPending}
            onClick={() => logoutAll.mutate(undefined, { onSuccess: () => router.push("/") })}
            className={btnOutline}
          >
            Выйти на всех устройствах
          </button>
        </div>
        <ul className="mt-4 divide-y divide-brand-line text-sm">
          {sessions.isLoading ? (
            <li className="py-3 text-brand-muted">Загрузка…</li>
          ) : (sessions.data ?? []).length === 0 ? (
            <li className="py-3 text-brand-muted">Активных входов не найдено.</li>
          ) : (
            (sessions.data ?? []).map((s) => (
              <li key={s.jti} className="py-3">
                <p className="line-clamp-1 text-brand-ink">{s.user_agent ?? "Неизвестное устройство"}</p>
                <p className="text-xs text-brand-muted">
                  {s.ip ? `${s.ip} · ` : ""}вход {formatDateTime(s.created_at)}
                </p>
              </li>
            ))
          )}
        </ul>
      </section>
    </div>
  );
}
