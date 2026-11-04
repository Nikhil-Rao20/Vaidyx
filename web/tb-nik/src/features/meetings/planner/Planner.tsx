// The one-page planner (meetings-v2 3.3, owner D8, D9 and D10): what the MDT Coordinator sees on a planned meeting. When and where at the
// top (edited in place, the weekly series line), the case list below (filled by itself in urgency order; reorder by drag or Up and Down,
// move to another meeting, remove with a reason, add a Case File), the two steps on the right of the top (Send agenda, Start meeting),
// and at the side the join code and the members (made by themselves), the meeting PDF and More (minutes per case, video, cancel).
// Every change goes to the server and the page reads the meeting again; a reorder shows at once and is put back if the server refuses.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { notify } from "@/components/Toasts";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { useSession } from "@/lib/session";
import { errorCode, type LiveStatus, type MeetingState } from "@/lib/live";
import { errorText, useAnnounce } from "@/features/casefile/components/common";
import { addToAgenda, arrangeAgenda, cancelMeeting, listSeries, moveToMeeting, newCode, remindCase, sendAgenda, startMeeting, takeOffAgenda, updateMeeting } from "../api";
import type { NewMeeting } from "../types";
import { PlanHeader } from "./PlanHeader";
import { JustAddedPlan, PlanLists, type RowActions } from "./PlanLists";
import { JoinCodeCard, MembersCard, MoreCard, PdfCard } from "./PlanSide";
import { AddCaseDialog, MoveDialog } from "./CaseDialogs";
import type { ListKey, PlanMeeting, PlanRow, PlanState } from "./types";
import { dayAndDate, useCancerLabel, whenWords } from "./util";

const nameOf = (r: PlanRow) => (r.patient_line || r.case_id).split(",")[0];

/** The urgency order of a list as the server keeps it (meetings.by_urgency): urgency 5 first (none last), then the earliest sent. */
export function byUrgency(rows: PlanRow[]): PlanRow[] {
  return rows.map((r, i) => ({ r, i })).sort((a, b) => (b.r.urgency ?? 0) - (a.r.urgency ?? 0) || String(a.r.sent_at ?? "").localeCompare(String(b.r.sent_at ?? "")) || a.i - b.i).map((x) => x.r);
}

