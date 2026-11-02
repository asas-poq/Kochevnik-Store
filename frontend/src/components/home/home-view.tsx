"use client";

import Link from "next/link";
import { PackageSearch } from "lucide-react";
import { CategoryTiles } from "@/components/home/category-tiles";
import { HeroBanner } from "@/components/home/hero-banner";
import { ProductSection } from "@/components/product/product-section";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { useRecommendations } from "@/hooks/use-products";
import { getDiscount } from "@/lib/utils";

export function HomeView() {
  // Один запрос отдаёт все подборки: popular, seasonal, new_arrivals, on_sale
  const { data, isLoading, isError, refetch } = useRecommendations({ limit: 12 });

  // Каждая секция показывает только свои товары.
  // В «Привилегии сезона» попадают только товары с настоящей скидкой.
  const popular = data?.popular ?? [];
  const newArrivals = data?.new_arrivals ?? [];
  const onSale = (data?.on_sale ?? []).filter((p) => getDiscount(p) !== null);

  const isEverythingEmpty =
    !isLoading &&
    !isError &&
    popular.length === 0 &&
    newArrivals.length === 0 &&
    onSale.length === 0;

  return (
    <>
      <HeroBanner />

      {isError ? (
        <div className="container-page py-16">
          <ErrorState onRetry={() => refetch()} />
        </div>
      ) : isEverythingEmpty ? (
        <div className="container-page py-16">
          <EmptyState
            icon={<PackageSearch />}
            title="Скоро здесь появятся новинки"
            description="Каталог пока пополняется. Загляните сюда чуть позже."
            action={
              <Link
                href="/catalog"
                className="inline-flex h-10 items-center rounded-full bg-brand-ink px-6 text-sm font-medium text-brand-surface"
              >
                Открыть каталог
              </Link>
            }
          />
        </div>
      ) : (
        <ProductSection
          title="Хиты продаж"
          subtitle="Знаковые силуэты, заслужившие любовь наших ценителей"
          href="/catalog?sort=popular"
          linkLabel="Весь каталог хитов"
          products={popular.slice(0, 4)}
          isLoading={isLoading}
          badge="hit"
        />
      )}

      <CategoryTiles />

      {!isError ? (
        <>
          <ProductSection
            eyebrow="СВЕЖИЙ РЕЛИЗ"
            title="Новинки сезона"
            subtitle="Свежее пополнение коллекции: природная палитра без химического окрашивания"
            href="/catalog?sort=newest"
            products={newArrivals}
            isLoading={isLoading}
            badge="new"
            layout="carousel"
          />

          <ProductSection
            title="Привилегии сезона"
            subtitle="Особые ценовые условия на завершающие капсулы прошлых релизов"
            href="/catalog?on_sale=true&sort=discount"
            linkLabel="Смотреть весь архив"
            products={onSale.slice(0, 4)}
            isLoading={isLoading}
            badge="sale"
          />
        </>
      ) : null}
    </>
  );
}
