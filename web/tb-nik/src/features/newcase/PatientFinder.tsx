// The lookup box of the New Case File page with a drop-down (docs/new-case/DESIGN.md N1). One box, two ways: a number (UHID, IP / OP
// No., ABHA) and Look up work exactly as before; 2 or more letters (or 4 or more digits, a part of a number) open, after 250 ms, a
// list of the 8 best matches from GET /his/find: name, age / sex, UHID, last visit, a "Has a Case File" badge, and for a word match
// the matched words in context. Picking a row puts its UHID in the box and runs the same lookup as Look up. An accessible combobox:
// arrow keys move, Enter picks the highlighted row (with none highlighted, Enter is Look up as before), Escape closes.
// A Case File the person may not open comes without its id, cancer or status: the badge says only "A Case File exists (department)".
// `off` (the Vaidyx admin, who reads patients only through break-glass): no search is sent; the page says why.
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { CornerDownLeft, FolderOpen, Loader2, PenLine, Search, Unplug } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Pill } from "@/components/StatusPill";
import { Highlight } from "@/components/Highlight";
import { useDebounce } from "@/hooks/useDebounce";
import { api, ApiError } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import { ageSex, formatDate } from "@/lib/format";
import type { HisFind, HisFindRow } from "@/lib/types";
import { cn } from "@/lib/utils";

const DEBOUNCE_MS = 250;

/** The drop-down opens for 2 or more letters, or 4 or more digits (a part of a number such as "4219"). */
export function wantsFind(q: string): boolean {
  const s = q.trim();
  return (s.match(/\p{L}/gu)?.length ?? 0) >= 2 || (s.match(/\d/g)?.length ?? 0) >= 4;
}

/** `text` in pieces with every word that starts with one of `terms` marked (case does not matter). */
function marked(text: string, terms: string[]): Array<{ text: string; hit: boolean }> {
  const ts = [...new Set(terms.map((t) => t.toLowerCase().trim()).filter((t) => t.length >= 2))];
  if (!text || !ts.length) return [{ text, hit: false }];
  const low = text.toLowerCase();
  const marks = new Array<boolean>(text.length).fill(false);
  for (const t of ts) {
    let i = low.indexOf(t);
    while (i >= 0) {
      if (i === 0 || !/[\p{L}\p{N}]/u.test(low[i - 1])) for (let k = i; k < i + t.length; k++) marks[k] = true;
      i = low.indexOf(t, i + 1);
    }
  }
  const out: Array<{ text: string; hit: boolean }> = [];
  let start = 0;
  for (let i = 1; i <= text.length; i++) {
    if (i === text.length || marks[i] !== marks[start]) { out.push({ text: text.slice(start, i), hit: marks[start] }); start = i; }
  }
  return out;
}

function Marked({ text, terms, className }: { text: string; terms: string[]; className?: string }) {
  return (
    <span className={className}>
      {marked(text, terms).map((p, i) => (p.hit ? <mark key={i} className="rounded-[3px] bg-primary/20 px-0.5 text-inherit">{p.text}</mark> : <span key={i}>{p.text}</span>))}
    </span>
  );
}

function pickable(r: HisFindRow): boolean {
  return Boolean(r.uhid);
}

