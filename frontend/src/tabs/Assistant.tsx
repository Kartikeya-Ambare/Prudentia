import { lazy, Suspense, useEffect, useRef, useState, type FormEvent } from "react";
import { ChatCircleDotsIcon, XIcon } from "@phosphor-icons/react";
import clsx from "clsx";
import { useSession } from "@/store/session";
import { useAssistant } from "@/store/assistant";
import { useT } from "@/lib/i18n";
import { prudieStateFor, type AgentPhase } from "@/prudie/agent";
import { Conversation, SendButton } from "@/tabs/ChatPanel";
import { DotMatrixLoader } from "@/components/viz/DotMatrixLoader";

const Prudie = lazy(() => import("@/prudie/Prudie"));

/** Things the chat can do right now, offered as one-tap messages while the box is empty. */
const SUGGESTIONS = [
  "Make it safer",
  "Move 10% from stocks to FD",
  "Why did you pick these stocks?",
  "What happens in the worst case?",
] as const;

/**
 * The assistant, as a bar at the bottom of the page instead of a column beside it: the plan keeps the full width and the chat
 * costs one line. The latest reply sits just above the bar; "History" opens the whole conversation in a panel.
 */
export function AssistantBar() {
  const t = useT();
  const plan = useSession((s) => s.lastResult);
  const history = useSession((s) => s.chatHistory);
  const pending = useAssistant((s) => s.pending);
  const done = useAssistant((s) => s.done);
  const setDone = useAssistant((s) => s.setDone);
  const send = useAssistant((s) => s.send);
  const setSheetOpen = useAssistant((s) => s.setSheetOpen);
  const [draft, setDraft] = useState("");
  const [focused, setFocused] = useState(false);
  const [dismissed, setDismissed] = useState(0);        // history length at the moment the last reply was dismissed
  const input = useRef<HTMLTextAreaElement>(null);

  // "/" jumps to the box from anywhere on the page, like a command bar.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey) return;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)) return;
      e.preventDefault();
      input.current?.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const last = history.at(-1);
  const reply = last?.role === "assistant" && history.length > dismissed ? last : null;
  const phase: AgentPhase = pending ? "thinking" : done ? "done" : focused && draft ? "typing" : "idle";

  // A reply is a notice, not a fixture: it clears itself (a plan update is already visible on the page, so sooner),
  // and the whole text stays in the conversation panel.
  useEffect(() => {
    if (!reply || pending) return;
    const id = setTimeout(() => setDismissed(history.length), reply.allocation ? 7000 : 14000);
    return () => clearTimeout(id);
  }, [reply, pending, history.length]);

  function submit(text: string) {
    if (!text.trim() || pending) return;
    setDraft("");
    void send(text);
  }
  function onSubmit(e: FormEvent) {
    e.preventDefault();
    submit(draft);
  }
  const showSuggestions = !!plan && !pending && !draft && !reply;

  return (
    <div className="z-30 mt-auto bg-surface px-4 pb-3 pt-4 sm:px-8 md:sticky md:bottom-0 md:-mx-8 md:pb-4 max-md:fixed max-md:inset-x-0 max-md:bottom-[calc(4.25rem+env(safe-area-inset-bottom,0px))] max-md:border-t max-md:border-line">
      <div className="mx-auto flex w-full max-w-[860px] flex-col gap-2">
        {(pending || reply) && (
          <div className="msg-in flex items-start gap-3 rounded-[var(--radius-panel)] border border-line bg-rail px-4 py-3" role="status" aria-live="polite">
            {pending ? (
              <p className="flex items-center gap-3 text-[14px] leading-6 text-ink-2"><DotMatrixLoader dot={5} gap={2} label={t("thinking")} />{t("thinking")}</p>
            ) : (
              <>
                <p className="line-clamp-3 min-w-0 flex-1 text-[14.5px] leading-6">{reply?.content}</p>
                <button type="button" onClick={() => setSheetOpen(true)} className="sl -my-1 shrink-0 rounded-full px-3 py-1.5 text-[13px] font-medium text-accent">
                  Open conversation
                </button>
                <button type="button" aria-label="Dismiss" onClick={() => setDismissed(history.length)}
                  className="sl -my-1 -mr-2 flex size-8 shrink-0 items-center justify-center rounded-full text-ink-3">
                  <XIcon size={16} aria-hidden />
                </button>
              </>
            )}
          </div>
        )}

        {showSuggestions && (
          <ul className="flex gap-2 overflow-x-auto pb-0.5" aria-label="Suggestions">
            {SUGGESTIONS.map((s) => (
              <li key={s} className="shrink-0">
                <button type="button" onClick={() => submit(s)}
                  className="sl min-h-[36px] whitespace-nowrap rounded-full border border-line bg-surface px-3.5 text-[13px] font-medium text-ink-2 transition-transform duration-150 ease-out active:scale-[0.97]">
                  {s}
                </button>
              </li>
            ))}
          </ul>
        )}

        <form onSubmit={onSubmit}
          className="flex items-end gap-2 rounded-[20px] border border-ctl bg-surface p-1.5 transition-colors focus-within:border-accent hover:border-ink-3">
          <div className="hidden shrink-0 self-center pl-1 sm:block" aria-hidden>
            <Suspense fallback={<div style={{ width: 40, aspectRatio: "300 / 360" }} />}>
              <Prudie
                size={40} state={prudieStateFor(phase)} followPointer={false} idleEvery={[10, 16]} greeting="" bubble="top"
                onSettle={(finished) => { if (finished === "thumbsup") setDone(false); }}
              />
            </Suspense>
          </div>
          <textarea
            ref={input}
            rows={1}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(draft); } }}
            name="assistant-message"
            autoComplete="off"
            aria-label={plan ? "Ask Prudie to change your plan" : "Describe the plan you want"}
            placeholder={plan ? "Ask Prudie to change your plan" : "Describe a plan, for example 5 lakh for 5 years, moderate risk"}
            className="max-h-32 min-h-[44px] min-w-0 flex-1 resize-none bg-transparent px-2 py-2.5 text-[15px] leading-6 outline-none placeholder:text-ink-3"
          />
          <button type="button" onClick={() => setSheetOpen(true)} aria-label="Open conversation history"
            className="sl flex size-[44px] shrink-0 items-center justify-center rounded-full text-ink-2">
            <ChatCircleDotsIcon size={22} aria-hidden />
          </button>
          <SendButton disabled={!draft.trim() || pending} />
        </form>
      </div>
    </div>
  );
}

