const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
const inrWhole = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

/** 1,00,000.00 — Indian digit grouping, two decimals. */
export const number = (n: number) => inr.format(n);

/** Compact axis label: 20k, 1.5L, 2Cr. */
export function compact(n: number): string {
  const abs = Math.abs(n);
  if (abs >= 1e7) return `${+(n / 1e7).toFixed(2)}Cr`;
  if (abs >= 1e5) return `${+(n / 1e5).toFixed(2)}L`;
  if (abs >= 1e3) return `${+(n / 1e3).toFixed(1)}k`;
  return inrWhole.format(n);
}

export const pct = (n: number, digits = 1) => `${n.toFixed(digits)}%`;

/** Whole rupees, Indian digit grouping, no decimals: for headline figures. */
export const whole = (n: number) => Math.round(n).toLocaleString("en-IN");
