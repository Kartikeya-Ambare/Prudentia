import type { Bucket } from "@/api/types";
import { useSession } from "@/store/session";
import { pct, whole } from "@/lib/format";
import { useT, type Key } from "@/lib/i18n";
import { DataTable } from "@/components/ui/DataTable";
import { CountUp } from "@/components/ui/CountUp";
import { useEnter } from "@/lib/useEnter";
import { Kpi, useProjColumns, useWeightColumns } from "@/tabs/PlanView";
import { ChartPieSliceIcon, TargetIcon, TrendUpIcon, WalletIcon } from "@phosphor-icons/react";

const ORDER: Bucket[] = ["stock", "mf", "bank"];
const NAME: Record<Bucket, Key> = { stock: "stocks", mf: "mf", bank: "fd" };

/** One asset class's slice of the shared plan: what is in it, what it is worth today and later. */
export function ClassPage({ bucket }: { bucket: Bucket }) {
  const t = useT();
  const plan = useSession((s) => s.lastResult);
  const total = plan?.bucket_projections.reduce((a, b) => a + b.present_value, 0) ?? 0;
  const weightColumns = useWeightColumns(total);
  const projColumns = useProjColumns();
  const name = t(NAME[bucket]);
  const enter = useEnter<HTMLDivElement>(`${bucket}:${plan?.profile_id}`);

  if (!plan) {
    return (
      <div className="panel p-6">
        <h2 className="text-[20px] leading-7">{t("noPlanYet")}</h2>
        <p className="mt-2 text-[15px] leading-6 text-ink-2">{t("noPlanHow")}</p>
      </div>
    );
  }

  const slice = plan.bucket_projections[ORDER.indexOf(bucket)];
  if (!slice || slice.present_value <= 0) {
    return (
      <div className="panel p-6">
        <h2 className="text-[20px] leading-7">{name} {t("notInPlan")}</h2>
        <p className="mt-2 text-[15px] leading-6 text-ink-2">{t("notInPlanHow")}</p>
      </div>
    );
  }

  const weights = plan.weights.filter((w) => w.bucket === bucket);
  // Projection rows are keyed by id for stocks and funds but by display name for banks: accept either.
  const labels = new Set(weights.flatMap((w) => [w.label, w.display_name]));
  const rows = plan.instrument_projections.filter((r) => labels.has(r.label));

  return (
    <div ref={enter.ref} data-enter={enter.state} className="flex flex-col gap-4">
      <ul className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi label={t("share")} icon={ChartPieSliceIcon} note="of your plan"><CountUp value={plan.split_pct[bucket]} format={pct} /></Kpi>
        <Kpi label={t("today")} icon={WalletIcon} note="invested now">Rs. <CountUp value={slice.present_value} format={whole} /></Kpi>
        <Kpi label={t("projected")} icon={TargetIcon} note="expected case">Rs. <CountUp value={slice.projected_value} format={whole} /></Kpi>
        <Kpi label={t("yearlyReturn")} icon={TrendUpIcon} note="per year, after tax"><span className="text-gain"><CountUp value={slice.projected_return_pct} format={pct} /></span></Kpi>
      </ul>
      <div data-enter-item className="panel p-5 sm:p-6">
        <h2 className="mb-4 text-[20px] leading-7">{t("weights")}</h2>
        <DataTable caption={`${name}: ${t("weights")}`} columns={weightColumns} rows={weights} />
      </div>
      <div data-enter-item className="panel p-5 sm:p-6">
        <h2 className="mb-4 text-[20px] leading-7">{t("projections")}</h2>
        <DataTable caption={`${name}: ${t("projections")}`} columns={projColumns} rows={rows} />
      </div>
    </div>
  );
}
