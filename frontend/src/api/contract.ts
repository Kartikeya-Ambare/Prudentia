import type { BankOption, ChatReply, DriftCheck, PlanRequest, PlanResult, SectorAllocation } from "./types";

/** Every backend call the UI makes. `live.ts` implements it. */
export interface Api {
  health(): Promise<{ status: string }>;
  plan(request: PlanRequest): Promise<PlanResult>;
  banks(): Promise<BankOption[]>;
  sectorAllocation(fundName: string): Promise<SectorAllocation>;
  chat(message: string, profileId: string | undefined, sessionId: string): Promise<ChatReply>;
  rebalanceCheck(profileId: string): Promise<DriftCheck>;
}
