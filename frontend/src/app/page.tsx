import { HomeView } from "@/components/home/home-view";
import { ShopShell } from "@/components/layout/shop-shell";

export default function HomePage() {
  return (
    <ShopShell>
      <HomeView />
    </ShopShell>
  );
}
