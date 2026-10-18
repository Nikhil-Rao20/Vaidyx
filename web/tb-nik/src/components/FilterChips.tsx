import { useState, type ReactElement, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Check, Pin, PinOff, Plus, X } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { DateInput, isoToDmy } from "@/components/DateInput";
import { cn } from "@/lib/utils";
import type { CaseListFilters, FilterOption, SavedFilter } from "@/lib/types";
import { URGENCY_CHOICES, STATUS_WORDS, activeKeys, describeValue, optionId, optionLabel, type FilterKey, type FilterQuery } from "@/lib/filters";

type ChipDef = { id: string; label: string; keys: FilterKey[] };

const CHIPS: ChipDef[] = [
  { id: "created", label: "Date", keys: ["from", "to"] },
  { id: "owner", label: "Treated by", keys: ["owner"] },
  { id: "organ", label: "Cancer", keys: ["organ"] },
  { id: "imaging", label: "Imaging", keys: ["imaging"] },
  { id: "urgency", label: "Urgency", keys: ["urgency"] },
  { id: "status", label: "Status", keys: ["status"] },
  { id: "board", label: "Board date", keys: ["board_from", "board_to"] },
  { id: "department", label: "Department", keys: ["department"] },
  { id: "mine", label: "Mine only", keys: ["mine"] },
];

function chipText(chip: ChipDef, q: FilterQuery, filters?: CaseListFilters): string {
  if (chip.id === "created" || chip.id === "board") {
    const [a, b] = chip.keys.map((k) => (q[k] ? isoToDmy(q[k] as string) || q[k] : q[k]));
    if (a && b) return `${chip.label}: ${a} to ${b}`;
    if (a) return `${chip.label}: from ${a}`;
    if (b) return `${chip.label}: to ${b}`;
    return chip.label;
  }
  const k = chip.keys[0];
  const v = q[k];
  if (!v) return chip.label;
  if (k === "mine") return "Mine only";
  return `${chip.label}: ${describeValue(k, v, filters)}`;
}

/** One filter chip. `trigger` wraps the main button (a popover trigger); without it the chip is an on / off toggle. */
function Chip({ active, children, onClear, onClick, ariaLabel, trigger }: { active: boolean; children: ReactNode; onClear?: () => void; onClick?: () => void; ariaLabel?: string; trigger?: (button: ReactElement) => ReactNode }) {
  const button = (
    <button type="button" onClick={trigger ? undefined : onClick} className="inline-flex h-full items-center gap-1 pl-2.5 pr-2 outline-none focus-visible:ring-2 focus-visible:ring-ring active:scale-[0.98]" aria-pressed={trigger ? undefined : active}>
      {!active ? <Plus className="size-3.5 text-muted-foreground" aria-hidden /> : <Check className="size-3.5" aria-hidden />}
      <span className="max-w-[16rem] truncate">{children}</span>
    </button>
  );
  return (
    <span className={cn("inline-flex h-8 items-center overflow-hidden rounded-full border text-sm transition-colors", active ? "border-primary bg-secondary text-secondary-foreground" : "border-border bg-card text-body hover:border-border-strong hover:bg-accent")}>
      {trigger ? trigger(button) : button}
      {active && onClear ? (
        <button type="button" onClick={onClear} className="inline-flex h-full items-center border-l border-primary/30 px-1.5 hover:bg-primary/15" aria-label={`Clear ${ariaLabel ?? "filter"}`}>
          <X className="size-3.5" aria-hidden />
        </button>
      ) : null}
    </span>
  );
}

function OptionList({ options, value, onPick, emptyText = "No choices yet" }: { options: FilterOption[]; value?: string; onPick: (v: string) => void; emptyText?: string }) {
  if (!options.length) return <p className="px-1 py-2 text-sm text-muted-foreground">{emptyText}</p>;
  return (
    <div className="max-h-64 overflow-auto" role="listbox" aria-label="Choices">
      {options.map((o) => {
        const id = optionId(o);
        const selected = id === value;
        return (
          <button key={id} type="button" role="option" aria-selected={selected} onClick={() => onPick(id)} className={cn("flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent", selected && "bg-secondary text-secondary-foreground")}>
            <span className="truncate">{optionLabel(o)}</span>
            {selected ? <Check className="size-4 shrink-0" aria-hidden /> : null}
          </button>
        );
      })}
    </div>
  );
}

