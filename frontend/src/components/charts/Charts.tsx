import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
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

function ChartTitle({ children }: { children: string }) {
  return <h3 className="mb-2 text-[14px] font-medium leading-5 tracking-normal">{children}</h3>;
}

/** Present vs. projected value for each asset class, as grouped bars. */
export function BucketBars({ rows }: { rows: ValueProjection[] }) {
  const data = rows.map((r) => ({ label: r.label, Present: r.present_value, Projected: r.projected_value }));
  return (
    <figure>
      <ChartTitle>Present vs. Projected value by bucket</ChartTitle>
      <div className="h-[320px]" role="img" aria-label="Grouped bar chart of present and projected value for each bucket. The table beside it lists the same figures.">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--color-line)" />
            <XAxis dataKey="label" tickLine={false} axisLine={{ stroke: "var(--color-ctl)" }} tick={{ fontSize: 13, fill: "var(--color-ink-2)" }} />
            <YAxis tickFormatter={compact} tickLine={false} axisLine={false} width={52} tick={{ fontSize: 12, fill: "var(--color-ink-3)" }} />
            <Tooltip contentStyle={tooltipStyle} formatter={(v) => number(Number(v))} cursor={{ fill: "var(--color-page)" }} />
            <Legend iconType="circle" wrapperStyle={{ fontSize: 13 }} />
            <Bar dataKey="Present" fill="var(--color-present)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
            <Bar dataKey="Projected" fill="var(--color-accent)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}
