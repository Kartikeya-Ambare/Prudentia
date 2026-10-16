/** Mirrors backend shared/schemas/models.py. Keep in sync with the FastAPI contract. */

export type Mode = "naive" | "knowledgeable";
export type Bucket = "stock" | "mf" | "bank";
export type McCategory = "Large Cap" | "Mid Cap" | "Small Cap";

export interface UserProfile {
  profile_id?: string | null;
  mode: Mode;
  capital: number;
  risk_thermometer: number;
  horizon_years: number;
  sector_pref: string[];
  mf_category_pref: McCategory[];
}

export interface InstrumentWeight {
  label: string;
  display_name: string;
  bucket: Bucket;
  weight_pct: number;
  amount: number;
}

export interface ValueProjection {
  label: string;
  present_value: number;
  projected_value: number;
  projected_return_pct: number;
  horizon_years: number;
}

export interface AllocationExplanation {
  profile_id: string;
  mode: Mode;
  risk_thermometer: number;
  horizon_years: number;
  weights: InstrumentWeight[];
  expected_return_pct: number;
  expected_volatility_pct: number;
  explanation_text: string;
  bucket_projections: ValueProjection[];
  instrument_projections: ValueProjection[];
  banks_selected: InstrumentWeight[];
}

/** Asset classes a plan can hold. Each maps to a bucket: stocks→stock, mf→mf, fd→bank. */
export type AssetClass = "stocks" | "mf" | "fd";

export interface PlanRequest {
  profile_id?: string | null;
  capital: number;
  horizon_years: number;
  /** The risk % the user can afford, 0–100. */
  risk_thermometer: number;
  classes?: AssetClass[];
  sector_pref?: string[];
  mf_category_pref?: McCategory[];
  banks?: "auto" | string[];
  /** Percent per chosen class, must cover exactly the chosen classes and add up to 100. */
  manual_split?: Partial<Record<AssetClass, number>>;
}
export type PlanPatch = Partial<Omit<PlanRequest, "profile_id">> & { manual_split?: PlanRequest["manual_split"] | null };

export interface Scenario { projected_value: number; return_pct: number }
export interface PlanResult extends AllocationExplanation {
  classes: AssetClass[];
  split_pct: Record<Bucket, number>;
  banks_mode: "auto" | "custom";
  data_as_of: { stocks: string | null; mf: string | null };
  scenarios: Partial<Record<"bear" | "base" | "bull", Scenario>> | null;
  warnings: string[];
  /** The request the plan was built from (capital as typed, before any rounding by the engine). */
  plan_request?: { capital?: number };
}


export interface BankOption {
  id: string; display_name: string; tier: string; category: string; rate_pct: number;
}

export interface SectorAllocation {
  scheme_code: string;
  date: string;
  sector_json: Record<string, number>;
  source_url: string;
  fetched_at: string;
}

export interface DriftRow {
  bucket: string;
  before: number;
  after: number;
  delta: number;
}

export interface DriftCheck {
  found: boolean;
  drifted: boolean;
  diff: DriftRow[];
  checked_at: string;
  stored_updated_at: string;
}

export interface ChatReply {
  reply: string;
  /** Chat service fields (live mode). */
  intent?: string;
  blocked?: boolean;
  category?: string;
  missing?: string[];
  diff?: DriftRow[];
  allocation?: PlanResult | AllocationExplanation;
  sector_json?: Record<string, number>;
  source_url?: string;
  date?: string;
}

/** Thrown for any non-2xx response; the UI shows `message` verbatim. */
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}
