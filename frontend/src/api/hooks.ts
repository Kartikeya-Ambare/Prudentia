import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "./index";

export const useHealth = () =>
  useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 30_000, retry: false });

export const useSectorAllocation = (fundName: string | null) =>
  useQuery({
    queryKey: ["sector", fundName],
    queryFn: () => api.sectorAllocation(fundName!),
    enabled: !!fundName,
    staleTime: 5 * 60_000,
    retry: false,
  });

export const useDrift = (profileId: string | undefined) =>
  useQuery({
    queryKey: ["drift", profileId],
    queryFn: () => api.rebalanceCheck(profileId!),
    enabled: !!profileId,
    staleTime: 60_000,
    retry: false,
  });

export const useChat = () =>
  useMutation({
    mutationKey: ["chat"],
    mutationFn: (vars: { message: string; profileId?: string; sessionId: string }) =>
      api.chat(vars.message, vars.profileId, vars.sessionId),
  });

/** The plan build is the only slow step that shows the big "reading prices, picking stocks" loader; chat actions have their own small one. */
export const usePlan = () => useMutation({ mutationKey: ["plan"], mutationFn: api.plan });

export const useBanks = () => useQuery({ queryKey: ["banks"], queryFn: api.banks, staleTime: 10 * 60_000 });
