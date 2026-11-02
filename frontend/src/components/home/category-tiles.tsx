"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { useCategories } from "@/hooks/use-categories";
import { findCategoryByKeywords } from "@/lib/categories";

// Плитки категорий. Название и картинка берутся из макета,
// ссылка ищется в дереве категорий бэкенда по ключевым словам в названии.
const TILES = [
  {
    title: "Сумки из натуральной кожи",
    keywords: ["сумк"],
    image: "/images/home/tile-bags.jpg",
  },
  {
    title: "Женская одежда из кашемира, пуха яка и шерсти верблюда",
    keywords: ["женск", "одежд"],
    image: "/images/home/tile-women.jpg",
  },
  {
    title: "Ремни из натуральной кожи",
    keywords: ["ремн"],
    image: "/images/home/tile-belts.jpg",
  },
  {
    title: "Пледы и одеяла",
    keywords: ["плед"],
    image: "/images/home/tile-blankets.jpg",
  },
  {
    title: "Женские джемперы и водолазки",
    keywords: ["женск", "джемпер"],
    image: "/images/home/tile-sweaters.jpg",
  },
  {
    title: "Мужская одежда из кашемира, пуха яка и шерсти верблюда",
    keywords: ["мужск", "одежд"],
    image: "/images/home/tile-men.jpg",
  },
];

export function CategoryTiles() {
  const { data: tree } = useCategories();

  return (
    <section className="container-page py-6 md:py-10">
      <div className="grid gap-4 md:grid-cols-2 md:gap-6">
        {TILES.map((tile) => {
          const category = findCategoryByKeywords(tree, tile.keywords);
          const href = category
            ? `/catalog?category=${encodeURIComponent(category.slug)}`
            : "/catalog";

          return (
            <Link
              key={tile.title}
              href={href}
              className="group relative isolate block aspect-[16/10] overflow-hidden rounded-xl bg-[linear-gradient(135deg,#8a7a66_0%,#392e21_100%)]"
            >
              <div
                className="absolute inset-0 -z-20 bg-cover bg-center transition-transform duration-700 group-hover:scale-105"
                style={{ backgroundImage: `url('${tile.image}')` }}
              />
              <div className="absolute inset-0 -z-10 bg-gradient-to-t from-black/65 via-black/10 to-transparent" />

              <h3 className="absolute bottom-10 left-5 max-w-[85%] font-accent text-2xl font-medium leading-tight text-brand-section/85 sm:left-8 sm:text-3xl md:text-[34px] lg:text-[40px] lg:leading-[1.1]">
                {tile.title}
              </h3>
              <span className="absolute bottom-4 right-5 flex items-center gap-1 text-sm tracking-[0.01em] text-brand-faint sm:right-8">
                <ArrowRight className="size-3.5" />
                Перейти
              </span>
            </Link>
          );
        })}
      </div>
    </section>
  );
}
