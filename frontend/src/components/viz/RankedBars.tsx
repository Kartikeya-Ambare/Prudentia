import { useEffect, useState } from "react";
import { useT } from "@/lib/i18n";

export interface RankedRow { key: string; label: string; share: number; color: string; value?: string; tag?: string }

/**
 * Many items of one whole, largest first: name, a bar scaled to the biggest row, the share and the amount.
 * Shows the top rows and folds the rest behind a toggle, so 17 holdings never become a wall of labels.
 */
export function RankedBars({ rows, top = 8, unit = "%" }: { rows: RankedRow[]; top?: number; unit?: string }) {
  const t = useT();
  const sorted = [...rows].sort((a, b) => b.share - a.share);
  const [all, setAll] = useState(false);
  const [on, setOn] = useState(false);
  useEffect(() => { const id = requestAnimationFrame(() => setOn(true)); return () => cancelAnimationFrame(id); }, []);
  const shown = all ? sorted : sorted.slice(0, top);
  const max = sorted[0]?.share || 1;

  return (
    <div>
      <ol className="flex flex-col gap-1">
        {shown.map((r) => (
          <li key={r.key} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 rounded-[var(--radius-control)] px-3 py-2 sm:grid-cols-[minmax(0,17rem)_minmax(0,1fr)_auto]">
            <span className="flex min-w-0 items-center gap-2 text-[14.5px] leading-5">
              <span className="size-2.5 shrink-0 rounded-[3px]" style={{ background: r.color }} aria-hidden />
              <span className="truncate" title={r.label}>{r.label}</span>
              {r.tag && <span className="hidden shrink-0 rounded-full bg-rail px-2 text-[11.5px] leading-5 text-ink-2 2xl:inline">{r.tag}</span>}
            </span>
            <span className="num text-right text-[14px] leading-5 sm:order-3 sm:min-w-[9.5rem]">
              <span className="font-semibold">{r.share.toFixed(1)}{unit}</span>
              {r.value && <span className="ml-2 text-ink-3">{r.value}</span>}
            </span>
            <span className="col-span-2 h-2 overflow-hidden rounded-full bg-rail sm:order-2 sm:col-span-1" aria-hidden>
              <span
                className="block h-full rounded-full transition-[width] duration-[700ms] ease-[cubic-bezier(0.16,1,0.3,1)] motion-reduce:transition-none"
                style={{ width: on ? `${(r.share / max) * 100}%` : 0, background: r.color }}
              />
            </span>
          </li>
        ))}
      </ol>
      {sorted.length > top && (
        <button type="button" onClick={() => setAll((v) => !v)} aria-expanded={all}
          className="sl mt-2 min-h-[44px] rounded-full px-4 text-[14px] font-medium text-accent">
          {all ? `${t("showTop")} ${top}` : `${t("showAll")} (${sorted.length})`}
        </button>
      )}
    </div>
  );
}
