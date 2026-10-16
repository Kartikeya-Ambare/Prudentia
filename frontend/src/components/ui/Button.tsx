import type { ButtonHTMLAttributes } from "react";
import clsx from "clsx";

export function Button({
  variant = "primary", className, ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" }) {
  return (
    <button
      className={clsx(
        "sl inline-flex min-h-[48px] items-center justify-center gap-2 rounded-[var(--radius-control)] px-5 text-[14px] font-medium leading-5",
        "transition-transform duration-[160ms] ease-[var(--ease-out)] active:scale-[0.97]",
        "disabled:opacity-[.38] disabled:active:scale-100",
        variant === "primary"
          ? "sl-fill bg-brand text-on-brand"
          : "border border-ctl bg-surface text-ink",
        className,
      )}
      {...rest}
    />
  );
}
