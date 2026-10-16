import { useEffect, useState } from "react";
import { useT } from "@/lib/i18n";

/**
 * A small 3x3 dot-matrix loader in the style of the "Glyph Pulse" loader: the centre lights first, then the
 * four edge dots, then the corners, and the pulse repeats. Dots are tiny and use the current text colour
 * (or the accent), so it sits next to a line of text instead of becoming a feature of its own.
 * Static (middle dot lit) under reduced motion.
 */
export function DotMatrixLoader({ dot = 5, gap = 2, label = "Loading", className }: { dot?: number; gap?: number; label?: string; className?: string }) {
  return (
    <span
      role="status"
      aria-label={label}
      className={`dm inline-grid shrink-0 text-accent ${className ?? ""}`}
      style={{ gridTemplateColumns: `repeat(3, ${dot}px)`, gap }}
    >
      {Array.from({ length: 9 }, (_, i) => {
        const x = i % 3, y = Math.floor(i / 3);
        const ring = x === 1 && y === 1 ? 0 : x === 1 || y === 1 ? 1 : 2; // centre, edges, corners
        return <i key={i} className="dm-dot" data-centre={ring === 0 || undefined} style={{ width: dot, height: dot, animationDelay: `${ring * 180}ms` }} />;
      })}
    </span>
  );
}

/** Shown from the moment a request goes to the engine until the plan comes back. Compact: one line, not a card. */
export function EngineLoader() {
  const t = useT();
  const steps = t("loaderSteps").split("|");
  const [i, setI] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setI((n) => (n + 1) % steps.length), 1700);
    return () => clearInterval(id);
  }, [steps.length]);

  return (
    <div className="panel flex items-center gap-4 px-5 py-4" aria-live="polite">
      <DotMatrixLoader dot={6} gap={2} label={t("loaderTitle")} />
      <div className="min-w-0">
        <p className="shimmer-text text-[15px] font-medium leading-6">{t("loaderTitle")}</p>
        <p key={i} className="swap truncate text-[13.5px] leading-5 text-ink-2">{steps[i]}…</p>
      </div>
    </div>
  );
}
