import Link from "next/link";
import { Feather, ShieldCheck, Sparkles } from "lucide-react";
import { Logo } from "@/components/layout/logo";
import { CONTACTS, SOCIAL_LINKS } from "@/lib/constants";

// Три преимущества магазина над подвалом
const FEATURES = [
  {
    icon: ShieldCheck,
    title: "100% Чистый пух",
    text: "Полное отсутствие синтетических примесей и агрессивного химического обесцвечивания.",
  },
  {
    icon: Sparkles,
    title: "Монгольское происхождение",
    text: "Традиционный ручной вычес сырья в период весенней линьки в степях Монголии.",
  },
  {
    icon: Feather,
    title: "Тактильное совершенство",
    text: "Невесомое тепло, естественная терморегуляция и гипоаллергенные свойства.",
  },
];

const BUYER_LINKS = [
  { label: "Доставка и возврат", href: "/#delivery" },
  { label: "Уход за кашемиром", href: "/catalog?material=Кашемир" },
  { label: "Шоурумы", href: "/#delivery" },
];

const COLLECTION_LINKS = [
  { label: "Кашемир", href: "/catalog?material=Кашемир" },
  { label: "Кожа", href: "/catalog?material=Кожа" },
  { label: "Пух яка", href: "/catalog?material=Пух яка" },
  { label: "Аксессуары", href: "/catalog?search=аксессуары" },
];

const linkClass =
  "text-sm tracking-[0.01em] text-brand-ink-2 transition-colors hover:text-brand-accent";
const headingClass =
  "mb-4 font-accent text-lg font-medium text-brand-ink md:text-xl";

export function SiteFooter() {
  return (
    <footer className="mt-10 bg-brand-section">
      {/* Преимущества */}
      <section id="about" className="container-page grid gap-8 py-12 md:grid-cols-3 md:gap-10 md:py-16">
        {FEATURES.map(({ icon: Icon, title, text }) => (
          <div key={title} className="flex items-start gap-4">
            <div className="grid size-12 shrink-0 place-items-center rounded-full border border-brand-line bg-brand-surface text-brand-accent">
              <Icon className="size-5" />
            </div>
            <div>
              <h3 className="font-accent text-lg font-medium leading-7 text-brand-ink">
                {title}
              </h3>
              <p className="mt-1 text-sm leading-relaxed text-brand-subtle">
                {text}
              </p>
            </div>
          </div>
        ))}
      </section>

      {/* Ссылки */}
      <div className="container-page grid gap-10 pb-10 pt-4 sm:grid-cols-2 lg:grid-cols-[1.1fr_1fr_1fr_1fr_1fr] lg:pt-10">
        <Logo className="sm:col-span-2 lg:col-span-1" />

        <div id="delivery">
          <h4 className={headingClass}>Покупателям</h4>
          <ul className="flex flex-col gap-3">
            {BUYER_LINKS.map((l) => (
              <li key={l.label}>
                <Link href={l.href} className={linkClass}>
                  {l.label}
                </Link>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <h4 className={headingClass}>Коллекции</h4>
          <ul className="flex flex-col gap-3">
            {COLLECTION_LINKS.map((l) => (
              <li key={l.label}>
                <Link href={l.href} className={linkClass}>
                  {l.label}
                </Link>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <h4 className={headingClass}>Мы в соцсетях</h4>
          <ul className="flex flex-col gap-3">
            {SOCIAL_LINKS.map((l) => (
              <li key={l.label}>
                <a href={l.href} className={`${linkClass} underline underline-offset-4`}>
                  {l.label}
                </a>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <h4 className={headingClass}>Связаться с нами</h4>
          <ul className="flex flex-col gap-3">
            <li>
              <a
                href={CONTACTS.githubUrl}
                target="_blank"
                rel="noopener noreferrer"
                className={`${linkClass} underline underline-offset-4`}
              >
                {CONTACTS.github}
              </a>
            </li>
            <li>
              <a href={CONTACTS.phoneHref} className={`${linkClass} underline underline-offset-4`}>
                {CONTACTS.phone}
              </a>
            </li>
            <li className={`${linkClass} underline underline-offset-4`}>
              {CONTACTS.hours}
            </li>
          </ul>
        </div>
      </div>

      {/* Реквизиты */}
      <div className="container-page flex flex-col gap-4 pb-8 pt-6 text-sm leading-relaxed tracking-[0.01em] text-brand-muted">
        <p className="max-w-xl">
          ООО «УЛААНБААТАР» · ОГРН 1247800033392 · ИНН 7816748604 · 192236,
          Санкт-Петербург, ул. Белы Куна, д. 34А, лит. А, пом. 4-Н/15 О.102
        </p>
        <a
          href={CONTACTS.githubUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="w-fit underline underline-offset-4 transition-colors hover:text-brand-accent"
        >
          Разработчик магазина asas-poq
        </a>
      </div>

      <div className="container-page flex flex-col gap-3 pb-[max(2rem,env(safe-area-inset-bottom))] text-xs font-medium tracking-[0.04em] text-brand-subtle sm:flex-row sm:items-center sm:justify-between">
        <span>© 2025 Kochevnik. Все права защищены.</span>
        <div className="flex gap-6 text-sm font-normal text-brand-muted">
          <span>MIR</span>
          <span>VISA</span>
          <span>Mastercard</span>
          <span>СБП</span>
        </div>
      </div>
    </footer>
  );
}
