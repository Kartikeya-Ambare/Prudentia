import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowUpIcon } from "@phosphor-icons/react";
import clsx from "clsx";
import type { DriftRow } from "@/api/types";
import { useSession } from "@/store/session";
import { useAssistant } from "@/store/assistant";
import { number } from "@/lib/format";
import { useMedia } from "@/lib/useMedia";
import { useT } from "@/lib/i18n";
import { lazy, Suspense } from "react";
import { prudieStateFor, type AgentPhase } from "@/prudie/agent";

// The mascot engine is large and only needed once a chat shows: load it after the page is interactive.
const Prudie = lazy(() => import("@/prudie/Prudie"));
import { PlanReplyCard } from "@/tabs/PlanReplyCard";
import { EngineLoader, DotMatrixLoader } from "@/components/viz/DotMatrixLoader";
import { DataTable, type Column } from "@/components/ui/DataTable";

const diffColumns: Column<DriftRow>[] = [
  { key: "bucket", header: "", render: (r) => r.bucket },
  { key: "before", header: "Before", render: (r) => number(r.before), numeric: true },
  { key: "after", header: "After", render: (r) => number(r.after), numeric: true },
  { key: "delta", header: "Change", render: (r) => number(r.delta), numeric: true },
];

const RISK_ANSWERS = ["Low risk", "Medium risk", "High risk"] as const;

/** The conversation: the messages and the box to type in. */
export function Conversation({ variant }: { variant: "full" | "sheet" }) {
  const t = useT();
  const plan = useSession((s) => s.lastResult);
  const history = useSession((s) => s.chatHistory);
  const pending = useAssistant((s) => s.pending);
  const send = useAssistant((s) => s.send);
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLLIElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);

  const full = variant === "full";
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [history.length, pending]);

  const last = history.at(-1);
  const askingRisk = last?.role === "assistant" && !!last.missing?.some((m) => /risk/i.test(m)) && !pending;

  function submit(text: string) {
    if (!text.trim() || pending) return;
    setDraft("");
    void send(text);
  }
  function onSubmit(e: FormEvent) {
    e.preventDefault();
    submit(draft);
  }

  return (
    <>
      <ul className={clsx("flex flex-1 flex-col gap-4 overflow-y-auto", full ? "px-1 py-4" : "px-1 pb-2")} aria-live="polite" aria-label={t("chat")}>
        {!full && (
          <li className="flex">
            <p className="max-w-[92%] rounded-[var(--radius-panel)] bg-rail px-4 py-3 text-[14.5px] leading-6">{plan ? t("chatEdit") : t("chatIntro")}</p>
          </li>
        )}
        {history.map((m, i) => (
          <li key={i} className={clsx("msg-in flex", m.role === "user" && "justify-end")}>
            <div className={clsx(
              "rounded-[var(--radius-panel)] px-4 py-3 text-[14.5px] leading-6",
              full ? "max-w-[85%]" : "max-w-[94%]",
              m.role === "user" ? "bg-accent-container text-ink" : "bg-rail",
            )}>
              <p className="whitespace-pre-line">{m.content}</p>
              {m.allocation && <PlanReplyCard plan={m.allocation} />}
              {m.diff && <div className="mt-3"><DataTable caption="" columns={diffColumns} rows={m.diff} /></div>}
            </div>
          </li>
        ))}
        {pending && (plan ? (
          <li className="flex items-center gap-3 text-[14px] text-ink-2"><DotMatrixLoader dot={5} gap={2} label={t("thinking")} />{t("thinking")}</li>
        ) : (
          // The very first plan is the slow one (prices, picks, banks, scenarios): show those steps. Later chat actions just say "Working on it".
          <li className="max-w-[420px]"><EngineLoader /></li>
        ))}
        <li ref={endRef} aria-hidden />
      </ul>

      <div className="flex flex-col gap-2">
        {askingRisk && (
          <div className="flex flex-wrap items-center gap-2" role="group" aria-label={t("riskAsk")}>
            {RISK_ANSWERS.map((r) => (
              <button key={r} type="button" onClick={() => submit(r)}
                className="sl min-h-[40px] rounded-full border border-ctl bg-surface px-4 text-[13.5px] font-medium text-ink-2">
                {r}
              </button>
            ))}
          </div>
        )}
        <form onSubmit={onSubmit} className={clsx(
          "flex items-end gap-2 border border-ctl bg-surface p-2 transition-colors focus-within:border-accent hover:border-ink-3",
          full ? "rounded-[20px]" : "rounded-[var(--radius-panel)]",
        )}>
          <textarea
            ref={box}
            rows={full ? 2 : 1}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(draft); }
            }}
            name="message"
            aria-label={t("chatPlaceholder")}
            placeholder={t("chatPlaceholder")}
            className="max-h-40 min-h-[44px] min-w-0 flex-1 resize-none bg-transparent px-2 py-2.5 text-[15px] leading-6 outline-none placeholder:text-ink-3"
          />
          <SendButton disabled={!draft.trim() || pending} />
        </form>
      </div>
    </>
  );
}

