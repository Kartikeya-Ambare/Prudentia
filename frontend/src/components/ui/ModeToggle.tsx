import { startTransition, useEffect, useState } from "react";
import { ChatCircleDotsIcon, SlidersHorizontalIcon } from "@phosphor-icons/react";
import clsx from "clsx";
import { useT, type Key } from "@/lib/i18n";
import { useLevel, type Level } from "@/store/ui";

const LEVELS: { id: Level; label: Key; hint: Key; Icon: typeof SlidersHorizontalIcon }[] = [
  { id: "beginner", label: "modeBeginner", hint: "modeBeginnerHint", Icon: ChatCircleDotsIcon },
  { id: "expert", label: "modeExpert", hint: "modeExpertHint", Icon: SlidersHorizontalIcon },
];

/**
 * Two equal segments and one thumb. The thumb moves by whole multiples of its own width, so the slide is
 * a single compositor-only transform. Arrow keys move between the two options (radio group).
 */
export function ModeToggle() {
  const t = useT();
  const { level, setLevel } = useLevel();
  // The thumb follows the click at once; swapping the page content underneath is a low-priority transition,
  // so the next paint is not held up by mounting the other mode's screen.
  const [shown, setShown] = useState<Level>(level);
  useEffect(() => setShown(level), [level]);
  const choose = (id: Level) => {
    setShown(id);
    startTransition(() => setLevel(id));
  };
  const index = LEVELS.findIndex((l) => l.id === shown);

  return (
    <div
      role="radiogroup"
      aria-label={t("modes")}
      className="relative grid w-[min(100%,300px)] grid-cols-2 rounded-full bg-rail p-1"
      onKeyDown={(e) => {
        if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
          e.preventDefault();
          choose(LEVELS[(index + 1) % 2].id);
        }
      }}
    >
      <span
        aria-hidden
        className="pointer-events-none absolute inset-y-1 left-1 w-[calc((100%-0.5rem)/2)] rounded-full bg-brand transition-transform duration-[420ms] ease-[cubic-bezier(0.32,0.72,0,1)] motion-reduce:transition-none"
        style={{ transform: `translateX(${index * 100}%)` }}
      />
      {LEVELS.map(({ id, label, hint, Icon }) => {
        const on = id === shown;
        return (
          <button
            key={id}
            type="button"
            role="radio"
            aria-checked={on}
            tabIndex={on ? 0 : -1}
            title={t(hint)}
            onClick={() => choose(id)}
            className={clsx(
              "sl relative z-10 flex min-h-[44px] items-center justify-center gap-2 rounded-full px-3 text-[14px] font-medium leading-5 transition-colors duration-300",
              on ? "text-on-brand" : "text-ink-2",
            )}
          >
            <Icon size={18} weight={on ? "fill" : "regular"} aria-hidden />
            {t(label)}
          </button>
        );
      })}
    </div>
  );
}
