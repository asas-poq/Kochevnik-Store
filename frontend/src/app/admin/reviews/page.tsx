import type { Metadata } from "next";
import { ReviewsAdmin } from "@/components/admin/reviews-admin";

export const metadata: Metadata = { title: "Админка: отзывы" };

export default function AdminReviewsPage() {
  return <ReviewsAdmin />;
}

// Эти страницы открываются только после входа, поэтому проверку мгновенной навигации отключаем
export const instant = false;
