// The filters of the Case File list: one "Filter" button (with the count of filters on) opening a panel with every filter in
// sections (several values at once), the active filters as removable tokens under the toolbar, and "Save as a view".
import { useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Bookmark, Check, ListFilter, X } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { DateInput } from "@/components/DateInput";
import { cn } from "@/lib/utils";
import type { CaseListFilters, FilterOption } from "@/lib/types";
import { FILTER_LABELS, STATUS_WORDS, URGENCY_CHOICES, describeValue, filterKeys, listOf, optionId, optionLabel, toggleIn, type FilterKey, type FilterQuery } from "@/lib/filters";

const STATUS_ORDER = ["needs_me", "waiting_department", "ready", "scheduled", "decided", "draft", "archived"];

function Section({ title, children, hint }: { title: string; children: ReactNode; hint?: string }) {
  return (
    <fieldset className="min-w-0">
      <legend className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{title}</legend>
      {hint ? <p className="mb-1.5 text-xs text-muted-foreground">{hint}</p> : null}
      {children}
    </fieldset>
  );
}

function Checks({ options, selected, onToggle, name }: { options: Array<{ id: string; label: string }>; selected: string[]; onToggle: (id: string) => void; name: string }) {
  if (!options.length) return <p className="text-xs text-muted-foreground">Nothing to choose from yet.</p>;
  return (
    <ul className="grid gap-1">
      {options.map((o) => {
        const on = selected.includes(o.id);
        const id = `${name}-${o.id}`;
        return (
          <li key={o.id}>
            <label htmlFor={id} className={cn("flex cursor-pointer items-center gap-2 rounded-md px-1.5 py-1 text-sm transition-colors hover:bg-accent", on && "text-foreground")}>
              <Checkbox id={id} checked={on} onCheckedChange={() => onToggle(o.id)} />
              <span className="min-w-0 flex-1 truncate">{o.label}</span>
            </label>
          </li>
        );
      })}
    </ul>
  );
}

