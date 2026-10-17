import { lazy, Suspense, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import clsx from "clsx";
import { ArrowRightIcon, CurrencyInrIcon, HourglassMediumIcon, ShieldCheckIcon, TrendUpIcon, type Icon } from "@phosphor-icons/react";
import type { Bucket, InstrumentWeight, PlanResult, ValueProjection } from "@/api/types";
import { gsapReady, NO_REDUCED_MOTION, REDUCED_MOTION } from "@/lib/gsap";
import { number, pct, whole } from "@/lib/format";
import { useT, type Key } from "@/lib/i18n";
import { Segmented } from "@/components/ui/Choice";
import { Alert } from "@/components/ui/Feedback";
import { Donut } from "@/components/viz/Donut";
import { RankedBars } from "@/components/viz/RankedBars";
import { DataTable, type Column } from "@/components/ui/DataTable";

const BucketBars = lazy(() => import("@/components/charts/Charts").then((m) => ({ default: m.BucketBars })));

const BUCKET_COLOR: Record<Bucket, string> = {
  stock: "var(--color-stocks)", mf: "var(--color-funds)", bank: "var(--color-fd)",
};
const BUCKET_ORDER: Bucket[] = ["stock", "mf", "bank"];
const BUCKET_KEY: Record<Bucket, Key> = { stock: "stocks", mf: "mf", bank: "fd" };

/** 1057410 -> 10.6 L, 12500000 -> 1.25 Cr: the short form used where the full figure sits in a table nearby. */
const compact = (n: number) => (n >= 1e7 ? `${(n / 1e7).toFixed(2)} Cr` : n >= 1e5 ? `${(n / 1e5).toFixed(1)} L` : whole(n));

/** 2026-10-14 -> 14 Oct */
const shortDate = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" });

function Card({ title, aside, className, children }: { title: string; aside?: ReactNode; className?: string; children: ReactNode }) {
  return (
    <div data-enter-item className={clsx("panel min-w-0 p-5", className)}>
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-[18px] leading-6">{title}</h2>
        {aside}
      </div>
      {children}
    </div>
  );
}

/** Counts up to `value` when a new plan lands, so the change registers. */
function Metric({ value, tone }: { value: number; tone?: "gain" }) {
  const ref = useRef<HTMLSpanElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.textContent = pct(value);
    let cancelled = false;
    let mm: { revert: () => void } | undefined;
    gsapReady.then(({ gsap }) => {
      if (cancelled) return;
      const m = gsap.matchMedia();
      mm = m;
      m.add(NO_REDUCED_MOTION, () => {
        const counter = { n: 0 };
        el.textContent = pct(0);
        gsap.to(counter, { n: value, duration: 0.8, ease: "power3.out", onUpdate: () => { el.textContent = pct(counter.n); } });
      });
    });
    return () => { cancelled = true; mm?.revert(); };
  }, [value]);
  return <span ref={ref} aria-label={pct(value)} className={clsx("num", tone === "gain" && "text-gain")} />;
}

export function Kpi({ label, icon: Icon, note, children }: { label: string; icon: Icon; note?: string; children: ReactNode }) {
  return (
    <li data-enter-item className="panel flex min-w-0 flex-col gap-1 px-4 py-3.5">
      <p className="flex items-center gap-2.5 text-[13px] leading-5 text-ink-2">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent"><Icon size={17} weight="bold" aria-hidden /></span>
        <span className="min-w-0 truncate">{label}</span>
      </p>
      <p className="num mt-1.5 whitespace-nowrap text-[20px] font-semibold leading-8 tracking-[-0.01em] @2xl:text-[26px]">{children}</p>
      <p className="min-h-4 truncate text-[12.5px] leading-4 text-ink-3">{note}</p>
    </li>
  );
}

function ChartFallback() {
  return <div className="h-[320px] rounded-[var(--radius-control)] bg-rail" aria-hidden />;
}

