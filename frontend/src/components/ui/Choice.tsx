import clsx from "clsx";
import type { ReactNode } from "react";
import { Toggle } from "@/components/ui/Form";

/**
 * One asset class: a coloured edge, a name, an include switch, and that class's own options underneath.
 * Switched off, the options fold away, so it is always clear which options belong to which class.
 */
export function ClassCard({
  color, title, blurb, on, locked, onToggle, children,
}: { color: string; title: string; blurb: string; on: boolean; locked: boolean; onToggle: () => void; children: ReactNode }) {
  return (
    <section
      className={clsx(
        "rounded-[var(--radius-panel)] border transition-colors duration-200",
        on ? "border-line bg-surface" : "border-line bg-rail/60",
      )}
      style={{ borderLeft: `4px solid ${on ? color : "var(--color-line)"}` }}
    >
      <div className="flex items-center gap-4 px-4 py-2">
        <div className="min-w-0 flex-1">
          <h4 className={clsx("text-[16px] font-semibold leading-6", !on && "text-ink-3")}>{title}</h4>
          <p className="text-[13px] leading-5 text-ink-3">{blurb}</p>
        </div>
        <div className={clsx(locked && "opacity-60")}>
          <Toggle checked={on} onChange={() => !locked && onToggle()}>
            <span className="sr-only">{title}</span>
          </Toggle>
        </div>
      </div>
      {on && <div className="route-panel flex flex-col gap-3 px-4 pb-4 pt-1">{children}</div>}
    </section>
  );
}

/** Single choice, shown as a segmented row (radio semantics). */
export function Segmented<T extends string | number>({
  label, options, value, onChange,
}: { label: string; options: { id: T; label: string }[]; value: T | null; onChange: (v: T) => void }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-grid auto-cols-fr grid-flow-col gap-1 rounded-full bg-rail p-1">
      {options.map((o) => (
        <button
          key={String(o.id)}
          type="button"
          role="radio"
          aria-checked={value === o.id}
          onClick={() => onChange(o.id)}
          className={clsx(
            "sl min-h-[40px] rounded-full px-4 text-[13.5px] font-medium leading-5 transition-colors duration-200",
            value === o.id ? "bg-surface text-ink" : "text-ink-2",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
