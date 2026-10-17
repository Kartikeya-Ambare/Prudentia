import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Navigate, NavLink, useLocation } from "react-router";
import { useIsMutating } from "@tanstack/react-query";
import {
  BankIcon, ChartDonutIcon, ChartLineUpIcon, ChartPieSliceIcon, ChatCircleDotsIcon, LockSimpleIcon, SquaresFourIcon, XIcon,
} from "@phosphor-icons/react";
import clsx from "clsx";
import { useHealth } from "@/api/hooks";
import type { Bucket } from "@/api/types";
import { useSession } from "@/store/session";
import { useLevel } from "@/store/ui";
import { useMedia } from "@/lib/useMedia";
import { useT, type Key } from "@/lib/i18n";
import { RoutePanel } from "@/components/ui/RoutePanel";
import { Alert } from "@/components/ui/Feedback";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { ModeToggle } from "@/components/ui/ModeToggle";
import { EngineLoader } from "@/components/viz/DotMatrixLoader";
import { PlanForm } from "@/tabs/PlanForm";
import { PlanView } from "@/tabs/PlanView";
import { ClassPage } from "@/tabs/ClassPage";
import { ChatPanel } from "@/tabs/ChatPanel";
import { SectorTab } from "@/tabs/SectorTab";

// Page URLs. Backend calls live under /api/ (see src/api/live.ts), so these never collide with them.
// Everything except the recommendation page needs a plan to show anything, so it stays locked until there is one.
const PAGES: { path: string; nav: Key; title: Key; Icon: typeof SquaresFourIcon; bucket?: Bucket; needsPlan?: boolean }[] = [
  { path: "/", nav: "navHome", title: "pageHome", Icon: SquaresFourIcon },
  { path: "/stocks", nav: "navStocks", title: "navStocks", Icon: ChartLineUpIcon, bucket: "stock", needsPlan: true },
  { path: "/mutual-funds", nav: "navMf", title: "navMf", Icon: ChartPieSliceIcon, bucket: "mf", needsPlan: true },
  { path: "/deposits", nav: "navFd", title: "navFd", Icon: BankIcon, bucket: "bank", needsPlan: true },
  { path: "/sectors", nav: "navSectors", title: "navSectors", Icon: ChartDonutIcon, needsPlan: true },
];
const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://127.0.0.1:8000";

function Brand() {
  return (
    <NavLink to="/" end aria-label="Prudentia, home" className="sl flex items-center gap-3 rounded-[var(--radius-control)] px-3 py-1">
      <img src="/favicon.svg" alt="" width={32} height={32} />
      <span className="font-display text-[20px] font-semibold leading-7">Prudentia</span>
    </NavLink>
  );
}

/**
 * Destinations only. No border: the sidebar is set apart from the page by tone. The active page is marked by one
 * pill that slides between items (not a background that switches), and when the first plan arrives the locked
 * items light up one after another.
 */
