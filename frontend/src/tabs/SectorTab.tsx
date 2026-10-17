import { useState } from "react";
import { useQueries } from "@tanstack/react-query";
import { api } from "@/api";
import { useSectorAllocation } from "@/api/hooks";
import { useSession } from "@/store/session";
import { pct } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { Spinner } from "@/components/ui/Feedback";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { RankedBars } from "@/components/viz/RankedBars";
import { CountUp } from "@/components/ui/CountUp";
import { useEnter } from "@/lib/useEnter";
import { Donut } from "@/components/viz/Donut";
import { ViewToggle } from "@/tabs/PlanView";

// Each sector keeps its own colour everywhere (donut, bars, chips); the label still carries the meaning.
const sectorColor = (name: string) => `var(--sector-${name.toLowerCase().replace(/&/g, "").replace(/[^a-z]+/g, "-").replace(/^-|-$/g, "")}, var(--color-funds))`;

/** One fund's sector split, from the latest saved snapshot (fund holdings change slowly, so nothing is fetched live). */
function FundSectors({ fundName, weightPct }: { fundName: string; weightPct: number }) {
  const t = useT();
  const sector = useSectorAllocation(fundName);
  const [view, setView] = useState<"chart" | "table">("chart");

  const head = (
    <div className="mb-4 flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
      <h2 className="text-[20px] leading-7">{fundName}</h2>
      <p className="num text-[13px] leading-5 text-ink-3">{pct(weightPct)} of your mutual funds</p>
    </div>
  );

  if (sector.isPending) return <div className="panel p-5 sm:p-6">{head}<Spinner>{fundName}…</Spinner></div>;
  if (sector.isError) {
    return (
      <div className="panel p-5 sm:p-6">
        {head}
        <p className="text-[14.5px] leading-6 text-ink-2">{t("sectorsNone")}</p>
      </div>
    );
  }

  const { sector_json, source_url, date } = sector.data;
  const rows = Object.entries(sector_json).map(([name, value]) => ({ name, value }));
  const columns: Column<{ name: string; value: number }>[] = [
    { key: "name", header: "Sector", render: (r) => r.name },
    { key: "value", header: "Share", render: (r) => pct(r.value, 2), numeric: true },
  ];

  return (
    <div data-enter-item className="panel p-5 sm:p-6">
      {head}
      <ul className="-mt-2 mb-4 flex flex-wrap gap-2" aria-label="Top sectors">
        {[...rows].sort((a, b) => b.value - a.value).slice(0, 3).map((r) => (
          <li key={r.name} className="num rounded-full bg-rail px-3 py-1 text-[12.5px] leading-5 text-ink-2">
            <span className="mr-1.5 inline-block size-2 rounded-full align-middle" style={{ background: sectorColor(r.name) }} aria-hidden />
            {r.name} <span className="font-semibold text-ink">{pct(r.value, 0)}</span>
          </li>
        ))}
      </ul>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <ViewToggle value={view} onChange={setView} />
        <p className="num text-[13px] leading-5 text-ink-3">{t("sectorsAsOf")} {date}</p>
      </div>
      {view === "chart" ? (
        <RankedBars
          rows={rows.map((r) => ({ key: r.name, label: r.name, share: r.value, color: sectorColor(r.name) }))}
          top={6}
        />
      ) : (
        <DataTable caption={`${fundName}: sectors`} columns={columns} rows={rows} />
      )}
      <p className="mt-4 text-[12px] leading-4 text-ink-3">
        Source: {sourceLabel(source_url)}
      </p>
    </div>
  );
}

/** Sector breakdown for the mutual funds in the current plan. Reached only once a plan exists. */
// The stored source can be a link or a sentence; show just a short name.
function sourceLabel(src: string) {
  if (/^https?:\/\//i.test(src)) {
    try { return <a href={src} target="_blank" rel="noreferrer noopener" className="underline underline-offset-[3px] hover:text-accent">{new URL(src).hostname.replace(/^www\./, "")}</a>; } catch { /* fall through */ }
  }
  if (/groww/i.test(src)) return "Groww";
  if (/official/i.test(src)) return "Fund house";
  return "Fund data";
}



/** All the plan's funds as one: each fund's sector split weighted by how much of the mutual-fund money it gets. */
function CombinedSectors({ funds }: { funds: { name: string; weight: number }[] }) {
  const results = useQueries({
    queries: funds.map((f) => ({
      queryKey: ["sector", f.name],
      queryFn: () => api.sectorAllocation(f.name),
      staleTime: 5 * 60_000,
      retry: false,
    })),
  });
  if (results.some((r) => r.isPending)) return null;

  const totals: Record<string, number> = {};
  let covered = 0;
  results.forEach((r, i) => {
    if (!r.data) return;
    covered += funds[i].weight;
    for (const [sector, v] of Object.entries(r.data.sector_json) as [string, number][]) totals[sector] = (totals[sector] ?? 0) + (funds[i].weight * v) / 100;
  });
  if (!covered) return null;

  const ranked = Object.entries(totals).map(([name, v]) => ({ name, share: (v / covered) * 100 })).sort((a, b) => b.share - a.share);
  const top = ranked;
  // A donut stays readable up to about six slices: the five biggest sectors, and the rest together.
  const MAX_SLICES = 6;
  const head = ranked.length > MAX_SLICES ? ranked.slice(0, MAX_SLICES - 1) : ranked;
  const rest = ranked.length > MAX_SLICES ? ranked.slice(MAX_SLICES - 1) : [];
  const segments = [
    ...head.map((r) => ({ key: r.name, label: r.name, value: r.share, color: sectorColor(r.name) })),
    ...(rest.length ? [{ key: "other-sectors", label: `Other sectors (${rest.length})`, value: rest.reduce((a, r) => a + r.share, 0), color: "var(--sector-diversified)" }] : []),
  ];

  return (
    <div data-enter-item className="panel p-5 sm:p-6">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
        <h2 className="text-[20px] leading-7">All your mutual funds together</h2>
        <p className="num text-[13px] leading-5 text-ink-3">
          {covered < 99.5 ? `Based on funds with data (${pct(covered)} of your mutual funds)` : "Weighted by how much each fund gets"}
        </p>
      </div>
      <Donut segments={segments} centre={<><CountUp className="num text-[22px] font-semibold leading-7" value={top[0].share} format={(n) => `${n.toFixed(0)}%`} /><span className="text-[12.5px] leading-4 text-ink-3">{top[0].name}</span></>} />
    </div>
  );
}

export function SectorTab() {
  const t = useT();
  const plan = useSession((s) => s.lastResult);
  const funds = (plan?.weights ?? []).filter((w) => w.bucket === "mf");

  const enter = useEnter<HTMLDivElement>(plan?.profile_id);
  return (
    <div ref={enter.ref} data-enter={enter.state} className="flex flex-col gap-4">
      <p data-enter-item className="max-w-[68ch] text-[15px] leading-6 text-ink-2">{t("sectorsIntro")}</p>
      {funds.length > 1 && <CombinedSectors funds={funds.map((w) => ({ name: w.display_name, weight: w.weight_pct }))} />}
      {funds.map((w) => <FundSectors key={w.label} fundName={w.display_name} weightPct={w.weight_pct} />)}
    </div>
  );
}
