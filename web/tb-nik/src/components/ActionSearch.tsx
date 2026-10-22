// The search bar in the middle of the top bar: a patient's name, any part of a UHID, an IP or OP number, an accession, a cancer
// or a doctor finds Case Files as the person types (the same matching as the list, lib/search), with the matched parts marked;
// plus three commands: New Case File, Join a Case File with a code, Join a meeting with a code. Our own build on cmdk;
// Ctrl+K or "/" focuses it.
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Command as CommandPrimitive } from "cmdk";
import { motion } from "motion/react";
import { CalendarPlus, CornerDownLeft, FolderPlus, KeyRound, Loader2, Search, UserSearch, X } from "lucide-react";
import { JoinDialog, type JoinKind } from "@/components/JoinDialog";
import { UrgencyTag } from "@/components/UrgencyTag";
import { StatusPill } from "@/components/StatusPill";
import { Highlight } from "@/components/Highlight";
import { useCaseList } from "@/hooks/useQueries";
import { useDebounce } from "@/hooks/useDebounce";
import { matches } from "@/lib/search";
import type { CaseListItem } from "@/lib/types";
import { cn } from "@/lib/utils";

const COMMANDS: Array<{ id: string; label: string; icon: typeof FolderPlus; keywords: string }> = [
  { id: "new", label: "New Case File", icon: FolderPlus, keywords: "new create case file patient uhid" },
  { id: "join-case", label: "Join a Case File with a code", icon: KeyRound, keywords: "join code resident team" },
  { id: "join-meeting", label: "Join a meeting with a code", icon: CalendarPlus, keywords: "join meeting code board" },
];

function looksLikeIdentifier(s: string): boolean {
  return /^(VXH|VDX|IP|OP|UHID|CR|MRN)[\s/:-]?/i.test(s) || /^[A-Z]{1,4}[/-]?\d{2,}[/-]?\d*$/i.test(s) || /^\d{5,}$/.test(s);
}

const ITEM = "flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-2 text-sm data-[selected=true]:bg-accent";

