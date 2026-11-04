// The planner's two small dialogs (meetings-v2 3.3): "Add a Case File" searches the Case Files the coordinator may list (the patient's
// name, the UHID, the cancer) and puts one on For discussion or For noting; "Move to another meeting" lists the other open meetings
// (planned, today or later) and moves the Case File to the same list there.
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarClock, CalendarDays, MapPin, Repeat, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { UrgencyTag } from "@/components/UrgencyTag";
import { cn } from "@/lib/utils";
import { LoadingButton, SkeletonLines, errorText } from "@/features/casefile/components/common";
import { findCaseFiles, listOpenMeetings } from "../api";
import type { ListKey, PlanMeeting, PlanRow } from "./types";
import { dayAndDate } from "./util";

const SHOWN = 8;

export function AddCaseDialog({ open, onOpenChange, onAgenda, onAdd }: {
  open: boolean; onOpenChange: (o: boolean) => void; onAgenda: Set<string>;
  onAdd: (cid: string, list: ListKey, name: string) => Promise<void>;
}) {
  const [typed, setTyped] = useState("");
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (open) { setTyped(""); setQ(""); setErr(null); } }, [open]);
  useEffect(() => { const t = window.setTimeout(() => setQ(typed.trim()), 250); return () => window.clearTimeout(t); }, [typed]);
  const res = useQuery({ queryKey: ["plan-find", q], queryFn: () => findCaseFiles(q), enabled: open, retry: false, staleTime: 15_000 });
  const rows = useMemo(() => {
    const words = q.toLowerCase().split(/\s+/).filter(Boolean);
    return (res.data?.cases ?? [])
      .filter((c) => !c.linked_only && c.status?.key !== "archived" && !onAgenda.has(c.case_id))
      .filter((c) => words.every((w) => [c.patient?.name, c.patient?.uhid, c.case_id, c.protocol_label, c.cancer_name].join(" ").toLowerCase().includes(w)));
  }, [res.data, q, onAgenda]);
  const add = async (cid: string, list: ListKey, name: string) => {
    setBusy(cid + list); setErr(null);
    try { await onAdd(cid, list, name); } catch (e) { setErr(errorText(e)); } finally { setBusy(null); }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!busy) onOpenChange(o); }}>
      <DialogContent aria-describedby="add-desc" data-testid="add-case-dialog" className="max-h-[calc(100dvh-2rem)] overflow-y-auto overflow-x-hidden p-4 sm:max-w-xl sm:p-6">
        <DialogHeader>
          <DialogTitle>Add a Case File</DialogTitle>
          <DialogDescription id="add-desc">Search by the patient's name, the UHID or the cancer. Added after the agenda was sent, it is flagged to the members.</DialogDescription>
        </DialogHeader>
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <label htmlFor="add-search" className="sr-only">Search the Case Files</label>
          <Input id="add-search" value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="Name, UHID or cancer" className="pl-8" maxLength={80} autoFocus data-testid="add-search" />
        </div>
        {res.isLoading ? <SkeletonLines n={3} /> : null}
        {res.isError ? <p role="alert" className="text-sm text-bad">The Case Files could not be searched. {errorText(res.error)}</p> : null}
        {res.data && rows.length === 0 ? <p className="rounded-md border border-dashed border-border px-3 py-3 text-sm text-muted-foreground">{q ? `No Case File matches "${q}" that is not on this agenda already.` : "Every Case File you can list is on this agenda already."}</p> : null}
        <ul className="divide-y divide-border rounded-md border border-border empty:hidden" data-testid="add-results">
          {rows.slice(0, SHOWN).map((c) => (
            <li key={c.case_id} className="flex flex-col gap-2 px-3 py-2 text-sm sm:flex-row sm:items-center" data-testid="add-result" data-case-id={c.case_id}>
              <div className="min-w-0 flex-1">
                <p className="break-words font-medium text-foreground">{c.patient?.name ?? c.case_id}{c.patient?.agesex ? `, ${c.patient.agesex}` : ""}</p>
                <p className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
                  <UrgencyTag level={c.urgency?.level ?? null} size="sm" />
                  <span>{c.protocol_label || c.cancer_name}</span>
                  {c.patient?.uhid ? <span>UHID {c.patient.uhid}</span> : null}
                  {c.status?.label ? <span>{c.status.label}</span> : null}
                </p>
              </div>
              <div className="flex shrink-0 gap-1.5">
                <LoadingButton size="sm" loading={busy === c.case_id + "discussion"} disabled={!!busy} onClick={() => void add(c.case_id, "discussion", c.patient?.name ?? c.case_id)} aria-label={`Add ${c.patient?.name ?? c.case_id} for discussion`}>For discussion</LoadingButton>
                <LoadingButton size="sm" variant="outline" loading={busy === c.case_id + "noting"} disabled={!!busy} onClick={() => void add(c.case_id, "noting", c.patient?.name ?? c.case_id)} aria-label={`Add ${c.patient?.name ?? c.case_id} for noting`}>For noting</LoadingButton>
              </div>
            </li>
          ))}
        </ul>
        {rows.length > SHOWN ? <p className="text-xs text-muted-foreground">{rows.length - SHOWN} more: type to narrow the list.</p> : null}
        {err ? <p role="alert" className="text-sm text-bad">{err}</p> : null}
        <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)} disabled={!!busy}>Done</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function MeetingChoice({ m, on, onPick, first }: { m: PlanMeeting; on: boolean; onPick: () => void; first: boolean }) {
  return (
    <button type="button" role="radio" aria-checked={on} onClick={onPick} data-testid="move-meeting" data-meeting-id={m.id}
      className={cn("flex w-full items-start gap-2 rounded-md border px-3 py-2 text-left text-sm outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
        on ? "border-primary bg-secondary" : "border-border hover:bg-accent")}>
      <span aria-hidden className={cn("mt-0.5 grid size-4 shrink-0 place-items-center rounded-full border", on ? "border-primary" : "border-border-strong")}>
        {on ? <span className="size-2 rounded-full bg-primary" /> : null}
      </span>
      <span className="min-w-0 flex-1">
        <span className={cn("flex items-center gap-1.5 break-words", on && "font-semibold")}><CalendarDays className="size-4 shrink-0 text-muted-foreground" aria-hidden />{dayAndDate(m.date)}</span>
        <span className="mt-0.5 flex flex-wrap gap-x-3 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1"><CalendarClock className="size-3.5" aria-hidden />{m.time || "time not set"}</span>
          <span className="inline-flex min-w-0 items-center gap-1"><MapPin className="size-3.5 shrink-0" aria-hidden /><span className="truncate">{m.room || "room not set"}</span></span>
          {m.series_id ? <span className="inline-flex items-center gap-1"><Repeat className="size-3.5" aria-hidden />weekly</span> : null}
          {first ? <span>the next one</span> : null}
        </span>
      </span>
    </button>
  );
}

