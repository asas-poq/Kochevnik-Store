// Убирает из параметров запроса пустые значения, чтобы они не попадали в адрес:
// undefined, null, пустые строки, false и пустые массивы.
// Число 0 остаётся (например, min_price=0).
export function cleanParams<T extends object>(
  params: T,
): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (value === false) continue;
    if (Array.isArray(value) && value.length === 0) continue;
    result[key] = value;
  }
  return result;
}
