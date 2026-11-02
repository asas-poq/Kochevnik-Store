import { Suspense } from "react";
import { ProductEditor } from "@/components/admin/product-editor";
import { Skeleton } from "@/components/ui/skeleton";

async function EditorContent({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <ProductEditor slug={slug} />;
}

export default function AdminEditProductPage({ params }: { params: Promise<{ slug: string }> }) {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <EditorContent params={params} />
    </Suspense>
  );
}

// Эти страницы открываются только после входа, поэтому проверку мгновенной навигации отключаем
export const instant = false;
