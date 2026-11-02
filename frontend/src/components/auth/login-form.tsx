"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { FormField } from "@/components/shared/form-field";
import { useAuth, useLogin } from "@/hooks/use-auth";
import { btnPrimary, inputClass } from "@/lib/styles";
import { safeNextPath } from "@/lib/utils";

const schema = z.object({
  login: z.string().trim().min(3, "Введите почту или телефон"),
  password: z.string().min(1, "Введите пароль"),
});
type FormValues = z.infer<typeof schema>;

export function LoginForm() {
  const router = useRouter();
  const next = safeNextPath(useSearchParams().get("next"));
  const { isAuthenticated, hasHydrated } = useAuth();
  const login = useLogin();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { login: "", password: "" } });

  // Уже вошли: сразу отправляем дальше
  useEffect(() => {
    if (hasHydrated && isAuthenticated && !login.isPending) router.replace(next);
  }, [hasHydrated, isAuthenticated, login.isPending, next, router]);

  const onSubmit = handleSubmit((values) => {
    login.mutate(values, { onSuccess: () => router.replace(next) });
  });

  return (
    <div className="container-page flex justify-center py-12 md:py-20">
      <div className="w-full max-w-md rounded-2xl bg-brand-section p-6 shadow-[0_4px_24px_rgba(57,46,33,0.08)] md:p-10">
        <h1 className="font-accent text-3xl font-normal text-brand-ink">Вход</h1>
        <p className="mt-2 text-sm text-brand-muted">
          Войдите, чтобы видеть заказы, избранное и оставлять отзывы.
        </p>

        <form onSubmit={onSubmit} noValidate className="mt-8 flex flex-col gap-5">
          <FormField label="Почта или телефон" error={errors.login?.message}>
            <input {...register("login")} autoComplete="username" className={inputClass} />
          </FormField>
          <FormField label="Пароль" error={errors.password?.message}>
            <input {...register("password")} type="password" autoComplete="current-password" className={inputClass} />
          </FormField>
          <button type="submit" disabled={login.isPending} className={`${btnPrimary} mt-2 h-12 w-full`}>
            {login.isPending ? "Входим…" : "Войти"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-brand-muted">
          Ещё нет аккаунта?{" "}
          <Link
            href={next === "/profile" ? "/register" : `/register?next=${encodeURIComponent(next)}`}
            className="font-medium text-brand-accent underline underline-offset-4"
          >
            Зарегистрироваться
          </Link>
        </p>
      </div>
    </div>
  );
}
