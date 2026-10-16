import type { Api } from "./contract";
import { ApiError, type AllocationExplanation, type ChatReply, type InstrumentWeight, type ValueProjection } from "./types";

// Calls go to /api/..., which the dev server (or the production reverse proxy) forwards to FastAPI.
// Set VITE_API_BASE to a full backend URL instead if there is no proxy (the backend then needs CORS).
const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api";

// The chat service (chat-service) is a separate FastAPI app; the dev server forwards /chat-api -> its /api.
const CHAT_BASE = (import.meta.env.VITE_CHAT_BASE as string | undefined) ?? "/chat-api";

async function request<T>(path: string, init?: RequestInit, base: string = BASE): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${base}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(0, "Cannot reach the Prudentia backend. Check that it is running on the address in VITE_API_URL.");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

/** Allocation result as the chat service returns it (see chat-service/chat_service/schemas.py). */
interface ChatEngineResult {
  profile_id: string;
  amount: number;
  years: number;
  risk_score: number;
  buckets: Record<"stock" | "mf" | "bank", { weight_pct: number; amount: number }>;
  instruments: (InstrumentWeight & { projected_value?: number })[];
  expected_return_pct?: number;
  expected_volatility_pct?: number;
  explanation_text?: string;
  backend?: AllocationExplanation; // present when the engine is the real backend: use its own numbers
}
interface ChatServiceReply {
  reply: string;
  intent: string;
  result?: ChatEngineResult;
  blocked?: boolean;
  category?: string;
  missing?: string[];
}

const BUCKET_LABEL = { stock: "Stocks", mf: "Mutual Funds", bank: "Bank/FD" } as const;

function toAllocation(r: ChatEngineResult): AllocationExplanation {
  if (r.backend) return r.backend;
  const proj = (label: string, pv: number, fv: number | undefined): ValueProjection => ({
    label, present_value: pv, projected_value: fv ?? pv,
    projected_return_pct: pv > 0 && fv ? (Math.pow(fv / pv, 1 / r.years) - 1) * 100 : 0, horizon_years: r.years,
  });
  const byBucket = (b: string) => r.instruments.filter((i) => i.bucket === b);
  return {
    profile_id: r.profile_id, mode: "naive", risk_thermometer: r.risk_score, horizon_years: r.years,
    weights: r.instruments.map(({ label, display_name, bucket, weight_pct, amount }) => ({ label, display_name, bucket, weight_pct, amount })),
    expected_return_pct: r.expected_return_pct ?? 0, expected_volatility_pct: r.expected_volatility_pct ?? 0,
    explanation_text: r.explanation_text ?? "",
    bucket_projections: (["stock", "mf", "bank"] as const).map((b) =>
      proj(BUCKET_LABEL[b], r.buckets[b].amount, byBucket(b).reduce((a, i) => a + (i.projected_value ?? 0), 0) || undefined)),
    instrument_projections: r.instruments.map((i) => proj(i.display_name, i.amount, i.projected_value)),
    banks_selected: byBucket("bank").map(({ label, display_name, bucket, weight_pct, amount }) => ({ label, display_name, bucket, weight_pct, amount })),
  };
}

const post = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });
const enc = encodeURIComponent;

export const liveApi: Api = {
  health: () => request("/health"),
  plan: (req) => request("/plan", post(req)),
  banks: () => request("/banks"),
  sectorAllocation: (fund) => request(`/mutual-funds/${enc(fund)}/sector-allocation`),
  chat: async (message, profileId, sessionId): Promise<ChatReply> => {
    const r = await request<ChatServiceReply>(
      "/chat", post({ session_id: sessionId, message, profile_id: profileId ?? null }), CHAT_BASE);
    return {
      reply: r.reply, intent: r.intent, blocked: r.blocked, category: r.category, missing: r.missing,
      allocation: r.result ? toAllocation(r.result) : undefined,
    };
  },
  rebalanceCheck: (profileId) => request(`/rebalance-check/${enc(profileId)}`),
};