export function Planner({ mid, state, setState, refresh, liveStatus, liveDetail }: {
  mid: string; state: PlanState;
  setState: (fn: (old: MeetingState | null) => MeetingState | null) => void;
  refresh: () => Promise<unknown>;
  liveStatus: LiveStatus; liveDetail?: string;
}) {
  const { me } = useSession();
  const qc = useQueryClient();
  const cancer = useCancerLabel();
  const [announce, liveNode] = useAnnounce();
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<null | "send" | "start" | "code" | "order">(null);
  const [codeErr, setCodeErr] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [moving, setMoving] = useState<PlanRow | null>(null);
  const [removing, setRemoving] = useState<PlanRow | null>(null);
  const [justAdded, setJustAdded] = useState<string | null>(null);
  const focusAfter = useRef<{ cid: string; dir: "up" | "down" } | null>(null);
  const m = state.meeting;
  const seriesQ = useQuery({ queryKey: ["meeting-series"], queryFn: listSeries, enabled: !!m.series_id, retry: false, staleTime: 30_000 });
  const series = m.series_id ? seriesQ.data?.series.find((x) => x.id === m.series_id) : undefined;
  const lists = { discussion: state.agenda.discussion, noting: state.agenda.noting };
  const total = lists.discussion.length + lists.noting.length;
  const onAgenda = new Set([...lists.discussion, ...lists.noting, ...state.agenda.not_ready].map((r) => r.case_id));

  // The join code is made by itself (owner D9): once, when the planned meeting has none; New code makes another.
  const triedCode = useRef(false);
  useEffect(() => {
    if (state.code || triedCode.current || m.status !== "planned") return;
    triedCode.current = true;
    setBusy("code");
    newCode(mid).then(() => refresh()).catch((e) => setCodeErr(`The code could not be made: ${errorText(e)}`)).finally(() => setBusy(null));
  }, [state.code, m.status, mid, refresh]);

  // The row just added is ringed for a few seconds and scrolled into view (the owner, 18 Oct: an add must be seen).
  useEffect(() => {
    if (!justAdded) return;
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const show = window.setTimeout(() => document.querySelector('[data-testid="agenda-row"][data-just-added="true"]')?.scrollIntoView({ block: "center", behavior: still ? "auto" : "smooth" }), 60);
    const done = window.setTimeout(() => setJustAdded(null), 5000);
    return () => { window.clearTimeout(show); window.clearTimeout(done); };
  }, [justAdded]);

  // Up and Down keep the keyboard on the row that moved (the other arrow when it reached the end).
  useLayoutEffect(() => {
    const f = focusAfter.current;
    if (!f) return;
    focusAfter.current = null;
    const pick = (dir: string) => document.querySelector<HTMLButtonElement>(`[data-reorder="${f.cid}-${dir}"]`);
    const b = pick(f.dir);
    (b && !b.disabled ? b : pick(f.dir === "up" ? "down" : "up"))?.focus();
  });

  const run = async <T,>(fn: () => Promise<T>, said?: string): Promise<T> => {
    setErr(null);
    try { const r = await fn(); if (said) announce(said); await refresh(); return r; }
    catch (e) { setErr(errorText(e)); await refresh(); throw e; }
  };
  const quiet = (p: Promise<unknown>) => { void p.catch(() => undefined); };

  const saveMeeting = async (f: Partial<NewMeeting> & { title?: string }) => {
    await updateMeeting(mid, f as Partial<NewMeeting>);  // the server takes the title too (meetings.update)
    await refresh();
    if (f.date || f.time) { void qc.invalidateQueries({ queryKey: ["meeting-series"] }); notify.success("Saved", `${whenWords(f.date ?? m.date, f.time ?? m.time)}${m.agenda_sent_at ? ". The member departments are told." : "."}`); }
    else announce("Saved.");
  };

  /** A new order of one list: shown at once, then kept by the server (arranged by hand from now on). */
  const arrange = (list: ListKey, ids: string[], focus?: { cid: string; dir: "up" | "down" }) => {
    const d = list === "discussion" ? ids : lists.discussion.map((r) => r.case_id);
    const n = list === "noting" ? ids : lists.noting.map((r) => r.case_id);
    focusAfter.current = focus ?? null;
    setState((old) => {
      if (!old) return old;
      const all = new Map([...old.agenda.discussion, ...old.agenda.noting].map((r) => [r.case_id, r]));
      const pick = (xs: string[]) => xs.map((x) => all.get(x)).filter((r): r is PlanRow => !!r);
      const o = old as unknown as PlanState;
      return { ...old, agenda: { ...old.agenda, discussion: pick(d), noting: pick(n) }, agenda_order: { ...o.agenda_order, [list]: "hand" } } as unknown as MeetingState;
    });
    setBusy("order");
    const moved = focus ? lists[list].find((r) => r.case_id === focus.cid) : null;
    quiet(run(() => arrangeAgenda(mid, d, n), moved ? `${nameOf(moved)} moved ${focus!.dir}. Order saved.` : "Order saved.").finally(() => setBusy(null)));
  };

  const actions: RowActions = {
    onReorder: arrange,
    onMove: (r) => setMoving(r),
    onRemove: (r) => setRemoving(r),
    onOtherList: (r, from) => {
      const to: ListKey = from === "discussion" ? "noting" : "discussion";
      const rest = lists[from].filter((x) => x.case_id !== r.case_id);
      // Kept in urgency order when the other list is (the server then does not count it as arranged by hand).
      const target = state.agenda_order?.[to] === "hand" ? [...lists[to], r] : byUrgency([...lists[to], r]);
      const d = (from === "discussion" ? rest : target).map((x) => x.case_id);
      const n = (from === "noting" ? rest : target).map((x) => x.case_id);
      quiet(run(() => arrangeAgenda(mid, d, n), `${nameOf(r)} is now ${to === "noting" ? "for noting" : "for discussion"}.`));
    },
    onRemind: (r) => quiet(run(() => remindCase(mid, r.case_id), `Reminder sent to the treating team of ${nameOf(r)}.`)),
  };

  const addCase = async (cid: string, list: ListKey, name: string) => {
    await run(() => addToAgenda(mid, cid, list), `Added for ${list}.`);
    setAddOpen(false);
    setJustAdded(cid);
    notify.success(list === "discussion" ? "Added for discussion" : "Added for noting", `${name} is on the agenda${m.agenda_sent_at ? "; the members see it flagged as added later" : ""}.`);
  };

  const moveCase = async (r: PlanRow, to: PlanMeeting, reason: string) => {
    const list: ListKey = lists.noting.some((x) => x.case_id === r.case_id) ? "noting" : "discussion";
    try { await moveToMeeting(r.case_id, to.id, reason); }
    catch (e) {
      // A Case File put on by hand that was never sent to the board: put it on the other meeting (it leaves this one by itself).
      if (errorCode(e) !== "not_sent") throw e;
      await addToAgenda(to.id, r.case_id, list);
    }
    await refresh();
    void qc.invalidateQueries({ queryKey: ["meetings"] });
    notify.success("Moved", `${nameOf(r)} is on the meeting of ${whenWords(to.date, to.time)}.`);
  };

  const removeCase = async (r: PlanRow, reason: string) => {
    try { await takeOffAgenda(r.case_id, reason); }
    catch (e) {
      const code = errorCode(e);
      if (code !== "not_sent" && code !== "not_on_agenda") throw e;
      await arrangeAgenda(mid, lists.discussion.filter((x) => x.case_id !== r.case_id).map((x) => x.case_id), lists.noting.filter((x) => x.case_id !== r.case_id).map((x) => x.case_id));
    }
    await refresh();
    notify.success("Removed from this meeting", `${nameOf(r)} stays marked ready for a later meeting.`);
  };

  const send = () => {
    setBusy("send");
    quiet(run(() => sendAgenda(mid), "Agenda sent.").then((r) => {
      const to = (r as { sent_to?: unknown[] } | undefined)?.sent_to;
      notify.success(m.agenda_sent_at ? "Agenda sent again" : "Agenda sent", Array.isArray(to) ? `To ${to.length} department${to.length === 1 ? "" : "s"}, in Vaidyx.` : undefined);
    }).finally(() => setBusy(null)));
  };
  const start = () => { setBusy("start"); quiet(run(() => startMeeting(mid), "The meeting has started.").finally(() => setBusy(null))); };
  const makeCode = () => { setBusy("code"); setCodeErr(null); quiet(run(() => newCode(mid), "New join code ready.").catch((e) => setCodeErr(errorText(e))).finally(() => setBusy(null))); };
  const urgency = (list: ListKey) => {
    setBusy("order");
    quiet(run(() => arrangeAgenda(mid, lists.discussion.map((r) => r.case_id), lists.noting.map((r) => r.case_id), [list]), "Back in urgency order.").finally(() => setBusy(null)));
  };

  return (
    <div className="mx-auto max-w-6xl space-y-4 pb-24 lg:pb-8" data-testid="meeting-page" data-meeting-status={m.status} data-planner="coordinator">
      {liveNode}
      <PlanHeader m={m} canEdit series={series} onSeriesChanged={() => { void seriesQ.refetch(); void refresh(); void qc.invalidateQueries({ queryKey: ["meetings"] }); }}
        onSave={saveMeeting} liveStatus={liveStatus} liveDetail={liveDetail}
        steps={{ total, sending: busy === "send", onSend: send, starting: busy === "start", onStart: start }} />
      {err ? <p role="alert" className="rounded-md bg-bad-soft px-3 py-2 text-sm text-bad">{err}</p> : null}
      <div className="grid items-start gap-4 lg:grid-cols-12">
        <div className="min-w-0 lg:col-span-8">
          <JustAddedPlan.Provider value={justAdded}>
            <PlanLists state={state} canManage cancer={cancer} actions={actions} onUrgency={urgency} urgencyBusy={busy === "order"} onAdd={() => setAddOpen(true)}
              onToDiscussion={(cid) => { const r = state.agenda.not_ready.find((x) => x.case_id === cid); quiet(addCase(cid, "discussion", r ? nameOf(r) : cid)); }}
              onRemind={actions.onRemind} />
          </JustAddedPlan.Provider>
        </div>
        <aside className="min-w-0 space-y-3 lg:col-span-4" aria-label="The meeting's members, code and options">
          <JoinCodeCard code={state.code} onNew={makeCode} busy={busy === "code"} error={codeErr} />
          <MembersCard state={state} />
          <PdfCard mid={mid} after={false} />
          <MoreCard m={m} total={total} videoAvailable={!!me?.features?.video} onSave={saveMeeting}
            onCancel={async (reason) => {
              await cancelMeeting(mid, reason);
              await refresh();
              void qc.invalidateQueries({ queryKey: ["meetings"] });
              notify.success("Meeting cancelled", `${dayAndDate(m.date)}. ${total ? "Its Case Files went to the next planned meeting, or wait for the next one." : ""}`.trim());
            }} />
        </aside>
      </div>
      <AddCaseDialog open={addOpen} onOpenChange={setAddOpen} onAgenda={onAgenda} onAdd={addCase} />
      <MoveDialog row={moving} meetingId={mid} onOpenChange={(o) => { if (!o) setMoving(null); }} onMove={moveCase} />
      <ConfirmDialog open={!!removing} onOpenChange={(o) => { if (!o) setRemoving(null); }} destructive requireReason reasonLabel="Reason (kept with the Case File)"
        title="Remove from this meeting?" confirmText="Remove" doneText="Removed"
        text={removing ? `${nameOf(removing)} comes off the agenda of ${dayAndDate(m.date)}. It stays marked ready, so it can go to a later meeting.` : ""}
        onConfirm={(reason) => (removing ? removeCase(removing, reason) : undefined)} />
    </div>
  );
}
