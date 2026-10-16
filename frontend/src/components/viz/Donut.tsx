import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { gsapReady, NO_REDUCED_MOTION } from "@/lib/gsap";

export interface DonutSegment { key: string; label: string; value: number; color: string; detail?: string }

const R = 80;
const STROKE = 28;
const GAP = 1.2; // percent of the ring left between segments: a gap of surface colour, not a border

/**
 * Part-to-whole for a handful of classes (6 at most). Sweeps in once with GSAP; hovering a legend row
 * lifts its slice. The legend carries the names and numbers, so nothing relies on colour alone.
 */
export function Donut({ segments, centre }: { segments: DonutSegment[]; centre: ReactNode }) {
  const total = segments.reduce((a, s) => a + s.value, 0) || 1;
  const [hot, setHot] = useState<string | null>(null);
  const arcs = useRef<(SVGCircleElement | null)[]>([]);
  const ring = 2 * Math.PI * R;

  let from = 0;
  const laid = segments.map((s) => {
    const share = (s.value / total) * 100;
    const start = from;
    from += share;
    return { ...s, share, start };
  });

  // Draws each arc from its start to its end; `p` is how far the sweep has got (0 to 1).
  const draw = (p: number) =>
    laid.forEach((s, i) => {
      const el = arcs.current[i];
      if (!el) return;
      const len = Math.max(Math.min(s.share, Math.max(0, p * 100 - s.start)) - (laid.length > 1 ? GAP : 0), 0);
      el.style.strokeDasharray = `${(len / 100) * ring} ${ring}`;
      el.style.strokeDashoffset = `${(-(s.start + GAP / 2) / 100) * ring}`;
    });

  const key = laid.map((s) => `${s.key}:${s.share.toFixed(1)}`).join("|");
  useLayoutEffect(() => {
    draw(1);
    let cancelled = false;
    let mm: { revert: () => void } | undefined;
    gsapReady.then(({ gsap }) => {
      if (cancelled) return;
      const m = gsap.matchMedia();
      mm = m;
      m.add(NO_REDUCED_MOTION, () => {
        const proxy = { p: 0 };
        draw(0);
        gsap.to(proxy, { p: 1, duration: 0.9, ease: "power3.out", onUpdate: () => draw(proxy.p) });
      });
    });
    return () => { cancelled = true; mm?.revert(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return (
    <div className="flex flex-wrap items-center gap-x-10 gap-y-6">
      <div className="relative size-[200px] shrink-0">
        <svg viewBox="0 0 200 200" className="size-full -rotate-90" role="img"
          aria-label={laid.map((s) => `${s.label} ${s.share.toFixed(0)}%`).join(", ")}>
          <circle cx="100" cy="100" r={R} fill="none" stroke="var(--color-rail)" strokeWidth={STROKE} />
          {laid.map((s, i) => (
            <circle
              key={s.key}
              ref={(el) => { arcs.current[i] = el; }}
              cx="100" cy="100" r={R} fill="none" stroke={s.color} strokeWidth={hot === s.key ? STROKE + 6 : STROKE}
              style={{ transition: "stroke-width 160ms ease, opacity 160ms ease", opacity: hot && hot !== s.key ? 0.35 : 1 }}
            />
          ))}
        </svg>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">{centre}</div>
      </div>
      <ul className="flex min-w-[220px] flex-1 flex-col gap-1">
        {laid.map((s) => (
          <li key={s.key}>
            <div
              onMouseEnter={() => setHot(s.key)} onMouseLeave={() => setHot(null)}
              onFocus={() => setHot(s.key)} onBlur={() => setHot(null)} tabIndex={0}
              className="flex items-center gap-3 rounded-[var(--radius-control)] px-3 py-2 outline-none focus-visible:outline-2 focus-visible:outline-accent"
            >
              <span className="size-3 shrink-0 rounded-[4px]" style={{ background: s.color }} aria-hidden />
              <span className="flex-1 text-[15px] leading-6">{s.label}</span>
              <span className="text-right">
                <span className="num block text-[16px] font-semibold leading-6">{s.share.toFixed(1)}%</span>
                {s.detail && <span className="num block text-[12.5px] leading-4 text-ink-3">{s.detail}</span>}
              </span>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
