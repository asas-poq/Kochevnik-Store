import type { Schema } from "@/types";

export type CategoryNode = Schema<"CategoryTreeOut">;

// Разворачивает дерево категорий в плоский список
export function flattenCategories(
  tree: CategoryNode[] | undefined,
): CategoryNode[] {
  if (!tree) return [];
  const result: CategoryNode[] = [];
  const walk = (nodes: CategoryNode[]) => {
    for (const node of nodes) {
      result.push(node);
      if (node.children?.length) walk(node.children);
    }
  };
  walk(tree);
  return result;
}

// Ищет категорию по slug
export function findCategoryBySlug(
  tree: CategoryNode[] | undefined,
  slug: string,
): CategoryNode | null {
  return flattenCategories(tree).find((c) => c.slug === slug) ?? null;
}

// Путь от корня до категории: нужен для «хлебных крошек»
export function findCategoryPath(
  tree: CategoryNode[] | undefined,
  slug: string,
): CategoryNode[] {
  if (!tree) return [];
  const walk = (nodes: CategoryNode[], trail: CategoryNode[]): CategoryNode[] => {
    for (const node of nodes) {
      const next = [...trail, node];
      if (node.slug === slug) return next;
      if (node.children?.length) {
        const found = walk(node.children, next);
        if (found.length) return found;
      }
    }
    return [];
  };
  return walk(tree, []);
}

// Ищет первую категорию, в названии которой есть ВСЕ указанные слова
// (используется для плиток на главной: «сумк», «ремн», «плед»…)
export function findCategoryByKeywords(
  tree: CategoryNode[] | undefined,
  keywords: string[],
): CategoryNode | null {
  const words = keywords.map((w) => w.toLowerCase());
  return (
    flattenCategories(tree).find((c) => {
      const name = c.name.toLowerCase();
      return words.every((w) => name.includes(w));
    }) ?? null
  );
}
