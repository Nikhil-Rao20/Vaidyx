// The draft stage and the staging book (tumour_board/api/staging.py; owner decision 22 Oct 2026, docs/staging/DECISION.md).
import { useQuery } from "@tanstack/react-query";
import { TB, api } from "@/lib/api";
import { caseUrl } from "../api";

const enc = encodeURIComponent;

export interface Criterion { cat: string; group?: string; text: string; page: number; find: string; feature?: boolean }
export interface Quote { doc_id: string; doc_title: string; quote: string; page?: number | null; date?: string | null; final?: boolean }
export interface Component {
  cat: string; group: string; criterion: Criterion; quotes: Quote[]; how: string; size_mm?: number; note?: string;
  entered?: { by?: string; by_name?: string; at?: string; reason?: string };
}
export interface Draft {
  status: "staged" | "cannot_stage"; stage: string | null; row: { T: string[]; N: string[]; M: string[]; stage: string; find?: string } | null;
  components: Partial<Record<"T" | "N" | "M", Component>>; missing: string[]; rules: string; system: string; at: string; by: string; model?: string;
  confirmed: { by: string; by_name?: string; at: string; note?: string } | null; rejected: { by: string; by_name?: string; at: string; reason: string } | null;
}
export interface Written { fact: string; value: string; quote: string; doc_id: string; doc_title: string; date?: string | null; page?: number | null; prefix: string; superseded: boolean; final: boolean }
export interface Book { id: string; title: string; short?: string; file: string; first_page: number; licensed?: boolean }
export interface StagingView {
  switch: { on: boolean; preview: boolean; label: string; why: string };
  draft_label: string;
  written: Written[];
  draft: Draft | null;
  comparison: { written: Written; result: "matches" | "differs" | "partial"; differences: string[] } | null;
  stale: boolean;
  book: Book | null;
  system?: string;
  label?: string;
  groups_note?: string;
  groups_ref?: { title: string; page: number; find: string } | null;
  criteria?: Record<"T" | "N" | "M", Array<{ cat: string; text: string }>> | null;
}
export interface BookMeta { id: string; title: string; pages: number; printed: number[]; first_page: number; last_page: number; aspect?: number }
export interface BookTarget { book: string; page: number; find?: string; label?: string }

export const getStaging = (id: string) => api.get<StagingView>(`${caseUrl(id)}/staging`);
export const runStaging = (id: string) => api.post<StagingView>(`${caseUrl(id)}/staging/run`, {});
export const confirmStaging = (id: string) => api.post<StagingView>(`${caseUrl(id)}/staging/confirm`, {});
export const rejectStaging = (id: string, reason: string) => api.post<StagingView>(`${caseUrl(id)}/staging/reject`, { reason });
export const enterPart = (id: string, part: string, cat: string, reason: string) => api.post<StagingView>(`${caseUrl(id)}/staging/enter`, { part, cat, reason });
export const getBook = (book: string) => api.get<BookMeta>(`${TB}/staging/books/${enc(book)}`);
export const bookPageUrl = (book: string, page: number, find?: string) => `${TB}/staging/books/${enc(book)}/pages/${page}${find ? `?find=${enc(find)}` : ""}`;

export function useStaging(id: string, enabled = true) {
  return useQuery({ queryKey: ["staging", id], queryFn: () => getStaging(id), enabled, retry: false, refetchInterval: 60_000, refetchIntervalInBackground: false });
}
