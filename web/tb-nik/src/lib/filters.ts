// The Case File list filters: the query keys the server understands (GET /case-list) and the same matching done on the
// client, so a chip reacts at once and the list stays right when the server ignores a key.
import type { CaseListItem, CaseListFilters, FilterOption, SavedFilter } from "@/lib/types";
import { parseDate } from "@/lib/format";

export type FilterKey = "q" | "from" | "to" | "owner" | "department" | "organ" | "imaging" | "urgency" | "status" | "board_from" | "board_to" | "mine";

export type FilterQuery = Partial<Record<FilterKey, string>>;

export const FILTER_KEYS: FilterKey[] = ["q", "from", "to", "owner", "department", "organ", "imaging", "urgency", "status", "board_from", "board_to", "mine"];

/** Chip order and plain labels. */
export const FILTER_LABELS: Record<FilterKey, string> = {
  q: "Search",
  from: "Created from",
  to: "Created to",
  owner: "Treated by",
  department: "Department",
  organ: "Cancer",
  imaging: "Imaging",
  urgency: "Urgency",
  status: "Status",
  board_from: "Board from",
  board_to: "Board to",
  mine: "Mine only",
};

export const STATUS_WORDS: Record<string, string> = {
  needs_me: "Needs you",
  waiting_department: "Waiting on a department",
  ready: "Ready for the board",
  scheduled: "Scheduled",
  decided: "Decided",
  archived: "Archived",
  draft: "Reading records",
  quiet: "Nothing open",
};

export const URGENCY_CHOICES: Array<{ value: string; label: string }> = [
  { value: "5", label: "5, most urgent" },
  { value: "4", label: "4" },
  { value: "high", label: "4 and 5" },
  { value: "3", label: "3" },
  { value: "2", label: "2" },
  { value: "1", label: "1, least urgent" },
  { value: "none", label: "Not set" },
];

export function parseQuery(sp: URLSearchParams): FilterQuery {
  const q: FilterQuery = {};
  for (const k of FILTER_KEYS) {
    const v = sp.get(k);
    if (v) q[k] = v;
  }
  return q;
}

export function toSearchParams(q: FilterQuery): URLSearchParams {
  const sp = new URLSearchParams();
  for (const k of FILTER_KEYS) {
    const v = q[k];
    if (v) sp.set(k, v);
  }
  return sp;
}

export function queryString(q: FilterQuery): string {
  const s = toSearchParams(q).toString();
  return s ? `?${s}` : "";
}

export function activeKeys(q: FilterQuery): FilterKey[] {
  return FILTER_KEYS.filter((k) => Boolean(q[k]));
}

export function sameQuery(a: FilterQuery, b: FilterQuery): boolean {
  return FILTER_KEYS.every((k) => (a[k] || "") === (b[k] || ""));
}

export function optionId(o: FilterOption): string {
  if (typeof o === "string") return o;
  return "id" in o ? o.id : o.key;
}
export function optionLabel(o: FilterOption): string {
  return typeof o === "string" ? o : o.label || optionId(o);
}

/** The words shown on an active chip, e.g. "Status: Ready for the board". */
export function describeValue(key: FilterKey, value: string, filters?: CaseListFilters): string {
  const find = (list?: FilterOption[]) => list?.find((o) => optionId(o) === value);
  switch (key) {
    case "status": return STATUS_WORDS[value] || optionLabel(find(filters?.statuses) ?? value);
    case "urgency": return URGENCY_CHOICES.find((c) => c.value === value)?.label ?? value;
    case "imaging": return value === "yes" ? "present" : "not yet";
    case "mine": return "on";
    case "owner": return optionLabel(find(filters?.owners) ?? value);
    case "department": return optionLabel(find(filters?.departments) ?? value);
    case "organ": return optionLabel(find(filters?.organs) ?? value);
    default: return value;
  }
}

function within(value: string | null | undefined, from?: string, to?: string): boolean {
  if (!from && !to) return true;
  const d = parseDate(value);
  if (!d) return false;
  const f = parseDate(from);
  const t = parseDate(to);
  if (f && d < f) return false;
  if (t) {
    const end = new Date(t.getFullYear(), t.getMonth(), t.getDate(), 23, 59, 59);
    if (d > end) return false;
  }
  return true;
}

function text(c: CaseListItem): string {
  return [c.patient?.name, c.patient?.uhid, c.patient?.agesex, c.protocol_label, c.cancer_name, c.owner?.doctor_name, c.owner?.department_label, c.case_id, c.status?.label]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

/** The same matches the server makes; `user` is the signed-in login for "mine". */
export function applyFilters(cases: CaseListItem[], q: FilterQuery, user?: string): CaseListItem[] {
  const needle = (q.q || "").trim().toLowerCase();
  return cases.filter((c) => {
    if (needle && !text(c).includes(needle)) return false;
    if (!within(c.created, q.from, q.to)) return false;
    if (q.owner && c.owner?.doctor !== q.owner && c.owner?.doctor_name !== q.owner) return false;
    if (q.department && c.owner?.department !== q.department) return false;
    if (q.organ && c.protocol !== q.organ && (c.cancer_name || "").toLowerCase() !== q.organ.toLowerCase()) return false;
    if (q.imaging === "yes" && !c.imaging_present) return false;
    if (q.imaging === "no" && c.imaging_present) return false;
    if (q.urgency) {
      const lvl = c.urgency?.level ?? null;
      if (q.urgency === "high" && !(lvl === 4 || lvl === 5)) return false;
      if (q.urgency === "none" && lvl !== null) return false;
      if (/^[1-5]$/.test(q.urgency) && lvl !== Number(q.urgency)) return false;
    }
    if (q.status && c.status?.key !== q.status) return false;
    if (!within(c.board_date, q.board_from, q.board_to)) return false;
    if (q.mine === "1" && user && !(c.mine ?? c.owner?.doctor === user)) return false;
    return true;
  });
}

/** Saved filters live in the profile (saved_filters). Names are unique; saving the same name replaces. */
export function upsertSaved(list: SavedFilter[], name: string, query: FilterQuery): SavedFilter[] {
  const clean: Record<string, string> = {};
  for (const k of activeKeys(query)) clean[k] = query[k] as string;
  const others = list.filter((f) => f.name !== name);
  return [...others, { name, query: clean }];
}

export function removeSaved(list: SavedFilter[], name: string): SavedFilter[] {
  return list.filter((f) => f.name !== name);
}

export function findSaved(list: SavedFilter[], query: FilterQuery): SavedFilter | undefined {
  return list.find((f) => sameQuery(f.query as FilterQuery, query));
}

/** Newest first: created, then last change. */
export function sortNewest(cases: CaseListItem[]): CaseListItem[] {
  return [...cases].sort((a, b) => (parseDate(b.created)?.getTime() ?? 0) - (parseDate(a.created)?.getTime() ?? 0));
}
