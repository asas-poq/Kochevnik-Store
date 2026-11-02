import type { Metadata } from "next";
import { MyReviews } from "@/components/profile/my-reviews";

export const metadata: Metadata = { title: "Мои отзывы" };

export default function ProfileReviewsPage() {
  return <MyReviews />;
}

// Эти страницы открываются только после входа, поэтому проверку мгновенной навигации отключаем
export const instant = false;
