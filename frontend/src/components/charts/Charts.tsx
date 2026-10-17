import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ValueProjection } from "@/api/types";
import { compact, number } from "@/lib/format";


const tooltipStyle = {
  background: "var(--color-raised)",
  color: "var(--color-ink)",
  border: "1px solid var(--color-line)",
  borderRadius: 8,
  fontSize: 13,
  boxShadow: "none",
};

/** The same colour per class as the donut, the holdings bars and the class pages, so a colour always means the same thing. */
const CLASS_COLOR: Record<string, string> = {
  "Stocks": "var(--color-stocks)", "Mutual Funds": "var(--color-funds)", "Bank/FD": "var(--color-fd)",
};
const colorOf = (label: string) => CLASS_COLOR[label] ?? "var(--color-accent)";
/** Today is the class colour softened into the card; the end value is the full colour. */
const softened = (c: string) => `color-mix(in srgb, ${c} 38%, var(--color-surface))`;

function ChartTitle({ children }: { children: string }) {
  return <h3 className="mb-2 text-[14px] font-medium leading-5 tracking-normal">{children}</h3>;
}

/** Present vs. projected value for each asset class, as grouped bars. */
export function BucketBars({ rows, years }: { rows: ValueProjection[]; years: number }) {
  const data = rows.map((r) => ({ label: r.label, Present: r.present_value, Projected: r.projected_value }));
  return (
    <figure>
      <ChartTitle>Today and after the plan, by class</ChartTitle>
      <div className="h-[320px]" role="img" aria-label="Grouped bar chart of present and projected value for each bucket. The table beside it lists the same figures.">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--color-line)" />
            <XAxis dataKey="label" tickLine={false} axisLine={{ stroke: "var(--color-ctl)" }} tick={{ fontSize: 13, fill: "var(--color-ink-2)" }} />
            <YAxis tickFormatter={compact} tickLine={false} axisLine={false} width={52} tick={{ fontSize: 12, fill: "var(--color-ink-3)" }} />
            <Tooltip contentStyle={tooltipStyle} formatter={(v) => number(Number(v))} cursor={{ fill: "var(--color-page)" }} />
            <Bar dataKey="Present" radius={[4, 4, 0, 0]} isAnimationActive={false}>
              {data.map((d) => <Cell key={d.label} fill={softened(colorOf(d.label))} />)}
            </Bar>
            <Bar dataKey="Projected" radius={[4, 4, 0, 0]} isAnimationActive={false}>
              {data.map((d) => <Cell key={d.label} fill={colorOf(d.label)} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      {/* The legend says what the two bars mean; the class colours are named by the axis. */}
      <p className="mt-2 flex items-center justify-center gap-5 text-[13px] leading-5 text-ink-2">
        <span className="inline-flex items-center gap-2"><span className="size-3 rounded-[3px] bg-ink-3 opacity-40" aria-hidden />Today</span>
        <span className="inline-flex items-center gap-2"><span className="size-3 rounded-[3px] bg-ink-3" aria-hidden />After {years} {years === 1 ? "year" : "years"}</span>
      </p>
    </figure>
  );
}
