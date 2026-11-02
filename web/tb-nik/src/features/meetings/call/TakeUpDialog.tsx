// "Take up another Case File" during the meeting (meetings-v2 3.4, owner decision D7): the coordinator searches the Case Files they may
// list (the patient's name, any part of the UHID or another identifier, the cancer; lib/search, as the Case File list), leaving out
// those already on this meeting's lists; picking one adds it for discussion as taken up during the meeting and puts it on the floor, so
// the room and every member follow it on the Board view. The agenda rail marks it "Taken up"; the meeting PDF marks it too (the
// backend: added after the start, meeting_pdf.taken_up_during). A Case File without a cancer chosen cannot go to the board (the server
// refuses it), so it is not offered.
import { useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Loader2, Search } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Highlight } from "@/components/Highlight";
import { useCaseList } from "@/hooks/useQueries";
import { useDebounce } from "@/hooks/useDebounce";
import { api } from "@/lib/api";
import type { AgendaRow } from "@/lib/live";
import { matches } from "@/lib/search";
import type { CaseListItem } from "@/lib/types";
import { LoadingButton, errorText, indianDates } from "@/features/casefile/components/common";
import { mUrl, setCurrent } from "../api";
import { cn } from "@/lib/utils";

/** The reason kept on the agenda entry; the rail and the minutes read it. The server also marks an entry added after the start. */
export const TAKEN_UP_REASON = "Taken up during the meeting";
export const TAKEN_UP_WORD = "Taken up";

/** True when the agenda row was taken up during the meeting (its reason, or a flag a later server may send). Pure. */
export function takenUp(r: Pick<AgendaRow, "reason"> & { taken_up?: boolean; unplanned?: boolean }): boolean {
  return !!(r.taken_up || r.unplanned || (r.reason ?? "").trim().toLowerCase() === TAKEN_UP_REASON.toLowerCase());
}

/** Adds the Case File for discussion as taken up during the meeting (the server keeps the reason; `unplanned` is sent for a server that
 *  keeps it), then puts it on the floor. */
export async function takeUpCase(mid: string, caseId: string): Promise<void> {
  await api.post(`${mUrl(mid)}/agenda/add`, { case_id: caseId, list: "discussion", reason: TAKEN_UP_REASON, unplanned: true });
  await setCurrent(mid, caseId);
}

/** The Case Files that may be taken up: listed for the board (a cancer chosen), not archived, not on this meeting's lists. Pure. */
export function takeUpChoices(rows: CaseListItem[], onAgenda: Set<string>): CaseListItem[] {
  return rows.filter((r) => !!r.protocol && r.status?.key !== "archived" && !r.linked_only && !onAgenda.has(r.case_id));
}

export function TakeUpDialog({ open, onOpenChange, mid, agenda, beforeMove, onDone }: {
  open: boolean; onOpenChange: (o: boolean) => void; mid: string; agenda: { discussion: AgendaRow[]; noting: AgendaRow[]; not_ready: AgendaRow[] };
  /** The recorder's cut: the words said about the case on the floor are posted before another comes up. */
  beforeMove?: () => Promise<void>;
  onDone: (name: string) => void;
}) {
  const [text, setText] = useState("");
  const q = useDebounce(text, 120).trim();
  const list = useCaseList({}, { enabled: open });
  const onAgenda = useMemo(() => new Set([...agenda.discussion, ...agenda.noting].map((r) => r.case_id)), [agenda]);
  const notReady = useMemo(() => new Set(agenda.not_ready.map((r) => r.case_id)), [agenda]);
  const choices = useMemo(() => takeUpChoices(list.data?.cases ?? [], onAgenda), [list.data, onAgenda]);
  const results = useMemo(() => (q ? choices.filter((c) => matches(c, q)) : choices).slice(0, 30), [choices, q]);
  const take = useMutation({
    mutationFn: async (c: CaseListItem) => { await beforeMove?.(); await takeUpCase(mid, c.case_id); return c; },
    onSuccess: (c) => { onDone(c.patient?.name || c.case_id); setText(""); onOpenChange(false); },
  });

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!take.isPending) { onOpenChange(o); if (!o) take.reset(); } }}>
      <DialogContent aria-describedby="takeup-desc" data-testid="take-up-dialog" className="flex max-h-[85dvh] flex-col gap-3 text-foreground sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Take up another Case File</DialogTitle>
          <DialogDescription id="takeup-desc">It is added for discussion as taken up during the meeting and goes on the screen for everyone. The minutes say so.</DialogDescription>
        </DialogHeader>
        <label className="relative block">
          <span className="sr-only">Search a patient, UHID or cancer</span>
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input autoFocus value={text} onChange={(e) => setText(e.target.value)} placeholder="Search a patient, UHID or cancer" className="h-10 pl-9 text-base sm:text-sm" data-testid="take-up-search" maxLength={80} />
        </label>
        {take.isError ? <p role="alert" className="rounded-md bg-bad-soft px-3 py-2 text-sm text-bad">{errorText(take.error)}</p> : null}
        <div className="scroll-thin -mx-1 min-h-0 flex-1 overflow-y-auto px-1" aria-live="polite">
          {list.isLoading ? <p className="flex items-center gap-2 py-6 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" aria-hidden />Loading the Case Files</p>
            : list.isError ? <p className="py-6 text-sm text-bad">{errorText(list.error)}</p>
            : results.length === 0 ? <p className="py-6 text-center text-sm text-muted-foreground" data-testid="take-up-empty">{q ? "No Case File not on this agenda matches." : "Every Case File you may list is on this agenda already."}</p>
            : (
              <ul className="space-y-1" aria-label="Case Files">
                {results.map((c) => {
                  const cancer = c.protocol_label || c.cancer_name || "";
                  const busy = take.isPending && take.variables?.case_id === c.case_id;
                  return (
                    <li key={c.case_id} className="flex items-center gap-3 rounded-lg border border-border px-3 py-2" data-testid="take-up-row" data-case={c.case_id}>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium"><Highlight text={c.patient?.name || c.case_id} q={q} />{c.patient?.agesex ? <span className="font-normal text-muted-foreground">, {c.patient.agesex}</span> : null}</p>
                        <p className="truncate text-xs text-muted-foreground">
                          {c.patient?.uhid ? <>UHID <Highlight text={c.patient.uhid} q={q} id /></> : null}
                          {cancer ? <> · <Highlight text={cancer} q={q} /></> : null}
                          {c.owner?.department_label ? ` · ${c.owner.department_label}` : ""}
                        </p>
                        {notReady.has(c.case_id) ? <p className="text-xs text-warn">On this meeting's not ready list</p> : c.status?.label ? <p className="truncate text-xs text-muted-foreground">{indianDates(c.status.label)}</p> : null}
                      </div>
                      <LoadingButton size="sm" className={cn("shrink-0", busy && "min-w-24")} loading={busy} loadingText="Taking up" disabled={take.isPending} onClick={() => take.mutate(c)} data-testid="take-up-pick" aria-label={`Take up ${c.patient?.name || c.case_id}`}>Take up</LoadingButton>
                    </li>
                  );
                })}
              </ul>
            )}
        </div>
        <p className="text-xs text-muted-foreground">Case Files without a cancer chosen are not listed: they cannot go to the board yet.</p>
      </DialogContent>
    </Dialog>
  );
}
