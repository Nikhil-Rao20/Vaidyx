// "Change the cancer" from the Overview warning: the checklists the server has (GET /protocols) and their settings; the Case File is
// listed again under the one picked (POST /cases/{id}/listing), its reports read again for that cancer.
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useProtocols } from "@/hooks/useQueries";
import { cn } from "@/lib/utils";
import { LoadingButton, errorText } from "../components/common";
import { changeListing } from "./api";

export function ChangeCancerDialog({ open, onOpenChange, caseId, current, onChanged }: { open: boolean; onOpenChange: (o: boolean) => void; caseId: string; current: string; onChanged: (job: string) => void }) {
  const protocols = useProtocols({ enabled: open });
  const [pick, setPick] = useState(current);
  const [setting, setSetting] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (open) { setPick(current); setSetting(""); setErr(null); } }, [open, current]);
  const list = (protocols.data?.protocols ?? []).filter((p) => p.id !== "generic");
  const chosen = list.find((p) => p.id === pick);
  const save = async () => {
    setBusy(true); setErr(null);
    try { const r = await changeListing(caseId, { protocol: pick, setting }); onChanged(r.job); onOpenChange(false); }
    catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!busy) onOpenChange(o); }}>
      <DialogContent aria-describedby="cancer-desc" data-testid="change-cancer">
        <DialogHeader>
          <DialogTitle>Change the cancer</DialogTitle>
          <DialogDescription id="cancer-desc">The checklist follows the cancer. Every report is read again for the cancer you pick.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div role="radiogroup" aria-label="Cancer" className="grid gap-1.5 sm:grid-cols-2">
            {list.map((p) => (
              <button key={p.id} type="button" role="radio" aria-checked={pick === p.id} onClick={() => { setPick(p.id); setSetting(""); }}
                className={cn("rounded-md border px-3 py-2 text-left text-sm", pick === p.id ? "border-primary bg-secondary font-semibold" : "border-border hover:bg-accent")}>{p.label}</button>
            ))}
          </div>
          {chosen?.settings?.length ? (
            <div>
              <p className="mb-1 text-sm font-medium">Setting, as recorded</p>
              <div role="radiogroup" aria-label="Setting" className="flex flex-wrap gap-1.5">
                {chosen.settings.map((s) => (
                  <button key={s.id} type="button" role="radio" aria-checked={setting === s.id} onClick={() => setSetting(s.id)} title={s.definition}
                    className={cn("rounded-full border px-3 py-1 text-sm", setting === s.id ? "border-primary bg-secondary font-semibold" : "border-border hover:bg-accent")}>{s.label}</button>
                ))}
              </div>
            </div>
          ) : null}
          {err ? <p role="alert" className="text-sm text-bad">{err}</p> : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
          <LoadingButton onClick={save} loading={busy} disabled={!pick || pick === current && !setting}>Change and read again</LoadingButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
