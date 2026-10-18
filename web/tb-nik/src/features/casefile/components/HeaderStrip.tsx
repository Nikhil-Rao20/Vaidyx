// The header strip: who the patient is, the cancer and setting, the owner, the board date, the urgency tag, the
// "N left before the board" counter with Mark ready, and the one-click panels. Sticky mini-header on mobile. A cancer with no
// checklist yet (protocol "generic") is named by case.cancer_name, "(no checklist yet)", with what the generic rule checks.
import { useState } from "react";
import { Link } from "react-router-dom";
import { Archive, BookOpen, CalendarDays, ChevronDown, ClipboardList, Download, Flag, Printer, Sparkles, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Textarea } from "@/components/ui/textarea";
import { ownerOf } from "../api";
import type { CaseFile, Team, Urgency } from "../types";
import { DisabledReason, LoadingButton, StatusChip, fmtDate, plural } from "./common";
import { cn } from "@/lib/utils";
import { GENERIC_RULE, NO_CHECKLIST_WORDS, isGeneric } from "@/lib/cancers";

export type PanelKind = "helpers" | "team" | "board" | "published" | null;

const URGENCY_WORD: Record<number, string> = { 1: "routine", 2: "low", 3: "normal", 4: "high", 5: "most urgent" };

export function UrgencyTag({ urgency, resident, canSet, consultantName, onSet, busy }: { urgency?: Urgency | null; resident: boolean; canSet: boolean; consultantName: string; onSet: (level: number, note?: string) => Promise<void>; busy?: boolean }) {
  const [open, setOpen] = useState(false);
  const [level, setLevel] = useState<number | null>(urgency?.level ?? null);
  const [note, setNote] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const lvl = urgency?.level;
  const colour = lvl === 5 ? "status-bad" : lvl === 4 ? "status-warn" : "bg-muted text-muted-foreground";
  const proposed = urgency?.proposed ?? (urgency?.proposals ?? []).find(() => true) ?? null;
  const label = lvl ? `Urgency ${lvl}: ${urgency?.label || URGENCY_WORD[lvl] || ""}` : "Urgency not set";
  return (
    <Popover open={open} onOpenChange={(o) => { setOpen(o); setErr(null); if (o) setLevel(urgency?.level ?? null); }}>
      <div className="inline-flex items-center gap-1.5 flex-wrap">
        <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium", colour)} data-testid="urgency-tag">
          <Flag className="size-3.5" aria-hidden />{label}
        </span>
        {urgency?.set_by_name || urgency?.set_by ? <span className="text-xs text-muted-foreground">set by {urgency.set_by_name ?? urgency.set_by}</span> : null}
        {proposed ? <StatusChip kind="review">{proposed.by_name ? `${proposed.by_name} proposes` : "resident proposes"} {proposed.level}</StatusChip> : null}
        {canSet ? (
          <PopoverTrigger asChild>
            <Button variant="ghost" size="xs" aria-label={resident ? "Propose an urgency" : "Change the urgency"}>{resident ? "Propose" : "Change"}<ChevronDown className="size-3" /></Button>
          </PopoverTrigger>
        ) : null}
      </div>
      <PopoverContent align="start" className="w-72 space-y-2">
        <p className="text-sm font-medium">{resident ? `Propose an urgency to Dr ${consultantName}` : "Set the urgency"}</p>
        <p className="text-xs text-muted-foreground">1 routine to 5 most urgent. Colour only on 4 and 5. Your name is recorded.</p>
        <div role="radiogroup" aria-label="Urgency level" className="flex gap-1">
          {[1, 2, 3, 4, 5].map((n) => (
            <button key={n} type="button" role="radio" aria-checked={level === n} onClick={() => setLevel(n)} className={cn("flex-1 rounded-md border py-1.5 text-sm font-medium transition active:scale-95", level === n ? (n >= 5 ? "status-bad border-bad" : n === 4 ? "status-warn border-warn" : "bg-secondary text-secondary-foreground border-primary") : "border-border hover:bg-muted")}>{n}</button>
          ))}
        </div>
        <Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why (optional)" className="min-h-12 text-sm" maxLength={200} aria-label="Reason" />
        {err ? <p role="alert" className="text-xs text-bad">{err}</p> : null}
        <div className="flex justify-end gap-1.5">
          <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
          <LoadingButton size="sm" loading={busy} disabled={level === null || (level === urgency?.level && !note.trim())} onClick={async () => { if (level === null) return; setErr(null); try { await onSet(level, note.trim() || undefined); setOpen(false); setNote(""); } catch (e) { setErr(e instanceof Error ? e.message : "Could not save."); } }}>
            {resident ? `Ask Dr ${consultantName} to sign off` : "Save"}
          </LoadingButton>
        </div>
      </PopoverContent>
    </Popover>
  );
}

