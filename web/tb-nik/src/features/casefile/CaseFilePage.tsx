// The Case File page: the fill-in summary. Header strip, then two columns on a laptop (summary left, Ask and Reports
// right) and tabs on a phone. Small steps act in place with Undo; evidence steps open the right side panel; only
// Mark ready, Archive and Sign use a modal.
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { Archive, ArrowLeft, BellRing, Eye } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError } from "@/lib/api";
import {
  archiveCase, buildSummary, clearSlotValue, createFreeRequest, exportVtbUrl, getPublished, getRequestDraft, markReady, notBuiltYet, postConfirmation, unarchiveCase,
  postProposal, remindRequest, reviewArtefact, sendRequest, setSlotValue, setUrgency, slotAskDepartment, slotNotNeeded,
} from "./api";
import { useCaseFile, useMyRole, useProposals, useRememberCase, useSlots, useTeam } from "./hooks";
import type { SlotAction } from "./types";
import { ArchiveDialog } from "./components/ArchiveDialog";
import { AskPanel } from "./components/AskPanel";
import { BoardFormPanel } from "./components/BoardFormPanel";
import { EmptyState, ErrorState, LoadingButton, SkeletonLines, errorText, plural, useAnnounce } from "./components/common";
import { useDeferred } from "./components/deferred";
import { HeaderStrip, type PanelKind } from "./components/HeaderStrip";
import { HelpersPanel, useHelpers } from "./components/HelpersPanel";
import { MarkReadyDialog } from "./components/MarkReadyDialog";
import { ProposalsStrip } from "./components/ProposalsStrip";
import { PublishedPanel } from "./components/PublishedPanel";
import { ReportsPanel } from "./components/ReportsPanel";
import { RequestEditPanel } from "./components/RequestEditPanel";
import { ReviewPanel } from "./components/ReviewPanel";
import { SidePanel } from "./components/SidePanel";
import type { SlotContext, SlotHandlers } from "./components/SlotLine";
import { SourceViewer, type SourceTarget } from "./components/SourceViewer";
import { SummaryColumn } from "./components/SummaryColumn";
import { TeamPanel } from "./components/TeamPanel";
import { RequestsOnlyView } from "./components/RequestsOnlyView";
import "./print.css";

type SideState =
  | { kind: "panel"; panel: Exclude<PanelKind, null> }
  | { kind: "source"; target: SourceTarget }
  | { kind: "review"; slotId: string }
  | { kind: "request"; slotId: string; action: SlotAction };

