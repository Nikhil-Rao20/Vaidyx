// /meetings/:id: the agenda page before the meeting, the coordinator's control view during it, a read-only agenda for
// everyone else, and the old session read-only when the new route is not on the server.
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, Check, Copy, KeyRound, ListPlus, MonitorPlay, Play, Presentation, Send, Users, Video, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { notify } from "@/components/Toasts";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { api, TB } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useMeetingLive, type AgendaRow, type MeetingState } from "@/lib/live";
import { addToAgenda, cancelMeeting, getOldSession, meetingDeckUrl, newCode, putAgenda, remindCase, sendAgenda, startMeeting } from "./api";
import { AgendaLists } from "./components/AgendaLists";
import { ControlView } from "./components/ControlView";
import { LiveDot, MeetingStatusChip, MembersStrip } from "./components/shared";
import { EmptyState, ErrorState, LoadingButton, NotYetState, SkeletonLines, errorText, fmtDate, fmtDateTime, useAnnounce, useCopy } from "@/features/casefile/components/common";

function OldSessionView({ sid }: { sid: string }) {
  const q = useQuery({ queryKey: ["old-session", sid], queryFn: () => getOldSession(sid), retry: false });
  if (q.isLoading) return <SkeletonLines n={4} />;
  if (q.isError) return <ErrorState error={q.error} retry={() => void q.refetch()} />;
  const s = q.data!.session;
  return (
    <div className="space-y-3" data-testid="old-session">
      <NotYetState what="The new meeting page" fallback="This is the old board session, read-only. Run it from /tb." />
      <div className="surface p-4">
        <h1>{fmtDate(s.date)}{s.title ? `, ${s.title}` : ""}</h1>
        <div className="mt-1"><MeetingStatusChip status={s.status} /></div>
        <ol className="mt-3 space-y-1 text-sm list-decimal pl-5">{(s.agenda ?? []).map((a) => <li key={a.case_id}><Link className="text-link underline" to={`/cases/${a.case_id}`}>{a.case_id}</Link>{a.owner_ready ? " (ready)" : ""}</li>)}</ol>
      </div>
    </div>
  );
}