function Segmented<T extends string>({ value, options, onChange, label }: { value: T; options: Array<{ value: T; label: string }>; onChange: (v: T) => void; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-md bg-muted p-0.5">
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={value === o.value} onClick={() => onChange(o.value)} className={cn("rounded-[5px] px-2.5 py-1 text-xs font-medium transition-colors", value === o.value ? "bg-card text-foreground shadow-[var(--shadow-outer)]" : "text-muted-foreground hover:text-foreground")}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function FilterButton({ query, onChange, filters, organs, owners, showDepartment, showMine, onSave }: {
  query: FilterQuery;
  onChange: (q: FilterQuery) => void;
  filters?: CaseListFilters;
  organs: FilterOption[];
  owners: FilterOption[];
  showDepartment: boolean;
  showMine: boolean;
  onSave?: (name: string, q: FilterQuery) => Promise<void> | void;
}) {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState("");
  const n = filterKeys(query).length;
  const opt = (list: FilterOption[]) => list.map((o) => ({ id: optionId(o), label: optionLabel(o) }));
  const statuses = (filters?.statuses?.length ? filters.statuses.map((o) => ({ id: optionId(o), label: STATUS_WORDS[optionId(o)] || optionLabel(o) })) : STATUS_ORDER.map((k) => ({ id: k, label: STATUS_WORDS[k] })))
    .sort((a, b) => STATUS_ORDER.indexOf(a.id) - STATUS_ORDER.indexOf(b.id));
  const urg = listOf(query, "urgency");
  const set = (k: FilterKey, v: string) => { const next = { ...query }; if (v) next[k] = v; else delete next[k]; onChange(next); };
  const imaging = (query.imaging === "yes" ? "yes" : query.imaging === "no" ? "no" : "any") as "any" | "yes" | "no";

  return (
    <Popover open={open} onOpenChange={(o) => { setOpen(o); if (!o) { setSaving(false); setName(""); } }}>
      <PopoverTrigger asChild>
        <Button type="button" variant={n ? "secondary" : "outline"} size="sm" className="h-10 gap-1.5 px-3" aria-label={n ? `Filters, ${n} on` : "Filters"}>
          <ListFilter className="size-4" aria-hidden />
          Filter
          {n ? <span className="rounded-full bg-primary px-1.5 text-[11px] font-bold leading-4 text-primary-foreground">{n}</span> : null}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" side="bottom" sideOffset={6} collisionPadding={12} className="flex w-[min(92vw,40rem)] flex-col overflow-hidden p-0" style={{ maxHeight: "min(40rem, var(--radix-popover-content-available-height))" }}>
        <div className="scroll-thin min-h-0 flex-1 overflow-y-auto p-4">
          <div className="grid gap-5 sm:grid-cols-2">
            <Section title="Status">
              <Checks name="st" options={statuses} selected={listOf(query, "status")} onToggle={(id) => onChange(toggleIn(query, "status", id))} />
            </Section>
            <div className="grid gap-5">
              <Section title="Urgency">
                <div className="flex flex-wrap gap-1">
                  {URGENCY_CHOICES.map((u) => {
                    const on = urg.includes(u.value);
                    return (
                      <button key={u.value} type="button" aria-pressed={on} onClick={() => onChange(toggleIn(query, "urgency", u.value))} className={cn("inline-flex h-8 items-center gap-1 rounded-md border px-2.5 text-xs font-medium transition-colors", on ? "border-primary bg-secondary text-secondary-foreground" : "border-border hover:bg-accent")}>
                        {on ? <Check className="size-3" aria-hidden /> : null}{u.value === "none" ? "Not set" : u.value === "5" ? "5, most urgent" : u.value}
                      </button>
                    );
                  })}
                </div>
              </Section>
              <Section title="Board date">
                <div className="grid grid-cols-2 gap-2">
                  <DateInput value={query.board_from || ""} onChange={(v) => set("board_from", v)} aria-label="Board date from" placeholder="From" />
                  <DateInput value={query.board_to || ""} onChange={(v) => set("board_to", v)} aria-label="Board date to" placeholder="To" />
                </div>
              </Section>
              <Section title="Imaging">
                <Segmented label="Imaging" value={imaging} onChange={(v) => set("imaging", v === "any" ? "" : v)} options={[{ value: "any", label: "Any" }, { value: "yes", label: "Present" }, { value: "no", label: "Not yet" }]} />
              </Section>
            </div>
            <Section title="Cancer">
              <Checks name="org" options={opt(organs)} selected={listOf(query, "organ")} onToggle={(id) => onChange(toggleIn(query, "organ", id))} />
            </Section>
            <div className="grid gap-5">
              <Section title="Treated by">
                <Checks name="own" options={opt(owners)} selected={listOf(query, "owner")} onToggle={(id) => onChange(toggleIn(query, "owner", id))} />
              </Section>
              {showDepartment ? (
                <Section title="Department">
                  <Checks name="dep" options={opt(filters?.departments ?? [])} selected={listOf(query, "department")} onToggle={(id) => onChange(toggleIn(query, "department", id))} />
                </Section>
              ) : null}
              <Section title="Created">
                <div className="grid grid-cols-2 gap-2">
                  <DateInput value={query.from || ""} onChange={(v) => set("from", v)} aria-label="Created from" placeholder="From" />
                  <DateInput value={query.to || ""} onChange={(v) => set("to", v)} aria-label="Created to" placeholder="To" />
                </div>
              </Section>
              {showMine ? (
                <label className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2 text-sm">
                  <span>Mine only <span className="block text-xs text-muted-foreground">Case Files I own or am on</span></span>
                  <Switch checked={query.mine === "1"} onCheckedChange={(v) => set("mine", v ? "1" : "")} aria-label="Mine only" />
                </label>
              ) : null}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 border-t border-border bg-muted/50 px-4 py-2.5">
          <Button type="button" variant="ghost" size="sm" onClick={() => onChange({ q: query.q })} disabled={!n}><X className="size-4" aria-hidden />Clear all</Button>
          <span className="flex-1" />
          {onSave ? (
            saving ? (
              <form className="flex items-center gap-2" onSubmit={async (e) => { e.preventDefault(); if (!name.trim()) return; await onSave(name.trim(), query); setSaving(false); setName(""); setOpen(false); }}>
                <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name this view" className="h-8 w-44" autoFocus aria-label="View name" />
                <Button type="submit" size="sm" disabled={!name.trim()}>Save</Button>
              </form>
            ) : (
              <Button type="button" variant="outline" size="sm" onClick={() => setSaving(true)} disabled={!n} title="Keep these filters as a view of your own"><Bookmark className="size-4" aria-hidden />Save as a view</Button>
            )
          ) : null}
          <Button type="button" size="sm" onClick={() => setOpen(false)}>Done</Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

/** The filters on, as tokens the person can take off one by one. */
export function ActiveFilters({ query, onChange, filters, className }: { query: FilterQuery; onChange: (q: FilterQuery) => void; filters?: CaseListFilters; className?: string }) {
  const keys = filterKeys(query);
  // a date pair reads as one token
  const shown: Array<{ id: string; label: string; clear: FilterKey[] }> = [];
  const pair = (a: FilterKey, b: FilterKey, label: string) => {
    if (!query[a] && !query[b]) return;
    const f = query[a] ? describeValue(a, query[a] as string) : "", t = query[b] ? describeValue(b, query[b] as string) : "";
    const dmy = (iso: string) => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso); return m ? `${m[3]}/${m[2]}/${m[1]}` : iso; };
    shown.push({ id: a, label: `${label}: ${f && t ? `${dmy(f)} to ${dmy(t)}` : f ? `from ${dmy(f)}` : `to ${dmy(t)}`}`, clear: [a, b] });
  };
  pair("board_from", "board_to", "Board date");
  pair("from", "to", "Created");
  for (const k of keys) {
    if (["board_from", "board_to", "from", "to"].includes(k)) continue;
    shown.push({ id: k, label: k === "mine" ? "Mine only" : `${FILTER_LABELS[k]}: ${describeValue(k, query[k] as string, filters)}`, clear: [k] });
  }
  return (
    <AnimatePresence initial={false}>
      {shown.length ? (
        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.18 }} className={cn("flex flex-wrap items-center gap-1.5 overflow-hidden", className)} aria-label="Filters on">
            {shown.map((t) => (
              <motion.span key={t.id} layout initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }} className="inline-flex h-7 max-w-full items-center gap-1 rounded-md bg-secondary pl-2.5 pr-1 text-xs font-medium text-secondary-foreground">
                <span className="truncate">{t.label}</span>
                <button type="button" onClick={() => { const next = { ...query }; for (const k of t.clear) delete next[k]; onChange(next); }} className="rounded p-0.5 hover:bg-primary/20" aria-label={`Remove: ${t.label}`}><X className="size-3" aria-hidden /></button>
              </motion.span>
            ))}
            <Button type="button" variant="ghost" size="xs" onClick={() => onChange({ q: query.q })}>Clear all</Button>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
