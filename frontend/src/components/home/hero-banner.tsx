import Link from "next/link";

// Большой баннер на главной.
// Фото лежит в public/images/home/hero.jpg. Если файла нет, показывается тёплый тёмный фон.
export function HeroBanner() {
  return (
    <section className="relative isolate flex min-h-[460px] items-center overflow-hidden bg-[linear-gradient(135deg,#4a3b2c_0%,#1a1612_100%)] md:min-h-[656px]">
      <div
        className="absolute inset-0 -z-20 bg-cover bg-center"
        style={{ backgroundImage: "url('/images/home/hero.jpg')" }}
      />
      {/* Затемнение слева (для читаемости текста) и снизу */}
      <div className="absolute inset-0 -z-10 bg-[linear-gradient(90deg,rgba(26,22,18,0.85)_0%,rgba(26,22,18,0.6)_50%,rgba(26,22,18,0)_100%)]" />
      <div className="absolute inset-0 -z-10 bg-[linear-gradient(0deg,rgba(26,22,18,0.7)_0%,rgba(26,22,18,0)_50%)]" />

      <div className="container-page flex flex-col items-center py-16">
        <h1 className="w-full max-w-4xl self-start text-4xl font-normal leading-[1.1] text-brand-cream sm:text-5xl lg:text-[64px]">
          Познакомьтесь с каталогом
          <span className="block font-accent text-brand-beige">
            натурального кашемира и шерсти
          </span>
        </h1>

        <Link
          href="/catalog"
          className="mt-12 inline-flex h-11 items-center rounded-full bg-brand-subtle/80 px-8 text-[15px] font-medium tracking-[0.02em] text-white backdrop-blur transition-colors hover:bg-brand-accent"
        >
          Смотреть коллекцию
        </Link>
      </div>
    </section>
  );
}
