// The end-of-case card: Agree, or Concern with a note. Asked of each board head when the coordinator ends a case.
// The note takes dictation (night-v3 4.4): the words go into the box as an edit; the card is sent only by "Send card".
import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Check, MessageSquareWarning } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { MicButton } from "@/components/MicButton";
import { sendCard } from "../api";
import { LoadingButton, errorText } from "@/features/casefile/components/common";
import { cn } from "@/lib/utils";

export function CardDialog({ mid, caseId, patientLine, open, onOpenChange, required, onSent }: { mid: string; caseId: string; patientLine: string; open: boolean; onOpenChange: (o: boolean) => void; required?: boolean; onSent?: () => void }) {
  const [choice, setChoice] = useState<"agree" | "concern" | null>(null);
  const [note, setNote] = useState("");
  const noteRef = useRef<HTMLTextAreaElement>(null);
  const send = useMutation({ mutationFn: () => sendCard(mid, caseId, choice === "agree", note.trim() || undefined), onSuccess: () => { onSent?.(); onOpenChange(false); setChoice(null); setNote(""); } });
  const needNote = choice === "concern" && note.trim().length < 3;
  const showNoteErr = needNote && note.trim().length > 0;
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!send.isPending) onOpenChange(o); }}>
      <DialogContent aria-describedby="card-desc" data-testid="card-dialog">
        <DialogHeader>
          <DialogTitle>Your card for {patientLine}</DialogTitle>
          <DialogDescription id="card-desc">{required ? "Board heads give a card for every case. " : ""}The coordinator and the owner's team read it. A concern always goes in the record, in your words.</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Agree or concern">
          <button type="button" role="radio" aria-checked={choice === "agree"} onClick={() => setChoice("agree")} className={cn("rounded-md border p-3 text-left transition active:scale-[0.98]", choice === "agree" ? "border-ok bg-ok-soft" : "border-border hover:bg-muted")} data-testid="card-agree">
            <Check className="size-5 text-ok" aria-hidden /><p className="font-medium mt-1">Agree</p><p className="text-xs text-muted-foreground">With the decision as read back.</p>
          </button>
          <button type="button" role="radio" aria-checked={choice === "concern"} onClick={() => setChoice("concern")} className={cn("rounded-md border p-3 text-left transition active:scale-[0.98]", choice === "concern" ? "border-warn bg-warn-soft" : "border-border hover:bg-muted")} data-testid="card-concern">
            <MessageSquareWarning className="size-5 text-warn" aria-hidden /><p className="font-medium mt-1">Concern</p><p className="text-xs text-muted-foreground">Say what, in your own words.</p>
          </button>
        </div>
        <div>
          <label htmlFor="card-note" className="text-sm font-medium">{choice === "concern" ? "Your concern" : "Note (optional)"}</label>
          <Textarea ref={noteRef} id="card-note" value={note} onChange={(e) => setNote(e.target.value)} className="mt-1 min-h-20 text-sm" maxLength={500} aria-invalid={showNoteErr} aria-describedby="card-note-help" />
          <div className="flex items-start justify-end gap-2">
            <div className="min-w-0 flex-1">
              {choice === "concern" ? <p id="card-note-help" className={showNoteErr ? "text-xs text-bad mt-0.5" : "text-xs text-muted-foreground mt-0.5"}>{showNoteErr ? "A few more words, please: the concern goes in the record as you write it." : "Write the concern; it goes in the record as you write it."}</p> : null}
            </div>
            <MicButton target={noteRef} screen="card-note" context="note" label={choice === "concern" ? "Dictate your concern" : "Dictate the note"} caseId={caseId} className="max-w-[70%] shrink-0" onInsert={(next) => { if (next.length > 500) setNote(next.slice(0, 500)); }} />
          </div>
        </div>
        {send.isError ? <p role="alert" className="text-sm text-bad">{errorText(send.error)}</p> : null}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={send.isPending}>Later</Button>
          <LoadingButton onClick={() => send.mutate()} loading={send.isPending} loadingText="Sending" disabled={!choice || needNote} data-testid="card-send">Send card</LoadingButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
