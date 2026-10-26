// "Open with a reason" (owner decision D8, night-v3 item 1.9): a doctor who cannot open a Case File may open it read-only for
// 24 hours with a reason. The owner's consultants are told and the opening is recorded with the doctor's name. The button sits on
// the Case File's 403 page; the banner on the Case File while the window is open.
import { useEffect, useState } from "react";
import { format, isValid, parseISO } from "date-fns";
import { Eye, KeyRound } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { ActionButton } from "@/components/ActionButton";
import { Field } from "@/components/Field";
import { notify } from "@/components/Toasts";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { ApiError, api } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import { errorCode } from "@/lib/errors";
import { useSession } from "@/lib/session";
import type { BreakGlassOpened, BreakGlassWindow, Me } from "@/lib/types";

const REASON_MIN = 3;
const REASON_MAX = 500;

/** 28/10/2026 14:05 */
function untilText(iso?: string | null): string {
  if (!iso) return "";
  const d = parseISO(String(iso));
  return isValid(d) ? format(d, "dd/MM/yyyy HH:mm") : String(iso);
}

/** True when the Case File's 403 says this person may open it with a reason ({"detail": {"code": "no_access", "break_glass": true}}). */
export function mayOpenWithReason(error: unknown): boolean {
  if (!(error instanceof ApiError) || error.status !== 403) return false;
  const body = error.detail as { detail?: { break_glass?: unknown } } | null;
  return Boolean(body && typeof body === "object" && body.detail && typeof body.detail === "object" && body.detail.break_glass === true);
}

/** The person's open window on this Case File (GET /me break_glass), or null. */
export function windowFor(me: Me | null | undefined, caseId: string): BreakGlassWindow | null {
  const now = Date.now();
  return (me?.break_glass ?? []).find((w) => w.case_id === caseId && (!isValid(parseISO(w.until)) || parseISO(w.until).getTime() > now)) ?? null;
}

export function OpenWithReasonButton({ caseId, onOpened, via }: { caseId: string; onOpened?: (w: BreakGlassOpened) => void; via?: string }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [code, setCode] = useState("");
  const { refresh } = useSession();
  const text = reason.trim().replace(/\s+/g, " ");
  const action = useAsyncAction(async () => {
    setCode("");
    try {
      const w = await api.post<BreakGlassOpened>(EP.breakGlass, { case_id: caseId, reason: text, ...(via ? { via } : {}) });
      notify.success("Opened read-only", `Until ${untilText(w.until)}. The owner's consultants are told.`);
      setOpen(false);
      void refresh();
      onOpened?.(w);
    } catch (e) {
      setCode(errorCode(e));
      throw e;
    }
  });
  useEffect(() => { if (!open) { setReason(""); setCode(""); action.reset(); } }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  const short = text.length > 0 && text.length < REASON_MIN;
  const err = action.state === "error" ? (code === "can_open" ? "You can open this Case File already. Reload the page." : action.error) : null;
  return (
    <>
      <Button type="button" onClick={() => setOpen(true)} data-testid="open-with-reason">
        <KeyRound className="size-4" aria-hidden />Open with a reason
      </Button>
      <Dialog open={open} onOpenChange={(o) => { if (action.state !== "loading") setOpen(o); }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Open with a reason</DialogTitle>
            <DialogDescription>
              Only the owner's team, the departments asked and the MDT Coordinator open this Case File. You may open it read-only for 24 hours
              with a reason. The owner's consultants are told, and the opening is recorded with your name.
            </DialogDescription>
          </DialogHeader>
          <form className="grid gap-4" onSubmit={(e) => { e.preventDefault(); if (text.length >= REASON_MIN) void action.run(); }}>
            <Field id="open-reason" label="Reason" required hint={`Why you need to read it, in a line. ${REASON_MIN} to ${REASON_MAX} characters.`}
              error={short ? `Write at least ${REASON_MIN} characters.` : null}>
              <Textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={REASON_MAX}
                placeholder="e.g. Second opinion on the systemic plan" />
            </Field>
            {err ? <p role="alert" className="rounded-md status-bad px-3 py-2 text-sm">{err}</p> : null}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setOpen(false)} disabled={action.state === "loading"}>Cancel</Button>
              <ActionButton type="submit" state={action.state} doneText="Opened" disabled={text.length < REASON_MIN}>Open read-only</ActionButton>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}

export function ReadOnlyBanner({ until, reason }: { until: string; reason: string }) {
  return (
    <p role="status" className="flex items-start gap-2 rounded-md status-review px-3 py-2 text-sm" data-testid="read-only-banner">
      <Eye className="mt-0.5 size-4 shrink-0" aria-hidden />
      <span>Read-only until {untilText(until)}, opened with a reason: {reason}</span>
    </p>
  );
}
