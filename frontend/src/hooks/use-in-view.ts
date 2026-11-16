
import { useEffect, useRef, useState } from "react";

// Срабатывает один раз, когда элемент попал в зону видимости экрана.
// Нужен, чтобы подгружать данные карточки только для тех товаров, которые видны.
export function useInView<T extends Element>(rootMargin = "200px") {
  const ref = useRef<T | null>(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const el = ref.current;

    if (!el || inView) return;

    if (typeof IntersectionObserver === "undefined") {
      const frame = requestAnimationFrame(() => {
        setInView(true);
      });

      return () => cancelAnimationFrame(frame);
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          setInView(true);
          observer.disconnect();
        }
      },
      { rootMargin },
    );

    observer.observe(el);

    return () => observer.disconnect();
  }, [inView, rootMargin]);

  return [ref, inView] as const;
}
