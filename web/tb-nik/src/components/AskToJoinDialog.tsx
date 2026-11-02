// "Ask to join" a Case File without a code (POST /case-join/ask, night-v3 item 1.1): a doctor who cannot open a Case File of
// this patient asks its owner, with an optional note. The owner's consultants approve or reject it in the Team panel.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { ActionButton } from "@/components/ActionButton";
import { Field } from "@/components/Field";
import { notify } from "@/components/Toasts";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { api } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import { errorCode } from "@/lib/errors";

export interface AskTarget {
  case_id: string;
  /** "Breast Cancer, Breast Surgery, Dr Rao": what the dialog names. */
  label: string;
}

export function AskToJoinDialog({ target, onOpenChange, onAsked }: { target: AskTarget | null; onOpenChange: (o: boolean) => void; onAsked?: (caseId: string) => void }) {
  const [note, setNote] = useState("");
  const [code, setCode] = useState("");
  const open = Boolean(target);
  const action = useAsyncAction(async () => {
    if (!target) return;
    setCode("");
    try {
      const r = await api.post<{ status: string; case_id: string; already?: boolean }>(EP.askToJoin, { case_id: target.case_id, note: note.trim() });
      notify.info(r.already ? "Already asked" : "Asked to join", "The owner's consultants will decide; you will hear when they do.");
      onAsked?.(target.case_id);
      onOpenChange(false);
    } catch (e) {
      setCode(errorCode(e));
      throw e;
    }
  });
  useEffect(() => { if (!open) { setNote(""); setCode(""); action.reset(); } }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  const err = action.state === "error" ? (code === "can_open" ? "You can open this Case File already." : action.error) : null;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Ask to join</DialogTitle>
          <DialogDescription>
            {target ? <>The owner's consultants of <span className="font-medium text-foreground">{target.label}</span> are told and decide. Once approved, you read the whole Case File; the owner's decisions stay with them.</> : null}
          </DialogDescription>
        </DialogHeader>
        <form className="grid gap-4" onSubmit={(e) => { e.preventDefault(); void action.run(); }}>
          <Field id="ask-note" label="Note for the owner" optional hint="Why you ask, in a line. Up to 500 characters.">
            <Textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} placeholder="e.g. Second opinion on the same patient" />
          </Field>
          {err ? (
            <p role="alert" className="rounded-md status-bad px-3 py-2 text-sm">
              {err}
              {code === "can_open" && target ? <> <Link className="font-medium underline" to={`/cases/${encodeURIComponent(target.case_id)}`}>Open it</Link></> : null}
            </p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <ActionButton type="submit" state={action.state} doneText="Asked">Ask to join</ActionButton>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
