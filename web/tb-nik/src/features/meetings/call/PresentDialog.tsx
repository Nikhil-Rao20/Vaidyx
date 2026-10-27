// "Present a screen" (night-v3 5.2): asked once per meeting in this browser tab before the first share. One line, Share and Cancel;
// Share opens the browser's own picker (a tab, a window or the whole screen). The share goes through the hospital's LiveKit server
// and is not recorded.
import { MonitorUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

export const presentOkKey = (mid: string) => `tbnik.call.present-ok.${mid}`;

/** True when this person already agreed to the line in this tab for this meeting. */
export function presentAsked(mid: string): boolean {
  try { return sessionStorage.getItem(presentOkKey(mid)) === "1"; } catch { return false; }
}
export function markPresentAsked(mid: string) {
  try { sessionStorage.setItem(presentOkKey(mid), "1"); } catch { /* no storage: asked again next time */ }
}

export function PresentDialog({ open, onOpenChange, onShare }: { open: boolean; onOpenChange: (o: boolean) => void; onShare: () => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent aria-describedby="present-desc" data-testid="present-dialog" className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Present a screen</DialogTitle>
          <DialogDescription id="present-desc">Only share what the board needs. The share is not recorded.</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="present-cancel">Cancel</Button>
          <Button onClick={onShare} data-testid="present-share" title="Choose a tab, a window or the whole screen"><MonitorUp className="size-4" aria-hidden />Share</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
