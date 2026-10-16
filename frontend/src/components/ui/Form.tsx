import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import clsx from "clsx";
import { CaretDownIcon, MinusIcon, PlusIcon, XIcon } from "@phosphor-icons/react";

const controlBox =
  "h-[48px] w-full rounded-[var(--radius-control)] border border-ctl bg-surface text-[15px] " +
  "transition-colors duration-150 hover:border-ink-3 focus-within:border-accent";

/** st.toggle */
export function Toggle({
  checked, onChange, children,
}: { checked: boolean; onChange: (v: boolean) => void; children: ReactNode }) {
  return (
    <label className="flex min-h-[48px] w-fit cursor-pointer select-none items-center gap-3 text-[15px]">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={clsx(
          "relative h-[28px] w-[48px] shrink-0 rounded-full transition-colors duration-150",
          checked ? "bg-accent" : "bg-ctl",
        )}
      >
        <span
          className={clsx(
            "absolute left-0.5 top-0.5 size-[24px] rounded-full bg-surface transition-transform duration-[300ms] ease-[cubic-bezier(0.34,1.56,0.64,1)] motion-reduce:transition-none",
            checked && "translate-x-[20px]",
          )}
        />
      </button>
      {children}
    </label>
  );
}

export function Field({
  label, htmlFor, error, children,
}: { label: string; htmlFor?: string; error?: string | null; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={htmlFor} className="text-[14px] font-medium leading-5">{label}</label>
      {children}
      {error && <p role="alert" className="text-[12px] leading-4 text-loss">{error}</p>}
    </div>
  );
}

/** st.number_input: typed value, with − / + steppers. */
export function NumberInput({
  id, value, onChange, min, max, step, invalid,
}: {
  id: string;
  value: number;
  onChange: (v: number) => void;
  min: number;
  max?: number;
  step: number;
  invalid?: boolean;
}) {
  const [text, setText] = useState(String(value));
  useEffect(() => setText(String(value)), [value]);

  const clamp = (n: number) => Math.min(max ?? Infinity, Math.max(min, n));
  const commit = (raw: string) => {
    const n = Number(raw);
    onChange(Number.isFinite(n) && raw.trim() !== "" ? clamp(n) : min);
  };
  const stepper =
    "sl flex h-full w-[48px] items-center justify-center text-ink-2 disabled:opacity-[.38]";

  return (
    <div className={clsx(controlBox, "flex items-center overflow-hidden", invalid && "border-loss")}>
      <input
        id={id}
        name={id}
        autoComplete="off"
        inputMode="decimal"
        value={text}
        aria-invalid={invalid || undefined}
        onChange={(e) => setText(e.target.value)}
        onBlur={() => commit(text)}
        onKeyDown={(e) => e.key === "Enter" && commit(text)}
        className="num h-full min-w-0 flex-1 bg-transparent px-3 outline-none"
      />
      <button type="button" aria-label="Decrease" className={stepper} disabled={value <= min} onClick={() => onChange(clamp(value - step))}>
        <MinusIcon size={16} aria-hidden />
      </button>
      <button type="button" aria-label="Increase" className={stepper} disabled={max !== undefined && value >= max} onClick={() => onChange(clamp(value + step))}>
        <PlusIcon size={16} aria-hidden />
      </button>
    </div>
  );
}

/** st.slider: value shown above the thumb row, range ends below. */
export function Slider({
  id, value, onChange, min, max,
}: { id: string; value: number; onChange: (v: number) => void; min: number; max: number }) {
  const fill = ((value - min) / (max - min)) * 100;
  return (
    <div>
      <p className="num text-[14px] font-medium leading-5 text-accent" aria-hidden>{value}</p>
      <input
        id={id}
        type="range"
        name={id}
        className="range"
        min={min}
        max={max}
        step={1}
        value={value}
        style={{ ["--fill" as string]: `${fill}%` }}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      <div className="num flex justify-between text-[12px] leading-4 text-ink-3" aria-hidden>
        <span>{min}</span>
        <span>{max}</span>
      </div>
    </div>
  );
}

/** st.multiselect: selected values as removable tags, options in a dropdown. */
export function MultiSelect({
  label, options, selected, onChange,
}: { label: string; options: readonly string[]; selected: string[]; onChange: (v: string[]) => void }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const listId = useId();

  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => !root.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  const toggle = (o: string) =>
    onChange(selected.includes(o) ? selected.filter((x) => x !== o) : [...selected, o]);

  return (
    <div ref={root} className="relative flex flex-col gap-2">
      <span id={`${listId}-label`} className="text-[14px] font-medium">{label}</span>
      <div className={clsx(controlBox, "flex h-auto min-h-[48px] items-center gap-1.5 py-1.5 pl-2 pr-1")}>
        <div className="flex min-w-0 flex-1 flex-wrap gap-1.5">
          {selected.map((s) => (
            <span key={s} className="inline-flex items-center gap-1 rounded-[6px] bg-accent-soft py-0.5 pl-2 pr-1 text-[13.5px] font-medium text-accent">
              {s}
              <button type="button" aria-label={`Remove ${s}`} onClick={() => toggle(s)} className="sl rounded p-0.5">
                <XIcon size={12} weight="bold" aria-hidden />
              </button>
            </span>
          ))}
          <button
            type="button"
            aria-haspopup="listbox"
            aria-expanded={open}
            aria-controls={listId}
            aria-labelledby={`${listId}-label`}
            onClick={() => setOpen((o) => !o)}
            className={clsx("min-h-9 flex-1 px-1 text-left text-[15px] text-ink-3", selected.length && "min-w-16")}
          >
            {selected.length ? "" : "Choose options"}
          </button>
        </div>
        <button type="button" tabIndex={-1} aria-hidden onClick={() => setOpen((o) => !o)} className="p-2 text-ink-3">
          <CaretDownIcon size={16} />
        </button>
      </div>
      {open && (
        <ul
          id={listId}
          role="listbox"
          aria-multiselectable
          aria-labelledby={`${listId}-label`}
          className="absolute left-0 right-0 top-full z-10 mt-1 max-h-72 overflow-auto rounded-[var(--radius-control)] border border-ctl bg-raised p-1"
        >
          {options.map((o) => {
            const on = selected.includes(o);
            return (
              <li key={o} role="option" aria-selected={on}>
                <label className="sl flex min-h-[48px] cursor-pointer items-center gap-3 rounded-[6px] px-3 text-[14px] leading-5">
                  <input type="checkbox" checked={on} onChange={() => toggle(o)} className="size-[18px] accent-[var(--color-accent)]" />
                  {o}
                </label>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