function useMinWidth(px: number): boolean {
  const [ok, setOk] = useState(() => (typeof window !== "undefined" ? window.matchMedia(`(min-width: ${px}px)`).matches : true));
  useEffect(() => {
    const mq = window.matchMedia(`(min-width: ${px}px)`);
    const on = () => setOk(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [px]);
  return ok;
}

const PANEL_TITLES: Record<Exclude<PanelKind, null>, string> = { helpers: "Specialty helpers", team: "Team", board: "Board form", published: "Published cases" };

export default function CaseFilePage() {
  const { id = "", view } = useParams();
  const nav = useNavigate();
  useRememberCase(id);
  const cfq = useCaseFile(id);
  const cf = cfq.data;
  // A supporting department sees only what it was asked for (access scope "requests"): no summary, chats, team or helpers.
  const requestsOnly = (cf?.access?.scope ?? "").toLowerCase() === "requests";
  const full = !!cf && !requestsOnly;
  const slotsq = useSlots(id, cf, !requestsOnly);
  const role = useMyRole(cf);
  const teamq = useTeam(id, cf, !requestsOnly);
  const proposalsq = useProposals(id, full && !role.resident);
  const helpersq = useHelpers(id, cf, full);
  const publishedq = useQuery({ queryKey: ["published", id], queryFn: () => getPublished(id), retry: false, enabled: full });
  const deferred = useDeferred();
  const wide = useMinWidth(1024);
  const [announce, liveNode] = useAnnounce();
  const [stack, setStack] = useState<SideState[]>([]);
  const [readyOpen, setReadyOpen] = useState(false);
  const [tab, setTab] = useState("summary");
  const [proseBusy, setProseBusy] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  const [urgencyBusy, setUrgencyBusy] = useState(false);
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [unarchiving, setUnarchiving] = useState(false);

  const side = stack[stack.length - 1] ?? null;
  const open = useCallback((s: SideState) => setStack((st) => [...st.filter((x) => !(x.kind === "panel" && s.kind === "panel")), s]), []);
  const closeAll = useCallback(() => setStack([]), []);
  const PANEL_VIEWS = ["helpers", "team", "board", "published"];
  // The panel views are links too (/cases/:id/team): opening one from the header updates the address, closing returns.
  const openPanelLinked = (p: Exclude<PanelKind, null>) => { open({ kind: "panel", panel: p }); nav(`/cases/${encodeURIComponent(id)}/${p}`, { replace: true }); };
  const closeLinked = () => { closeAll(); if (view && PANEL_VIEWS.includes(view)) nav(`/cases/${encodeURIComponent(id)}`, { replace: true }); };
  const back = useCallback(() => setStack((st) => st.slice(0, -1)), []);
  const activePanel: PanelKind = side?.kind === "panel" ? side.panel : null;

  const slots = slotsq.data;
  const allSlots = useMemo(() => (slots?.sections ?? []).flatMap((s) => s.slots), [slots]);
  const reviewQueue = useMemo(() => allSlots.filter((s) => s.status === "needs_confirmation"), [allSlots]);
  const consultantName = teamq.data?.owner?.doctors?.[0]?.name ?? cf?.access?.owner_name ?? "the consultant";
  const consultantShort = consultantName.replace(/^Dr\.?\s+/i, "");
  const canAct = !!cf && (role.resident || !!cf.permissions?.send_request || !!cf.permissions?.mark_ready || !!cf.permissions?.upload);

  const refresh = useCallback(async () => { await cfq.refresh(); await slotsq.refetch(); await proposalsq.refetch(); }, [cfq, slotsq, proposalsq]);

  useEffect(() => { if (flash) { const t = window.setTimeout(() => setFlash(null), 6000); return () => window.clearTimeout(t); } return undefined; }, [flash]);
  // /cases/:id/<view> opens the matching panel or tab once the Case File is on screen.
  useEffect(() => {
    if (!cf || !view) return;
    if (view === "helpers" || view === "team" || view === "board" || view === "published") open({ kind: "panel", panel: view });
    else if (view === "reports" || view === "ask") setTab(view);
    // only on arrival
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [!!cf, view]);

  // ---- the real calls behind the in-place steps -------------------------------------------------------------------
  const propose = useCallback(async (action: string, payload: Record<string, unknown>, label: string) => {
    try {
      await postProposal(id, action, payload);
      announce(`Sent to Dr ${consultantShort} to sign off: ${label}`);
      setFlash(`Dr ${consultantShort} has been asked to sign off: ${label}.`);
      await proposalsq.refetch();
    } catch (e) {
      if (notBuiltYet(e)) throw new Error("Asking the consultant to sign off is not available on this server yet.");
      throw e;
    }
  }, [id, announce, consultantShort, proposalsq]);

  const handlers: SlotHandlers = useMemo(() => ({
    openSource: (t) => open({ kind: "source", target: t }),
    review: (slot) => open({ kind: "review", slotId: slot.id }),
    editRequest: (slot, action) => open({ kind: "request", slotId: slot.id, action }),
    ask: async (slot, action) => {
      try {
        if (!slotsq.derived) { await slotAskDepartment(id, slot.id); }
        else if (action.action_id) { const d = await getRequestDraft(id, action.action_id); await sendRequest(id, action.action_id, { message: d.body, due: d.due, subject: d.subject }); }
        else if (action.department) { await createFreeRequest(id, { department: action.department, label: slot.label }); }
        else throw new Error("There is no department to ask for this line.");
      } catch (e) { setFlash(`Could not send the request: ${errorText(e)}`); throw e; }
      await refresh();
    },
    notNeeded: async (slot, reason) => {
      try {
        if (!slotsq.derived) await slotNotNeeded(id, slot.id, reason);
        else await postConfirmation(id, { type: "waive", key: slot.id, reason });
      } catch (e) { setFlash(`Could not mark it not needed: ${errorText(e)}`); throw e; }
      await refresh();
    },
    remind: async (slot) => {
      const aid = slot.request?.action_id;
      if (!aid) throw new Error("There is no sent request to remind about.");
      try { await remindRequest(id, aid); } catch (e) { setFlash(`Could not send the reminder: ${errorText(e)}`); throw e; }
      await refresh();
    },
    enterValue: async (slot, value) => {
      try { await setSlotValue(id, slotsq.derived ? (slot.fact_id ?? slot.id) : slot.id, value); }
      catch (e) { if (notBuiltYet(e)) throw new Error("Typed values are not available on this server yet."); throw e; }
      await refresh();
    },
    clearValue: async (slot) => { await clearSlotValue(id, slotsq.derived ? (slot.fact_id ?? slot.id) : slot.id); await refresh(); },
    propose,
    schedule: deferred.schedule,
    undo: deferred.undo,
    pending: deferred.get,
  }), [id, slotsq.derived, refresh, propose, deferred.schedule, deferred.undo, deferred.get, open]);

  const slotCtx: SlotContext = useMemo(() => ({ resident: role.resident, canAct, consultantName: consultantShort, derived: slotsq.derived }), [role.resident, canAct, consultantShort, slotsq.derived]);

  // ---- header actions ------------------------------------------------------------------------------------------------
  const onMarkReady = async (note: string) => {
    if (role.resident) { await propose("mark_ready", { note }, "mark ready"); return; }
    await markReady(id, true, note);
    announce("Marked ready for the board.");
    await refresh();
  };
  const onReviewProse = async () => {
    try { await reviewArtefact(id, "summary", "reviewed"); }
    catch (e) { setFlash(`Could not mark it reviewed: ${errorText(e)}`); throw e; }
    announce("Narrative marked reviewed.");
    await refresh();
  };
  const onPrepareProse = async () => {
    setProseBusy(true);
    try {
      const r = await buildSummary(id, true);
      const status = typeof r.status === "string" ? r.status : "";
      if (status === "not_listed" || status === "gate_not_met") setFlash(String(r.message ?? "The narrative cannot be written yet: the checklist is not complete."));
      await refresh();
    } catch (e) { setFlash(errorText(e)); }
    finally { setProseBusy(false); }
  };
  const onUrgency = async (level: number, note?: string) => {
    setUrgencyBusy(true);
    try {
      const r = await setUrgency(id, level, note);
      announce(r.proposal ? `Dr ${consultantShort} asked to set urgency ${level}.` : `Urgency set to ${level}.`);
      await refresh();
    } catch (e) {
      if (notBuiltYet(e)) throw new Error("The urgency tag is not available on this server yet.");
      throw e;
    } finally { setUrgencyBusy(false); }
  };

  // ---- states ----------------------------------------------------------------------------------------------------------
  if (cfq.isLoading) {
    return (
      <div className="space-y-4 p-1" aria-busy="true" aria-label="Loading the Case File">
        <div className="surface p-4 space-y-2"><div className="skeleton-line h-7 w-1/3" /><div className="skeleton-line h-4 w-1/2" /><div className="skeleton-line h-4 w-2/5" /></div>
        <div className="grid gap-4 lg:grid-cols-12"><div className="lg:col-span-7 surface p-4"><SkeletonLines n={8} /></div><div className="lg:col-span-5 surface p-4"><SkeletonLines n={5} /></div></div>
      </div>
    );
  }
  if (cfq.error && !cf) {
    const e = cfq.error;
    const status = e instanceof ApiError ? e.status : 0;
    return (
      <div className="max-w-xl mx-auto py-8" data-testid="casefile-error" data-status={status}>
        {status === 404 ? <EmptyState title="This Case File does not exist" text={`No Case File with the id ${id}. The link may be old.`} action={<Button asChild variant="outline"><Link to="/home"><ArrowLeft className="size-4" />Back to Home</Link></Button>} />
          : status === 403 ? <EmptyState title="You do not have access to this Case File" text="Only the owner's team, the departments asked, and the MDT Coordinator can open it." action={<Button asChild variant="outline"><Link to="/home"><ArrowLeft className="size-4" />Back to Home</Link></Button>} />
          : <ErrorState error={e} retry={() => void cfq.refetch()} />}
      </div>
    );
  }
  if (!cf) return null;
  if (requestsOnly) return <RequestsOnlyView id={id} cf={cf} />;

  const prose = slots?.prose;
  const summaryArt = cf.state?.artefacts?.summary;
  const reviewed = prose?.reviewed ?? summaryArt?.review?.status === "reviewed";
  const exportAllowed = !!reviewed;
  const exportReason = exportAllowed ? null : summaryArt || prose?.status === "ready" ? "Review the narrative first, then export." : "Prepare and review the narrative first.";
  const left = slots ? slots.left_before_board : null;
  const blockersNow = !slotsq.derived ? slots?.blockers ?? [] : [];
  const mayMark = role.resident || !!cf.permissions?.mark_ready;
  const canMarkReady = !cf.case.board_ready && mayMark && blockersNow.length === 0;
  const markReadyReason = cf.case.board_ready ? null : !mayMark ? "Only the owner's consultant marks the Case File ready." : blockersNow.length ? blockersNow[0].why : null;
  const boardQuestionMissing = allSlots.some((s) => (s.fact_id ?? s.id) === "clinical_question" && (s.status === "not_found"));
  const isOwner = teamq.data?.can?.manage ?? (!!cf.permissions?.manage_participants || !!cf.permissions?.mark_ready);
  const canSetUrgency = teamq.data?.can ? !!(teamq.data.can.set_urgency || teamq.data.can.propose) : role.resident || !!cf.permissions?.mark_ready;
  const helpersCount = helpersq.helpers.length || 6;
  const publishedCount = publishedq.data?.items.length ?? 0;
  const panelTitle = side?.kind === "panel" ? PANEL_TITLES[side.panel] : side?.kind === "source" ? (side.target.title ?? "Source") : side?.kind === "review" ? "Review" : side?.kind === "request" ? "Edit the request" : "";
  const reviewSlot = side?.kind === "review" ? allSlots.find((s) => s.id === side.slotId) ?? null : null;
  const requestSlot = side?.kind === "request" ? allSlots.find((s) => s.id === side.slotId) ?? null : null;

  const summary = slots ? (
    <SummaryColumn slots={slots} derived={slotsq.derived} ctx={slotCtx} h={handlers} onReviewProse={onReviewProse} onPrepareProse={onPrepareProse} proseBusy={proseBusy} canReview={role.resident || !!cf.permissions?.review} docs={cf.documents} />
  ) : slotsq.error ? <ErrorState error={slotsq.error} retry={() => void slotsq.refetch()} /> : <div className="surface p-4"><SkeletonLines n={8} /></div>;
  const ask = <AskPanel caseId={id} docs={cf.documents} onOpenSource={handlers.openSource} compact={!wide} />;
  const reports = <ReportsPanel caseId={id} cf={cf} onOpenSource={handlers.openSource} onChanged={refresh} compact={!wide} />;

  return (
    <div id="casefile-print" className="space-y-3 pb-24 lg:pb-8" data-testid="casefile-page">
      {liveNode}
      <AnimatePresence>
        {cfq.stale ? (
          <motion.div key="stale" initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} role="status" className="sticky top-2 z-30 flex items-center gap-2 rounded-md border border-primary/50 bg-secondary px-3 py-2 text-sm shadow-[var(--shadow-outer)] print:hidden" data-testid="stale-banner">
            <BellRing className="size-4 text-brand" aria-hidden />
            <span className="flex-1">{plural(cfq.newCount, "new record", "new records")} since you looked.</span>
            <Button size="sm" onClick={() => { cfq.show(); announce("Showing the latest records."); }}><Eye className="size-4" />Show</Button>
          </motion.div>
        ) : null}
      </AnimatePresence>
      {flash ? <div role="status" className="rounded-md border border-border bg-card px-3 py-2 text-sm shadow-[var(--shadow-outer)] print:hidden">{flash}</div> : null}

      <HeaderStrip
        cf={cf} team={teamq.data} left={left} resident={role.resident} consultantName={consultantShort}
        canMarkReady={canMarkReady} markReadyReason={markReadyReason} onMarkReady={() => setReadyOpen(true)}
        onOpenPanel={(p) => (p ? openPanelLinked(p) : closeLinked())} activePanel={activePanel}
        onPrint={() => window.print()} exportAllowed={exportAllowed} exportReason={exportReason} exportHref={exportVtbUrl(id)}
        onUrgency={onUrgency} urgencyBusy={urgencyBusy} canSetUrgency={canSetUrgency}
        helpersCount={helpersCount} publishedCount={publishedCount} protocolLabel={slots?.protocol_label}
        onArchive={teamq.data?.can?.archive && !teamq.data?.archived ? () => setArchiveOpen(true) : undefined}
      />
      {teamq.data?.archived ? (
        <div role="status" className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-muted px-3 py-2 text-sm print:hidden" data-testid="archived-banner">
          <Archive className="size-4 text-muted-foreground" aria-hidden />
          <span className="flex-1">Archived{teamq.data.archived.by ? ` by ${teamq.data.archived.by}` : ""}{teamq.data.archived.reason ? `: ${teamq.data.archived.reason}` : ""}. Read-only until it is brought back.</span>
          {teamq.data.can?.archive ? <LoadingButton size="sm" variant="outline" loading={unarchiving} onClick={async () => { setUnarchiving(true); try { await unarchiveCase(id); announce("Brought back from the archive."); await teamq.refetch(); await refresh(); } catch (e) { setFlash(`Could not bring it back: ${errorText(e)}`); } finally { setUnarchiving(false); } }}>Bring back</LoadingButton> : null}
        </div>
      ) : null}
      {!role.resident && proposalsq.proposals.length ? <ProposalsStrip caseId={id} proposals={proposalsq.proposals} onChanged={refresh} labelOf={(sid) => allSlots.find((x) => x.id === sid)?.label} /> : null}
      {!canAct && !teamq.data?.archived ? (
        <p role="note" className="flex items-center gap-2 text-sm text-muted-foreground rounded-md bg-muted px-3 py-2 print:hidden" data-testid="read-only-note">
          <Eye className="size-4 shrink-0" aria-hidden />Read only for you: the owner's team ({teamq.data?.owner?.department_label || cf.access?.owner_name || "the Responsible Department"}) asks, enters values and marks it ready.
        </p>
      ) : null}

      {wide ? (
        <div className="grid gap-4 lg:grid-cols-12 items-start">
          <div className="lg:col-span-7 min-w-0" data-print-area>{summary}</div>
          <div className="lg:col-span-5 min-w-0 space-y-4 print:hidden">{ask}{reports}</div>
        </div>
      ) : (
        <Tabs value={tab} onValueChange={setTab} className="print:block">
          <div className="sticky top-14 z-20 -mx-4 px-4 py-2 bg-background/95 backdrop-blur border-b border-border print:hidden">
            <div className="flex items-center justify-between gap-2 text-sm">
              <span className="font-medium truncate">{cf.case.patient?.name}</span>
              <span className="text-xs text-muted-foreground shrink-0">{cf.case.board_ready ? "ready for the board" : left === null ? "" : left === 0 ? "nothing left before the board" : `${left} left before the board`}</span>
            </div>
            <TabsList className="mt-1.5 w-full grid grid-cols-3">
              <TabsTrigger value="summary">Summary</TabsTrigger>
              <TabsTrigger value="ask">Ask</TabsTrigger>
              <TabsTrigger value="reports">Reports</TabsTrigger>
            </TabsList>
          </div>
          <TabsContent value="summary" className="mt-3" data-print-area>{summary}</TabsContent>
          <TabsContent value="ask" className="mt-3 print:hidden">{ask}</TabsContent>
          <TabsContent value="reports" className="mt-3 print:hidden">{reports}</TabsContent>
        </Tabs>
      )}

      <SidePanel open={!!side} onClose={closeLinked} title={panelTitle} width={side?.kind === "source" ? "wide" : "normal"}
        subtitle={stack.length > 1 ? <button type="button" className="inline-flex items-center gap-1 text-link hover:underline" onClick={back}><ArrowLeft className="size-3" aria-hidden />Back</button> : side?.kind === "source" ? "Quotes are shown as printed; nothing is interpreted." : undefined}>
        {side?.kind === "panel" && side.panel === "helpers" ? <HelpersPanel caseId={id} cf={cf} onOpenSource={handlers.openSource} onCaseChanged={refresh} /> : null}
        {side?.kind === "panel" && side.panel === "team" ? <TeamPanel caseId={id} team={teamq.data} derived={teamq.derived} isOwner={isOwner} resident={role.resident} onChanged={async () => { await teamq.refetch(); await refresh(); }} me={role.me?.user ?? ""} /> : null}
        {side?.kind === "panel" && side.panel === "board" ? <BoardFormPanel cf={cf} coordinator={role.coordinator} /> : null}
        {side?.kind === "panel" && side.panel === "published" ? <PublishedPanel caseId={id} resident={role.resident} consultantName={consultantShort} onPropose={(payload, label) => propose("published_case", payload, label)} /> : null}
        {side?.kind === "source" ? <SourceViewer caseId={id} target={side.target} doc={cf.documents.find((d) => d.doc_id === side.target.docId)} /> : null}
        {side?.kind === "review" ? (reviewSlot ? (
          <ReviewPanel caseId={id} cf={cf} slot={reviewSlot} queue={reviewQueue} derived={slotsq.derived} resident={role.resident} consultantName={consultantShort}
            onOpenSource={handlers.openSource} onDone={refresh} onPropose={propose}
            onNext={(next) => setStack((st) => (next ? [...st.slice(0, -1), { kind: "review", slotId: next.id }] : st.slice(0, -1)))} />
        ) : <EmptyState title="Nothing left to review" text="This line is confirmed." className="py-6" />) : null}
        {side?.kind === "request" ? (requestSlot ? <RequestEditPanel caseId={id} slot={requestSlot} action={side.action} onSent={async () => { closeAll(); announce("Request sent."); await refresh(); }} /> : null) : null}
      </SidePanel>

      <ArchiveDialog open={archiveOpen} onOpenChange={setArchiveOpen} patient={cf.case.patient?.name || id} onConfirm={async (reason) => { await archiveCase(id, reason); nav("/home", { replace: true }); }} />
      <MarkReadyDialog open={readyOpen} onOpenChange={setReadyOpen} slots={slots} resident={role.resident} consultantName={consultantShort} onConfirm={onMarkReady} boardQuestionMissing={boardQuestionMissing} />
    </div>
  );
}