export function MoveDialog({ row, meetingId, onOpenChange, onMove }: {
  row: PlanRow | null; meetingId: string; onOpenChange: (o: boolean) => void;
  onMove: (r: PlanRow, to: PlanMeeting, reason: string) => Promise<void>;
}) {
  const open = !!row;
  const q = useQuery({ queryKey: ["meetings", "open"], queryFn: listOpenMeetings, enabled: open, staleTime: 15_000 });
  const choices = useMemo(() => ((q.data?.meetings ?? []) as PlanMeeting[]).filter((m) => m.id !== meetingId), [q.data, meetingId]);
  const [pick, setPick] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (open) { setPick(""); setReason(""); setErr(null); } }, [open]);
  useEffect(() => { if (open && !pick && choices.length) setPick(choices[0].id); }, [open, pick, choices]);
  const go = async () => {
    const to = choices.find((m) => m.id === pick);
    if (!row || !to || busy) return;
    setBusy(true); setErr(null);
    try { await onMove(row, to, reason.trim()); onOpenChange(false); } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!busy) onOpenChange(o); }}>
      <DialogContent aria-describedby="move-desc" data-testid="move-dialog" className="max-h-[calc(100dvh-2rem)] overflow-y-auto overflow-x-hidden p-4 sm:max-w-lg sm:p-6">
        <DialogHeader>
          <DialogTitle className="pr-6">Move to another meeting</DialogTitle>
          <DialogDescription id="move-desc">{(row?.patient_line || row?.case_id || "").split(", UHID")[0]} goes to the same list of the meeting you choose.</DialogDescription>
        </DialogHeader>
        <div>
          <p className="mb-2 text-sm font-medium" id="move-which">Which meeting</p>
          {q.isLoading ? <SkeletonLines n={2} />
            : q.isError ? <p role="alert" className="text-sm text-bad">The meetings could not be loaded. {errorText(q.error)}</p>
            : choices.length ? (
              <div role="radiogroup" aria-labelledby="move-which" className="grid max-h-72 gap-1.5 overflow-y-auto">
                {choices.map((m, i) => <MeetingChoice key={m.id} m={m} on={pick === m.id} onPick={() => setPick(m.id)} first={i === 0} />)}
              </div>
            ) : <p className="rounded-md border border-dashed border-border px-3 py-3 text-sm text-muted-foreground" data-testid="move-none">No other meeting is planned. Plan one from Meetings first.</p>}
        </div>
        <div>
          <label htmlFor="move-reason" className="text-sm font-medium">Reason (optional)</label>
          <Textarea id="move-reason" value={reason} onChange={(e) => setReason(e.target.value)} className="mt-1 min-h-16 text-sm" maxLength={500} placeholder="For example: the PET-CT report is due after this meeting" />
        </div>
        {err ? <p role="alert" className="text-sm text-bad">{err}</p> : null}
        <DialogFooter className="gap-2 sm:gap-2">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
          <LoadingButton type="button" loading={busy} loadingText="Moving" disabled={!pick} onClick={() => void go()} data-testid="move-confirm">Move</LoadingButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
