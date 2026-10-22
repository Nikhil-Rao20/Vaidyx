// A request card for the supporting doctor (SPEC 3.6): patient, UHID, IP/OP, accession, what is missing, who asked,
// due date, Open order in HIS (straight to the order, after the HIS login if needed), Acknowledge, Done with a note.
import { useState } from "react";
import { Link } from "react-router-dom";
import { CalendarClock, CheckCircle2, ExternalLink, FolderOpen, Handshake, Hourglass, Images, MessageSquareText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { ActionButton } from "@/components/ActionButton";
import { PatientLine } from "@/components/PatientLine";
import { DateText } from "@/components/DateText";
import { Pill } from "@/components/StatusPill";
import { CopyButton } from "@/components/CopyButton";
import { notify } from "@/components/Toasts";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { api } from "@/lib/api";
import { EP, himsLink } from "@/lib/endpoints";
import type { InboxRequest } from "@/lib/types";
import { personWord } from "@/lib/format";
import { cn } from "@/lib/utils";

export function RequestCard({ request: r, onChanged, canAnswer = true }: { request: InboxRequest; onChanged: () => void; canAnswer?: boolean }) {
  const [note, setNote] = useState("");
  const [doneOpen, setDoneOpen] = useState(false);
  const completed = r.status === "completed";
  const ack = useAsyncAction(async () => {
    await api.post(EP.requestAcknowledge(r.case_id, r.action_id));
    notify.success("Taken up", "The treating doctor can see you are on it.");
    onChanged();
  }, { onError: (m) => notify.error("Could not acknowledge", m) });
  const board = r.source === "board";
  const done = useAsyncAction(async () => {
    // A Tumour Board action (source board) is closed on the action itself; a Pre-Authorization request gets "done" back.
    if (board) await api.post(`${EP.case(r.case_id)}/actions/${encodeURIComponent(r.action_id)}`, { status: "completed", note: note.trim() || undefined });
    else await api.post(EP.requestDone(r.case_id, r.action_id), { note: note.trim() });
    setDoneOpen(false);
    notify.success(board ? "Board action closed" : "Done sent back", board ? undefined : r.free ? "The request is closed." : "It closes by itself when the signed record arrives.");
    onChanged();
  }, { onError: (m) => notify.error("Could not send done", m) });
  const asked = r.sent?.by ? ((r.sent as { by_name?: string }).by_name || personWord(r.sent.by)) : board ? "the Tumour Board" : "the treating doctor";
  const encounter = r.encounter?.ip_no ? `IP ${r.encounter.ip_no}` : r.encounter?.op_no ? `OP ${r.encounter.op_no}` : "";
  const stateWord = completed ? { tone: "ok" as const, icon: CheckCircle2, text: "Closed" }
    : r.done ? { tone: "ok" as const, icon: CheckCircle2, text: "Done, awaiting the record" }
    : r.acknowledged ? { tone: "info" as const, icon: Handshake, text: `Taken up by ${personWord(r.acknowledged.by) || "your department"}` }
    : r.overdue ? { tone: "bad" as const, icon: Hourglass, text: `${r.days_overdue || 1} day${(r.days_overdue || 1) === 1 ? "" : "s"} late` }
    : { tone: "warn" as const, icon: Hourglass, text: "Open" };
  const Icon = stateWord.icon;
  return (
    <article className={cn("surface-inner row-lift flex flex-col gap-3 p-4", completed && "opacity-80")} aria-label={`Request for ${r.patient?.name}: ${r.label}`}>
      <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-2">
        <div className="min-w-0">
          <PatientLine patient={{ name: r.patient?.name, agesex: r.patient?.agesex, uhid: r.uhid || r.patient?.mrn }} extra={encounter} />
          <p className="mt-1 text-sm">
            {board ? <span className="mr-1.5 rounded-md status-review px-1.5 py-0.5 align-middle text-[11px] font-medium">Board action</span> : null}
            <span className="font-bold text-foreground">{r.label}</span>
            {r.what ? <span className="text-muted-foreground"> {r.what}</span> : null}
          </p>
        </div>
        <Pill tone={stateWord.tone} icon={Icon}>{stateWord.text}</Pill>
      </div>
      <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-2">
        <div className="flex items-center gap-1"><dt className="text-muted-foreground">Asked by</dt><dd className="font-medium">{asked}</dd></div>
        {completed ? (
          <div className="flex items-center gap-1"><dt className="text-muted-foreground">Closed</dt><dd><DateText value={r.completed || r.done?.at} fallback="closed" /></dd></div>
        ) : (
          <div className="flex items-center gap-1"><dt className="flex items-center gap-1 text-muted-foreground"><CalendarClock className="size-3.5" aria-hidden /><span className="sr-only">Due</span></dt><dd><DateText value={r.due} mode="due" fallback="no due date" /></dd></div>
        )}
        {r.accession ? <div className="flex items-center gap-1"><dt className="text-muted-foreground">Accession</dt><dd className="mono inline-flex items-center gap-1">{r.accession}<CopyButton text={r.accession} label="Copy accession" size="icon-xs" /></dd></div> : null}
        {r.sent?.at ? <div className="flex items-center gap-1"><dt className="text-muted-foreground">Sent</dt><dd><DateText value={r.sent.at} mode="ago" /></dd></div> : null}
        {r.done?.note ? <div className="sm:col-span-2 flex items-start gap-1"><dt className="text-muted-foreground">Your note</dt><dd>{r.done.note}</dd></div> : null}
      </dl>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" size="sm" asChild>
          <a href={himsLink({ accession: r.accession, uhid: r.uhid || r.patient?.mrn })} target="_blank" rel="noopener noreferrer"
            title={r.accession ? `Opens ${r.accession} in the hospital system; sign in there first if it asks` : "Opens the patient in the hospital system"}>
            <ExternalLink className="size-4" aria-hidden /> {r.accession ? "Open order in HIS" : "Open patient in HIS"}
          </a>
        </Button>
        {r.viewer_url ? (
          <Button type="button" variant="outline" size="sm" asChild>
            <a href={r.viewer_url} target="_blank" rel="noopener noreferrer"><Images className="size-4" aria-hidden /> Open images</a>
          </Button>
        ) : null}
        <Button type="button" variant="ghost" size="sm" asChild>
          <Link to={`/cases/${encodeURIComponent(r.case_id)}`} title="What was asked, and your department's records in this Case File"><FolderOpen className="size-4" aria-hidden /> Case File</Link>
        </Button>
        {!completed && canAnswer ? (
          <span className="ml-auto flex items-center gap-2">
            {!r.acknowledged && !board ? (
              <ActionButton type="button" variant="secondary" size="sm" state={ack.state} doneText="Taken up" onClick={() => void ack.run()} icon={<Handshake className="size-4" aria-hidden />}>
                Acknowledge
              </ActionButton>
            ) : null}
            {!r.done ? (
              <Popover open={doneOpen} onOpenChange={setDoneOpen}>
                <PopoverTrigger asChild>
                  <Button type="button" size="sm"><CheckCircle2 className="size-4" aria-hidden /> Done</Button>
                </PopoverTrigger>
                <PopoverContent align="end" className="w-80">
                  <form className="grid gap-3" onSubmit={(e) => { e.preventDefault(); void done.run(); }}>
                    <div>
                      <p className="text-sm font-bold">{board ? "Close this board action" : "Send \"done\" back"}</p>
                      <p className="text-xs text-muted-foreground">{board ? "Say what was done; the owner's team sees it." : "The report is signed in your own system. Add a line if something is worth knowing."}</p>
                    </div>
                    <div className="grid gap-1.5">
                      <Label htmlFor={`note-${r.action_id}`} className="flex items-center gap-1"><MessageSquareText className="size-3.5" aria-hidden /> Note (optional)</Label>
                      <Textarea id={`note-${r.action_id}`} rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Signed today; addendum on IHC follows" />
                    </div>
                    <ActionButton type="submit" size="sm" state={done.state} doneText="Sent">Send done</ActionButton>
                  </form>
                </PopoverContent>
              </Popover>
            ) : null}
          </span>
        ) : null}
      </div>
    </article>
  );
}
