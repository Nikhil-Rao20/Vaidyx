import { useEffect, useState, type ReactNode } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ActionButton } from "@/components/ActionButton";
import { useAsyncAction } from "@/hooks/useAsyncAction";

/**
 * The modal of the action ladder: only for steps that cannot be undone (archive, sign, remove a person). Reads back what
 * will happen, takes a reason when asked, and closes itself when the work succeeds.
 */
export function ConfirmDialog({ open, onOpenChange, title, text, confirmText = "Confirm", cancelText = "Cancel", destructive, onConfirm, requireReason, reasonLabel = "Reason", children, doneText = "Done" }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  text?: ReactNode;
  confirmText?: string;
  cancelText?: string;
  destructive?: boolean;
  onConfirm: (reason: string) => Promise<unknown> | unknown;
  requireReason?: boolean;
  reasonLabel?: string;
  children?: ReactNode;
  doneText?: string;
}) {
  const [reason, setReason] = useState("");
  const action = useAsyncAction(async () => {
    await onConfirm(reason.trim());
    window.setTimeout(() => onOpenChange(false), 500);
  });
  useEffect(() => { if (!open) { setReason(""); action.reset(); } }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  const blocked = Boolean(requireReason && !reason.trim());
  return (
    <Dialog open={open} onOpenChange={(o) => { if (action.state !== "loading") onOpenChange(o); }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {text ? <DialogDescription>{text}</DialogDescription> : null}
        </DialogHeader>
        {children}
        {requireReason ? (
          <div className="grid gap-1.5">
            <Label htmlFor="confirm-reason">{reasonLabel}</Label>
            <Textarea id="confirm-reason" value={reason} onChange={(e) => setReason(e.target.value)} rows={3} placeholder="In your own words; this is kept in the record" aria-required />
          </div>
        ) : null}
        {action.error ? <p role="alert" className="text-sm text-bad">{action.error}</p> : null}
        <DialogFooter className="gap-2 sm:gap-2">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={action.state === "loading"}>{cancelText}</Button>
          <ActionButton type="button" variant={destructive ? "destructive" : "default"} state={action.state} doneText={doneText} disabled={blocked} onClick={() => void action.run()}>
            {confirmText}
          </ActionButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
