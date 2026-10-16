import type { ReactNode } from "react";
import clsx from "clsx";
import { CircleNotchIcon, InfoIcon, WarningCircleIcon, WarningIcon } from "@phosphor-icons/react";

// Soft tinted banner: pale background, and icon and text in the same hue. Every pair passes 4.5:1.
const tones = {
  info: { box: "bg-accent-soft text-accent", Icon: InfoIcon },
  warning: { box: "bg-warn-soft text-warn", Icon: WarningIcon },
  error: { box: "bg-loss-soft text-loss", Icon: WarningCircleIcon },
} as const;

/** st.info / st.warning / st.error. */
export function Alert({
  tone, children, className,
}: { tone: keyof typeof tones; children: ReactNode; className?: string }) {
  const { box, Icon } = tones[tone];
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={clsx("flex items-start gap-3 rounded-[var(--radius-control)] px-4 py-3.5 text-[14px] font-medium leading-5", box, className)}
    >
      <Icon size={22} weight="regular" className="mt-px shrink-0" aria-hidden />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

/** st.spinner. */
export function Spinner({ children }: { children: ReactNode }) {
  return (
    <p role="status" className="flex items-center gap-2.5 text-[14px] leading-5 text-ink-2">
      <CircleNotchIcon size={18} weight="bold" className="animate-spin text-accent" aria-hidden />
      {children}
    </p>
  );
}
