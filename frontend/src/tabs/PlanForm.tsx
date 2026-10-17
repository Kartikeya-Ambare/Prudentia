import { useMemo, useState } from "react";
import { useBanks, usePlan } from "@/api/hooks";
import type { AssetClass, McCategory, PlanRequest } from "@/api/types";
import { asPlan, useSession } from "@/store/session";
import { useT } from "@/lib/i18n";
import { Button } from "@/components/ui/Button";
import { ClassCard, Segmented } from "@/components/ui/Choice";
import { Alert } from "@/components/ui/Feedback";
import { Field, MultiSelect, NumberInput, Slider } from "@/components/ui/Form";

const SECTOR_OPTIONS = [
  "Banking", "NBFC, Insurance & Asset Management", "Information Technology",
  "Pharma & Healthcare", "Automobile & Auto Ancillaries", "FMCG & Consumer Staples",
  "Metals & Mining", "Energy, Oil & Gas, Power", "Realty & Infrastructure",
  "Capital Goods, Industrials & Defence", "Consumer Durables & Retail",
  "Media & Digital / New-Age Internet",
] as const;
const MF_CATEGORIES: McCategory[] = ["Large Cap", "Mid Cap", "Small Cap"];
const ALL: AssetClass[] = ["stocks", "mf", "fd"];
// Low / moderate / high presets for the 0–100 risk-you-can-afford scale.
const RISK_PRESETS = [20, 50, 80] as const;

