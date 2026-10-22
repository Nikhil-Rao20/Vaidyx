// The guided Case File's own calls (tumour_board/api/steps.py); everything else goes through ../api.
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { caseUrl } from "../api";
import type { Steps } from "./types";

const enc = encodeURIComponent;

export const getSteps = (id: string) => api.get<Steps>(`${caseUrl(id)}/steps`);
export const putReason = (id: string, value: string) => api.put<{ value: string; label: string }>(`${caseUrl(id)}/reason`, { value });
export const postKeyCheck = (id: string, body: { fact_id: string; value: string; doc_id: string }) => api.post(`${caseUrl(id)}/key-checks`, body);
export const deleteKeyCheck = (id: string, factId: string) => api.del(`${caseUrl(id)}/key-checks/${enc(factId)}`);
export const dismissWarning = (id: string, key: string) => api.post(`${caseUrl(id)}/warnings/${enc(key)}/dismiss`, {});
export const changeListing = (id: string, body: { protocol: string; setting?: string }) => api.post<{ job: string; total: number }>(`${caseUrl(id)}/listing`, body);

/** The guided view; refetched with the Case File (the page invalidates ["steps", id] after every action). */
export function useSteps(id: string, enabled = true) {
  return useQuery({ queryKey: ["steps", id], queryFn: () => getSteps(id), enabled, retry: false, refetchInterval: 30_000, refetchIntervalInBackground: false });
}