/** The whole conversation, with its plan cards, over the page. It never pushes the layout; Escape or a tap outside closes it. */
export function AssistantSheet() {
  const t = useT();
  const open = useAssistant((s) => s.sheetOpen);
  const setOpen = useAssistant((s) => s.setSheetOpen);
  const closeBtn = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    closeBtn.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("keydown", onKey); previous?.focus?.(); };
  }, [open, setOpen]);

  if (!open) return null;
  return (
    <div className="sheet-scrim fixed inset-0 z-50 flex justify-end bg-black/40" onClick={() => setOpen(false)}>
      <div
        role="dialog" aria-modal="true" aria-label={t("chat")}
        className={clsx("sheet-panel flex h-full w-[min(440px,100vw)] flex-col gap-3 bg-surface p-4 pb-[max(1rem,env(safe-area-inset-bottom,0px))] shadow-[-8px_0_32px_rgba(0,0,0,0.25)] sm:rounded-l-[20px]")}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-[18px] leading-6">{t("chat")}</h2>
          <button ref={closeBtn} type="button" aria-label={t("chatClose")} onClick={() => setOpen(false)}
            className="sl flex size-[44px] items-center justify-center rounded-full bg-rail text-ink">
            <XIcon size={18} aria-hidden />
          </button>
        </div>
        <Conversation variant="sheet" />
      </div>
    </div>
  );
}
