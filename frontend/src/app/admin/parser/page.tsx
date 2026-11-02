import type { Metadata } from "next";
import { ParserAdmin } from "@/components/admin/parser-admin";

export const metadata: Metadata = { title: "Админка: парсер" };

export default function AdminParserPage() {
  return <ParserAdmin />;
}

// Эти страницы открываются только после входа, поэтому проверку мгновенной навигации отключаем
export const instant = false;
