import { create } from "zustand";
import { api } from "@/api";
import { ApiError } from "@/api/types";
import { queryClient } from "@/lib/queryClient";
import { asPlan, useSession } from "@/store/session";

const ERR_SLOW = "Please wait a second between messages.";
const ERR_DOWN = "Chat is not reachable right now. Switch to Expert to use the form instead.";

interface AssistantState {
  /** A message is waiting for its reply. */
  pending: boolean;
  /** A reply just landed: drives Prudie's thumbs up, then the mascot resets it. */
  done: boolean;
  /** The full conversation, as a panel over the page (it never takes layout space). */
  sheetOpen: boolean;
  setSheetOpen: (open: boolean) => void;
  setDone: (done: boolean) => void;
  send: (text: string) => Promise<void>;
}

/**
 * The single place a chat message is sent, whichever part of the screen it was typed in (the start screen, the bar at the
 * bottom, the conversation panel). It adds both messages to the active mode's conversation and, when the reply carries a plan,
 * makes it the plan on screen.
 */
export const useAssistant = create<AssistantState>()((set, get) => ({
  pending: false,
  done: false,
  sheetOpen: false,
  setSheetOpen: (sheetOpen) => set({ sheetOpen }),
  setDone: (done) => set({ done }),
  send: async (text) => {
    const message = text.trim();
    if (!message || get().pending) return;
    const { activeLevel: asked, lastResult: plan, sessionId, addMessage, setLastResult } = useSession.getState();
    addMessage({ role: "user", content: message }, asked);
    set({ pending: true });
    try {
      const body = await api.chat(message, plan?.profile_id, sessionId);
      const card = body.allocation ? asPlan(body.allocation) : undefined;
      // A plan is shown as a card; if the service text is a long dump of the same numbers, use a short lead instead.
      const dump = !!card && (body.reply.length > 220 || /\n\s*[-*•]/.test(body.reply));
      addMessage({
        role: "assistant", diff: body.diff, missing: body.missing, allocation: card,
        content: dump ? (plan ? "Your plan is updated." : "Here is your plan.") : body.reply,
      }, asked);
      if (body.allocation) {
        setLastResult(body.allocation, asked);
        queryClient.invalidateQueries({ queryKey: ["drift"] });
      }
      set({ done: true });
    } catch (err) {
      addMessage({
        role: "assistant",
        content: err instanceof ApiError && err.status === 429 ? ERR_SLOW
          : err instanceof ApiError && err.status > 0 ? err.message : ERR_DOWN,
      }, asked);
    } finally {
      set({ pending: false });
    }
  },
}));
