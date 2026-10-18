// Archive (never delete): a modal with the reason, which goes in the record. The owner's consultant, or the MDT
// Coordinator with a reason; an archived Case File is listed only under "Archived" and can be brought back.
import { useState } from "react";
import { Archive } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { LoadingButton, errorText } from "./common";

export function ArchiveDialog({ open, onOpenChange, patient, onConfirm }: { open: boolean; onOpenChange: (o: boolean) => void; patient: string; onConfirm: (reason: string) => Promise<void> }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const short = reason.trim().length < 5;
  const go = async () => {
    setBusy(true); setErr(null);
    try { await onConfirm(reason.trim()); setReason(""); onOpenChange(false); }
    catch (e) { setErr(errorText(e)); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!busy) onOpenChange(o); }}>
      <DialogContent aria-describedby="archive-desc" data-testid="archive-dialog">
        <DialogHeader>
          <DialogTitle>Archive the Case File of {patient}?</DialogTitle>
          <DialogDescription id="archive-desc">Nothing is deleted. The Case File leaves the lists and stays readable under Archived; it can be brought back. The reason is recorded with your name.</DialogDescription>
        </DialogHeader>
        <div>
          <label htmlFor="archive-reason" className="text-sm font-medium">Reason</label>
          <Textarea id="archive-reason" value={reason} onChange={(e) => setReason(e.target.value)} className="mt-1 min-h-20 text-sm" maxLength={300} placeholder="for example: created twice for the same patient; treatment completed elsewhere" aria-invalid={!!err} />
          <p className="text-xs text-muted-foreground mt-0.5">{short ? "A few words, at least 5 characters." : "Ready."}</p>
        </div>
        {err ? <p role="alert" className="text-sm text-bad">{err}</p> : null}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Keep it</Button>
          <LoadingButton variant="destructive" loading={busy} loadingText="Archiving" onClick={go} disabled={short}><Archive className="size-4" />Archive</LoadingButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
