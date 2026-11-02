import type { Metadata } from "next";
import { LikesView } from "@/components/profile/likes-view";

export const metadata: Metadata = { title: "Избранное" };

export default function ProfileLikesPage() {
  return <LikesView />;
}

// Эти страницы открываются только после входа, поэтому проверку мгновенной навигации отключаем
export const instant = false;
