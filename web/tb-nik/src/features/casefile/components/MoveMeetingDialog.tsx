// The doctor moves or withdraws a case (night-v3 item 1.6, design B8): "Move to another meeting" lists the open meetings (planned, not
// cancelled, today or later) as radio cards with the date, time and room, takes an optional reason and moves it; "Take off the agenda"
// asks for the reason. Both tell the MDT Coordinator. Used by the Case File's More menu and by the meeting chip of the Case Files list.
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarDays, CalendarClock, MapPin } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { formatDateWords } from "@/lib/format";
import type { Meeting } from "@/lib/types";
import { cn } from "@/lib/utils";
import { getOpenMeetings } from "../api";
import { LoadingButton, errorText, fmtDate } from "./common";

const MAX_REASON = 500;

function MeetingCard({ m, on, onPick, first }: { m: Meeting; on: boolean; onPick: () => void; first: boolean }) {
  return (
    <button type="button" role="radio" aria-checked={on} onClick={onPick} data-testid="move-meeting"
      className={cn("flex w-full items-start gap-2 rounded-md border px-3 py-2 text-left text-sm outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
        on ? "border-primary bg-secondary" : "border-border hover:bg-accent")}>
      <span aria-hidden className={cn("mt-0.5 grid size-4 shrink-0 place-items-center rounded-full border", on ? "border-primary" : "border-border-strong")}>
        {on ? <span className="size-2 rounded-full bg-primary" /> : null}
      </span>
      <span className="min-w-0 flex-1">
        <span className={cn("flex items-center gap-1.5 break-words", on && "font-semibold")}><CalendarDays className="size-4 shrink-0 text-muted-foreground" aria-hidden />{formatDateWords(m.date)}</span>
        <span className="mt-0.5 flex flex-wrap gap-x-3 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1"><CalendarClock className="size-3.5" aria-hidden />{m.time || "time not set"}</span>
          <span className="inline-flex min-w-0 items-center gap-1"><MapPin className="size-3.5 shrink-0" aria-hidden /><span className="truncate">{m.room || "room not set"}</span></span>
          {first ? <span>The next open meeting</span> : null}
        </span>
      </span>
    </button>
  );
}

export function MoveMeetingDialog({ open, onOpenChange, patient, currentMeetingId, currentDate, onConfirm }: {
  open: boolean; onOpenChange: (o: boolean) => void; patient: string;
  /** The meeting it is on now (left out of the choices). */
  currentMeetingId?: string | null; currentDate?: string | null;
  onConfirm: (meetingId: string, reason: string) => Promise<void>;
}) {
  const q = useQuery({ queryKey: ["meetings", "open"], queryFn: getOpenMeetings, enabled: open, staleTime: 15_000 });
  const choices = useMemo(() => (q.data?.meetings ?? []).filter((m) => m.id !== currentMeetingId), [q.data, currentMeetingId]);
  const [pick, setPick] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (open) { setPick(""); setReason(""); setErr(null); } }, [open]);
  useEffect(() => { if (open && !pick && choices.length) setPick(choices[0].id); }, [open, pick, choices]);

  const go = async () => {
    if (!pick || busy) return;
    setBusy(true); setErr(null);
    try { await onConfirm(pick, reason.trim()); onOpenChange(false); }
    catch (e) { setErr(errorText(e)); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!busy) onOpenChange(o); }}>
      <DialogContent aria-describedby="move-desc" data-testid="move-dialog" className="max-h-[calc(100dvh-2rem)] overflow-y-auto overflow-x-hidden p-4 sm:max-w-lg sm:p-6">
        <DialogHeader>
          <DialogTitle className="pr-6">Move to another meeting</DialogTitle>
          <DialogDescription id="move-desc">
            {patient}{currentDate ? ` is on the meeting of ${fmtDate(currentDate)}` : ""}. It moves to the same list on the meeting you choose; the MDT Coordinator is told.
          </DialogDescription>
        </DialogHeader>
        <div>
          <p className="mb-2 text-sm font-medium" id="move-meeting">Which meeting</p>
          {q.isLoading ? <div className="space-y-2" aria-busy="true"><div className="skeleton-line h-12 w-full" /><div className="skeleton-line h-12 w-full" /></div>
            : q.error ? <p role="alert" className="text-sm text-bad">The meetings could not be loaded. {errorText(q.error)}</p>
            : choices.length ? (
              <div role="radiogroup" aria-labelledby="move-meeting" className="grid max-h-72 gap-1.5 overflow-y-auto">
                {choices.map((m) => <MeetingCard key={m.id} m={m} on={pick === m.id} onPick={() => setPick(m.id)} first={m.id === q.data?.meetings[0]?.id} />)}
              </div>
            ) : <p className="rounded-md border border-dashed border-border px-3 py-3 text-sm text-muted-foreground" data-testid="move-none">No other meeting is planned yet. Ask the MDT Coordinator to plan one.</p>}
        </div>
        <div>
          <label htmlFor="move-reason" className="text-sm font-medium">Reason (optional)</label>
          <Textarea id="move-reason" value={reason} onChange={(e) => setReason(e.target.value)} className="mt-1 min-h-16 text-sm" maxLength={MAX_REASON}
            placeholder="For example: the PET-CT report is due after this meeting" />
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

/** "Take off the agenda": the reason is required (the server keeps 3 to 500 characters); the ready mark stays. */
export function TakeOffDialog({ open, onOpenChange, patient, currentDate, onConfirm }: {
  open: boolean; onOpenChange: (o: boolean) => void; patient: string; currentDate?: string | null; onConfirm: (reason: string) => Promise<void>;
}) {
  return (
    <ConfirmDialog open={open} onOpenChange={onOpenChange} title="Take it off the agenda?" destructive requireReason reasonLabel="Reason"
      confirmText="Take off the agenda" doneText="Taken off"
      text={`${patient} leaves the agenda${currentDate ? ` of ${fmtDate(currentDate)}` : ""}. The MDT Coordinator is told. It stays marked ready, so you can send it to the board again later.`}
      onConfirm={onConfirm} />
  );
}
