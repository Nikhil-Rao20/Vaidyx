// Join a Case File (POST /cases/join) or a meeting (POST /meetings/join) with a 6-digit code.
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ActionButton } from "@/components/ActionButton";
import { Field } from "@/components/Field";
import { notify } from "@/components/Toasts";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { api, ApiError } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import { errorCode } from "@/lib/errors";

export type JoinKind = "case" | "meeting";

export function JoinDialog({ kind, open, onOpenChange }: { kind: JoinKind; open: boolean; onOpenChange: (o: boolean) => void }) {
  const [code, setCode] = useState("");
  const navigate = useNavigate();
  const clean = code.replace(/\D/g, "").slice(0, 6);
  const [lastCode, setLastCode] = useState("");
  const action = useAsyncAction(async () => {
    setLastCode("");
    try { await join(); } catch (e) { setLastCode(errorCode(e)); throw e; }
  });
  const join = async () => {
    if (kind === "case") {
      const r = await api.post<{ status: "joined" | "pending"; case_id: string; patient_line?: string }>(EP.joinCase, { code: clean });
      if (r.status === "joined") {
        notify.success("You are on the Case File", r.patient_line);
        onOpenChange(false);
        navigate(`/cases/${encodeURIComponent(r.case_id)}`);
      } else {
        notify.info("Asked to join", "The owner's consultant has to approve you; you will hear when that happens.");
        onOpenChange(false);
      }
    } else {
      const r = await api.post<{ meeting_id: string; status: "admitted" | "waiting" }>(EP.joinMeeting, { code: clean });
      notify.success(r.status === "admitted" ? "You are in the meeting" : "In the waiting room", r.status === "admitted" ? undefined : "The coordinator admits you in a moment.");
      onOpenChange(false);
      navigate(`/meetings/${encodeURIComponent(r.meeting_id)}`);
    }
  };
  useEffect(() => { if (!open) { setCode(""); action.reset(); } }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  const err = action.state === "error" ? (lastCode === "no_such_code" ? (kind === "case" ? "No Case File has this code. Check it with the person who gave it to you." : "No meeting has this code. Check it with the coordinator.") : action.error) : null;
  const title = kind === "case" ? "Join a Case File" : "Join a meeting";
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            {kind === "case" ? "Type the 6-digit code the treating doctor gave you. A resident of the same department joins at once; others wait for approval." : "Type the 6-digit code from the coordinator. You wait in the room until the coordinator lets you in."}
          </DialogDescription>
        </DialogHeader>
        <form className="grid gap-4" onSubmit={(e) => { e.preventDefault(); if (clean.length === 6) void action.run(); }}>
          <Field id="join-code" label="Code" error={err} hint="6 digits; 5 tries per 15 minutes">
            <Input value={clean} onChange={(e) => setCode(e.target.value)} inputMode="numeric" autoComplete="one-time-code" placeholder="123456" className="mono text-center text-lg tracking-[0.3em]" autoFocus maxLength={6} />
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <ActionButton type="submit" state={action.state} doneText="Joined" disabled={clean.length !== 6}>Join</ActionButton>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function isRateLimited(e: unknown): boolean {
  return e instanceof ApiError && e.status === 429;
}