/**
 * Filters as chips. An inactive chip opens a small popover with the choices; an active one shows its value and an x.
 * Saved filters (pinned) sit above; the current set can be pinned with a name.
 */
export function FilterChips({ query, onChange, filters, saved, onPin, onUnpin, pinnedName, hideMine, organs, owners, className }: {
  query: FilterQuery;
  onChange: (q: FilterQuery) => void;
  filters?: CaseListFilters;
  saved?: SavedFilter[];
  onPin?: (name: string) => Promise<unknown> | void;
  onUnpin?: (name: string) => Promise<unknown> | void;
  pinnedName?: string | null;
  hideMine?: boolean;
  /** Extra choices computed on the client when the server sends none. */
  organs?: FilterOption[];
  owners?: FilterOption[];
  className?: string;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const [pinName, setPinName] = useState("");
  const [pinOpen, setPinOpen] = useState(false);
  const [pinBusy, setPinBusy] = useState(false);
  const set = (patch: FilterQuery) => onChange({ ...query, ...patch });
  const clearChip = (chip: ChipDef) => {
    const next = { ...query };
    for (const k of chip.keys) delete next[k];
    onChange(next);
  };
  const active = activeKeys(query).filter((k) => k !== "q");
  const chips = hideMine ? CHIPS.filter((c) => c.id !== "mine") : CHIPS;
  const statusOptions: FilterOption[] = filters?.statuses?.length ? filters.statuses : Object.entries(STATUS_WORDS).map(([id, label]) => ({ id, label }));
  const content = (chip: ChipDef): ReactNode => {
    switch (chip.id) {
      case "created":
      case "board": {
        const [kf, kt] = chip.keys;
        return (
          <div className="grid gap-3">
            <div className="grid gap-1.5"><Label htmlFor={`f-${kf}`}>From</Label><DateInput id={`f-${kf}`} value={query[kf] ?? ""} onChange={(v) => set({ [kf]: v || undefined })} /></div>
            <div className="grid gap-1.5"><Label htmlFor={`f-${kt}`}>To</Label><DateInput id={`f-${kt}`} value={query[kt] ?? ""} onChange={(v) => set({ [kt]: v || undefined })} /></div>
            <Button type="button" size="sm" onClick={() => setOpen(null)}>Apply</Button>
          </div>
        );
      }
      case "owner": return <OptionList options={filters?.owners?.length ? filters.owners : owners ?? []} value={query.owner} onPick={(v) => { set({ owner: v }); setOpen(null); }} emptyText="No doctors to pick from yet" />;
      case "organ": return <OptionList options={filters?.organs?.length ? filters.organs : organs ?? []} value={query.organ} onPick={(v) => { set({ organ: v }); setOpen(null); }} emptyText="No cancers in the list yet" />;
      case "department": return <OptionList options={filters?.departments ?? []} value={query.department} onPick={(v) => { set({ department: v }); setOpen(null); }} emptyText="No departments to pick from" />;
      case "status": return <OptionList options={statusOptions} value={query.status} onPick={(v) => { set({ status: v }); setOpen(null); }} />;
      case "urgency": return <OptionList options={URGENCY_CHOICES.map((c) => ({ id: c.value, label: c.label }))} value={query.urgency} onPick={(v) => { set({ urgency: v }); setOpen(null); }} />;
      case "imaging": return <OptionList options={[{ id: "yes", label: "Imaging present" }, { id: "no", label: "No imaging yet" }]} value={query.imaging} onPick={(v) => { set({ imaging: v }); setOpen(null); }} />;
      case "mine": return null;
      default: return null;
    }
  };
  return (
    <div className={cn("flex flex-col gap-2", className)}>
      {saved?.length ? (
        <div className="flex flex-wrap items-center gap-2" aria-label="Saved filters">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Pinned</span>
          {saved.map((f) => {
            const isOn = f.name === pinnedName;
            return (
              <span key={f.name} className={cn("inline-flex h-8 items-center overflow-hidden rounded-full border text-sm", isOn ? "border-primary bg-secondary text-secondary-foreground" : "border-border bg-card hover:bg-accent")}>
                <button type="button" onClick={() => onChange(isOn ? {} : (f.query as FilterQuery))} className="inline-flex h-full items-center gap-1 pl-2.5 pr-2 outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-pressed={isOn}>
                  <Pin className="size-3.5" aria-hidden /> {f.name}
                </button>
                {onUnpin ? (
                  <button type="button" onClick={() => void onUnpin(f.name)} className="inline-flex h-full items-center border-l border-border px-1.5 text-muted-foreground hover:bg-accent hover:text-foreground" aria-label={`Unpin ${f.name}`} title="Unpin">
                    <PinOff className="size-3.5" aria-hidden />
                  </button>
                ) : null}
              </span>
            );
          })}
        </div>
      ) : null}
      {/* One row that scrolls sideways on a phone, so the list starts higher up; wraps on a laptop. */}
      <div className="-mx-4 flex items-center gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0 sm:pb-0 [&>*]:shrink-0" role="group" aria-label="Filters">
        {chips.map((chip) => {
          const isActive = chip.keys.some((k) => Boolean(query[k]));
          if (chip.id === "mine") {
            return <Chip key={chip.id} active={isActive} onClick={() => (isActive ? clearChip(chip) : set({ mine: "1" }))} onClear={() => clearChip(chip)} ariaLabel="Mine only">Mine only</Chip>;
          }
          return (
            <Popover key={chip.id} open={open === chip.id} onOpenChange={(o) => setOpen(o ? chip.id : null)}>
              <Chip active={isActive} onClear={() => clearChip(chip)} ariaLabel={chip.label} trigger={(b) => <PopoverTrigger asChild>{b}</PopoverTrigger>}>{chipText(chip, query, filters)}</Chip>
              <PopoverContent align="start" className="w-64 p-2">
                <p className="px-1 pb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">{chip.label}</p>
                {content(chip)}
              </PopoverContent>
            </Popover>
          );
        })}
        <AnimatePresence>
          {active.length ? (
            <motion.div key="actions" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="inline-flex items-center gap-1">
              <Button type="button" variant="ghost" size="sm" onClick={() => onChange(query.q ? { q: query.q } : {})}>Clear all</Button>
              {onPin && !pinnedName ? (
                <Popover open={pinOpen} onOpenChange={setPinOpen}>
                  <PopoverTrigger asChild>
                    <Button type="button" variant="ghost" size="sm"><Pin className="size-3.5" aria-hidden /> Pin this</Button>
                  </PopoverTrigger>
                  <PopoverContent align="start" className="w-64 p-3">
                    <form className="grid gap-2" onSubmit={async (e) => { e.preventDefault(); if (!pinName.trim()) return; setPinBusy(true); try { await onPin(pinName.trim()); setPinOpen(false); setPinName(""); } finally { setPinBusy(false); } }}>
                      <Label htmlFor="pin-name">Name this view</Label>
                      <Input id="pin-name" value={pinName} onChange={(e) => setPinName(e.target.value)} placeholder="e.g. My urgent ones" autoFocus maxLength={40} />
                      <Button type="submit" size="sm" disabled={!pinName.trim() || pinBusy} aria-busy={pinBusy}>{pinBusy ? "Pinning" : "Pin to my home"}</Button>
                    </form>
                  </PopoverContent>
                </Popover>
              ) : null}
            </motion.div>
          ) : null}
        </AnimatePresence>
      </div>
      {hideMine ? null : (
        <div className="sr-only" aria-live="polite">{active.length ? `${active.length} filters on` : "No filters on"}</div>
      )}
    </div>
  );
}

/** A small labelled switch used inside filter popovers and settings. */
export function SwitchRow({ id, label, hint, checked, onCheckedChange, disabled }: { id: string; label: string; hint?: string; checked: boolean; onCheckedChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5">
      <div className="min-w-0">
        <Label htmlFor={id} className="cursor-pointer">{label}</Label>
        {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
      </div>
      <Switch id={id} checked={checked} onCheckedChange={onCheckedChange} disabled={disabled} />
    </div>
  );
}