/** Case Files listed for the board on the meeting's date that are not on the agenda yet (old route /sessions/candidates). */
function AddCaseDialog({ open, onOpenChange, date, onAgenda, onAdd }: { open: boolean; onOpenChange: (o: boolean) => void; date: string; onAgenda: Set<string>; onAdd: (cid: string, list: "discussion" | "noting") => Promise<void> }) {
  const q = useQuery({ queryKey: ["candidates", date], queryFn: () => api.get<{ cases: Array<{ case_id: string; patient?: { name?: string; agesex?: string; mrn?: string }; protocol_label?: string; protocol?: string; ready?: unknown; gate?: { satisfied?: number; total?: number } }> }>(`${TB}/sessions/candidates?date=${encodeURIComponent(date)}`), enabled: open, retry: false });
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const add = async (cid: string, list: "discussion" | "noting") => { setBusy(cid + list); setErr(null); try { await onAdd(cid, list); } catch (e) { setErr(errorText(e)); } finally { setBusy(null); } };
  const rows = (q.data?.cases ?? []).filter((c) => !onAgenda.has(c.case_id));
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent aria-describedby="add-desc" data-testid="add-case-dialog">
        <DialogHeader>
          <DialogTitle>Add a Case File to the agenda</DialogTitle>
          <DialogDescription id="add-desc">Case Files listed for the board on {fmtDate(date)}. Added after the agenda was sent, they are flagged to the members.</DialogDescription>
        </DialogHeader>
        {q.isLoading ? <SkeletonLines n={3} /> : null}
        {q.isError ? <p className="text-sm text-muted-foreground">The list of Case Files for this date could not be read ({errorText(q.error)}). Type the Case File id below.</p> : null}
        {q.data && rows.length === 0 ? <p className="text-sm text-muted-foreground">Every Case File listed for this date is already on the agenda.</p> : null}
        <ul className="max-h-64 overflow-y-auto divide-y divide-border rounded-md border border-border empty:hidden">
          {rows.map((c) => (
            <li key={c.case_id} className="flex items-center gap-2 px-2 py-1.5 text-sm">
              <span className="flex-1 min-w-0 truncate">{c.patient?.name ?? c.case_id}{c.patient?.agesex ? `, ${c.patient.agesex}` : ""}<span className="text-xs text-muted-foreground"> {(c.protocol_label ?? c.protocol ?? "").replace(/_/g, " ")}{c.ready ? ", ready" : ", not marked ready"}{typeof c.gate?.total === "number" ? `, ${c.gate.satisfied ?? 0} of ${c.gate.total} records` : ""}</span></span>
              <LoadingButton size="xs" loading={busy === c.case_id + "discussion"} onClick={() => void add(c.case_id, "discussion")}>Discussion</LoadingButton>
              <LoadingButton size="xs" variant="outline" loading={busy === c.case_id + "noting"} onClick={() => void add(c.case_id, "noting")}>Noting</LoadingButton>
            </li>
          ))}
        </ul>
        <form className="flex gap-1.5" onSubmit={(e) => { e.preventDefault(); if (typed.trim()) void add(typed.trim(), "discussion"); }}>
          <label htmlFor="add-cid" className="sr-only">Case File id</label>
          <Input id="add-cid" value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="or type a Case File id, for example TB-005" className="h-8 text-sm" maxLength={60} />
          <LoadingButton size="sm" type="submit" loading={busy === typed.trim() + "discussion"} disabled={!typed.trim()}>Add</LoadingButton>
        </form>
        {err ? <p role="alert" className="text-sm text-bad">{err}</p> : null}
        <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Done</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function reorderLocally(s: MeetingState, discussion: string[], noting: string[]): MeetingState {
  const all = new Map<string, AgendaRow>([...s.agenda.discussion, ...s.agenda.noting].map((r) => [r.case_id, r]));
  const pick = (ids: string[]) => ids.map((id) => all.get(id)).filter((r): r is AgendaRow => !!r);
  return { ...s, agenda: { ...s.agenda, discussion: pick(discussion), noting: pick(noting) } };
}

export default function MeetingAgendaPage() {
  const { id = "" } = useParams();
  const { me } = useSession();
  const live = useMeetingLive(id);
  const [copied, copy] = useCopy();
  const [announce, liveNode] = useAnnounce();
  const [err, setErr] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const s = live.state;
  const canManage = !!(s?.can?.manage ?? me?.roles?.coordinator);
  const wrap = <T,>(fn: () => Promise<T>, said?: string) => async () => { setErr(null); try { const r = await fn(); if (said) announce(said); await live.refresh(); return r; } catch (e) { setErr(errorText(e)); await live.refresh(); throw e; } };
  const reorder = useMutation({
    mutationFn: (x: { d: string[]; n: string[] }) => {
      live.setState((old) => (old ? reorderLocally(old, x.d, x.n) : old));
      return wrap(() => putAgenda(id, x.d, x.n), "Agenda order saved.")();
    },
  });
  const send = useMutation({ mutationFn: () => wrap(() => sendAgenda(id), "Agenda sent to the members.")() });
  const remind = useMutation({ mutationFn: (cid: string) => wrap(() => remindCase(id, cid), "Reminder sent to the owner.")() });
  const code = useMutation({ mutationFn: () => wrap(() => newCode(id), "New join code ready.")() });
  const start = useMutation({ mutationFn: () => wrap(() => startMeeting(id), "The meeting has started. This page is now the control view.")() });
  const cancel = useMutation({ mutationFn: () => wrap(() => cancelMeeting(id, cancelReason.trim() || undefined), "Meeting cancelled.")(), onSuccess: () => setCancelOpen(false) });
  const addCase = async (cid: string, list: "discussion" | "noting") => {
    await wrap(() => addToAgenda(id, cid, list), `Added for ${list}.`)();
    const name = [...(live.state?.agenda.discussion ?? []), ...(live.state?.agenda.noting ?? [])].find((r) => r.case_id === cid)?.patient_line ?? cid;
    notify.success(`Added for ${list}`, `${name} is on the agenda${live.state?.meeting.agenda_sent_at ? "; the members see it flagged as added later" : ""}.`);
  };

  if (live.notBuilt) return <div className="max-w-4xl mx-auto"><OldSessionView sid={id} /></div>;
  if (live.isLoading) return <div className="max-w-5xl mx-auto space-y-3" aria-busy="true"><div className="skeleton-line h-8 w-1/3" /><div className="surface p-4"><SkeletonLines n={5} /></div></div>;
  if (!s) {
    return (
      <div className="max-w-xl mx-auto py-8">
        {live.missing ? <EmptyState title="This meeting does not exist" text="The link may be old, or the meeting was removed." action={<Button asChild variant="outline"><Link to="/meetings"><ArrowLeft className="size-4" />All meetings</Link></Button>} />
          : live.forbidden ? <EmptyState title="You are not on this meeting" text="Join with the 6-digit code from the MDT Coordinator; you wait until they admit you." action={<Button asChild><Link to="/meetings/join"><KeyRound className="size-4" />Join with a code</Link></Button>} />
          : <ErrorState error={live.error} retry={() => void live.refresh()} />}
      </div>
    );
  }

  const inSession = s.meeting.status === "in_session";
  const closed = s.meeting.status === "closed";
  const cancelled = s.meeting.status === "cancelled";
  const total = s.agenda.discussion.length + s.agenda.noting.length;
  const onAgenda = new Set([...s.agenda.discussion, ...s.agenda.noting, ...s.agenda.not_ready].map((r) => r.case_id));
  const amIn = s.me?.status === "present" || s.me?.status === "remote";

  return (
    <div className="space-y-4 max-w-6xl mx-auto pb-24 lg:pb-8" data-testid="meeting-page" data-meeting-status={s.meeting.status}>
      {liveNode}
      <header className="surface p-4 flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs text-muted-foreground"><Link to="/meetings" className="hover:underline inline-flex items-center gap-1"><ArrowLeft className="size-3" aria-hidden />Meetings</Link></p>
          <h1 className="break-words sm:truncate">Tumour Board, {fmtDate(s.meeting.date)}{s.meeting.time ? ` at ${s.meeting.time}` : ""}</h1>
          <p className="text-sm text-muted-foreground flex flex-wrap gap-x-3">
            {s.meeting.room ? <span>{s.meeting.room}</span> : null}
            <span>{total} on the agenda{s.meeting.minutes_per_case ? `, ${s.meeting.minutes_per_case} min each` : ""}</span>
            {s.meeting.video ? <span className="inline-flex items-center gap-1"><Video className="size-3.5" aria-hidden />video on</span> : null}
            {s.meeting.agenda_sent_at ? <span>agenda sent {fmtDateTime(s.meeting.agenda_sent_at)}</span> : <span>agenda not sent</span>}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-2"><MeetingStatusChip status={s.meeting.status} /><LiveDot status={live.status} detail={live.statusDetail} /></div>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {(canManage || amIn) && !cancelled && !me?.roles?.outside_expert ? <Button asChild size="sm" variant="ghost" title={closed ? "The deck with the outcomes and the minutes (.pptx)" : "The agenda deck (.pptx)"}><a href={meetingDeckUrl(id)} download><Presentation className="size-4" />{closed ? "Deck with minutes" : "Deck"}</a></Button> : null}
          {!closed && !cancelled && (amIn || !canManage) ? <Button asChild size="sm" variant="outline"><Link to={`/meetings/${id}/member`}><Users className="size-4" />Member view</Link></Button> : null}
          {canManage && !closed && !cancelled ? <Button asChild size="sm" variant="outline"><Link to={`/meetings/${id}/room`} target="_blank" rel="noopener" title="Opens the full-screen room screen in a new tab, for the room computer"><MonitorPlay className="size-4" />Room screen</Link></Button> : null}
          {canManage && !inSession && !closed && !cancelled ? <LoadingButton size="sm" loading={start.isPending} loadingText="Starting" onClick={() => start.mutate()} disabled={total === 0} title={total === 0 ? "Add a Case File to the agenda first" : "Starts the meeting; this page becomes the control view"} data-testid="start-meeting"><Play className="size-4" />Start meeting</LoadingButton> : null}
          {canManage && !inSession && !closed && !cancelled && total === 0 ? <p className="basis-full text-right text-xs text-muted-foreground">Add a Case File to the agenda to start.</p> : null}
        </div>
      </header>
      {err ? <p role="alert" className="text-sm text-bad rounded-md bg-bad-soft px-3 py-2">{err}</p> : null}
      {cancelled ? <div className="surface p-4"><EmptyState kind="wait" title="This meeting was cancelled" text={s.meeting.cancelled?.reason ? `Reason: ${s.meeting.cancelled.reason}` : "The members were told."} /></div> : null}

      {inSession && canManage ? <ControlView mid={id} state={s} onChanged={() => void live.refresh()} liveStatus={live.status} liveDetail={live.statusDetail} /> : null}

      {!inSession && !closed && !cancelled || (inSession && !canManage) ? (
        <div className="grid gap-4 lg:grid-cols-12 items-start">
          <div className="lg:col-span-8 space-y-2">
            {inSession ? <p className="text-sm status-ok rounded-md px-3 py-2">The meeting is in session. <Link className="underline font-medium" to={`/meetings/${id}/member`}>Open the member view</Link> to follow the shared screen.</p> : null}
            <AgendaLists agenda={s.agenda} canManage={canManage && !inSession} onChange={(d, n) => reorder.mutate({ d, n })} onRemind={canManage ? (cid) => remind.mutate(cid) : undefined} remindBusy={remind.isPending} currentId={s.current?.case_id} onAddFromNotReady={canManage && !inSession ? (cid) => void addCase(cid, "discussion").catch(() => undefined) : undefined} />
            {canManage && !inSession ? <Button size="sm" variant="outline" onClick={() => setAddOpen(true)} data-testid="add-case"><ListPlus className="size-4" />Add a Case File</Button> : null}
          </div>
          <div className="lg:col-span-4 space-y-3">
            {canManage && !inSession ? (
              <section className="surface p-3 space-y-2" aria-label="Before the meeting">
                <h2 className="text-sm font-semibold">Before the meeting</h2>
                <LoadingButton size="sm" className="w-full" loading={send.isPending} loadingText="Sending" onClick={() => send.mutate()} disabled={total === 0} data-testid="send-agenda"><Send className="size-4" />{s.meeting.agenda_sent_at ? "Send the agenda again" : "Send agenda"}</LoadingButton>
                <p className="text-xs text-muted-foreground">Members get the list in-app; Case Files added later are flagged to them.</p>
                <div className="rounded-md border border-border p-2">
                  <p className="text-xs font-medium flex items-center gap-1"><KeyRound className="size-3.5" aria-hidden />Join code</p>
                  {s.code ? (
                    <div className="mt-1 flex items-center gap-2 flex-wrap">
                      <span className="mono text-2xl tracking-[0.3em]" data-testid="meeting-code">{s.code.value}</span>
                      <Button size="sm" variant="outline" onClick={() => copy(s.code!.value)} aria-label="Copy the join code">{copied ? <Check className="size-4" /> : <Copy className="size-4" />}{copied ? "Copied" : "Copy"}</Button>
                    </div>
                  ) : <p className="text-xs text-muted-foreground mt-1">No code yet. Members join with it from Meetings, Join with a code.</p>}
                  {s.code ? <p className="text-xs text-muted-foreground mt-0.5">expires {fmtDateTime(s.code.expires_at)}</p> : null}
                  <LoadingButton size="xs" variant={s.code ? "ghost" : "outline"} className="mt-1.5" loading={code.isPending} loadingText="Making the code" onClick={() => code.mutate()} data-testid="new-code"><KeyRound className="size-3" aria-hidden />{s.code ? "New code (the old one stops working)" : "Create a code"}</LoadingButton>
                </div>
                <Button size="xs" variant="ghost" className="text-bad" onClick={() => setCancelOpen(true)}><XCircle className="size-3" />Cancel this meeting</Button>
              </section>
            ) : null}
            <section className="surface p-3" aria-label="Members">
              <h2 className="text-sm font-semibold mb-1">Members</h2>
              <MembersStrip attendance={s.attendance} hands={s.hands} />
              {!canManage && !amIn ? <p className="text-xs text-muted-foreground mt-2">Join with the 6-digit code from the coordinator: <Link className="text-link underline" to="/meetings/join">Join with a code</Link>.</p> : null}
            </section>
          </div>
        </div>
      ) : null}

      {closed ? (
        <div className="surface p-4" data-testid="meeting-closed">
          <h2 className="text-base">This meeting is closed</h2>
          <p className="text-sm text-muted-foreground">Outcomes were sent to the owners. The Case Files keep their board records.</p>
          <ol className="mt-2 space-y-1 text-sm">
            {[...s.agenda.discussion, ...s.agenda.noting].map((r) => <li key={r.case_id} className="flex items-center gap-2"><Link className="text-link underline" to={`/cases/${r.case_id}`}>{r.patient_line || r.case_id}</Link><span className="text-xs text-muted-foreground">{r.outcome_label ?? (r.outcome ? r.outcome.replace(/_/g, " ") : "no outcome saved")}</span></li>)}
          </ol>
        </div>
      ) : null}

      <AddCaseDialog open={addOpen} onOpenChange={setAddOpen} date={s.meeting.date} onAgenda={onAgenda} onAdd={addCase} />
      <Dialog open={cancelOpen} onOpenChange={(o) => { if (!cancel.isPending) setCancelOpen(o); }}>
        <DialogContent aria-describedby="cancel-desc">
          <DialogHeader><DialogTitle>Cancel this meeting?</DialogTitle><DialogDescription id="cancel-desc">The members of the agenda departments are told. The Case Files stay ready for the next meeting.</DialogDescription></DialogHeader>
          <label htmlFor="cancel-reason" className="text-sm font-medium">Reason (shown to the members)</label>
          <Input id="cancel-reason" value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} maxLength={300} placeholder="for example: holiday declared" />
          {cancel.isError ? <p role="alert" className="text-sm text-bad">{errorText(cancel.error)}</p> : null}
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancelOpen(false)} disabled={cancel.isPending}>Keep the meeting</Button>
            <LoadingButton variant="destructive" loading={cancel.isPending} onClick={() => cancel.mutate()}>Cancel the meeting</LoadingButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
