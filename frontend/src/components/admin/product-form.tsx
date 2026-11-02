"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowDown, ArrowUp, ImagePlus, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Panel } from "@/components/admin/admin-ui";
import { useCategories } from "@/hooks/use-categories";
import {
  useCreateProduct,
  useDeleteProductImage,
  useReorderProductImages,
  useUpdateProduct,
  useUploadProductImages,
} from "@/hooks/use-products";
import { flattenCategories } from "@/lib/categories";
import {
  adminBtn,
  adminBtnDanger,
  adminBtnOutline,
  adminInput,
  adminLabel,
  adminTextarea,
} from "@/lib/styles";
import type { Schema } from "@/types";

type Product = Schema<"ProductDetailOut">;

function Field({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <label className={adminLabel}>{label}</label>
      {children}
    </div>
  );
}

const emptyToNull = (v: string) => (v.trim() === "" ? null : v.trim());

// Менеджер фото: загрузка, порядок, удаление
function ImagesManager({ product }: { product: Product }) {
  const upload = useUploadProductImages();
  const reorder = useReorderProductImages();
  const remove = useDeleteProductImage();
  const fileRef = useRef<HTMLInputElement>(null);

  const images = [...(product.images ?? [])].sort((a, b) => (a.position ?? 0) - (b.position ?? 0));

  const move = (index: number, dir: -1 | 1) => {
    const target = index + dir;
    if (target < 0 || target >= images.length) return;
    const ids = images.map((i) => i.id);
    [ids[index], ids[target]] = [ids[target], ids[index]];
    reorder.mutate({ productId: product.id, imageIds: ids });
  };

  return (
    <Panel
      title="Фотографии"
      actions={
        <>
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            multiple
            hidden
            onChange={(e) => {
              const files = Array.from(e.target.files ?? []);
              if (files.length) upload.mutate({ productId: product.id, files });
              e.target.value = "";
            }}
          />
          <button type="button" disabled={upload.isPending} onClick={() => fileRef.current?.click()} className={adminBtn}>
            <ImagePlus className="size-4" /> {upload.isPending ? "Загружаем…" : "Загрузить фото"}
          </button>
        </>
      }
    >
      {images.length === 0 ? (
        <p className="text-sm text-muted-foreground">Фото ещё нет. Первое фото станет главным.</p>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {images.map((img, i) => (
            <li key={img.id} className="overflow-hidden rounded-md border border-border bg-card">
              <div className="relative aspect-[3/4] bg-muted">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={img.url} alt="" className="size-full object-cover" />
                {i === 0 ? (
                  <span className="absolute left-2 top-2 rounded bg-primary px-1.5 py-0.5 text-[10px] font-semibold text-primary-foreground">
                    Главное
                  </span>
                ) : null}
              </div>
              <div className="flex items-center justify-between gap-1 p-2">
                <div className="flex gap-1">
                  <button
                    type="button"
                    disabled={i === 0 || reorder.isPending}
                    onClick={() => move(i, -1)}
                    aria-label="Выше"
                    className={`${adminBtnOutline} px-2`}
                  >
                    <ArrowUp className="size-4" />
                  </button>
                  <button
                    type="button"
                    disabled={i === images.length - 1 || reorder.isPending}
                    onClick={() => move(i, 1)}
                    aria-label="Ниже"
                    className={`${adminBtnOutline} px-2`}
                  >
                    <ArrowDown className="size-4" />
                  </button>
                </div>
                <button
                  type="button"
                  disabled={remove.isPending}
                  onClick={() => window.confirm("Удалить это фото?") && remove.mutate({ productId: product.id, imageId: img.id })}
                  aria-label="Удалить фото"
                  className={`${adminBtnDanger} px-2`}
                >
                  <Trash2 className="size-4" />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

// Форма товара: и для создания, и для редактирования
export function ProductForm({ product }: { product?: Product }) {
  const router = useRouter();
  const isEdit = Boolean(product);
  const { data: tree } = useCategories();
  const categories = flattenCategories(tree);

  const create = useCreateProduct();
  const update = useUpdateProduct();
  const upload = useUploadProductImages();

  const [slug, setSlug] = useState(product?.slug ?? "");
  const [name, setName] = useState(product?.name ?? "");
  const [article, setArticle] = useState(product?.article ?? "");
  const [brand, setBrand] = useState(product?.brand ?? "KOCHEVNIK");
  const [categoryId, setCategoryId] = useState(product?.category_id ? String(product.category_id) : "");
  const [status, setStatus] = useState<"active" | "draft" | "archived">(
    (product?.status as "active" | "draft" | "archived" | undefined) ?? "active",
  );
  const [color, setColor] = useState(product?.color ?? "");
  const [colorHex, setColorHex] = useState(product?.color_hex ?? "#8a6f55");
  const [colorGroup, setColorGroup] = useState(product?.color_group ?? "");
  const [composition, setComposition] = useState(product?.composition ?? "");
  const [density, setDensity] = useState(product?.density_yarn ?? "");
  const [care, setCare] = useState(product?.care_text ?? "");
  const [measurements, setMeasurements] = useState(product?.measurements ?? "");
  const [description, setDescription] = useState(product?.description ?? "");
  const [price, setPrice] = useState(product ? String(product.current_price) : "");
  const [oldPrice, setOldPrice] = useState(product?.old_price ? String(product.old_price) : "");
  const [sizes, setSizes] = useState<{ size: string; stock: string }[]>(
    product?.sizes?.length
      ? product.sizes.map((s) => ({ size: s.size, stock: String(s.stock) }))
      : [{ size: "ONE SIZE", stock: "1" }],
  );
  const [materials, setMaterials] = useState<{ material: string; percent: string }[]>(
    (product?.materials ?? []).map((m) => ({ material: m.material, percent: m.percent != null ? String(m.percent) : "" })),
  );
  const [attrs, setAttrs] = useState<{ key: string; value: string }[]>(
    (product?.attributes ?? []).map((a) => ({ key: a.attr_key, value: a.attr_value })),
  );
  const [siblings, setSiblings] = useState((product?.color_variants ?? []).map((v) => v.sibling_slug).join("\n"));
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!isEdit && !/^[a-z0-9][a-z0-9-]*$/.test(slug.trim())) {
      toast.error("Адрес (slug) может содержать только латинские буквы, цифры и дефисы");
      return;
    }
    if (name.trim().length < 2) {
      toast.error("Введите название товара");
      return;
    }
    const priceNum = Number(price);
    if (!Number.isInteger(priceNum) || priceNum <= 0) {
      toast.error("Цена должна быть целым числом больше нуля");
      return;
    }
    const oldNum = oldPrice.trim() === "" ? null : Number(oldPrice);
    if (oldNum !== null && (!Number.isInteger(oldNum) || oldNum <= 0)) {
      toast.error("Старая цена должна быть целым числом или пустой");
      return;
    }

    const sizesStock: Record<string, number> = {};
    for (const row of sizes) {
      const s = row.size.trim();
      if (!s) continue;
      const n = Number(row.stock);
      if (!Number.isInteger(n) || n < 0) {
        toast.error(`Остаток для размера «${s}» должен быть целым числом от 0`);
        return;
      }
      sizesStock[s] = n;
    }
    if (!isEdit && Object.keys(sizesStock).length === 0) {
      toast.error("Добавьте хотя бы один размер");
      return;
    }

    // Для каждого материала процент обязателен (число от 0 до 100)
    const materialsList: { material: string; percent: number }[] = [];
    for (const m of materials) {
      const materialName = m.material.trim();
      if (!materialName) continue;
      const percentNum = Number(m.percent);
      if (m.percent.trim() === "" || !Number.isFinite(percentNum) || percentNum < 0 || percentNum > 100) {
        toast.error(`Для материала «${materialName}» укажите процент от 0 до 100`);
        return;
      }
      materialsList.push({ material: materialName, percent: percentNum });
    }
    const attributes: Record<string, string> = {};
    for (const a of attrs) if (a.key.trim()) attributes[a.key.trim()] = a.value.trim();
    const siblingSlugs = siblings.split(/[\s,]+/).map((s) => s.trim()).filter(Boolean);

    const common = {
      name: name.trim(),
      article: emptyToNull(article),
      brand: brand.trim() || "KOCHEVNIK",
      category_id: categoryId ? Number(categoryId) : null,
      color: emptyToNull(color),
      color_hex: emptyToNull(colorHex),
      color_group: emptyToNull(colorGroup),
      composition: emptyToNull(composition),
      density_yarn: emptyToNull(density),
      care_text: emptyToNull(care),
      measurements: emptyToNull(measurements),
      description: emptyToNull(description),
      current_price: priceNum,
      old_price: oldNum,
      sizes_stock: sizesStock,
      materials: materialsList,
      sibling_slugs: siblingSlugs,
      attributes,
    };

    if (isEdit && product) {
      update.mutate({ productId: product.id, data: { ...common, status } });
      return;
    }

    try {
      const created = await create.mutateAsync({ ...common, slug: slug.trim(), sizes_stock: sizesStock });
      if (pendingFiles.length > 0) {
        await upload.mutateAsync({ productId: created.id, files: pendingFiles });
      }
      router.push(`/admin/products/${created.slug}`);
    } catch {
      // ошибка уже показана уведомлением
    }
  };

  const busy = create.isPending || update.isPending || upload.isPending;

  return (
    <form onSubmit={submit} className="flex flex-col gap-5">
      <Panel title="Основное">
        <div className="grid gap-4 md:grid-cols-2">
          {!isEdit ? (
            <Field label="Адрес товара (slug), латиницей *">
              <input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="temno-korichnevaya-manishka" className={adminInput} />
            </Field>
          ) : (
            <Field label="Адрес товара (slug)">
              <input value={slug} disabled className={`${adminInput} opacity-60`} />
            </Field>
          )}
          <Field label="Название *">
            <input value={name} onChange={(e) => setName(e.target.value)} className={adminInput} />
          </Field>
          <Field label="Артикул">
            <input value={article} onChange={(e) => setArticle(e.target.value)} className={adminInput} />
          </Field>
          <Field label="Бренд">
            <input value={brand} onChange={(e) => setBrand(e.target.value)} className={adminInput} />
          </Field>
          <Field label="Категория">
            <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)} className={adminInput}>
              <option value="">Не выбрана</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.parent_id ? "— " : ""}
                  {c.name}
                </option>
              ))}
            </select>
          </Field>
          {isEdit ? (
            <Field label="Статус">
              <select value={status} onChange={(e) => setStatus(e.target.value as typeof status)} className={adminInput}>
                <option value="active">Опубликован</option>
                <option value="draft">Черновик</option>
                <option value="archived">В архиве</option>
              </select>
            </Field>
          ) : null}
          <Field label="Цена, ₽ *">
            <input value={price} onChange={(e) => setPrice(e.target.value)} inputMode="numeric" className={adminInput} />
          </Field>
          <Field label="Старая цена, ₽ (если есть скидка)">
            <input value={oldPrice} onChange={(e) => setOldPrice(e.target.value)} inputMode="numeric" className={adminInput} />
          </Field>
        </div>
      </Panel>

      <Panel title="Цвет">
        <div className="grid gap-4 md:grid-cols-3">
          <Field label="Название цвета">
            <input value={color} onChange={(e) => setColor(e.target.value)} placeholder="Тёмный шоколад" className={adminInput} />
          </Field>
          <Field label="Цвет (оттенок)">
            <div className="flex gap-2">
              <input
                type="color"
                value={/^#[0-9a-fA-F]{6}$/.test(colorHex) ? colorHex : "#8a6f55"}
                onChange={(e) => setColorHex(e.target.value)}
                className="h-9 w-12 cursor-pointer rounded-md border border-input bg-card p-1"
              />
              <input value={colorHex} onChange={(e) => setColorHex(e.target.value)} className={adminInput} />
            </div>
          </Field>
          <Field label="Группа цвета">
            <input value={colorGroup} onChange={(e) => setColorGroup(e.target.value)} className={adminInput} />
          </Field>
          <Field label="Другие цвета этого товара (slug, по одному в строке)" className="md:col-span-3">
            <textarea value={siblings} onChange={(e) => setSiblings(e.target.value)} className={adminTextarea} />
          </Field>
        </div>
      </Panel>

      <Panel
        title="Размеры и остатки"
        actions={
          <button type="button" onClick={() => setSizes([...sizes, { size: "", stock: "0" }])} className={adminBtnOutline}>
            <Plus className="size-4" /> Добавить размер
          </button>
        }
      >
        <div className="grid gap-2">
          {sizes.map((row, i) => (
            <div key={i} className="flex gap-2">
              <input
                value={row.size}
                onChange={(e) => setSizes(sizes.map((r, j) => (j === i ? { ...r, size: e.target.value } : r)))}
                placeholder="Размер (S, M, ONE SIZE)"
                className={adminInput}
              />
              <input
                value={row.stock}
                onChange={(e) => setSizes(sizes.map((r, j) => (j === i ? { ...r, stock: e.target.value } : r)))}
                inputMode="numeric"
                placeholder="Остаток"
                className={`${adminInput} max-w-32`}
              />
              <button type="button" onClick={() => setSizes(sizes.filter((_, j) => j !== i))} aria-label="Убрать размер" className={`${adminBtnDanger} px-2.5`}>
                <Trash2 className="size-4" />
              </button>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="Описание и характеристики">
        <div className="grid gap-4">
          <Field label="Описание">
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} className={`${adminTextarea} min-h-32`} />
          </Field>
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Состав">
              <textarea value={composition} onChange={(e) => setComposition(e.target.value)} className={adminTextarea} />
            </Field>
            <Field label="Уход">
              <textarea value={care} onChange={(e) => setCare(e.target.value)} className={adminTextarea} />
            </Field>
            <Field label="Мерки изделия">
              <textarea value={measurements} onChange={(e) => setMeasurements(e.target.value)} className={adminTextarea} />
            </Field>
            <Field label="Плотность пряжи">
              <input value={density} onChange={(e) => setDensity(e.target.value)} className={adminInput} />
            </Field>
          </div>
        </div>
      </Panel>

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel
          title="Материалы"
          actions={
            <button type="button" onClick={() => setMaterials([...materials, { material: "", percent: "" }])} className={adminBtnOutline}>
              <Plus className="size-4" /> Добавить
            </button>
          }
        >
          <div className="grid gap-2">
            {materials.length === 0 ? <p className="text-sm text-muted-foreground">Материалы не указаны.</p> : null}
            {materials.map((row, i) => (
              <div key={i} className="flex gap-2">
                <input
                  value={row.material}
                  onChange={(e) => setMaterials(materials.map((r, j) => (j === i ? { ...r, material: e.target.value } : r)))}
                  placeholder="Пух яка"
                  className={adminInput}
                />
                <input
                  value={row.percent}
                  onChange={(e) => setMaterials(materials.map((r, j) => (j === i ? { ...r, percent: e.target.value } : r)))}
                  inputMode="decimal"
                  placeholder="%"
                  className={`${adminInput} max-w-24`}
                />
                <button type="button" onClick={() => setMaterials(materials.filter((_, j) => j !== i))} aria-label="Убрать материал" className={`${adminBtnDanger} px-2.5`}>
                  <Trash2 className="size-4" />
                </button>
              </div>
            ))}
          </div>
        </Panel>

        <Panel
          title="Свойства"
          actions={
            <button type="button" onClick={() => setAttrs([...attrs, { key: "", value: "" }])} className={adminBtnOutline}>
              <Plus className="size-4" /> Добавить
            </button>
          }
        >
          <div className="grid gap-2">
            {attrs.length === 0 ? <p className="text-sm text-muted-foreground">Свойства не указаны.</p> : null}
            {attrs.map((row, i) => (
              <div key={i} className="flex gap-2">
                <input
                  value={row.key}
                  onChange={(e) => setAttrs(attrs.map((r, j) => (j === i ? { ...r, key: e.target.value } : r)))}
                  placeholder="Название"
                  className={adminInput}
                />
                <input
                  value={row.value}
                  onChange={(e) => setAttrs(attrs.map((r, j) => (j === i ? { ...r, value: e.target.value } : r)))}
                  placeholder="Значение"
                  className={adminInput}
                />
                <button type="button" onClick={() => setAttrs(attrs.filter((_, j) => j !== i))} aria-label="Убрать свойство" className={`${adminBtnDanger} px-2.5`}>
                  <Trash2 className="size-4" />
                </button>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      {isEdit && product ? <ImagesManager product={product} /> : null}

      {!isEdit ? (
        <Panel title="Фотографии">
          <input
            type="file"
            accept="image/*"
            multiple
            onChange={(e) => setPendingFiles(Array.from(e.target.files ?? []))}
            className="text-sm"
          />
          <p className="mt-2 text-xs text-muted-foreground">
            Фото загрузятся сразу после создания товара. Выбрано: {pendingFiles.length}.
          </p>
        </Panel>
      ) : null}

      <div className="flex gap-3">
        <button type="submit" disabled={busy} className={adminBtn}>
          {busy ? "Сохраняем…" : isEdit ? "Сохранить изменения" : "Создать товар"}
        </button>
        <button type="button" onClick={() => router.push("/admin/products")} className={adminBtnOutline}>
          К списку товаров
        </button>
      </div>
    </form>
  );
}
