"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { ArrowRight, Check, Lock, ShoppingBag, Truck, X } from "lucide-react";
import { toast } from "sonner";
import { z } from "zod";
import { EmptyState } from "@/components/shared/empty-state";
import { FormField } from "@/components/shared/form-field";
import { PageSkeleton } from "@/components/shared/page-skeleton";
import { Stepper } from "@/components/shared/stepper";
import { useRequireAuth } from "@/hooks/use-require-auth";
import { useCreateOrder } from "@/hooks/use-orders";
import { FREE_DELIVERY_THRESHOLD } from "@/lib/constants";
import { btnPrimary, cardClass, inputClass, pageTitleClass, textareaClass } from "@/lib/styles";
import { cn, formatPrice, pluralize } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth-store";
import {
  cartItemsToOrderItems,
  useCartStore,
  useCartTotals,
} from "@/stores/cart-store";

const DELIVERY_METHODS = ["cdek_courier", "cdek_pvz", "showroom_pickup", "russian_post"] as const;

const schema = z
  .object({
    first_name: z.string().trim().min(2, "Введите имя"),
    last_name: z.string().trim().min(2, "Введите фамилию"),
    phone: z
      .string()
      .trim()
      .regex(/^\+?[\d\s()\-]{10,}$/, "Введите телефон, например +7 (926) 450-88-21"),
    email: z.string().trim().email("Введите корректную почту"),
    city: z.string().trim().min(2, "Укажите город получения"),
    delivery_method: z.enum(DELIVERY_METHODS),
    street: z.string(),
    apartment: z.string(),
    entrance: z.string(),
    intercom: z.string(),
    floor: z.string(),
    pvz_code: z.string(),
    comment: z.string(),
  })
  .superRefine((v, ctx) => {
    const needsStreet = v.delivery_method === "cdek_courier" || v.delivery_method === "russian_post";
    if (needsStreet && v.street.trim().length < 3) {
      ctx.addIssue({ code: "custom", path: ["street"], message: "Укажите улицу, дом и корпус" });
    }
    if (v.delivery_method === "cdek_pvz" && v.pvz_code.trim().length < 2) {
      ctx.addIssue({ code: "custom", path: ["pvz_code"], message: "Укажите код пункта выдачи СДЭК" });
    }
  });

type FormValues = z.infer<typeof schema>;

const DELIVERY_CARDS: { value: FormValues["delivery_method"]; title: string; text: string }[] = [
  { value: "cdek_courier", title: "Курьер СДЭК", text: "Доставка до двери курьером СДЭК." },
  { value: "cdek_pvz", title: "Пункт СДЭК", text: "Более 4 500 отделений с зеркалами." },
  { value: "showroom_pickup", title: "Самовывоз", text: "Бутик KOCHEVNIK на Б. Дмитровке." },
  { value: "russian_post", title: "Почта России", text: "Доставка в любое отделение по России." },
];

const POPULAR_CITIES = ["Москва", "Санкт-Петербург", "Казань"];

function buildAddress(v: FormValues): string {
  if (v.delivery_method === "showroom_pickup") return "Самовывоз: бутик KOCHEVNIK на Б. Дмитровке";
  if (v.delivery_method === "cdek_pvz") {
    return `Пункт выдачи СДЭК ${v.pvz_code.trim()}${v.street.trim() ? `, ${v.street.trim()}` : ""}`;
  }
  const extra = [
    v.apartment.trim() && `кв./офис ${v.apartment.trim()}`,
    v.entrance.trim() && `подъезд ${v.entrance.trim()}`,
    v.intercom.trim() && `домофон ${v.intercom.trim()}`,
    v.floor.trim() && `этаж ${v.floor.trim()}`,
  ].filter(Boolean);
  return [v.street.trim(), ...extra].join(", ");
}

