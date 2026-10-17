import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowUpIcon } from "@phosphor-icons/react";
import clsx from "clsx";
import { useQueryClient } from "@tanstack/react-query";
import { useChat, useDrift } from "@/api/hooks";
import { ApiError, type DriftRow } from "@/api/types";
import { asPlan, useSession } from "@/store/session";
import { number } from "@/lib/format";
import { useMedia } from "@/lib/useMedia";
import { useT } from "@/lib/i18n";
import { lazy, Suspense } from "react";
import { prudieStateFor, type AgentPhase } from "@/prudie/agent";

// The mascot engine is large and only needed once a chat shows: load it after the page is interactive.
const Prudie = lazy(() => import("@/prudie/Prudie"));
import { Alert } from "@/components/ui/Feedback";
import { PlanReplyCard } from "@/tabs/PlanReplyCard";
import { DotMatrixLoader, EngineLoader } from "@/components/viz/DotMatrixLoader";
import { DataTable, type Column } from "@/components/ui/DataTable";

const diffColumns: Column<DriftRow>[] = [
  { key: "bucket", header: "", render: (r) => r.bucket },
  { key: "before", header: "Before", render: (r) => number(r.before), numeric: true },
  { key: "after", header: "After", render: (r) => number(r.after), numeric: true },
  { key: "delta", header: "Change", render: (r) => number(r.delta), numeric: true },
];

const RISK_ANSWERS = ["Low risk", "Medium risk", "High risk"] as const;

/**
 * Chat is an action console, not a free-text assistant: it can build the plan (when the chat service runs
 * the intake) and change it. It edits the same shared plan the Expert form edits.
 *   variant "full": the Beginner start screen, a centred Claude-style conversation.
 *   variant "dock": the side panel next to the results.
 */