/** Builder: amount, years, risk. Architect: the same plus asset classes, sectors, fund types, banks and split. */
export function PlanForm({ full }: { full: boolean }) {
  const t = useT();
  const plan = usePlan();
  const banks = useBanks();
  const current = useSession((s) => s.lastResult);
  const setLastResult = useSession((s) => s.setLastResult);
  const addMessage = useSession((s) => s.addMessage);

  const [capital, setCapital] = useState(100_000);
  const [horizon, setHorizon] = useState(5);
  const [risk, setRisk] = useState(50);
  const [classes, setClasses] = useState<AssetClass[]>(ALL);
  const [sectors, setSectors] = useState<string[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [bankMode, setBankMode] = useState<"auto" | "pick">("auto");
  const [bankNames, setBankNames] = useState<string[]>([]);
  const [ownSplit, setOwnSplit] = useState(false);
  const [split, setSplit] = useState<Partial<Record<AssetClass, number>>>({});

  const toggleClass = (c: AssetClass) =>
    setClasses((cur) => (cur.includes(c) ? (cur.length > 1 ? cur.filter((x) => x !== c) : cur) : ALL.filter((x) => x === c || cur.includes(x))));
  const label = (c: AssetClass) => t(c === "stocks" ? "stocks" : c === "mf" ? "mf" : "fd");
  const bankList = banks.data ?? [];
  const bankByName = useMemo(() => new Map(bankList.map((b) => [b.display_name, b.id])), [bankList]);

  const splitValue = (c: AssetClass) => split[c] ?? Math.round(100 / classes.length);
  const splitTotal = classes.reduce((a, c) => a + splitValue(c), 0);
  const useSplit = full && ownSplit && classes.length > 1;
  const splitError = useSplit && Math.abs(splitTotal - 100) > 0.5 ? t("splitMust") : null;
  const bankError = full && classes.includes("fd") && bankMode === "pick" && bankNames.length === 0 ? t("banksNeedOne") : null;
  const blocked = !!splitError || !!bankError;
  const [shake, setShake] = useState(0);

  function submit() {
    if (blocked) { setShake((n) => n + 1); return; }
    const req: PlanRequest = { profile_id: current?.profile_id, capital, horizon_years: horizon, risk_thermometer: risk };
    if (full) {
      req.classes = classes;
      if (classes.includes("stocks")) req.sector_pref = sectors;
      if (classes.includes("mf")) req.mf_category_pref = categories as McCategory[];
      if (classes.includes("fd")) {
        req.banks = bankMode === "pick" ? bankNames.map((n) => bankByName.get(n)!).filter(Boolean) : "auto";
      }
      if (useSplit) req.manual_split = Object.fromEntries(classes.map((c) => [c, splitValue(c)]));
    }
    const asked = useSession.getState().activeLevel;
    plan.mutate(req, {
      onSuccess: (r) => {
        setLastResult(r, asked);
        // Keep every plan in the chat timeline, so a later change from the chat never makes the earlier result disappear.
        addMessage({ role: "assistant", content: current ? "Your plan is updated." : "Here is your plan.", allocation: asPlan(r) }, asked);
      },
    });
  }

  return (
    <div className="panel p-5 sm:p-6">
      <div className="grid gap-6 sm:grid-cols-2">
        <Field label={t("amount")} htmlFor="capital">
          <NumberInput id="capital" value={capital} onChange={setCapital} min={1000} step={1000} />
        </Field>
        <Field label={t("years")} htmlFor="horizon">
          <NumberInput id="horizon" value={horizon} onChange={setHorizon} min={1} max={40} step={1} />
        </Field>
        <div className="flex flex-col gap-3 sm:col-span-2">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <label htmlFor="risk" className="text-[14px] font-medium leading-5">{t("risk")}</label>
            <Segmented
              label={t("risk")}
              value={RISK_PRESETS.find((p) => p === risk) ?? null}
              onChange={setRisk}
              options={[
                { id: 20, label: t("riskLow") }, { id: 50, label: t("riskMod") }, { id: 80, label: t("riskHigh") },
              ]}
            />
          </div>
          <Slider id="risk" value={risk} onChange={setRisk} min={0} max={100} />
          <p className="text-[12px] leading-4 text-ink-3">{t("riskHelp")}</p>
        </div>
      </div>

      {full && (
        <div className="mt-6 flex flex-col gap-4 border-t border-line pt-6">
          <div>
            <h3 className="text-[16px] font-semibold leading-6">{t("assetClasses")}</h3>
            <p className="text-[13px] leading-5 text-ink-3">{t("pickOne")}</p>
          </div>

          <ClassCard
            color="var(--color-stocks)" title={t("stocks")} blurb={t("stocksBlurb")}
            on={classes.includes("stocks")} locked={classes.length === 1 && classes.includes("stocks")} onToggle={() => toggleClass("stocks")}
          >
            <MultiSelect label={t("sectorPref")} options={SECTOR_OPTIONS} selected={sectors} onChange={setSectors} />
          </ClassCard>

          <ClassCard
            color="var(--color-funds)" title={t("mf")} blurb={t("mfBlurb")}
            on={classes.includes("mf")} locked={classes.length === 1 && classes.includes("mf")} onToggle={() => toggleClass("mf")}
          >
            <MultiSelect label={t("mfPref")} options={MF_CATEGORIES} selected={categories} onChange={setCategories} />
          </ClassCard>

          <ClassCard
            color="var(--color-fd)" title={t("fd")} blurb={t("fdBlurb")}
            on={classes.includes("fd")} locked={classes.length === 1 && classes.includes("fd")} onToggle={() => toggleClass("fd")}
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span className="text-[14px] font-medium leading-5">{t("banks")}</span>
              <Segmented
                label={t("banks")} value={bankMode} onChange={setBankMode}
                options={[{ id: "auto", label: t("banksAuto") }, { id: "pick", label: t("banksPick") }]}
              />
            </div>
            {bankMode === "pick" && (
              <div className="mt-3">
                <MultiSelect label={t("banksPickHelp")} options={bankList.map((b) => b.display_name)} selected={bankNames} onChange={setBankNames} />
                {bankError && <p key={shake} role="alert" className={`mt-2 text-[12px] leading-4 text-loss ${shake ? "shake" : ""}`}>{bankError}</p>}
              </div>
            )}
          </ClassCard>

          {classes.length > 1 && (
            <div className="flex flex-col gap-3 rounded-[var(--radius-panel)] bg-rail p-4">
              <label className="flex min-h-[44px] w-fit cursor-pointer items-center gap-3 text-[14px] font-medium">
                <input type="checkbox" checked={ownSplit} onChange={(e) => setOwnSplit(e.target.checked)} className="size-[18px] accent-[var(--color-accent)]" />
                {t("ownSplit")}
              </label>
              {ownSplit && (
                <div className="grid gap-4 sm:grid-cols-3">
                  {classes.map((c) => (
                    <Field key={c} label={`${label(c)} %`} htmlFor={`split-${c}`}>
                      <NumberInput id={`split-${c}`} value={splitValue(c)} onChange={(v) => setSplit({ ...split, [c]: v })} min={0} max={100} step={5} />
                    </Field>
                  ))}
                  <p key={splitError ? shake : "ok"} className={`num text-[13px] leading-5 sm:col-span-3 ${splitError ? `text-loss ${shake ? "shake" : ""}` : "text-ink-3"}`} role={splitError ? "alert" : undefined}>
                    {t("splitTotal")}: {splitTotal}% {splitError && `— ${splitError}`}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <div className="mt-6 flex flex-col gap-4">
        <div>
          <Button onClick={submit} disabled={plan.isPending}>{current ? t("updatePlan") : t("getPlan")}</Button>
        </div>
        {plan.isError && <Alert tone="error">{t("failed")}: {plan.error.message}</Alert>}
      </div>
    </div>
  );
}