function Sidebar({ hasPlan }: { hasPlan: boolean }) {
  const t = useT();
  const { pathname } = useLocation();
  const nav = useRef<HTMLElement>(null);
  const items = useRef<Record<string, HTMLElement | null>>({});
  const [pill, setPill] = useState<{ x: number; y: number; w: number; h: number } | null>(null);
  const [fresh, setFresh] = useState(false); // true briefly right after the plan unlocks the pages
  const seenPlan = useRef(hasPlan);

  useLayoutEffect(() => {
    const place = () => {
      const el = items.current[pathname];
      if (el) setPill({ x: el.offsetLeft, y: el.offsetTop, w: el.offsetWidth, h: el.offsetHeight });
    };
    place();
    const ro = new ResizeObserver(place);
    if (nav.current) ro.observe(nav.current);
    return () => ro.disconnect();
  }, [pathname, hasPlan]);

  useEffect(() => {
    if (hasPlan && !seenPlan.current) {
      setFresh(true);
      const id = setTimeout(() => setFresh(false), 1600);
      seenPlan.current = true;
      return () => clearTimeout(id);
    }
    seenPlan.current = hasPlan;
  }, [hasPlan]);

  const item = "relative z-10 flex min-h-[48px] items-center gap-3 rounded-[var(--radius-control)] px-3 text-[14px] font-medium leading-5 max-md:min-h-[52px] max-md:min-w-0 max-md:flex-col max-md:justify-center max-md:gap-0.5 max-md:px-1 max-md:text-[11px] max-md:leading-4";
  return (
    <aside className="flex shrink-0 flex-col gap-8 bg-rail p-4 max-md:fixed max-md:inset-x-0 max-md:bottom-0 max-md:z-30 max-md:flex-row max-md:gap-0 max-md:p-1 max-md:pb-[max(0.25rem,env(safe-area-inset-bottom))] md:w-[236px] md:py-6">
      <div className="max-md:hidden"><Brand /></div>
      <nav ref={nav} aria-label={t("nav")} className="relative flex flex-1 gap-1 md:flex-col max-md:justify-around">
        {pill && (
          <span
            aria-hidden
            className="pointer-events-none absolute left-0 top-0 rounded-[var(--radius-control)] bg-surface transition-[transform,width,height] duration-[380ms] ease-[cubic-bezier(0.32,0.72,0,1)] motion-reduce:transition-none"
            style={{ width: pill.w, height: pill.h, transform: `translate(${pill.x}px, ${pill.y}px)` }}
          />
        )}
        {PAGES.map(({ path, nav: label, Icon, needsPlan }, index) => {
          if (needsPlan && !hasPlan) {
            return (
              <span key={path} role="link" aria-disabled="true" title={t("navLocked")} className={clsx(item, "cursor-not-allowed text-ink-3 opacity-60 max-md:flex-1")}>
                <Icon size={20} aria-hidden />
                <span>{t(label)}</span>
                <LockSimpleIcon size={13} className="ml-auto max-md:hidden" aria-hidden />
              </span>
            );
          }
          return (
            <NavLink
              key={path}
              to={path}
              end
              ref={(el) => { items.current[path] = el; }}
              style={fresh && needsPlan ? { ["--d" as string]: (index - 1) * 110 } : undefined}
              className={({ isActive }) => clsx("sl transition-colors duration-200 max-md:flex-1", item, isActive ? "text-ink" : "text-ink-2", fresh && needsPlan && "unlock")}
            >
              {({ isActive }) => (
                <>
                  <Icon size={20} weight={isActive ? "fill" : "regular"} className={isActive ? "text-accent" : undefined} aria-hidden />
                  {path === "/" ? <><span className="md:hidden">Plan</span><span className="max-md:hidden">{t(label)}</span></> : <span>{t(label)}</span>}
                </>
              )}
            </NavLink>
          );
        })}
      </nav>
      <div className="px-1 max-md:hidden"><ThemeToggle /></div>
    </aside>
  );
}

function TopBar({ title, tagline }: { title: string; tagline: boolean }) {
  const t = useT();
  return (
    <header className="mb-5">
      <div className="mb-3 flex items-center justify-between md:hidden">
        <Brand />
        <ThemeToggle />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <div className="min-w-0">
          <h1 className="text-[24px] leading-8 sm:text-[30px] sm:leading-9">{title}</h1>
          {tagline && <p className="mt-1.5 text-[14px] leading-5 text-ink-2">{t("tagline")}</p>}
        </div>
        <ModeToggle />
      </div>
    </header>
  );
}

/** On screens too narrow for a side panel, the chat lives behind a floating button and opens as a sheet. */
function ChatDrawer() {
  const t = useT();
  const [open, setOpen] = useState(false);
  return (
    <>
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="sl sl-fill fixed bottom-[5.5rem] right-4 z-40 inline-flex min-h-[52px] items-center gap-2 rounded-full bg-brand px-5 text-[14px] font-medium text-on-brand shadow-[0_6px_20px_rgba(20,24,50,0.25)] md:bottom-14"
        >
          <ChatCircleDotsIcon size={20} weight="fill" aria-hidden />{t("chatOpen")}
        </button>
      )}
      {open && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 md:items-stretch md:justify-end" onClick={() => setOpen(false)}>
          <div
            role="dialog" aria-modal="true" aria-label={t("chat")}
            className="route-panel relative flex h-[88dvh] w-full flex-col rounded-t-[24px] bg-surface p-3 md:h-auto md:w-[420px] md:rounded-none md:rounded-l-[24px]"
            onClick={(e) => e.stopPropagation()}
          >
            <button type="button" aria-label={t("chatClose")} onClick={() => setOpen(false)}
              className="sl absolute right-3 top-3 z-10 flex size-[44px] items-center justify-center rounded-full bg-rail text-ink">
              <XIcon size={18} aria-hidden />
            </button>
            <div className="min-h-0 flex-1"><ChatPanel variant="dock" /></div>
          </div>
        </div>
      )}
    </>
  );
}

