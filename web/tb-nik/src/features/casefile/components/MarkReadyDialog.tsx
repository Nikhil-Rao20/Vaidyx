// Send to the board (night-v3 item 1.4, design B7): five short steps in a dialog. 1 the meeting (the next open one pre-selected, or
// "not scheduled yet": the coordinator picks), 2 for discussion or for noting, 3 the presenter (you or a resident on the team), 4 a note
// for the coordinator and, when items are still open, the reason the board should see it anyway (the server requires it), 5 confirm.
// A resident's send goes to the consultant for sign-off with the same choices.
import { useEffect, useMemo, useState } from "react";
import { CalendarDays, CheckCircle2, CircleAlert, MessageSquareText, NotebookPen, UserRound } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Stepper, Step } from "@/components/Stepper";
import { KeyValue, KeyValueList } from "@/components/KeyValue";
import { useQuery } from "@tanstack/react-query";
import { useSession } from "@/lib/session";
import { consultantTitle, drName, formatDateWords, parseDate } from "@/lib/format";
import type { Meeting } from "@/lib/types";
import { cn } from "@/lib/utils";
import type { SendToBoardBody, SlotsResponse, Team } from "../types";
import { getOpenMeetings } from "../api";
import { errorText } from "./common";

const NOT_SCHEDULED = "";
const LISTS: Array<{ id: SendToBoardBody["list"]; title: string; text: string }> = [
  { id: "discussion", title: "For discussion", text: "The board discusses it and records a decision." },
  { id: "noting", title: "For noting", text: "The board notes it; no decision needed." },
];

function meetingWords(m: Meeting): string {
  return `${formatDateWords(m.date)}${m.time ? `, ${m.time}` : ""}${m.room ? `, ${m.room}` : ""}`;
}

/** The meetings a Case File can still go to: planned, not cancelled, today or later, earliest first (as the server checks). */
export function openMeetings(all: Meeting[] | undefined): Meeting[] {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return (all ?? [])
    .filter((m) => m.status === "planned" && !(m as Meeting & { cancelled?: unknown }).cancelled && (parseDate(m.date) ?? today) >= today)
    .sort((a, b) => (parseDate(a.date)?.getTime() ?? 0) - (parseDate(b.date)?.getTime() ?? 0) || String(a.time ?? "").localeCompare(String(b.time ?? "")));
}

function Choice({ on, onPick, title, text, icon, testId }: { on: boolean; onPick: () => void; title: string; text?: string; icon?: React.ReactNode; testId?: string }) {
  return (
    <button type="button" role="radio" aria-checked={on} onClick={onPick} data-testid={testId}
      className={cn("flex w-full items-start gap-2 rounded-md border px-3 py-2 text-left text-sm outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
        on ? "border-primary bg-secondary" : "border-border hover:bg-accent")}>
      <span aria-hidden className={cn("mt-0.5 grid size-4 shrink-0 place-items-center rounded-full border", on ? "border-primary" : "border-border-strong")}>
        {on ? <span className="size-2 rounded-full bg-primary" /> : null}
      </span>
      <span className="min-w-0 flex-1">
        <span className={cn("flex items-center gap-1.5 break-words", on && "font-semibold")}>{icon}{title}</span>
        {text ? <span className="block text-xs text-muted-foreground">{text}</span> : null}
      </span>
    </button>
  );
}

