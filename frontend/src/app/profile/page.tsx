import type { Metadata } from "next";
import { ProfileForm } from "@/components/profile/profile-form";

export const metadata: Metadata = { title: "Личный кабинет" };

export default function ProfilePage() {
  return <ProfileForm />;
}

// Эти страницы открываются только после входа, поэтому проверку мгновенной навигации отключаем
export const instant = false;
