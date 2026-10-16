import type { Bucket, PlanResult } from "@/api/types";
import { pct, whole } from "@/lib/format";
import { useT, type Key } from "@/lib/i18n";

const ORDER: Bucket[] = ["stock", "mf", "bank"];
const KEY: Record<Bucket, Key> = { stock: "stocks", mf: "mf", bank: "fd" };
const COLOR: Record<Bucket, string> = { stock: "var(--color-stocks)", mf: "var(--color-funds)", bank: "var(--color-fd)" };

/** A plan, laid out for a chat bubble: total, split, scenarios and banks. The full detail stays on the page. */
export function PlanReplyCard({ plan }: { plan: PlanResult }) {
  const t = useT();
  const total = plan.bucket_projections.reduce((a, b) => a + b.present_value, 0);
  const rows = ORDER.map((b, i) => ({ b, pv: plan.bucket_projections[i]?.present_value ?? 0 })).filter((r) => r.pv > 0);
  const scen = plan.scenarios ? (["bear", "base", "bull"] as const).filter((k) => plan.scenarios?.[k]) : [];
  const dates = [plan.data_as_of.stocks, plan.data_as_of.mf].filter(Boolean) as string[];

  return (
    <div className="mt-3 flex flex-col gap-3 rounded-[var(--radius-control)] bg-surface p-3.5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <span className="num text-[18px] font-semibold leading-6">Rs. {whole(total)}</span>
        <span className="text-[12.5px] leading-5 text-ink-3">{plan.horizon_years} {t("yearsUnit")}, risk {plan.risk_thermometer.toFixed(0)}%</span>
      </div>

      <div className="flex h-2.5 overflow-hidden rounded-full bg-rail" role="img"
        aria-label={rows.map((r) => `${t(KEY[r.b])} ${((r.pv / total) * 100).toFixed(0)}%`).join(", ")}>
        {rows.map((r) => <span key={r.b} className="h-full" style={{ width: `${(r.pv / total) * 100}%`, background: COLOR[r.b] }} />)}
      </div>
      <ul className="flex flex-col gap-2">
        {rows.map((r) => (
          <li key={r.b} className="flex items-center gap-2 text-[13.5px] leading-5">
            <span className="size-2.5 shrink-0 rounded-[3px]" style={{ background: COLOR[r.b] }} aria-hidden />
            <span className="min-w-0 flex-1">{t(KEY[r.b])}</span>
            <span className="text-right">
              <span className="num block font-semibold leading-5">{((r.pv / total) * 100).toFixed(1)}%</span>
              <span className="num block text-[12px] leading-4 text-ink-3">Rs. {whole(r.pv)}</span>
            </span>
          </li>
        ))}
      </ul>

      <div className="rounded-[8px] bg-rail px-3 py-2">
        <div className="flex items-baseline justify-between gap-2 text-[13px] leading-5">
          <span className="text-ink-2">{t("kpiReturn")}</span>
          <span className="num font-semibold text-gain">{pct(plan.expected_return_pct)}</span>
        </div>
        <p className="text-[11.5px] leading-4 text-ink-3">{t("perYear")}, {t("afterTax")}</p>
      </div>

      {scen.length > 0 && (
        <div>
          <p className="mb-1.5 text-[12.5px] font-medium leading-5 text-ink-2">{t("scenarios")}</p>
          <ul className="flex flex-col gap-1.5">
            {scen.map((k) => (
              <li key={k} className="flex items-center justify-between gap-2 rounded-[8px] bg-rail px-3 py-1.5 text-[13px] leading-5">
                <span className="text-ink-2">{t(k)}</span>
                <span className="num font-semibold">Rs. {whole(plan.scenarios![k]!.projected_value)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {plan.banks_selected.length > 0 && (
        <div>
          <p className="mb-1.5 text-[12.5px] font-medium leading-5 text-ink-2">{t("banksSel")}</p>
          <ul className="flex flex-wrap gap-1.5">
            {plan.banks_selected.map((b) => (
              <li key={b.label} className="rounded-full bg-rail px-2.5 py-1 text-[12px] leading-4 text-ink-2">{b.display_name}</li>
            ))}
          </ul>
        </div>
      )}

      <p className="text-[11.5px] leading-4 text-ink-3">
        {dates.length > 0 && `${t("dataAsOf")} ${dates.sort().at(-1)}. `}{t("scenarioNote")}
      </p>
    </div>
  );
}
