// Mark ready: a modal that reads back what is still open before the Case File goes to the board.
import { useState } from "react";
import { CheckCircle2, CircleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import type { SlotsResponse } from "../types";
import { LoadingButton, errorText } from "./common";

export function MarkReadyDialog({ open, onOpenChange, slots, resident, consultantName, onConfirm, boardQuestionMissing }: {
  open: boolean; onOpenChange: (o: boolean) => void; slots: SlotsResponse | null; resident: boolean; consultantName: string;
  onConfirm: (note: string) => Promise<void>; boardQuestionMissing: boolean;
}) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const blockers = slots?.blockers ?? [];
  const left = slots?.left_before_board ?? blockers.length;
  const confirm = async () => {
    setBusy(true); setErr(null);
    try { await onConfirm(note.trim()); onOpenChange(false); setNote(""); }
    catch (e) { setErr(errorText(e)); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!busy) onOpenChange(o); }}>
      <DialogContent aria-describedby="ready-desc" data-testid="mark-ready-dialog">
        <DialogHeader>
          <DialogTitle>{resident ? `Ask Dr ${consultantName} to mark ready` : "Mark ready for the board"}</DialogTitle>
          <DialogDescription id="ready-desc">{left === 0 ? "Every line of the summary is filled, confirmed or marked not needed." : `${left} ${left === 1 ? "item is" : "items are"} still open. The board will see them as open.`}</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          {blockers.length ? (
            <ul className="rounded-md border border-border divide-y divide-border max-h-56 overflow-y-auto">
              {blockers.map((b, i) => <li key={`${b.slot_id}-${i}`} className="flex items-start gap-2 px-3 py-1.5 text-sm"><CircleAlert className="size-4 mt-0.5 text-warn shrink-0" aria-hidden /><span>{b.why}</span></li>)}
            </ul>
          ) : (
            <p className="flex items-center gap-2 text-sm text-ok"><CheckCircle2 className="size-4" aria-hidden />Nothing left before the board.</p>
          )}
          {boardQuestionMissing ? <p role="alert" className="text-sm status-bad rounded-md px-2 py-1.5">The board question is not written yet. Enter it on the Board question line first.</p> : null}
          <div>
            <label htmlFor="ready-note" className="text-sm font-medium">Note for the coordinator (optional)</label>
            <Textarea id="ready-note" value={note} onChange={(e) => setNote(e.target.value)} className="mt-1 min-h-16 text-sm" maxLength={400} placeholder="Anything the board should know before the meeting" />
          </div>
          {err ? <p role="alert" className="text-xs text-bad">{err}</p> : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Not yet</Button>
          <LoadingButton onClick={confirm} loading={busy} loadingText="Marking" disabled={boardQuestionMissing}>{resident ? `Ask Dr ${consultantName} to sign off` : left === 0 ? "Mark ready" : `Mark ready with ${left} open`}</LoadingButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