export function ChatPanel({ variant }: { variant: "full" | "dock" }) {
  const t = useT();
  const plan = useSession((s) => s.lastResult);
  const setLastResult = useSession((s) => s.setLastResult);
  const history = useSession((s) => s.chatHistory);
  const addMessage = useSession((s) => s.addMessage);
  const sessionId = useSession((s) => s.sessionId);
  const chat = useChat();
  const queryClient = useQueryClient();
  const drift = useDrift(plan?.profile_id);
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLLIElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);

  const full = variant === "full";
  // On short windows the mascot is a little smaller so the whole start screen fits without a scrollbar.
  const tall = useMedia("(min-height: 740px)");
  const mid = useMedia("(min-height: 660px)");

  // Prudie mirrors what the chat is doing: rolls in when the chat opens, reads while you type,
  // searches while the service works, gives a thumbs up when the answer lands.
  const [typing, setTyping] = useState(false);
  const typingTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const [opened, setOpened] = useState(true);
  const [done, setDone] = useState(false);
  const [lookAt, setLookAt] = useState<{ x: number; y: number } | null>(null);
  const example = full && history.length === 0 ? t("startPlaceholder").replace(/^e\.g\.\s*/i, "") : "";
  const phase: AgentPhase = chat.isPending ? "thinking" : done ? "done" : typing ? "typing" : opened ? "chat-open" : "idle";
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
  const last = history.at(-1);
  const askingRisk = last?.role === "assistant" && !!last.missing?.some((m) => /risk/i.test(m)) && !chat.isPending;

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [history.length, chat.isPending]);

  function submit(text: string) {
    const message = text.trim();
    if (!message || chat.isPending) return;
    const asked = useSession.getState().activeLevel;
    addMessage({ role: "user", content: message }, asked);
    setDraft("");
    clearTimeout(typingTimer.current);
    setTyping(false);
    chat.mutate(
      { message, profileId: plan?.profile_id, sessionId },
      {
        onSuccess: (body) => {
          const card = body.allocation ? asPlan(body.allocation) : undefined;
          // A plan is shown as a card; if the service text is a long dump of the same numbers, use a short lead instead.
          const dump = !!card && (body.reply.length > 220 || /\n\s*[-*•]/.test(body.reply));
          addMessage({
            role: "assistant", diff: body.diff, missing: body.missing, allocation: card,
            content: dump ? (plan ? "Your plan is updated." : "Here is your plan.") : body.reply,
          }, asked);
          setDone(true);
          if (body.allocation) {
            setLastResult(body.allocation, asked);
            queryClient.invalidateQueries({ queryKey: ["drift"] });
          }
        },
        onError: (err) =>
          addMessage({
            role: "assistant",
            content: err instanceof ApiError && err.status === 429 ? t("chatSlow")
              : err instanceof ApiError && err.status > 0 ? err.message : t("chatDown"),
          }),
      },
    );
  }

  function send(e: FormEvent) {
    e.preventDefault();
    submit(draft);
  }

  const messages = (
    <ul className={clsx("flex flex-1 flex-col gap-4 overflow-y-auto", full ? "px-1 py-4" : "pr-1")} aria-live="polite" aria-label={t("chat")}>
      {!full && (
        <li className="flex">
          <p className="max-w-[92%] rounded-[var(--radius-panel)] bg-rail px-4 py-3 text-[14.5px] leading-6">{plan ? t("chatEdit") : t("chatIntro")}</p>
        </li>
      )}
      {history.map((m, i) => (
        <li key={i} className={clsx("msg-in flex", m.role === "user" && "justify-end")}>
          <div className={clsx(
            "rounded-[var(--radius-panel)] px-4 py-3 text-[14.5px] leading-6",
            full ? "max-w-[85%]" : "max-w-[92%]",
            m.role === "user" ? "bg-accent-container text-ink" : "bg-rail",
          )}>
            <p className="whitespace-pre-line">{m.content}</p>
            {m.allocation && <PlanReplyCard plan={m.allocation} />}
            {m.diff && <div className="mt-3"><DataTable caption="" columns={diffColumns} rows={m.diff} /></div>}
          </div>
        </li>
      ))}
      {chat.isPending && (plan ? (
        <li className="flex items-center gap-3 text-[14px] text-ink-2"><DotMatrixLoader dot={5} gap={2} label={t("thinking")} />{t("thinking")}</li>
      ) : (
        // The very first plan is the slow one (prices, picks, banks, scenarios): show those steps. Later chat actions just say "Working on it".
        <li className="max-w-[420px]"><EngineLoader /></li>
      ))}
      <li ref={endRef} aria-hidden />
    </ul>
  );

  const composer = (
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
      <form onSubmit={send} className={clsx(
        "flex items-end gap-2 border border-ctl bg-surface p-2 transition-colors focus-within:border-accent hover:border-ink-3",
        full ? "rounded-[20px]" : "rounded-[var(--radius-panel)]",
      )}>
        <textarea
          ref={box}
          rows={full ? 2 : 1}
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
          placeholder={full && history.length === 0 ? t("startPlaceholder") : t("chatPlaceholder")}
          className="max-h-40 min-h-[44px] min-w-0 flex-1 resize-none bg-transparent px-2 py-2.5 text-[15px] leading-6 outline-none placeholder:text-ink-3"
        />
        <button
          type="submit"
          aria-label={t("send")}
          disabled={!draft.trim() || chat.isPending}
          className="sl sl-fill flex size-[44px] shrink-0 items-center justify-center rounded-full bg-brand text-on-brand disabled:opacity-[.38]"
        >
          <ArrowUpIcon size={18} weight="bold" aria-hidden />
        </button>
      </form>
    </div>
  );

  if (full) {
    const started = history.length > 0;
    return (
      <section aria-label={t("chat")} className="mx-auto flex h-full min-h-[420px] w-full max-w-[760px] flex-col">
        {!started ? (
          // Before the first message the whole group is one centred block, composer included.
          <div className="flex flex-1 flex-col items-center justify-end gap-4 pb-4 text-center md:pb-10 [@media(max-height:720px)]:gap-2 [@media(max-height:720px)]:pb-1">
            <div className="rise" style={{ ["--d" as string]: 0 }}>{prudie(tall ? 210 : mid ? 170 : 130)}</div>
            <h2 className="rise max-w-[18ch] text-[34px] leading-[1.1] sm:max-w-none sm:text-[44px]" style={{ ["--d" as string]: 140 }}>{t("startHeading")}</h2>
            <p className="rise max-w-[56ch] text-[17px] leading-7 text-ink-2 sm:text-[18px]" style={{ ["--d" as string]: 240 }}>{t("startSub")}</p>
            <div className="rise mt-4 w-full" style={{ ["--d" as string]: 340 }}>{composer}</div>
          </div>
        ) : (
          <>
            {messages}
            {composer}
          </>
        )}
      </section>
    );
  }

  return (
    <section aria-label={t("chat")} className="panel flex min-h-[420px] flex-col p-4 sm:p-5 lg:h-full">
      <div className="mb-2 flex items-center gap-3">
        <div className="shrink-0">{prudie(84)}</div>
        <h2 className="text-[18px] leading-6">{t("chat")}</h2>
      </div>
      {drift.data?.drifted && <Alert tone="warning" className="mb-3">{t("drifted")}</Alert>}
      {messages}
      <div className="mt-4">{composer}</div>
    </section>
  );
}
