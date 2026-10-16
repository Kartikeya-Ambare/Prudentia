import { useLayoutEffect, useRef } from "react";
import { gsapReady, NO_REDUCED_MOTION } from "@/lib/gsap";

/** Counts from 0 to `value` when it appears or changes, like the dashboard numbers. `format` turns a number into text. */
export function CountUp({ value, format, className }: { value: number; format: (n: number) => string; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.textContent = format(value);
    let cancelled = false;
    let mm: { revert: () => void } | undefined;
    gsapReady.then(({ gsap }) => {
      if (cancelled) return;
      const m = gsap.matchMedia();
      mm = m;
      m.add(NO_REDUCED_MOTION, () => {
        const counter = { n: 0 };
        el.textContent = format(0);
        gsap.to(counter, { n: value, duration: 0.8, ease: "power3.out", onUpdate: () => { el.textContent = format(counter.n); } });
      });
    });
    return () => { cancelled = true; mm?.revert(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  return <span ref={ref} aria-label={format(value)} className={className} />;
}
