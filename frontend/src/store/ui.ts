import { create } from "zustand";
import { useSession } from "@/store/session";

export type Level = "beginner" | "expert";
const KEY = "prudentia-level";

function initial(): Level {
  try { return localStorage.getItem(KEY) === "expert" ? "expert" : "beginner"; } catch { return "beginner"; }
}

/** Beginner = chat-led. Expert = the full form. A remembered preference, not a page. */
export const useLevel = create<{ level: Level; setLevel: (l: Level) => void }>()((set) => ({
  level: initial(),
  setLevel: (level) => {
    try { localStorage.setItem(KEY, level); } catch { /* storage blocked */ }
    // Each mode keeps its own plan and conversation: park the old mode's and bring back the new one's.
    useSession.getState().switchLevel(level);
    set({ level });
  },
}));