export function PatientFinder({ value, onValueChange, onPick, onManual, off, id, placeholder, ...aria }: {
  value: string;
  onValueChange: (v: string) => void;
  /** A row was picked: the caller puts its UHID in the box and runs the lookup. */
  onPick: (row: HisFindRow) => void;
  /** "Make it by hand" from the empty list. */
  onManual?: () => void;
  /** Why this person may not search: no request is sent and the list stays closed (the page shows the reason). */
  off?: string;
  id?: string;
  placeholder?: string;
  "aria-describedby"?: string;
  "aria-invalid"?: boolean;
}) {
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [armed, setArmed] = useState(false);  // the person typed since the last pick (a picked UHID never reopens the list)
  const [active, setActive] = useState(-1);
  const q = useDebounce(value.trim(), DEBOUNCE_MS);
  const want = armed && wantsFind(q) && !off;
  const find = useQuery<HisFind, Error>({
    queryKey: ["his-find", q],
    queryFn: ({ signal }) => api.get<HisFind>(`${EP.hisFind}?q=${encodeURIComponent(q)}`, { signal }),
    enabled: want,
    staleTime: 30_000,
    retry: false,
    placeholderData: keepPreviousData,
  });
  const rows = useMemo(() => (want ? find.data?.results ?? [] : []), [want, find.data]);
  // a number opens the list only when something matches, so the list never covers Look up (below the box on a phone) for a plain number
  const shown = open && armed && wantsFind(value) && (!/\d/.test(value) || rows.length > 0) && !off;
  const waiting = value.trim() !== q || (find.isFetching && !find.data);
  const words = useMemo(() => q.toLowerCase().split(/\s+/).filter(Boolean), [q]);
  useEffect(() => { setActive(-1); }, [q]);

  const pick = (r: HisFindRow) => {
    if (!pickable(r)) return;
    setOpen(false);
    setArmed(false);
    setActive(-1);
    onPick(r);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      if (!rows.length) return;
      e.preventDefault();
      setOpen(true);
      setActive((a) => Math.min(rows.length - 1, a + 1));
    } else if (e.key === "ArrowUp") {
      if (!shown) return;
      e.preventDefault();
      setActive((a) => Math.max(-1, a - 1));
    } else if (e.key === "Enter") {
      if (shown && active >= 0 && rows[active]) {
        e.preventDefault();  // the highlighted row, not the form's Look up
        pick(rows[active]);
      } else {
        setOpen(false);
      }
    } else if (e.key === "Escape") {
      if (shown) { e.preventDefault(); setOpen(false); setActive(-1); }
    }
  };

  const optionId = (i: number) => `${listId}-opt-${i}`;
  const src = find.data?.sources;

  return (
    <div className="relative">
      <Input
        ref={inputRef}
        id={id}
        value={value}
        onChange={(e) => { onValueChange(e.target.value); setArmed(true); setOpen(true); }}
        onFocus={() => { if (armed) setOpen(true); }}
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        className="mono"
        autoFocus
        autoComplete="off"
        spellCheck={false}
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={shown}
        aria-controls={listId}
        aria-activedescendant={shown && active >= 0 ? optionId(active) : undefined}
        aria-describedby={aria["aria-describedby"]}
        aria-invalid={aria["aria-invalid"]}
      />
      {shown && find.isFetching ? <Loader2 className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 animate-spin text-muted-foreground" aria-hidden /> : null}
      <div
        className={cn("absolute left-0 right-0 top-full z-40 mt-1.5 overflow-hidden rounded-xl border border-border bg-popover text-popover-foreground shadow-[var(--shadow-lift)]", !shown && "hidden")}
        data-testid="patient-finder"
      >
        <ul id={listId} role="listbox" aria-label="Patients found" className="scroll-thin max-h-[min(60vh,460px)] overflow-auto p-1.5">
          {rows.map((r, i) => {
            const can = pickable(r);
            const terms = r.matched.on === "words" ? r.matched.terms ?? [] : r.matched.on === "name" ? words : [];
            return (
              <li
                key={`${r.uhid || r.case_files[0]?.case_id || r.name}-${i}`}
                id={optionId(i)}
                role="option"
                aria-selected={i === active}
                aria-disabled={!can || undefined}
                onMouseDown={(e) => e.preventDefault()}
                onMouseEnter={() => setActive(i)}
                onClick={() => pick(r)}
                className={cn("flex items-start gap-2.5 rounded-md px-2 py-2 text-sm", can ? "cursor-pointer" : "cursor-default opacity-80", i === active && "bg-accent")}
              >
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                    <Marked text={r.name || "Name not recorded"} terms={terms} className="font-semibold text-foreground" />
                    {ageSex(r.age, r.sex) ? <span className="text-xs text-muted-foreground">{ageSex(r.age, r.sex)}</span> : null}
                    {r.uhid ? <span className="mono text-xs text-muted-foreground">{r.matched.on === "identifier" ? <Highlight text={r.uhid} q={q.replace(/\s+/g, "")} /> : r.uhid}</span> : null}
                  </span>
                  <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                    {r.last_visit ? <span>Last visit: {[r.last_visit.department, formatDate(r.last_visit.date)].filter(Boolean).join(", ")}</span> : null}
                    {r.matched.on === "identifier" && r.matched.snippet && r.matched.snippet !== r.uhid ? <span>Number: <span className="mono">{r.matched.snippet}</span></span> : null}
                    {!r.uhid ? <span>No hospital number: open its Case File from Case Files</span> : null}
                    {r.case_files.map((f, k) => (f.case_id ? (
                      <Pill key={f.case_id} tone="info" icon={FolderOpen} title={[f.cancer, f.status].filter(Boolean).join(", ")}>Has a Case File: {f.case_id}{f.department ? `, ${f.department}` : ""}</Pill>
                    ) : (
                      <Pill key={`exists-${k}`} tone="neutral" icon={FolderOpen} title="You cannot open this Case File; ask its department to join">A Case File exists{f.department ? ` (${f.department})` : ""}</Pill>
                    )))}
                  </span>
                  {r.matched.on === "words" && r.matched.snippet ? (
                    <span className="mt-1 block text-xs text-body">
                      <Marked text={r.matched.snippet} terms={r.matched.terms ?? []} />
                      {r.matched.source ? <span className="text-muted-foreground"> ({r.matched.source})</span> : null}
                    </span>
                  ) : null}
                </span>
                {can ? <CornerDownLeft className="mt-1 hidden size-3.5 shrink-0 text-muted-foreground sm:block" aria-hidden /> : null}
              </li>
            );
          })}
        </ul>
        {waiting && !rows.length ? (
          <p className="flex items-center gap-2 px-3.5 pb-3 text-sm text-muted-foreground" role="status"><Search className="size-4" aria-hidden /> Searching</p>
        ) : find.error && !rows.length ? (
          <p className="px-3.5 pb-3 text-sm text-muted-foreground" role="status">
            {find.error instanceof ApiError && (find.error.status === 403 || find.error.status === 429) && find.error.message ? find.error.message : "The search did not answer. Type the UHID and press Look up."}
          </p>
        ) : find.data && !rows.length ? (
          <div className="grid gap-2 px-3.5 pb-3 text-sm" role="status">
            <p className="text-muted-foreground">No patient matches '{q}'. Try the UHID, or make it by hand.</p>
            {onManual ? (
              <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => { setOpen(false); onManual(); }} className="inline-flex w-fit items-center gap-1.5 font-medium text-primary underline-offset-4 hover:underline">
                <PenLine className="size-4" aria-hidden /> Make it by hand
              </button>
            ) : null}
          </div>
        ) : null}
        {src && (!src.his_live || (src.index.building && !src.index.patients)) && find.data ? (
          <div className="grid gap-1 border-t border-border px-3.5 py-2 text-xs text-muted-foreground" role="status">
            {!src.his_live ? <p className="flex items-center gap-1.5"><Unplug className="size-3.5 shrink-0" aria-hidden /> The hospital system is not connected or did not answer. Showing Case Files only.</p> : null}
            {src.his_live && src.index.building && !src.index.patients ? <p className="flex items-center gap-1.5"><Loader2 className="size-3.5 shrink-0 animate-spin" aria-hidden /> Still reading the hospital's records; names already work.</p> : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