export function useWeightColumns(total: number) {
  const t = useT();
  return useMemo<Column<InstrumentWeight>[]>(() => [
    { key: "name", header: t("colName"), render: (w) => w.display_name },
    {
      key: "bucket", header: t("colType"),
      render: (w) => (
        <span className="inline-flex items-center gap-2">
          <span className="size-2.5 rounded-[3px]" style={{ background: BUCKET_COLOR[w.bucket] }} aria-hidden />
          {t(BUCKET_KEY[w.bucket])}
        </span>
      ),
    },
    {
      key: "weight", header: t("colShare"), numeric: true,
      render: (w) => {
        const share = total > 0 ? (w.amount / total) * 100 : w.weight_pct;
        return (
          <span className="inline-flex items-center justify-end gap-2.5">
            <span className="h-1.5 w-16 overflow-hidden rounded-full bg-rail" aria-hidden>
              <span className="block h-full rounded-full" style={{ width: `${Math.min(share * 2.5, 100)}%`, background: BUCKET_COLOR[w.bucket] }} />
            </span>
            {share.toFixed(2)}%
          </span>
        );
      },
    },
    { key: "amount", header: t("colAmount"), render: (w) => number(w.amount), numeric: true },
  ], [t, total]);
}

export function useProjColumns() {
  const t = useT();
  return useMemo<Column<ValueProjection>[]>(() => [
    { key: "label", header: t("colName"), render: (r) => r.label },
    { key: "pv", header: t("colNow"), render: (r) => number(r.present_value), numeric: true },
    { key: "fv", header: t("colLater"), render: (r) => number(r.projected_value), numeric: true },
    { key: "ret", header: t("colReturn"), render: (r) => r.projected_return_pct.toFixed(2), numeric: true },
  ], [t]);
}

export function ViewToggle({ value, onChange }: { value: "chart" | "table"; onChange: (v: "chart" | "table") => void }) {
  const t = useT();
  return <Segmented label={`${t("viewChart")} / ${t("viewTable")}`} value={value} onChange={onChange}
    options={[{ id: "chart" as const, label: t("viewChart") }, { id: "table" as const, label: t("viewTable") }]} />;
}