export function HeaderStrip({ cf, team, left, resident, consultantName, canMarkReady, markReadyReason, onMarkReady, onOpenPanel, activePanel, onPrint, exportAllowed, exportReason, exportHref, onUrgency, urgencyBusy, canSetUrgency, helpersCount, publishedCount, onArchive, protocolLabel, helpersReady = 0, helpersPreparing = 0 }: {
  cf: CaseFile; team: Team | null; left: number | null; resident: boolean; consultantName: string;
  canMarkReady: boolean; markReadyReason: string | null; onMarkReady: () => void;
  onOpenPanel: (p: PanelKind) => void; activePanel: PanelKind; onPrint: () => void;
  exportAllowed: boolean; exportReason: string | null; exportHref: string;
  onUrgency: (level: number, note?: string) => Promise<void>; urgencyBusy: boolean; canSetUrgency: boolean;
  helpersCount: number; publishedCount: number; onArchive?: () => void; protocolLabel?: string;
  helpersReady?: number; helpersPreparing?: number;
}) {
  const c = cf.case;
  const p = c.patient ?? { name: "", mrn: "", agesex: "" };
  const generic = isGeneric(c.protocol);
  const cancerName = ((c as { cancer_name?: string }).cancer_name ?? "").trim();
  const cancer = generic
    ? `${cancerName || "Other cancer"} (${NO_CHECKLIST_WORDS})`
    : protocolLabel || c.protocol_label || (c.protocol ? c.protocol.replace(/_/g, " ") : "cancer not listed yet");
  const ids = (p.ids ?? []).filter((x) => x.kind === "ip_no" || x.kind === "op_no").map((x) => x.value);
  const ownerDept = team?.owner?.department_label || ownerOf(cf).name;
  const ownerName = team?.owner?.doctors?.[0]?.name ?? cf.access?.owner_name ?? "";
  const ready = !!c.board_ready;
  // The login that marked it ready, shown as the person's name when the team knows it.
  const readyLogin = c.board_ready?.by ?? "";
  const readyBy = readyLogin ? ([...(team?.owner?.doctors ?? []), ...(team?.residents ?? [])].find((d) => d.user === readyLogin)?.name || readyLogin) : "";
  const teamCount = (team?.residents?.length ?? 0) + (team?.owner?.doctors?.length ?? 0) + (team?.departments?.length ?? 0);
  const panelBtn = (kind: Exclude<PanelKind, null>, icon: React.ReactNode, label: string, extra?: React.ReactNode) => (
    <Button size="sm" variant={activePanel === kind ? "secondary" : "outline"} aria-pressed={activePanel === kind} onClick={() => onOpenPanel(activePanel === kind ? null : kind)} className="print:hidden" data-testid={`open-${kind}`}>{icon}{label}{extra}</Button>
  );
  const helpersExtra = helpersPreparing ? (
    <span className="relative ml-0.5 inline-flex size-2" title={`${helpersPreparing} preparing in the background`} aria-label={`${helpersPreparing} preparing`}><span className="absolute inline-flex size-full animate-ping rounded-full bg-primary opacity-75" /><span className="relative inline-flex size-2 rounded-full bg-primary" /></span>
  ) : helpersReady ? <span className="ml-0.5 rounded-full bg-ok-soft px-1.5 text-[11px] font-bold leading-4 text-ok" title={`${helpersReady} briefs ready`}>{helpersReady}</span> : null;
  return (
    <header className="surface p-3 sm:p-4 print:shadow-none print:border-0 print:p-0" data-testid="header-strip">
      <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:gap-4">
        <div className="min-w-0 flex-1">
          <h1 className="text-xl sm:text-2xl leading-tight break-words lg:truncate" title={p.name}>{p.name || "Unnamed patient"} <span className="text-base font-normal text-muted-foreground whitespace-nowrap">{p.agesex}</span></h1>
          <p className="text-sm text-muted-foreground flex flex-wrap gap-x-3 gap-y-0.5">
            <span>UHID <span className="mono text-foreground">{p.mrn}</span></span>
            {ids.map((v) => <span key={v} className="mono">{v}</span>)}
          </p>
          <p className="text-sm mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
            <span className="font-medium text-foreground break-words" data-testid="header-cancer">{cancer}</span>
            {generic ? (
              <span className="text-muted-foreground" title="Owner decision R05-Q04: histopathology, staging imaging, a clinical note with performance status, the question for the board">{GENERIC_RULE}</span>
            ) : c.setting ? <span className="text-muted-foreground">{c.setting.replace(/_/g, " ")}, as recorded</span> : null}
            <span className="text-muted-foreground">{ownerName ? `${ownerName}, ` : ""}{ownerDept || "no owner yet"}</span>
            <span className="inline-flex items-center gap-1 text-muted-foreground"><CalendarDays className="size-3.5" aria-hidden />{c.board_date ? `Board ${fmtDate(c.board_date)}` : "Board date not set"}{c.meeting_id ? <Link className="text-link underline underline-offset-2 ml-1" to={`/meetings/${c.meeting_id}`}>meeting</Link> : null}</span>
          </p>
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <UrgencyTag urgency={team?.urgency !== undefined ? team.urgency : c.urgency} resident={resident} canSet={canSetUrgency} consultantName={consultantName} onSet={onUrgency} busy={urgencyBusy} />
          </div>
        </div>
        <div className="flex flex-col items-start lg:items-end gap-2 shrink-0">
          <div className="flex items-center gap-2 flex-wrap" data-testid="left-counter">
            {ready ? (
              <StatusChip kind="ok">ready for the board{readyBy ? `, marked by ${readyBy}` : ""}</StatusChip>
            ) : left === null ? (
              <span className="skeleton-line h-6 w-36" aria-label="Counting" />
            ) : (
              <span className={cn("inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-sm font-medium", left === 0 ? "status-ok" : "status-warn")}>
                <ClipboardList className="size-4" aria-hidden />{left === 0 ? "Nothing left before the board" : `${plural(left, "item")} left before the board`}
              </span>
            )}
            {!ready ? (
              <DisabledReason reason={markReadyReason ?? ""}>
                <Button size="sm" onClick={onMarkReady} disabled={!canMarkReady} className="print:hidden" data-testid="mark-ready">{resident ? `Ask Dr ${consultantName} to mark ready` : "Mark ready"}</Button>
              </DisabledReason>
            ) : null}
          </div>
          {markReadyReason && !canMarkReady && !ready ? <p className="text-xs text-muted-foreground print:hidden">{markReadyReason}</p> : null}
        </div>
      </div>
      {/* One row that scrolls sideways on a phone (the summary starts higher up); wraps on a laptop. */}
      <div className="mt-3 -mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1 sm:flex-wrap sm:overflow-visible sm:pb-0 print:hidden [&>*]:shrink-0">
        {panelBtn("helpers", <Sparkles className="size-4" />, `Specialty helpers (${helpersCount})`, helpersExtra)}
        {panelBtn("team", <Users className="size-4" />, `Team${teamCount ? ` (${teamCount})` : ""}`)}
        {panelBtn("board", <ClipboardList className="size-4" />, "Board form")}
        {panelBtn("published", <BookOpen className="size-4" />, `Published cases${publishedCount ? ` (${publishedCount})` : ""}`)}
        <span className="flex-1" />
        {onArchive ? <Button size="sm" variant="ghost" onClick={onArchive} title="Archive the Case File (nothing is deleted)" data-testid="archive"><Archive className="size-4" />Archive</Button> : null}
        <Button size="sm" variant="ghost" onClick={onPrint} aria-label="Print the summary" title="Print the summary"><Printer className="size-4" />Print</Button>
        <DisabledReason reason={exportReason ?? ""}>
          <Button size="sm" variant="ghost" asChild={exportAllowed} disabled={!exportAllowed} title={exportReason ?? "Export the NCG Virtual Tumour Board template (.pptx)"}>
            {exportAllowed ? <a href={exportHref} download><Download className="size-4" />Export .pptx</a> : <span className="inline-flex items-center gap-2"><Download className="size-4" />Export .pptx</span>}
          </Button>
        </DisabledReason>
      </div>
    </header>
  );
}
