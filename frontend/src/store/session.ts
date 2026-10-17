import { create } from "zustand";
import type { AllocationExplanation, Bucket, DriftRow, PlanResult } from "@/api/types";

const BUCKETS: Bucket[] = ["stock", "mf", "bank"];
const CLASS_OF = { stock: "stocks", mf: "mf", bank: "fd" } as const;

/** Results from the chat service may predate the plan fields; fill them from what is there. */
export function asPlan(r: PlanResult | AllocationExplanation): PlanResult {
  if ("classes" in r && "split_pct" in r) return r;
  const total = r.bucket_projections.reduce((a, b) => a + b.present_value, 0) || 1;
  const split = Object.fromEntries(
    BUCKETS.map((b, i) => [b, +(((r.bucket_projections[i]?.present_value ?? 0) / total) * 100).toFixed(2)]),
  ) as Record<Bucket, number>;
  return {
    ...r, split_pct: split, classes: BUCKETS.filter((b) => split[b] > 0).map((b) => CLASS_OF[b]),
    banks_mode: "auto", data_as_of: { stocks: null, mf: null }, scenarios: null, warnings: [],
  };
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  diff?: DriftRow[];
  /** Details the chat service still needs (e.g. "risk"); drives the answer buttons. */
  missing?: string[];
  /** The plan this reply produced, shown as a card under the message. */
  allocation?: PlanResult;
}

export type Level = "beginner" | "expert";

/** Everything one mode owns. Beginner and Expert never share a plan, a conversation or a chat session. */
interface Slot {
  lastResult: PlanResult | null;
  chatHistory: ChatMessage[];
  /** The chat service keeps its conversation (and the plan it is editing) under this id. */
  sessionId: string;
}

const newId = () => (typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : String(Date.now() + Math.random()));
const emptySlot = (): Slot => ({ lastResult: null, chatHistory: [], sessionId: newId() });

function startLevel(): Level {
  try { return localStorage.getItem("prudentia-level") === "expert" ? "expert" : "beginner"; } catch { return "beginner"; }
}

/**
 * Lives for the page session only. The top-level fields (lastResult, chatHistory, sessionId) always belong to the
 * active mode, so screens read them as before; switching modes parks them in `slots` and loads the other mode's.
 */
interface SessionState extends Slot {
  activeLevel: Level;
  slots: Record<Level, Slot>;
  switchLevel: (next: Level) => void;
  /** `level` names the mode that asked; a reply that lands after a mode switch is filed under the mode that asked. */
  setLastResult: (result: PlanResult | AllocationExplanation, level?: Level) => void;
  addMessage: (message: ChatMessage, level?: Level) => void;
  /** The plan the other mode holds, shown here too. Chat history and chat session stay separate. */
  adoptPlanFromOtherMode: () => void;
}

export const useSession = create<SessionState>()((set) => {
  const first = startLevel();
  const slots: Record<Level, Slot> = { beginner: emptySlot(), expert: emptySlot() };
  return {
    ...slots[first],
    activeLevel: first,
    slots,
    switchLevel: (next) =>
      set((s) => {
        if (next === s.activeLevel) return {};
        const parked = { ...s.slots, [s.activeLevel]: { lastResult: s.lastResult, chatHistory: s.chatHistory, sessionId: s.sessionId } };
        return { activeLevel: next, slots: parked, ...parked[next] };
      }),
    setLastResult: (r, level) =>
      set((s) => {
        const plan = asPlan(r);
        if (!level || level === s.activeLevel) return { lastResult: plan };
        return { slots: { ...s.slots, [level]: { ...s.slots[level], lastResult: plan } } };
      }),
    adoptPlanFromOtherMode: () =>
      set((s) => {
        const other = s.activeLevel === "beginner" ? "expert" : "beginner";
        const plan = s.slots[other].lastResult;
        return plan ? { lastResult: plan } : {};
      }),
    addMessage: (message, level) =>
      set((s) => {
        if (!level || level === s.activeLevel) return { chatHistory: [...s.chatHistory, message] };
        const slot = s.slots[level];
        return { slots: { ...s.slots, [level]: { ...slot, chatHistory: [...slot.chatHistory, message] } } };
      }),
  };
});
