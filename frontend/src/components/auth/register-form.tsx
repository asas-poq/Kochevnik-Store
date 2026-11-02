"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { FormField } from "@/components/shared/form-field";
import { useAuth, useRegister } from "@/hooks/use-auth";
import { btnPrimary, inputClass } from "@/lib/styles";
import { safeNextPath } from "@/lib/utils";

const schema = z
  .object({
    full_name: z.string().trim().min(2, "Введите имя и фамилию"),
    email: z.string().trim().email("Введите корректную почту"),
    phone: z
      .string()
      .trim()
      .refine((v) => v === "" || /^\+?[\d\s()\-]{10,}$/.test(v), "Некорректный номер телефона"),
    default_city: z.string().trim(),
    password: z.string().min(8, "Пароль должен быть не короче 8 символов"),
    password2: z.string(),
  })
  .refine((v) => v.password === v.password2, {
    path: ["password2"],
    message: "Пароли не совпадают",
  });
type FormValues = z.infer<typeof schema>;

export function RegisterForm() {
  const router = useRouter();
  const next = safeNextPath(useSearchParams().get("next"));
  const { isAuthenticated, hasHydrated } = useAuth();
  const registerUser = useRegister();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { full_name: "", email: "", phone: "", default_city: "", password: "", password2: "" },
  });

  useEffect(() => {
    if (hasHydrated && isAuthenticated && !registerUser.isPending) router.replace(next);
  }, [hasHydrated, isAuthenticated, registerUser.isPending, next, router]);

  const onSubmit = handleSubmit((v) => {
    registerUser.mutate(
      {
        full_name: v.full_name.trim(),
        email: v.email.trim(),
        phone: v.phone.trim() || null,
        default_city: v.default_city.trim() || null,
        password: v.password,
      },
      { onSuccess: () => router.replace(next) },
    );
  });

  return (
    <div className="container-page flex justify-center py-12 md:py-20">
      <div className="w-full max-w-lg rounded-2xl bg-brand-section p-6 shadow-[0_4px_24px_rgba(57,46,33,0.08)] md:p-10">
        <h1 className="font-accent text-3xl font-normal text-brand-ink">Регистрация</h1>
        <p className="mt-2 text-sm text-brand-muted">Создайте аккаунт, чтобы оформлять заказы быстрее.</p>

        <form onSubmit={onSubmit} noValidate className="mt-8 grid gap-5 sm:grid-cols-2">
          <FormField label="Имя и фамилия" required error={errors.full_name?.message} className="sm:col-span-2">
            <input {...register("full_name")} autoComplete="name" className={inputClass} />
          </FormField>
          <FormField label="Электронная почта" required error={errors.email?.message} className="sm:col-span-2">
            <input {...register("email")} type="email" autoComplete="email" className={inputClass} />
          </FormField>
          <FormField label="Телефон" error={errors.phone?.message}>
            <input {...register("phone")} type="tel" autoComplete="tel" placeholder="+7 (926) 450-88-21" className={inputClass} />
          </FormField>
          <FormField label="Город" error={errors.default_city?.message}>
            <input {...register("default_city")} autoComplete="address-level2" className={inputClass} />
          </FormField>
          <FormField label="Пароль" required error={errors.password?.message}>
            <input {...register("password")} type="password" autoComplete="new-password" className={inputClass} />
          </FormField>
          <FormField label="Повторите пароль" required error={errors.password2?.message}>
            <input {...register("password2")} type="password" autoComplete="new-password" className={inputClass} />
          </FormField>
          <button type="submit" disabled={registerUser.isPending} className={`${btnPrimary} h-12 w-full sm:col-span-2`}>
            {registerUser.isPending ? "Создаём аккаунт…" : "Создать аккаунт"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-brand-muted">
          Уже есть аккаунт?{" "}
          <Link
            href={next === "/profile" ? "/login" : `/login?next=${encodeURIComponent(next)}`}
            className="font-medium text-brand-accent underline underline-offset-4"
          >
            Войти
          </Link>
        </p>
      </div>
    </div>
  );
}