function SectionCard({
  number,
  title,
  step,
  children,
}: {
  number: number;
  title: string;
  step?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={cardClass}>
      <div className="flex items-center justify-between border-b border-brand-line pb-4">
        <h2 className="flex items-center gap-3 font-accent text-xl font-normal text-brand-ink">
          <span className="grid size-7 place-items-center rounded-full bg-brand-sand text-xs text-brand-muted">
            {number}
          </span>
          {title}
        </h2>
        {step ? (
          <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-brand-muted">{step}</span>
        ) : null}
      </div>
      <div className="pt-5">{children}</div>
    </section>
  );
}

export function CheckoutView() {
  const gate = useRequireAuth();
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const cartReady = useCartStore((s) => s.hasHydrated);
  const items = useCartStore((s) => s.items);
  const removeItem = useCartStore((s) => s.removeItem);
  const clear = useCartStore((s) => s.clear);
  const totals = useCartTotals();
  const createOrder = useCreateOrder();
  const [redirecting, setRedirecting] = useState(false);

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    getValues,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    mode: "onTouched",
    defaultValues: {
      first_name: "",
      last_name: "",
      phone: "",
      email: "",
      city: "",
      delivery_method: "cdek_courier",
      street: "",
      apartment: "",
      entrance: "",
      intercom: "",
      floor: "",
      pvz_code: "",
      comment: "",
    },
  });

  // Подставляем данные профиля один раз
  const prefilled = useRef(false);
  useEffect(() => {
    if (!user || prefilled.current) return;
    prefilled.current = true;
    const [first = "", ...rest] = user.full_name.trim().split(/\s+/);
    const fill = (name: keyof FormValues, value: string | null | undefined) => {
      if (value && !getValues(name)) setValue(name, value);
    };
    fill("first_name", first);
    fill("last_name", rest.join(" "));
    fill("phone", user.phone);
    fill("email", user.email);
    fill("city", user.default_city);
    fill("street", user.default_delivery_address);
  }, [user, getValues, setValue]);

  const method = watch("delivery_method");
  const city = watch("city");

  const freeDelivery = totals.total >= FREE_DELIVERY_THRESHOLD;
  const toFree = Math.max(0, FREE_DELIVERY_THRESHOLD - totals.total);
  const deliveryFreeNow = method === "showroom_pickup" || (freeDelivery && method !== "russian_post");

  const onSubmit = handleSubmit(async (values) => {
    if (items.length === 0) {
      toast.error("Корзина пуста");
      return;
    }
    try {
      const order = await createOrder.mutateAsync({
        customer_name: `${values.first_name.trim()} ${values.last_name.trim()}`,
        customer_phone: values.phone.trim(),
        customer_email: values.email.trim(),
        delivery_method: values.delivery_method,
        delivery_city: values.city.trim(),
        delivery_address: buildAddress(values),
        cdek_pvz_code: values.delivery_method === "cdek_pvz" ? values.pvz_code.trim() : null,
        customer_comment: values.comment.trim() || null,
        items: cartItemsToOrderItems(items),
      });
      setRedirecting(true);
      clear();
      if (order.payment_url) {
        window.location.assign(order.payment_url); // переходим на оплату СБП
      } else {
        router.push(`/order/${order.id}`);
      }
    } catch {
      // Текст ошибки уже показан красным уведомлением
    }
  });

  if (gate !== "ok" || !cartReady) return <PageSkeleton />;

  if (items.length === 0 && !redirecting) {
    return (
      <div className="container-page py-16">
        <EmptyState
          icon={<ShoppingBag />}
          title="В корзине пока ничего нет"
          description="Добавьте товары, чтобы оформить заказ."
          action={
            <Link href="/catalog" className={btnPrimary}>
              Перейти в каталог
            </Link>
          }
        />
      </div>
    );
  }

  const busy = createOrder.isPending || redirecting;

  return (
    <form onSubmit={onSubmit} noValidate className="container-page py-10 md:py-16">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <h1 className={pageTitleClass}>Оформление заказа</h1>
        <Stepper current={2} />
      </div>

      <div className="mt-10 grid gap-8 lg:grid-cols-[1fr_380px] lg:items-start">
        <div className="flex flex-col gap-6">
          {/* Баннер про бесплатную доставку */}
          <div className="flex items-center gap-4 rounded-2xl bg-brand-section px-5 py-4 shadow-[0_2px_14px_rgba(57,46,33,0.05)]">
            <div className="grid size-10 shrink-0 place-items-center rounded-full bg-brand-sand text-brand-muted">
              <Truck className="size-5" />
            </div>
            <div className="flex-1">
              <p className="text-[11px] font-bold uppercase tracking-[0.08em] text-brand-ink">
                {freeDelivery ? "Бесплатная доставка активна" : "Бесплатная доставка"}
              </p>
              <p className="text-sm text-brand-muted">
                {freeDelivery
                  ? `Ваш заказ свыше ${formatPrice(FREE_DELIVERY_THRESHOLD)} доставляется курьером или в ПВЗ бесплатно.`
                  : `Добавьте товаров ещё на ${formatPrice(toFree)}, и доставка курьером или в ПВЗ будет бесплатной.`}
              </p>
            </div>
            {freeDelivery ? (
              <span className="rounded-full bg-status-paid-bg px-3 py-1 text-[11px] font-bold uppercase tracking-[0.06em] text-status-paid-fg">
                Бесплатно
              </span>
            ) : null}
          </div>

          <SectionCard number={1} title="Личные данные" step="Шаг 1 из 3">
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="Имя" required error={errors.first_name?.message}>
                <input {...register("first_name")} autoComplete="given-name" className={inputClass} />
              </FormField>
              <FormField label="Фамилия" required error={errors.last_name?.message}>
                <input {...register("last_name")} autoComplete="family-name" className={inputClass} />
              </FormField>
              <FormField label="Телефон" required error={errors.phone?.message}>
                <input {...register("phone")} type="tel" autoComplete="tel" placeholder="+7 (926) 450-88-21" className={inputClass} />
              </FormField>
              <FormField label="Электронная почта" required error={errors.email?.message}>
                <input {...register("email")} type="email" autoComplete="email" className={inputClass} />
              </FormField>
            </div>
          </SectionCard>

          <SectionCard number={2} title="Способ получения" step="Шаг 2 из 3">
            <FormField label="Город получения" required error={errors.city?.message}>
              <input {...register("city")} autoComplete="address-level2" className={inputClass} />
            </FormField>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-brand-muted">
              Популярные:
              {POPULAR_CITIES.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setValue("city", c, { shouldValidate: true })}
                  className={cn(
                    "rounded-full px-3 py-1 text-xs normal-case tracking-normal transition-colors",
                    city === c ? "bg-brand-ink text-brand-surface" : "bg-brand-sand text-brand-ink-2 hover:bg-brand-line",
                  )}
                >
                  {c}
                </button>
              ))}
            </div>

            <div className="mt-6 grid gap-3 sm:grid-cols-2">
              {DELIVERY_CARDS.map((card) => {
                const active = method === card.value;
                const costTag =
                  card.value === "showroom_pickup"
                    ? "0 ₽"
                    : card.value !== "russian_post" && freeDelivery
                      ? "0 ₽"
                      : "по тарифу";
                return (
                  <button
                    key={card.value}
                    type="button"
                    onClick={() => setValue("delivery_method", card.value, { shouldValidate: true })}
                    aria-pressed={active}
                    className={cn(
                      "rounded-xl p-4 text-left transition",
                      active
                        ? "border-2 border-brand-accent-dark bg-brand-surface"
                        : "border-2 border-transparent bg-brand-sand/70 hover:bg-brand-sand",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[11px] font-bold uppercase tracking-[0.08em] text-brand-ink">
                        {card.title}
                      </span>
                      <span className="rounded bg-status-paid-bg px-2 py-0.5 text-[10px] font-bold text-status-paid-fg">
                        {costTag}
                      </span>
                    </div>
                    <p className="mt-2 text-sm text-brand-muted">{card.text}</p>
                    <p
                      className={cn(
                        "mt-3 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.08em]",
                        active ? "text-brand-accent-dark" : "text-brand-subtle",
                      )}
                    >
                      {active ? (
                        <>
                          <Check className="size-3.5" /> Выбрано
                        </>
                      ) : (
                        "Выбрать"
                      )}
                    </p>
                  </button>
                );
              })}
            </div>

            {method === "showroom_pickup" ? (
              <p className="mt-5 rounded-xl bg-brand-sand/70 p-4 text-sm text-brand-muted">
                Заберите заказ в бутике KOCHEVNIK на Б. Дмитровке. Мы сообщим, когда он будет готов.
              </p>
            ) : (
              <div className="mt-5 rounded-xl bg-brand-sand/50 p-4 md:p-5">
                <div className="flex items-center justify-between">
                  <h3 className="text-[11px] font-bold uppercase tracking-[0.1em] text-brand-ink">
                    {method === "cdek_pvz" ? "Пункт выдачи СДЭК" : "Адрес доставки"}
                  </h3>
                  <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-brand-muted">Шаг 3 из 3</span>
                </div>
                <div className="mt-4 grid gap-4">
                  {method === "cdek_pvz" ? (
                    <FormField
                      label="Код пункта выдачи"
                      required
                      error={errors.pvz_code?.message}
                      hint="Код ПВЗ можно найти на сайте СДЭК, например MSK123"
                    >
                      <input {...register("pvz_code")} className={inputClass} />
                    </FormField>
                  ) : null}
                  <FormField
                    label={method === "cdek_pvz" ? "Комментарий к адресу пункта" : "Улица, дом, корпус"}
                    required={method !== "cdek_pvz"}
                    error={errors.street?.message}
                  >
                    <input {...register("street")} autoComplete="street-address" className={inputClass} />
                  </FormField>
                  {method !== "cdek_pvz" ? (
                    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                      <FormField label="Кв./офис">
                        <input {...register("apartment")} className={inputClass} />
                      </FormField>
                      <FormField label="Подъезд">
                        <input {...register("entrance")} className={inputClass} />
                      </FormField>
                      <FormField label="Домофон">
                        <input {...register("intercom")} className={inputClass} />
                      </FormField>
                      <FormField label="Этаж">
                        <input {...register("floor")} className={inputClass} />
                      </FormField>
                    </div>
                  ) : null}
                </div>
              </div>
            )}

            <FormField label="Комментарий к заказу" className="mt-5">
              <textarea
                {...register("comment")}
                placeholder="Код калитки, пожелания курьеру или комментарий"
                className={textareaClass}
              />
            </FormField>
          </SectionCard>

          <SectionCard number={3} title="Способ оплаты">
            <div className="flex items-start gap-4 rounded-xl border-2 border-brand-accent-dark bg-brand-surface p-4 md:p-5">
              <span className="mt-1 grid size-4 shrink-0 place-items-center rounded-full border-2 border-brand-accent-dark">
                <span className="size-2 rounded-full bg-brand-accent-dark" />
              </span>
              <div className="flex-1">
                <p className="text-[11px] font-bold uppercase tracking-[0.08em] text-brand-ink">
                  СБП (Система быстрых платежей)
                </p>
                <p className="mt-1 text-sm text-brand-muted">
                  Оплата в приложении любого банка в один клик. После нажатия кнопки мы перенесём вас на страницу оплаты.
                </p>
              </div>
              <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-brand-muted">
                <Lock className="size-3.5" /> Безопасная оплата
              </span>
            </div>
          </SectionCard>
        </div>

        {/* Сводка заказа */}
        <aside className="rounded-2xl bg-brand-section p-6 shadow-[0_4px_24px_rgba(57,46,33,0.08)] lg:sticky lg:top-28">
          <div className="flex items-center gap-3 border-b border-brand-line pb-4">
            <h2 className="font-accent text-xl font-normal text-brand-ink">Товары</h2>
            <span className="rounded-full bg-brand-sand px-2 py-0.5 text-[11px] text-brand-muted">
              {totals.count} шт.
            </span>
          </div>

          <ul className="divide-y divide-brand-line">
            {items.map((item) => (
              <li key={item.key} className="flex gap-3 py-4">
                <div className="h-20 w-16 shrink-0 overflow-hidden rounded-lg bg-brand-sand">
                  {item.imageUrl ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={item.imageUrl} alt={item.name} className="size-full object-cover" />
                  ) : null}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-2">
                    <p className="line-clamp-2 text-sm font-medium leading-snug text-brand-ink">{item.name}</p>
                    <button
                      type="button"
                      onClick={() => removeItem(item.key)}
                      aria-label="Удалить из заказа"
                      className="text-brand-subtle hover:text-brand-red"
                    >
                      <X className="size-4" />
                    </button>
                  </div>
                  <p className="mt-1 text-[11px] font-bold uppercase tracking-[0.04em] text-brand-muted">
                    {item.color ?? "Цвет не указан"} • {item.size}
                    {item.quantity > 1 ? ` • ${item.quantity} шт.` : ""}
                  </p>
                  <div className="mt-2 flex items-baseline gap-2">
                    <span className="text-[15px] font-semibold text-brand-ink">
                      {formatPrice(item.price * item.quantity)}
                    </span>
                    {item.oldPrice ? (
                      <span className="text-xs text-brand-subtle line-through">
                        {formatPrice(item.oldPrice * item.quantity)}
                      </span>
                    ) : null}
                  </div>
                </div>
              </li>
            ))}
          </ul>

          <dl className="space-y-3 border-t border-brand-line pt-5 text-sm text-brand-muted">
            <div className="flex justify-between">
              <dt>Сумма заказа</dt>
              <dd className="font-medium text-brand-ink">{formatPrice(totals.gross)}</dd>
            </div>
            {totals.discount > 0 ? (
              <div className="flex justify-between">
                <dt>Скидка</dt>
                <dd className="font-medium text-brand-red">−{formatPrice(totals.discount)}</dd>
              </div>
            ) : null}
            <div className="flex justify-between">
              <dt>Доставка</dt>
              <dd className="font-medium text-brand-ink">
                {deliveryFreeNow ? "Бесплатно" : "Рассчитается при оформлении"}
              </dd>
            </div>
          </dl>

          <div className="mt-6 flex items-end justify-between border-t border-brand-line pt-5">
            <span className="text-[11px] font-bold uppercase tracking-[0.1em] text-brand-muted">Итого к оплате</span>
            <span className="text-[11px] font-bold uppercase tracking-[0.06em] text-brand-muted">НДС включён</span>
          </div>
          <p className="mt-1 text-4xl font-semibold text-brand-ink">{formatPrice(totals.total)}</p>

          <button
            type="submit"
            disabled={busy}
            className={cn(btnPrimary, "mt-6 h-14 w-full justify-between rounded-xl px-5 text-xs font-bold uppercase")}
          >
            <span>{busy ? "Оформляем заказ…" : `Оплатить заказ на сумму ${formatPrice(totals.total)}`}</span>
            <ArrowRight className="size-4 shrink-0" />
          </button>
          <p className="mt-3 text-center text-[11px] leading-relaxed text-brand-muted">
            Нажимая кнопку, вы соглашаетесь с условиями оферты и политикой конфиденциальности.
          </p>
          <p className="mt-2 text-center text-xs text-brand-subtle">
            {totals.count} {pluralize(totals.count, "товар", "товара", "товаров")} в заказе
          </p>
        </aside>
      </div>
    </form>
  );
}
