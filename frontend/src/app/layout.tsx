import type { Metadata, Viewport } from "next";
import { Manrope, Modern_Antiqua, Playpen_Sans } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";
import { cn } from "@/lib/utils";

// Основной шрифт сайта (в макетах — Manrope), поддерживает кириллицу
const manrope = Manrope({
  subsets: ["latin", "cyrillic"],
  variable: "--font-manrope",
  display: "swap",
});

// Рукописный акцентный шрифт для крупных надписей на баннерах
const playpen = Playpen_Sans({
  subsets: ["latin"],
  variable: "--font-playpen",
  display: "swap",
});

// Шрифт логотипа KOCHEVNIK (в нём только латиница, это нормально для логотипа)
const antiqua = Modern_Antiqua({
  subsets: ["latin"],
  weight: "400",
  variable: "--font-antiqua",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL(
    process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000",
  ),
  title: {
    default: "Kochevnik Store — кашемир и кожа",
    template: "%s — Kochevnik Store",
  },
  description:
    "Интернет-магазин изделий из натурального монгольского кашемира, шерсти яка и кожи.",
  applicationName: "Kochevnik Store",
  // iPhone не должен превращать цифры (цены, телефоны) в синие ссылки
  formatDetection: { telephone: false, email: false, address: false },
  appleWebApp: { capable: true, title: "Kochevnik", statusBarStyle: "default" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover", // страница занимает весь экран iPhone, отступы мы делаем сами (safe-area)
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fdf9f4" },
    { media: "(prefers-color-scheme: dark)", color: "#0b0a09" },
  ],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // suppressHydrationWarning нужен для next-themes: он добавляет класс на <html>
    <html
      lang="ru"
      suppressHydrationWarning
      className={cn(
        "h-full",
        manrope.variable,
        playpen.variable,
        antiqua.variable,
      )}
    >
      <body className="flex min-h-dvh flex-col">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