export function PlanView({ result }: { result: PlanResult }) {
  const t = useT();
  const root = useRef<HTMLElement>(null);

  const buckets = (["stock", "mf", "bank"] as Bucket[]).filter((b) => (result.split_pct[b] ?? 0) > 0);
  const total = result.bucket_projections.reduce((a, b) => a + b.present_value, 0);
  const asOf = [result.data_as_of.stocks, result.data_as_of.mf].filter(Boolean);
  const latest = asOf.sort().at(-1);

  const requested = result.plan_request?.capital ?? total;
  const unallocated = requested - total;
  const [view, setView] = useState<"chart" | "table">("chart");
  const weightColumns = useWeightColumns(total);
  const holdingRows = useMemo(() => {
    const seen: Record<Bucket, number> = { stock: 0, mf: 0, bank: 0 };
    const count: Record<Bucket, number> = { stock: 0, mf: 0, bank: 0 };
    result.weights.forEach((w) => { count[w.bucket] += 1; });
    return result.weights.map((w) => ({
      key: `${w.bucket}-${w.label}`, label: w.display_name,
      share: total > 0 ? (w.amount / total) * 100 : w.weight_pct,
      value: `Rs. ${whole(w.amount)}`, tag: t(BUCKET_KEY[w.bucket]),
      color: `color-mix(in srgb, ${BUCKET_COLOR[w.bucket]}, white ${Math.round((count[w.bucket] <= 1 ? 0 : seen[w.bucket]++ / (count[w.bucket] - 1)) * 45)}%)`,
    }));
  }, [result.weights, total, t]);
  const projColumns = useProjColumns();

  // New plan: bring it into view on small screens where the form sits above it.
  useLayoutEffect(() => {
    if (window.matchMedia("(min-width: 1024px)").matches) return;
    root.current?.focus({ preventScroll: true });
    root.current?.scrollIntoView({ block: "start", behavior: "smooth" });
  }, [result.profile_id]);

  const scenarios = result.scenarios
    ? (["bear", "base", "bull"] as const).filter((k) => result.scenarios?.[k]).map((k) => ({ k, s: result.scenarios![k]! }))
    : [];

  const expectedCase = result.scenarios?.base;
  const cautiousCase = result.scenarios?.bear;
  const optimisticCase = result.scenarios?.bull;
  const [classView, setClassView] = useState<"chart" | "table">("chart");

  // One orchestrated moment when a new plan arrives: summary cards first, then the panels, each rising a little.
  // The cards sit invisible (CSS) until GSAP starts; a timeout reveals them if GSAP is slow or motion is reduced.
  const [enter, setEnter] = useState<"pending" | "done">("pending");
  useLayoutEffect(() => {
    const el = root.current;
    if (!el) return;
    if (window.matchMedia(REDUCED_MOTION).matches) { setEnter("done"); return; }
    setEnter("pending");
    const items = [...el.querySelectorAll("[data-enter-item]")];
    let cancelled = false;
    let tween: { kill: () => void } | undefined;
    // Safety net: whatever happens to the animation, the cards are visible after 1.8 s.
    const fallback = setTimeout(() => setEnter("done"), 1800);
    gsapReady.then(({ gsap }) => {
      if (cancelled) return;
      tween = gsap.fromTo(items, { opacity: 0, y: 16 }, {
        opacity: 1, y: 0, duration: 0.6, ease: "power3.out", stagger: 0.07,
        onComplete: () => { clearTimeout(fallback); setEnter("done"); },
      });
    });
    return () => { cancelled = true; clearTimeout(fallback); tween?.kill(); };
  }, [result.profile_id]);
  const live = result.bucket_projections.filter((b) => b.present_value > 0);
  const riskLabel = result.risk_thermometer < 35 ? t("riskLow") : result.risk_thermometer < 65 ? t("riskMod") : t("riskHigh");

  return (
    <section ref={root} tabIndex={-1} aria-label={t("summary")} data-enter={enter} className="@container scroll-mt-4 outline-none">
      {result.warnings.map((w) => <Alert key={w} tone="warning" className="mb-4">{w}</Alert>)}

      <p className="num mb-3 text-[13px] leading-5 text-ink-3">
        {result.horizon_years} {t("yearsUnit")}, volatility {pct(result.expected_volatility_pct)} {t("perYear")}{latest ? `. Prices as of ${shortDate(latest)} ${latest.slice(0, 4)}.` : "."}
      </p>
      <ul className="grid grid-cols-2 gap-3 @2xl:grid-cols-4">
        <Kpi label={t("invested")} icon={CurrencyInrIcon} note={unallocated > 1 ? `of Rs. ${whole(requested)}` : "today"}>
          <span className="mr-1 text-[15px] font-medium text-ink-3">Rs.</span><span className="num">{whole(total)}</span>
        </Kpi>
        <Kpi label={`After ${result.horizon_years} ${t("yearsUnit")}`} icon={HourglassMediumIcon}
          note={expectedCase && cautiousCase && optimisticCase ? `${compact(cautiousCase.projected_value)} to ${compact(optimisticCase.projected_value)}` : "expected"}>
          <span className="mr-1 text-[15px] font-medium text-ink-3">Rs.</span><span className="num">{whole(expectedCase?.projected_value ?? result.bucket_projections.reduce((a, b) => a + b.projected_value, 0))}</span>
        </Kpi>
        <Kpi label={t("kpiReturn")} icon={TrendUpIcon} note={`${t("perYear")}, ${t("afterTax")}`}>
          <Metric value={result.expected_return_pct} tone="gain" />
        </Kpi>
        <Kpi label="Risk level" icon={ShieldCheckIcon} note={`${Math.round(result.risk_thermometer)} out of 100`}>
          <span>{riskLabel}</span>
        </Kpi>
      </ul>

      <div className="mt-4 grid gap-4 @2xl:grid-cols-2 @4xl:grid-cols-3">
        {scenarios.length > 0 && (
          <Card title={t("scenarios")}>
            <ul className="flex flex-col gap-2">
              {scenarios.map(({ k, s }) => (
                <li key={k} className={clsx("flex items-center justify-between gap-3 rounded-[var(--radius-control)] px-4 py-3", k === "base" ? "bg-accent-container" : "bg-rail")}>
                  <span>
                    <span className="block text-[13px] leading-5 text-ink-2">{t(k)}</span>
                    <span className="num block text-[13px] leading-5 text-ink-2">{pct(s.return_pct)} / yr</span>
                  </span>
                  <span className="num whitespace-nowrap text-[20px] font-semibold leading-7">Rs. {whole(s.projected_value)}</span>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-[12px] leading-4 text-ink-3">{t("scenarioNote")}</p>
          </Card>
        )}
        <Card title={t("allocationByClass")}>
          <Donut
            segments={buckets.map((b) => ({
              key: b, label: t(BUCKET_KEY[b]), color: BUCKET_COLOR[b],
              value: result.bucket_projections[BUCKET_ORDER.indexOf(b)]?.present_value ?? 0,
              detail: `Rs. ${whole(result.bucket_projections[BUCKET_ORDER.indexOf(b)]?.present_value ?? 0)}`,
            }))}
            centre={<>
              <span className="num text-[20px] font-semibold leading-6">Rs. {whole(total)}</span>
              <span className="text-[12px] leading-4 text-ink-3">{t("invested")}</span>
            </>}
          />
        </Card>

        <Card title={t("byClass")} aside={<ViewToggle value={classView} onChange={setClassView} />}>
          {classView === "chart" ? (
            <Suspense fallback={<ChartFallback />}><BucketBars rows={live} years={result.horizon_years} /></Suspense>
          ) : (
            <DataTable caption={t("byClass")} columns={projColumns} rows={live} />
          )}
        </Card>

      </div>

      <div className="mt-4 grid gap-4 @2xl:grid-cols-[minmax(0,1fr)_minmax(0,0.6fr)]">
        <Card title={t("weights")} aside={<ViewToggle value={view} onChange={setView} />}>
          {view === "chart" ? <RankedBars rows={holdingRows} /> : <DataTable caption={t("weights")} columns={weightColumns} rows={result.weights} />}
        </Card>

        <div className="flex flex-col gap-4">
          <Card title="How your plan works">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 border-b border-line pb-4 text-[13px] leading-5">
              <div><dt className="text-ink-3">Risk level</dt><dd className="num mt-0.5 text-[15px] font-semibold">{Math.round(result.risk_thermometer)} out of 100</dd></div>
              <div><dt className="text-ink-3">Time frame</dt><dd className="num mt-0.5 text-[15px] font-semibold">{result.horizon_years} {t("yearsUnit")}</dd></div>
            </dl>
            <ul className="divide-y divide-line">
              {result.bucket_projections.map((b, i) => ({ ...b, bucket: BUCKET_ORDER[i] })).filter((b) => b.present_value > 0).map((b) => (
                <li key={b.bucket} className="py-3.5 first:pt-4">
                  <div className="flex items-center justify-between gap-3">
                    <span className="flex items-center gap-2.5 text-[14.5px] font-semibold leading-5">
                      <span className="size-3 shrink-0 rounded-[4px]" style={{ background: BUCKET_COLOR[b.bucket] }} aria-hidden />
                      {t(BUCKET_KEY[b.bucket])}
                    </span>
                    <span className="num text-[13px] leading-5 text-gain">{pct(b.projected_return_pct)} a year</span>
                  </div>
                  <p className="num mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 pl-[22px] text-[13.5px] leading-5 text-ink-2">
                    <span className="whitespace-nowrap">Rs. {whole(b.present_value)}</span>
                    <ArrowRightIcon size={14} className="shrink-0 text-ink-3" aria-label="grows to" />
                    <span className="whitespace-nowrap">Rs. {whole(b.projected_value)}</span>
                  </p>
                </li>
              ))}
            </ul>
            <p className="mt-1 text-[12px] leading-4 text-ink-3">Returns are after tax. Estimates from past data and a model.</p>
            {unallocated > 1 && (
              <p className="num mt-3 text-[12.5px] leading-5 text-ink-3">
                Rs. {whole(unallocated)} of the Rs. {whole(requested)} you entered is left unallocated by the engine's own limits.
              </p>
            )}
          </Card>
        </div>
      </div>

      <Card title={t("projections")} className="mt-4">
        <DataTable caption={t("projections")} columns={projColumns} rows={result.instrument_projections} />
      </Card>

      {result.banks_selected.length > 0 && (
        <Card title={t("banksSel")} className="mt-4">
          <DataTable caption={t("banksSel")} columns={weightColumns} rows={result.banks_selected} />
        </Card>
      )}
    </section>
  );
}
