// "End the meeting?": today's confirmation from the coordinator's control view, with the count of Case Files that have a saved
// outcome. Ending sends the saved outcomes to the owners; Case Files without one keep their place.
import { useMutation } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { LoadingButton, errorText } from "@/features/casefile/components/common";
import { endMeeting } from "../api";
import { useCall } from "./context";

export function EndMeetingDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const c = useCall();
  const finish = useMutation({ mutationFn: () => endMeeting(c.mid), onSuccess: () => { onOpenChange(false); c.announce("The meeting has ended."); c.refresh(); } });
  const done = c.order.filter((r) => r.decided || r.outcome).length;
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!finish.isPending) onOpenChange(o); }}>
      <DialogContent aria-describedby="end-desc" data-testid="end-meeting-dialog" data-theme="dark" className="text-foreground">
        <DialogHeader><DialogTitle>End the meeting?</DialogTitle><DialogDescription id="end-desc">The outcomes already saved go to the owners. Case Files without a saved outcome keep their place; mark them Not discussed first to move them to the next meeting.</DialogDescription></DialogHeader>
        <p className="text-sm">{done} of {c.order.length} Case Files have a saved outcome.</p>
        {finish.isError ? <p role="alert" className="text-sm text-bad">{errorText(finish.error)}</p> : null}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={finish.isPending}>Keep going</Button>
          <LoadingButton variant="destructive" loading={finish.isPending} loadingText="Ending" onClick={() => finish.mutate()} data-testid="confirm-end-meeting">End meeting</LoadingButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
