// The Case File list filters: the query keys the server understands (GET /case-list) and the same matching done on the
// client, so the list reacts at once. List-valued keys (status, organ, owner, department, urgency) hold comma-separated values.
// The built-in views (All, Mine, Needs me, ...) are query presets; a saved view is a named query in the profile.
import type { CaseListItem, CaseListFilters, FilterOption, SavedFilter } from "@/lib/types";
import { parseDate } from "@/lib/format";
import { matches } from "@/lib/search";

export type FilterKey = "q" | "from" | "to" | "owner" | "department" | "organ" | "imaging" | "urgency" | "status" | "board_from" | "board_to" | "mine";

export type FilterQuery = Partial<Record<FilterKey, string>>;

export const FILTER_KEYS: FilterKey[] = ["q", "from", "to", "owner", "department", "organ", "imaging", "urgency", "status", "board_from", "board_to", "mine"];
export const LIST_KEYS: FilterKey[] = ["status", "organ", "owner", "department", "urgency"];

/** Plain labels. */
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
  { value: "4", label: "4, urgent" },
  { value: "3", label: "3" },
  { value: "2", label: "2" },
  { value: "1", label: "1, least urgent" },
  { value: "none", label: "Not set" },
];

export type SortKey = "newest" | "board" | "urgency" | "name" | "changed";
export const SORT_CHOICES: Array<{ value: SortKey; label: string }> = [
  { value: "newest", label: "Newest first" },
  { value: "changed", label: "Last changed" },
  { value: "board", label: "Board date" },
  { value: "urgency", label: "Most urgent" },
  { value: "name", label: "Patient name" },
];

/** The built-in views: a preset query each; counts come from the unfiltered list. */
export interface View { id: string; label: string; query: FilterQuery; hint?: string }
export const VIEWS: View[] = [
  { id: "all", label: "All", query: {} },
  { id: "mine", label: "Mine", query: { mine: "1" }, hint: "Case Files I own or am on" },
  { id: "needs_me", label: "Needs me", query: { status: "needs_me" }, hint: "A step is waiting for me" },
  { id: "waiting", label: "Waiting", query: { status: "waiting_department" }, hint: "A department has an open request" },
  { id: "ready", label: "Ready", query: { status: "ready" }, hint: "Marked ready for the board" },
  { id: "scheduled", label: "On the agenda", query: { status: "scheduled" } },
  { id: "decided", label: "Decided", query: { status: "decided" } },
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

/** The filters other than the typed search. */
export function filterKeys(q: FilterQuery): FilterKey[] {
  return activeKeys(q).filter((k) => k !== "q");
}

export function sameQuery(a: FilterQuery, b: FilterQuery): boolean {
  return FILTER_KEYS.every((k) => (a[k] || "") === (b[k] || ""));
}

export function listOf(q: FilterQuery, k: FilterKey): string[] {
  return (q[k] || "").split(",").map((s) => s.trim()).filter(Boolean);
}

export function withList(q: FilterQuery, k: FilterKey, values: string[]): FilterQuery {
  const next = { ...q };
  if (values.length) next[k] = values.join(",");
  else delete next[k];
  return next;
}

export function toggleIn(q: FilterQuery, k: FilterKey, value: string): FilterQuery {
  const cur = listOf(q, k);
  return withList(q, k, cur.includes(value) ? cur.filter((v) => v !== value) : [...cur, value]);
}

export function optionId(o: FilterOption): string {
  if (typeof o === "string") return o;
  return "id" in o ? o.id : o.key;
}
export function optionLabel(o: FilterOption): string {
  return typeof o === "string" ? o : o.label || optionId(o);
}

/** The words shown for one value, e.g. "Ready for the board". */
export function describeOne(key: FilterKey, value: string, filters?: CaseListFilters): string {
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

/** The words shown on an active filter token, e.g. "Status: Ready for the board, Scheduled". */
export function describeValue(key: FilterKey, value: string, filters?: CaseListFilters): string {
  if (LIST_KEYS.includes(key)) return value.split(",").filter(Boolean).map((v) => describeOne(key, v, filters)).join(", ");
  return describeOne(key, value, filters);
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

function urgencyMatches(level: number | null, wanted: string[]): boolean {
  return wanted.some((w) => (w === "high" ? level === 4 || level === 5 : w === "none" ? level === null : /^[1-5]$/.test(w) && level === Number(w)));
}

/** The same matches the server makes; `user` is the signed-in login for "mine". */
export function applyFilters(cases: CaseListItem[], q: FilterQuery, user?: string): CaseListItem[] {
  const needle = (q.q || "").trim();
  const status = listOf(q, "status"), organ = listOf(q, "organ"), owner = listOf(q, "owner"), dept = listOf(q, "department"), urg = listOf(q, "urgency");
  return cases.filter((c) => {
    if (needle && !matches(c, needle)) return false;
    if (!within(c.created, q.from, q.to)) return false;
    if (owner.length && !owner.includes(c.owner?.doctor) && !owner.includes(c.owner?.doctor_name)) return false;
    if (dept.length && !dept.includes(c.owner?.department)) return false;
    if (organ.length && !organ.includes(c.protocol || "") && !organ.map((o) => o.toLowerCase()).includes((c.cancer_name || "").toLowerCase())) return false;
    if (q.imaging === "yes" && !c.imaging_present) return false;
    if (q.imaging === "no" && c.imaging_present) return false;
    if (urg.length && !urgencyMatches(c.urgency?.level ?? null, urg)) return false;
    if (status.length && !status.includes(c.status?.key)) return false;
    if (!within(c.board_date, q.board_from, q.board_to)) return false;
    if (q.mine === "1" && (isLinkedOnly(c) || (user && !(c.mine ?? c.owner?.doctor === user)))) return false;
    return true;
  });
}

/** Another department's Case File seen only because it is linked to one of the person's own (night-v3 item 1.3). */
export function isLinkedOnly(c: CaseListItem): boolean {
  return Boolean(c.linked_only) || c.relation === "linked";
}

/** The person's own list: every row but the linked-only ones, which no view or count includes. */
export function ownRows(cases: CaseListItem[]): CaseListItem[] {
  return cases.filter((c) => !isLinkedOnly(c));
}

/** The rows in their order, then the linked-only ones at the end (listed apart, under their own heading). */
export function linkedLast(cases: CaseListItem[]): CaseListItem[] {
  return [...ownRows(cases), ...cases.filter(isLinkedOnly)];
}

/** Saved views live in the profile (saved_filters). Names are unique; saving the same name replaces. */
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

export function sortCases(cases: CaseListItem[], sort: SortKey): CaseListItem[] {
  const t = (v?: string | null) => parseDate(v)?.getTime() ?? 0;
  const list = sortNewest(cases);
  switch (sort) {
    case "changed": return list.sort((a, b) => t(b.last_change || b.created) - t(a.last_change || a.created));
    case "board": return list.sort((a, b) => (t(a.board_date) || Infinity) - (t(b.board_date) || Infinity));
    case "urgency": return list.sort((a, b) => (b.urgency?.level ?? 0) - (a.urgency?.level ?? 0));
    case "name": return list.sort((a, b) => (a.patient?.name || "").localeCompare(b.patient?.name || ""));
    default: return list;
  }
}