export function SendButton({ disabled }: { disabled: boolean }) {
  const t = useT();
  return (
    <button
      type="submit"
      aria-label={t("send")}
      disabled={disabled}
      className="sl sl-fill flex size-[44px] shrink-0 items-center justify-center rounded-full bg-brand text-on-brand transition-transform duration-150 ease-out active:scale-[0.97] disabled:opacity-[.38]"
    >
      <ArrowUpIcon size={18} weight="bold" aria-hidden />
    </button>
  );
}

/** Beginner's start screen, before there is a plan: Prudie, the question, and one box, centred. */
export function StartScreen() {
  const t = useT();
  const history = useSession((s) => s.chatHistory);
  const pending = useAssistant((s) => s.pending);
  const done = useAssistant((s) => s.done);
  const setDone = useAssistant((s) => s.setDone);
  const send = useAssistant((s) => s.send);
  const [draft, setDraft] = useState("");
  const box = useRef<HTMLTextAreaElement>(null);

  // On short windows the mascot is a little smaller so the whole start screen fits without a scrollbar.
  const tall = useMedia("(min-height: 740px)");
  const mid = useMedia("(min-height: 660px)");

  // Prudie mirrors what the chat is doing: rolls in when the chat opens, reads while you type,
  // searches while the service works, gives a thumbs up when the answer lands.
  const [typing, setTyping] = useState(false);
  const typingTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const [opened, setOpened] = useState(true);
  const [lookAt, setLookAt] = useState<{ x: number; y: number } | null>(null);
  const example = history.length === 0 ? t("startPlaceholder").replace(/^e\.g\.\s*/i, "") : "";
  const phase: AgentPhase = pending ? "thinking" : done ? "done" : typing ? "typing" : opened ? "chat-open" : "idle";

  function submit(text: string) {
    const message = text.trim();
    if (!message || pending) return;
    setDraft("");
    clearTimeout(typingTimer.current);
    setTyping(false);
    void send(message);
  }

  const started = history.length > 0;
  const prudie = (size: number) => (
    // The placeholder keeps the same 5:6 box, so nothing shifts when the mascot arrives.
    <Suspense fallback={<div style={{ width: size, aspectRatio: "300 / 360" }} aria-hidden />}>
      <Prudie
        size={size}
        state={prudieStateFor(phase)}
        lookTarget={lookAt}
        onSettle={(finished) => {
          if (finished === "skate") setOpened(false);
          if (finished === "thumbsup") setDone(false);
        }}
      />
    </Suspense>
  );

  // After the first message the start screen turns into the plain conversation; the plan then arrives on the main page.
  if (started) {
    return (
      <section aria-label={t("chat")} className="mx-auto flex h-full min-h-[420px] w-full max-w-[760px] flex-col">
        <Conversation variant="full" />
      </section>
    );
  }

  return (
    <section aria-label={t("chat")} className="mx-auto flex h-full min-h-[420px] w-full max-w-[760px] flex-col">
      {/* Before the first message the whole group is one centred block, composer included. */}
      <div className="flex flex-1 flex-col items-center justify-end gap-4 pb-4 text-center md:pb-10 [@media(max-height:720px)]:gap-2 [@media(max-height:720px)]:pb-1">
        <div className="rise" style={{ ["--d" as string]: 0 }}>{prudie(tall ? 210 : mid ? 170 : 130)}</div>
        <h2 className="rise max-w-[18ch] text-[34px] leading-[1.1] sm:max-w-none sm:text-[44px]" style={{ ["--d" as string]: 140 }}>{t("startHeading")}</h2>
        <p className="rise max-w-[56ch] text-[17px] leading-7 text-ink-2 sm:text-[18px]" style={{ ["--d" as string]: 240 }}>{t("startSub")}</p>
        <div className="rise mt-4 w-full" style={{ ["--d" as string]: 340 }}>
          <form
            onSubmit={(e) => { e.preventDefault(); submit(draft); }}
            className="flex items-end gap-2 rounded-[20px] border border-ctl bg-surface p-2 transition-colors focus-within:border-accent hover:border-ink-3"
          >
            <textarea
              ref={box}
              rows={2}
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value);
                // Prudie lies down only while keys are being pressed and stands up again after a short pause.
                setTyping(!!e.target.value);
                clearTimeout(typingTimer.current);
                typingTimer.current = setTimeout(() => setTyping(false), 1500);
                const r = e.currentTarget.getBoundingClientRect();
                setLookAt({ x: r.left + Math.min(r.width, 24 + e.currentTarget.value.length * 8), y: r.top + r.height / 2 });
              }}
              onBlur={() => { clearTimeout(typingTimer.current); setTyping(false); }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(draft); return; }
                // Tab on an empty box accepts the example shown as the placeholder (like the Claude Code prompt).
                if (e.key === "Tab" && !e.shiftKey && !draft && example) {
                  e.preventDefault();
                  setDraft(example);
                  requestAnimationFrame(() => { const el = box.current; if (el) el.setSelectionRange(example.length, example.length); });
                }
              }}
              name="message"
              aria-label={t("chatPlaceholder")}
              placeholder={t("startPlaceholder")}
              className="max-h-40 min-h-[44px] min-w-0 flex-1 resize-none bg-transparent px-2 py-2.5 text-[15px] leading-6 outline-none placeholder:text-ink-3"
            />
            <SendButton disabled={!draft.trim() || pending} />
          </form>
        </div>
      </div>
    </section>
  );
}