export function ActionSearch({ className, canCreate = true, compact }: { className?: string; canCreate?: boolean; compact?: boolean }) {
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const [join, setJoin] = useState<JoinKind | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const debounced = useDebounce(text, 90);
  const list = useCaseList({}, { enabled: open });
  const q = debounced.trim();
  const results = useMemo<CaseListItem[]>(() => (q ? (list.data?.cases ?? []).filter((c) => matches(c, q)).slice(0, 8) : []), [list.data, q]);
  const commands = COMMANDS.filter((c) => canCreate || c.id !== "new");

  // cmdk always writes aria-expanded="true" on its input; keep it true to the popup.
  useEffect(() => { inputRef.current?.setAttribute("aria-expanded", String(open)); }, [open]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const typing = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); inputRef.current?.focus(); setOpen(true); }
      else if (e.key === "/" && !typing) { e.preventDefault(); inputRef.current?.focus(); setOpen(true); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const run = (id: string) => {
    setOpen(false);
    if (id === "new") navigate("/cases/new");
    else if (id === "join-case") setJoin("case");
    else if (id === "join-meeting") setJoin("meeting");
    else if (id.startsWith("lookup:")) navigate(`/cases/new?identifier=${encodeURIComponent(id.slice(7))}`);
    else if (id === "all") navigate(`/cases?q=${encodeURIComponent(q)}`);
    else navigate(`/cases/${encodeURIComponent(id)}`);
    setText("");
  };

  return (
    <div className={cn("relative", className)}>
      <CommandPrimitive label="Search Case Files and commands" shouldFilter={false} loop onKeyDown={(e) => { if (e.key === "Escape") { setOpen(false); inputRef.current?.blur(); } }}>
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <CommandPrimitive.Input
            ref={inputRef}
            value={text}
            onValueChange={(v) => { setText(v); setOpen(true); }}
            onFocus={() => setOpen(true)}
            onBlur={() => window.setTimeout(() => setOpen(false), 120)}
            placeholder={compact ? "Search" : "Search a patient, UHID, OP or IP number, or type a command"}
            aria-label="Search Case Files and commands"
            className={cn("h-9 w-full rounded-full border border-input bg-background pl-9 pr-16 text-sm text-foreground placeholder:text-muted-foreground transition-[box-shadow,border-color] hover:border-border-strong focus:border-ring focus:outline-none focus:ring-[3px] focus:ring-ring/30", compact && "h-10")}
          />
          <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 hidden items-center gap-1 text-[11px] text-muted-foreground sm:flex" aria-hidden>
            {open && list.isFetching ? <Loader2 className="size-3.5 animate-spin" /> : null}
            {!text ? <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-sans text-[10px] font-medium">Ctrl K</kbd> : null}
          </span>
          {text ? (
            <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => { setText(""); inputRef.current?.focus(); }} className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full p-1 text-muted-foreground hover:bg-accent hover:text-foreground" aria-label="Clear">
              <X className="size-4" aria-hidden />
            </button>
          ) : null}
        </div>
        {/* The list stays mounted (hidden when closed) so the input's aria-controls always points at it. */}
        <motion.div
          initial={false}
          animate={open ? { opacity: 1, y: 0, scale: 1 } : { opacity: 0, y: -4, scale: 0.99 }}
          transition={{ duration: 0.14 }}
          className={cn("absolute left-0 right-0 top-full z-50 mt-1.5 overflow-hidden rounded-xl border border-border bg-popover text-popover-foreground shadow-[var(--shadow-lift)]", !open && "pointer-events-none invisible")}
          aria-hidden={!open || undefined}
        >
          <CommandPrimitive.List className="scroll-thin max-h-[min(60vh,440px)] overflow-auto p-1.5">
            {q ? (
              <CommandPrimitive.Group heading={<span className="px-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Case Files</span>}>
                {list.isLoading && !list.data ? (
                  <div className="space-y-1.5 p-2" aria-busy="true"><div className="skeleton-line h-4 w-2/3" /><div className="skeleton-line h-4 w-1/2" /></div>
                ) : list.error && !list.data ? (
                  <p className="px-2 py-2 text-sm text-muted-foreground">The Case File list could not be read right now.</p>
                ) : results.length ? (
                  results.map((c) => (
                    <CommandPrimitive.Item key={c.case_id} value={c.case_id} onSelect={run} onMouseDown={(e) => e.preventDefault()} className={ITEM}>
                      <UrgencyTag level={c.urgency?.level ?? null} size="sm" />
                      <span className="min-w-0 flex-1">
                        <span className="flex min-w-0 items-baseline gap-x-2 truncate">
                          <span className="truncate font-semibold text-foreground"><Highlight text={c.patient?.name || "Unnamed"} q={q} /></span>
                          <span className="shrink-0 text-xs text-muted-foreground">{c.patient?.agesex}</span>
                          {c.patient?.uhid ? <span className="id shrink-0 text-xs text-muted-foreground"><Highlight text={c.patient.uhid} q={q} id /></span> : null}
                        </span>
                        <span className="block truncate text-xs text-muted-foreground">
                          <Highlight text={c.protocol_label || c.cancer_name || ""} q={q} />
                          {c.owner?.doctor_name ? <> · <Highlight text={c.owner.doctor_name} q={q} /></> : null}
                        </span>
                      </span>
                      <StatusPill status={c.status} className="hidden sm:inline-flex" />
                      <CornerDownLeft className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
                    </CommandPrimitive.Item>
                  ))
                ) : (
                  <p className="px-2 py-2 text-sm text-muted-foreground">No Case File matches "{q}".</p>
                )}
                {results.length >= 8 ? (
                  <CommandPrimitive.Item value="all" onSelect={run} onMouseDown={(e) => e.preventDefault()} className={ITEM}>
                    <Search className="size-4 text-primary" aria-hidden /> Show every match for "{q}" in the list
                  </CommandPrimitive.Item>
                ) : null}
                {canCreate && looksLikeIdentifier(q) ? (
                  <CommandPrimitive.Item value={`lookup:${q}`} onSelect={run} onMouseDown={(e) => e.preventDefault()} className={ITEM}>
                    <UserSearch className="size-4 text-primary" aria-hidden /> Look up <span className="id">{q}</span> in the hospital system (new Case File)
                  </CommandPrimitive.Item>
                ) : null}
              </CommandPrimitive.Group>
            ) : null}
            <CommandPrimitive.Group heading={<span className="px-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Commands</span>}>
              {commands.filter((c) => !q || c.label.toLowerCase().includes(q.toLowerCase()) || c.keywords.includes(q.toLowerCase())).map((c) => (
                <CommandPrimitive.Item key={c.id} value={c.id} onSelect={run} onMouseDown={(e) => e.preventDefault()} className={ITEM}>
                  <c.icon className="size-4 text-primary" aria-hidden /> {c.label}
                </CommandPrimitive.Item>
              ))}
            </CommandPrimitive.Group>
          </CommandPrimitive.List>
        </motion.div>
      </CommandPrimitive>
      <JoinDialog kind={join ?? "case"} open={join !== null} onOpenChange={(o) => { if (!o) setJoin(null); }} />
    </div>
  );
}