export function MarkReadyDialog({ open, onOpenChange, slots, resident, consultantName, onConfirm, boardQuestionMissing, team, openCount }: {
  open: boolean; onOpenChange: (o: boolean) => void; slots: SlotsResponse | null; resident: boolean; consultantName: string;
  onConfirm: (body: SendToBoardBody) => Promise<void>; boardQuestionMissing: boolean;
  /** The Case File team (residents who may present). */
  team?: Team | null;
  /** The one count of what is open (steps.left); the slots' count when not given. */
  openCount?: number | null;
}) {
  const { me } = useSession();
  // the open meetings (planned, not cancelled, today or later) for any placed login: GET /meetings/open (night-v3 item 1.6), not the
  // person's own meeting list, which hides an empty planned meeting from a department not yet on its attendance sheet
  const meetingsq = useQuery({ queryKey: ["meetings", "open"], queryFn: getOpenMeetings, enabled: open, retry: 1 });
  const meetings = useMemo(() => openMeetings(meetingsq.data?.meetings), [meetingsq.data]);
  const [step, setStep] = useState(1);
  const [meetingId, setMeetingId] = useState<string | null>(null);
  const [list, setList] = useState<SendToBoardBody["list"]>("discussion");
  const [presenter, setPresenter] = useState("");
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const blockers = slots?.blockers ?? [];
  const left = openCount ?? slots?.left_before_board ?? blockers.length;
  const needReason = left > 0;

  // Each opening starts again at step 1 with the next open meeting pre-selected.
  useEffect(() => {
    if (open) { setStep(1); setMeetingId(null); setList("discussion"); setPresenter(""); setNote(""); setReason(""); setErr(null); }
  }, [open]);
  useEffect(() => {
    if (open && meetingId === null && meetingsq.isFetched) setMeetingId(meetings[0]?.id ?? NOT_SCHEDULED);
  }, [open, meetingId, meetingsq.isFetched, meetings]);

  const meName = drName(me?.display_name || me?.user || "");
  const residents = (team?.residents ?? []).filter((r) => !r.expired);
  // Who may present: the consultant (the sender; an empty value) or a resident on the team. A resident sees the consultant by name.
  const presenters: Array<{ value: string; title: string; text?: string }> = [
    resident ? { value: "", title: `${consultantTitle(consultantName, true)}`, text: "The consultant" } : { value: "", title: `You (${meName})` },
    ...residents.map((r) => ({ value: r.user, title: r.user === me?.user ? `You (${drName(r.name)})` : drName(r.name), text: "Resident on the team" })),
  ];
  const chosenMeeting = meetings.find((m) => m.id === meetingId);
  const presenterTitle = presenters.find((p) => p.value === presenter)?.title ?? presenters[0].title;
  const sendLabel = resident ? `Send to ${consultantTitle(consultantName)} for sign-off` : "Send to the board";

  const stepOk = step === 1 ? meetingId !== null : step === 4 ? !needReason || reason.trim().length > 0 : step === 5 ? !boardQuestionMissing : true;

  const send = async () => {
    if (busy || !stepOk) return;
    setBusy(true); setErr(null);
    try {
      await onConfirm({ list, meeting_id: meetingId ?? NOT_SCHEDULED, presenter, note: note.trim(), reason: reason.trim() });
      onOpenChange(false);
    } catch (e) { setErr(errorText(e)); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!busy) onOpenChange(o); }}>
      <DialogContent aria-describedby="ready-desc" data-testid="mark-ready-dialog" className="max-h-[calc(100dvh-2rem)] overflow-y-auto overflow-x-hidden p-4 sm:max-w-xl sm:p-6">
        <DialogHeader>
          <DialogTitle className="pr-6">{sendLabel}</DialogTitle>
          <DialogDescription id="ready-desc">{left === 0 ? "Everything the board needs is in the reports, confirmed or marked not needed." : `${left} ${left === 1 ? "item is" : "items are"} still open. The board will see them as open.`}</DialogDescription>
        </DialogHeader>
        <Stepper
          step={step}
          onStepChange={(n) => { if (n < step || stepOk) { setStep(n); setErr(null); } }}
          onFinalStepCompleted={() => void send()}
          linear
          frame={false}
          nextDisabled={!stepOk}
          nextLoading={busy}
          nextButtonText="Continue"
          completeButtonText={busy ? "Sending" : sendLabel}
          // the long "Send to Dr X for sign-off" wraps on a phone instead of pushing the dialog sideways
          nextButtonProps={{ "data-testid": "send-next", className: "min-w-0 shrink! h-auto! min-h-[38px] py-2 leading-tight! text-left" } as React.ButtonHTMLAttributes<HTMLButtonElement>}
          backButtonProps={{ "data-testid": "send-back" } as React.ButtonHTMLAttributes<HTMLButtonElement>}
          data-testid="send-steps"
        >
          <Step title="Meeting">
            <p className="mb-2 text-sm font-medium" id="send-meeting">Which meeting</p>
            {meetingsq.isLoading ? <div className="space-y-2" aria-busy="true"><div className="skeleton-line h-10 w-full" /><div className="skeleton-line h-10 w-full" /></div> : (
              <div role="radiogroup" aria-labelledby="send-meeting" className="grid gap-1.5">
                {meetings.map((m, i) => (
                  <Choice key={m.id} on={meetingId === m.id} onPick={() => setMeetingId(m.id)} testId="send-meeting" icon={<CalendarDays className="size-4 shrink-0 text-muted-foreground" aria-hidden />}
                    title={meetingWords(m)} text={i === 0 ? "The next open meeting" : undefined} />
                ))}
                <Choice on={meetingId === NOT_SCHEDULED} onPick={() => setMeetingId(NOT_SCHEDULED)} testId="send-meeting-none" title="Not scheduled yet (the coordinator will pick)"
                  text={meetings.length ? undefined : "No meeting is planned yet."} />
              </div>
            )}
            {meetingsq.error ? <p className="mt-2 text-xs text-warn">The meetings could not be loaded. You can still send it; the coordinator picks the meeting.</p> : null}
          </Step>
          <Step title="List">
            <p className="mb-2 text-sm font-medium" id="send-list">For discussion or for noting</p>
            <div role="radiogroup" aria-labelledby="send-list" className="grid gap-1.5 sm:grid-cols-2">
              {LISTS.map((l) => <Choice key={l.id} on={list === l.id} onPick={() => setList(l.id)} title={l.title} text={l.text} testId={`send-list-${l.id}`} />)}
            </div>
          </Step>
          <Step title="Presenter">
            <p className="mb-2 text-sm font-medium" id="send-presenter">Who presents it at the meeting</p>
            <div role="radiogroup" aria-labelledby="send-presenter" className="grid gap-1.5">
              {presenters.map((p) => <Choice key={p.value || "consultant"} on={presenter === p.value} onPick={() => setPresenter(p.value)} title={p.title} text={p.text} testId="send-presenter"
                icon={<UserRound className="size-4 shrink-0 text-muted-foreground" aria-hidden />} />)}
            </div>
            {residents.length === 0 ? <p className="mt-2 text-xs text-muted-foreground">No resident is on the team; add one from Team to let them present.</p> : null}
          </Step>
          <Step title="Note">
            <div className="space-y-3">
              {blockers.length ? (
                <div>
                  <p className="text-sm font-medium">Still open ({left})</p>
                  <ul className="mt-1 max-h-40 divide-y divide-border overflow-y-auto rounded-md border border-border" data-testid="send-open-items">
                    {blockers.map((b, i) => <li key={`${b.slot_id}-${i}`} className="flex items-start gap-2 px-3 py-1.5 text-sm"><CircleAlert className="mt-0.5 size-4 shrink-0 text-warn" aria-hidden /><span className="min-w-0 break-words">{b.why}</span></li>)}
                  </ul>
                </div>
              ) : left === 0 ? (
                <p className="flex items-center gap-2 text-sm text-ok"><CheckCircle2 className="size-4" aria-hidden />Nothing left before the board.</p>
              ) : null}
              {needReason ? (
                <div>
                  <label htmlFor="ready-reason" className="text-sm font-medium">Why send it with {left} {left === 1 ? "item" : "items"} open <span className="text-xs font-normal text-bad">required</span></label>
                  <Textarea id="ready-reason" value={reason} onChange={(e) => setReason(e.target.value)} className="mt-1 min-h-16 text-sm" maxLength={400}
                    placeholder="For example: the surgery date is close; the pathology report is due before the meeting" aria-required="true" />
                </div>
              ) : null}
              <div>
                <label htmlFor="ready-note" className="text-sm font-medium">Note for the coordinator (optional)</label>
                <Textarea id="ready-note" value={note} onChange={(e) => setNote(e.target.value)} className="mt-1 min-h-16 text-sm" maxLength={400} placeholder="Anything the board should know before the meeting" />
              </div>
            </div>
          </Step>
          <Step title="Confirm">
            <KeyValueList className="rounded-md border border-border p-3" >
              <KeyValue label="Meeting" value={chosenMeeting ? meetingWords(chosenMeeting) : "Not scheduled yet (the coordinator will pick)"} />
              <KeyValue label="List" value={LISTS.find((l) => l.id === list)?.title} />
              <KeyValue label="Presenter" value={presenterTitle} />
              <KeyValue label="Open items" value={left === 0 ? "None" : `${left}: ${reason.trim()}`} />
              <KeyValue label="Note" value={note.trim()} fallback="none" />
            </KeyValueList>
            <p className="mt-2 flex items-start gap-1.5 text-xs text-muted-foreground">{resident ? <NotebookPen className="mt-0.5 size-3.5 shrink-0" aria-hidden /> : <MessageSquareText className="mt-0.5 size-3.5 shrink-0" aria-hidden />}
              {resident ? `${consultantTitle(consultantName, true)} signs off before it goes to the board.` : "The MDT Coordinator is told; the coordinator may still move it on the agenda."}</p>
            {boardQuestionMissing ? <p role="alert" className="mt-2 rounded-md px-2 py-1.5 text-sm status-bad">The board question is not written yet. Enter it on the Board question line first.</p> : null}
            {err ? <p role="alert" className="mt-2 text-sm text-bad">{err}</p> : null}
          </Step>
        </Stepper>
      </DialogContent>
    </Dialog>
  );
}