export function App() {
  const { pathname } = useLocation();
  const t = useT();
  const health = useHealth();
  const plan = useSession((s) => s.lastResult);
  const level = useLevel((s) => s.level);
  const busy = useIsMutating({ mutationKey: ["plan"] }) > 0;      // chat messages show their own small "Working on it"
  const wide = useMedia("(min-width: 1280px)");

  const page = PAGES.find((p) => p.path === pathname);
  // Unknown addresses (including the old /overview, /starter, /builder) go home. Locked pages do too.
  if (!page || (page.needsPlan && !plan)) return <Navigate to="/" replace />;

  if (health.isError) {
    return (
      <main className="mx-auto max-w-[900px] px-5 py-10">
        <Alert tone="error">
          {t("backendDown")} ({API_URL})
          <pre className="mt-2 font-mono text-[13px]">uvicorn backend.api.main:app --port 8000</pre>
        </Alert>
      </main>
    );
  }

  const home = page.path === "/";
  const onSectors = page.path === "/sectors";
  // Beginner with no plan yet: the whole screen is the conversation. Otherwise results with the chat docked.
  const chatOnly = level === "beginner" && !plan && home;

  return (
    <>
      <div className="flex min-h-dvh bg-page md:h-dvh md:p-4">
        <div className="mx-auto flex w-full max-w-[1760px] overflow-hidden bg-surface md:h-full md:rounded-[24px]">
          <Sidebar hasPlan={!!plan} />
          <div className="flex min-w-0 flex-1 flex-col">
          <main className="min-w-0 flex-1 px-4 pb-44 pt-5 sm:px-8 md:flex md:flex-col md:overflow-y-auto md:pb-6 md:pt-6">
            <TopBar title={t(page.title)} tagline={page.path === "/"} />
            {chatOnly ? (
              <div className="h-[calc(100dvh-17rem)] min-h-[440px] md:h-auto md:min-h-0 md:flex-1"><ChatPanel variant="full" /></div>
            ) : (
              <div className={clsx("grid items-start gap-6", !onSectors && "xl:grid-cols-[minmax(0,1fr)_340px]")}>
                <div key={`${pathname}-${level}`} className="route-panel flex min-w-0 flex-col gap-4">
                  {home && level === "expert" && <PlanForm full />}
                  {busy && <EngineLoader />}
                  <div className={clsx("transition-opacity duration-300", busy && plan && "pointer-events-none opacity-40")}>
                    {onSectors && <RoutePanel active><SectorTab /></RoutePanel>}
                    {home && (plan ? <PlanView result={plan} /> : level === "expert" && !busy && (
                      <p className="panel p-6 text-[15px] leading-6 text-ink-2">{t("starterEmpty")}</p>
                    ))}
                    {page.bucket && <ClassPage bucket={page.bucket} />}
                  </div>
                </div>
                {!onSectors && wide && (
                  <div className="xl:sticky xl:top-6 xl:h-[calc(100dvh-8rem)]"><ChatPanel variant="dock" /></div>
                )}
              </div>
            )}
            {!chatOnly && !wide && !onSectors && <ChatDrawer />}
            <p className="mt-10 text-center text-[12px] leading-4 text-ink-3 md:hidden">{t("disclaimer")}</p>
          </main>
          <footer className="shrink-0 px-8 pb-4 pt-1 text-center text-[12px] leading-4 text-ink-3 max-md:hidden">{t("disclaimer")}</footer>
          </div>
        </div>
      </div>
    </>
  );
}
