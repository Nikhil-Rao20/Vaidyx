// The guided Case File (21 Oct 2026, docs/ui/casefile-steps/DESIGN.md): a slim header, the left list of six sections in working order
// with one loud Continue (guide, do not lock), the section the doctor is in, a right side panel for the report, reviews and team, and the
// "Ask about this patient" bubble on every section. Each section is an address (/cases/:id/<section>); the Case File opens on Overview.
// A department that was only asked keeps its request view.
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { AnimatePresence, motion } from "motion/react";
import { ArrowLeft, BellRing, Eye, MessageSquareText } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { notify } from "@/components/Toasts";
import {
  archiveCase, buildSummary, createFreeRequest, deckUrl, exportVtbUrl, markReady, notBuiltYet, postConfirmation, postProposal, remindRequest, reviewArtefact,
  setSlotValue, setUrgency, slotAskDepartment, slotNotNeeded,
} from "./api";
import { useCaseFile, useMyRole, useProposals, useRememberCase, useSlots, useTeam } from "./hooks";
import type { Slot, SlotAction } from "./types";
import { ArchiveDialog } from "./components/ArchiveDialog";
import { AskPanel } from "./components/AskPanel";
import { BoardFormPanel } from "./components/BoardFormPanel";
import { EmptyState, ErrorState, SkeletonLines, errorText, plural, useAnnounce } from "./components/common";
import { UndoBar, useDeferred } from "./components/deferred";
import { HelpersPanel, NAMES as HELPER_NAMES, useHelpers } from "./components/HelpersPanel";
import { MarkReadyDialog } from "./components/MarkReadyDialog";
import { ProposalsStrip } from "./components/ProposalsStrip";
import { PublishedPanel } from "./components/PublishedPanel";
import { UploadDialog } from "./components/ReportsPanel";
import { RequestEditPanel } from "./components/RequestEditPanel";
import { ReviewPanel } from "./components/ReviewPanel";
import { RequestsOnlyView } from "./components/RequestsOnlyView";
import { SidePanel } from "./components/SidePanel";
import type { SlotHandlers } from "./components/SlotLine";
import { SourceViewer, type SourceTarget } from "./components/SourceViewer";
import { TeamPanel } from "./components/TeamPanel";
import { CaseHeader, type MorePanel } from "./steps/CaseHeader";
import { ChangeCancerDialog } from "./steps/ChangeCancerDialog";
import { CheckStep, type CheckHandlers } from "./steps/CheckStep";
import { Overview, type OverviewHandlers } from "./steps/Overview";
import { PreAuthStep, type PreAuthHandlers } from "./steps/PreAuthStep";
import { QuestionStep } from "./steps/QuestionStep";
import { ReportsStep } from "./steps/ReportsStep";
import { SectionChips, SectionNav } from "./steps/SectionNav";
import { SummaryStep } from "./steps/SummaryStep";
import { deleteKeyCheck, dismissWarning, postKeyCheck, putReason, useSteps } from "./steps/api";
import { SLUG, fromSlug, type MissingItem, type SectionId } from "./steps/types";
import "./print.css";

type Side =
  | { kind: "panel"; panel: MorePanel }
  | { kind: "source"; target: SourceTarget }
  | { kind: "review"; slotId: string }
  | { kind: "request"; slotId: string; action: SlotAction }
  | { kind: "ask" };

// Old addresses keep working: /cases/:id/helpers opens the Summary (the briefs live there), /team and /board open their panel.
const LEGACY: Record<string, { section: SectionId; side?: Side }> = {
  helpers: { section: "summary" }, published: { section: "summary" }, ask: { section: "overview", side: { kind: "ask" } },
  team: { section: "overview", side: { kind: "panel", panel: "team" } }, board: { section: "overview", side: { kind: "panel", panel: "board" } },
};

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

const leftOffKey = (id: string) => `tbnik.cf.${id}.section`;
function readLeftOff(id: string): SectionId | null {
  try { return fromSlug(localStorage.getItem(leftOffKey(id)) ?? undefined); } catch { return null; }
}

export default function GuidedCaseFilePage() {
  const { id = "", view } = useParams();
  const [search] = useSearchParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  useRememberCase(id);
  const cfq = useCaseFile(id);
  const cf = cfq.data;
  const requestsOnly = (cf?.access?.scope ?? "").toLowerCase() === "requests";
  const full = !!cf && !requestsOnly;
  const stepsq = useSteps(id, full);
  const steps = stepsq.data ?? null;
  const slotsq = useSlots(id, cf, full);
  const role = useMyRole(cf);
  const teamq = useTeam(id, cf, full);
  const proposalsq = useProposals(id, full && !role.resident);
  const helpersq = useHelpers(id, cf, full);
  const deferred = useDeferred();
  const wide = useMinWidth(1024);
  const [announce, liveNode] = useAnnounce();
  const legacy = view ? LEGACY[view] : undefined;
  const section: SectionId = fromSlug(view) ?? legacy?.section ?? "overview";
  const target = search.get("item");
  const [leftOff] = useState<SectionId | null>(() => readLeftOff(id));
  const [side, setSide] = useState<Side | null>(legacy?.side ?? null);
  const [readyOpen, setReadyOpen] = useState(false);
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [cancerOpen, setCancerOpen] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [writing, setWriting] = useState(false);
  const [reading, setReading] = useState(false);
  const [busyKeys, setBusyKeys] = useState<Record<string, boolean>>({});

  useEffect(() => { if (section !== "overview") { try { localStorage.setItem(leftOffKey(id), SLUG[section]); } catch { /* storage blocked */ } } }, [id, section]);

  const consultantName = (teamq.data?.owner?.doctors?.[0]?.name ?? cf?.access?.owner_name ?? "the consultant").replace(/^Dr\.?\s+/i, "");
  const allSlots = useMemo(() => (slotsq.data?.sections ?? []).flatMap((s) => s.slots), [slotsq.data]);
  const slotById = useCallback((sid: string) => allSlots.find((s) => s.id === sid) ?? null, [allSlots]);
  const prepare = steps?.mode === "prepare";
  const resident = role.resident;

  const refresh = useCallback(async () => {
    await cfq.refresh();
    await Promise.all([slotsq.refetch(), qc.invalidateQueries({ queryKey: ["steps", id] }), proposalsq.refetch(), teamq.refetch()]);
  }, [cfq, slotsq, qc, id, proposalsq, teamq]);

  const go = useCallback((s: SectionId, t?: string) => {
    nav(`/cases/${encodeURIComponent(id)}/${SLUG[s]}${t ? `?item=${encodeURIComponent(t)}` : ""}`);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [nav, id]);
  const openSource = useCallback((t: SourceTarget) => setSide({ kind: "source", target: t }), []);

  // A helper brief prepared in the background is announced once when it is ready.
  const [helperSeen, setHelperSeen] = useState<Record<string, string>>({});
  useEffect(() => {
    const next: Record<string, string> = {};
    for (const x of helpersq.helpers) {
      next[x.role] = x.brief.status;
      if (helperSeen[x.role] === "preparing" && (x.brief.status === "ready" || x.brief.status === "stale")) notify.success(`${HELPER_NAMES[x.role] ?? x.label} brief is ready`, "Open the Summary to read it.");
    }
    if (JSON.stringify(next) !== JSON.stringify(helperSeen)) setHelperSeen(next);
  }, [helpersq.helpers, helperSeen]);

  // ---- actions -----------------------------------------------------------------------------------------------------------------------
  const propose = useCallback(async (action: string, payload: Record<string, unknown>, label: string) => {
    try { await postProposal(id, action, payload); }
    catch (e) { if (notBuiltYet(e)) throw new Error("Sign-off by the consultant is not available on this server yet."); throw e; }
    notify.success(`Sent to Dr ${consultantName} for sign-off`, label);
    await refresh();
  }, [id, consultantName, refresh]);

  const typed = useCallback(async (slotId: string, value: string, label: string) => {
    if (resident) { await propose("typed_value", { slot: slotId, value }, label); return; }
    await setSlotValue(id, slotId, value);
    await refresh();
  }, [resident, propose, id, refresh]);

  const busy = (k: string) => !!busyKeys[k];
  const withBusy = async (k: string, fn: () => Promise<void>) => {
    setBusyKeys((b) => ({ ...b, [k]: true }));
    try { await fn(); } catch (e) { notify.error("Could not finish", errorText(e)); } finally { setBusyKeys((b) => ({ ...b, [k]: false })); }
  };

  /** One request per suggested request (two lines of the same report share one); Undo for 10 s before anything is sent. */
  const sendItems = useCallback((items: MissingItem[], key: string) => {
    const dept = items[0]?.department?.label ?? "the department";
    if (resident) {
      void (async () => {
        for (const it of items) await propose("send_request", it.department?.action_id ? { action_id: it.department.action_id } : { department: it.department?.id, label: it.label }, `Request to ${dept}: ${it.label}`);
      })().catch((e) => notify.error("Could not send for sign-off", errorText(e)));
      return;
    }
    const seen = new Set<string>();
    const once = items.filter((it) => { const k = it.department?.action_id || it.slot_id; if (seen.has(k)) return false; seen.add(k); return true; });
    deferred.schedule(key, `Request to ${dept}`, async () => {
      for (const it of once) {
        try { await slotAskDepartment(id, it.slot_id); }
        catch (e) { if (!(e instanceof ApiError && e.status === 409)) throw e; }
      }
      announce(`Request sent to ${dept}.`);
      await refresh();
    });
  }, [resident, propose, deferred, id, announce, refresh]);

  const slotHandlers: SlotHandlers = useMemo(() => ({
    openSource, review: (s: Slot) => setSide({ kind: "review", slotId: s.id }), editRequest: (s: Slot, a: SlotAction) => setSide({ kind: "request", slotId: s.id, action: a }),
    ask: async () => undefined, notNeeded: async () => undefined, remind: async () => undefined, enterValue: async () => undefined, clearValue: async () => undefined,
    propose, schedule: deferred.schedule, undo: deferred.undo, pending: deferred.get,
  }), [openSource, propose, deferred.schedule, deferred.undo, deferred.get]);

  const checkDoc = useCallback((docId: string) => {
    const s = allSlots.find((x) => x.status === "needs_confirmation" && (x.confirmation?.doc_id === docId || x.confirmation?.key === docId));
    if (s) setSide({ kind: "review", slotId: s.id });
    else openSource({ docId, page: 0 });
  }, [allSlots, openSource]);

  const groupFor = (slotIds: string[]) => (steps?.pre_authorization.groups ?? []).flatMap((g) => g.items).filter((i) => slotIds.includes(i.slot_id));

  const overviewH: OverviewHandlers = {
    go, openSource, busy,
    act: async (t) => {
      const a = t.action;
      if (a.kind === "go") go(t.section);
      else if (a.kind === "check") go("check", a.slot_id);
      else if (a.kind === "open_report" && a.doc_id) checkDoc(a.doc_id);
      else if (a.kind === "ask_department") sendItems(groupFor(a.slot_ids ?? []), t.id);
      else if (a.kind === "signoffs") document.getElementById("signoffs")?.scrollIntoView({ behavior: "smooth" });
    },
    fix: async (w, f) => {
      if (f.kind === "change_cancer") setCancerOpen(true);
      else if (f.kind === "dismiss") await withBusy(`${w.id}:dismiss`, async () => { await dismissWarning(id, w.id); await refresh(); });
      else if (f.kind === "open_report" && f.doc_id) checkDoc(f.doc_id);
      else if (f.kind === "ask_department" && f.slot_id) sendItems(groupFor([f.slot_id]).length ? groupFor([f.slot_id]) : [], `${w.id}:ask_department`);
    },
    remind: async (w) => {
      if (!w.action.action_id) return;
      deferred.schedule(w.id, `Reminder to ${w.department?.label ?? "the department"}`, async () => { await remindRequest(id, w.action.action_id!); await refresh(); });
    },
    rowExtra: (k) => { const p = deferred.get(k); return p ? <UndoBar pending={p} onUndo={() => deferred.undo(k)} className="mt-2 max-w-md" /> : null; },
  };

  const checkH: CheckHandlers = {
    confirmKey: async (k) => { await postKeyCheck(id, { fact_id: k.fact_id ?? "", value: k.value, doc_id: k.quote?.doc_id ?? "" }); announce(`${k.label} confirmed.`); await refresh(); },
    undoKey: async (k) => { await deleteKeyCheck(id, k.fact_id ?? ""); await refresh(); },
    correct: async (k, value, reason) => {
      const body = { type: "confirm_value", key: `${k.quote?.doc_id}:${k.fact_id}`, fields: { value }, reason };
      if (resident) await propose("confirm", body, `Correct ${k.label}: ${value}`);
      else { await postConfirmation(id, body); await refresh(); }
    },
    askAmend: async (k) => {
      const d = steps?.documents.find((x) => x.doc_id === k.quote?.doc_id);
      await createFreeRequest(id, { department: d?.department || "", label: `Please amend the report: ${k.label}`, what: `${k.label} reads "${k.value}" in ${d?.title ?? "the report"}${d?.date ? ` of ${d.date}` : ""}. Please check and amend the report if it is not right.` });
      await refresh();
    },
    review: (slotId, onDone) => {
      const s = slotById(slotId);
      if (!s || !cf) return <p className="text-sm text-muted-foreground">This value is settled.</p>;
      return <ReviewPanel caseId={id} cf={cf} slot={s} queue={allSlots.filter((x) => x.status === "needs_confirmation")} derived={slotsq.derived} resident={resident} consultantName={consultantName}
        onOpenSource={openSource} onDone={refresh} onPropose={propose} onNext={() => onDone()} />;
    },
  };

  const preAuthH: PreAuthHandlers = {
    sendGroup: sendItems,
    changeMessage: (it) => { const s = slotById(it.slot_id); if (s && it.department?.action_id) setSide({ kind: "request", slotId: s.id, action: { kind: "ask_department", label: "", action_id: it.department.action_id } }); },
    notNeeded: async (it, reason) => {
      if (resident) await propose("not_needed", { slot: it.slot_id, reason }, `Not needed: ${it.label}`);
      else { await slotNotNeeded(id, it.slot_id, reason); await refresh(); }
    },
    fillIn: async (it, value) => typed(it.slot_id, value, `${it.label}: ${value}`),
    upload: () => setUploadOpen(true),
    remind: async (it) => { if (it.request?.action_id) { await remindRequest(id, it.request.action_id); await refresh(); } },
    pendingBar: (k) => { const p = deferred.get(k); return p ? <div className="pb-3"><UndoBar pending={p} onUndo={() => deferred.undo(k)} className="max-w-md" /></div> : null; },
    isPending: (k) => !!deferred.get(k),
  };

  const onMarkReady = async (note: string) => {
    if (resident) { await propose("mark_ready", { note }, "send to the board"); return; }
    await markReady(id, true, note);
    announce("Sent to the board.");
    await refresh();
  };

  // ---- states ------------------------------------------------------------------------------------------------------------------------
  if (cfq.isLoading) {
    return (
      <div className="space-y-4 p-1" aria-busy="true" aria-label="Loading the Case File">
        <div className="surface space-y-2 p-4"><div className="skeleton-line h-7 w-1/3" /><div className="skeleton-line h-4 w-1/2" /></div>
        <div className="grid gap-4 lg:grid-cols-[248px_1fr]"><div className="surface p-4"><SkeletonLines n={6} /></div><div className="surface p-4"><SkeletonLines n={8} /></div></div>
      </div>
    );
  }
  if (cfq.error && !cf) {
    const e = cfq.error;
    const status = e instanceof ApiError ? e.status : 0;
    return (
      <div className="mx-auto max-w-xl py-8" data-testid="casefile-error" data-status={status}>
        {status === 404 ? <EmptyState title="This Case File does not exist" text={`No Case File with the id ${id}. The link may be old.`} action={<Button asChild variant="outline"><Link to="/cases"><ArrowLeft className="size-4" />Back to the Case Files</Link></Button>} />
          : status === 403 ? <EmptyState title="You do not have access to this Case File" text="Only the owner's team, the departments asked, and the MDT Coordinator can open it." action={<Button asChild variant="outline"><Link to="/cases"><ArrowLeft className="size-4" />Back to the Case Files</Link></Button>} />
          : <ErrorState error={e} retry={() => void cfq.refetch()} />}
      </div>
    );
  }
  if (!cf) return null;
  if (requestsOnly) return <RequestsOnlyView id={id} cf={cf} />;

  const prose = steps?.summary.prose;
  const exportAllowed = !!prose?.reviewed;
  const canWrite = prepare && (resident || !!cf.permissions?.mark_ready || !!cf.permissions?.review);
  const canConfirm = prepare && !resident && !!steps?.permissions?.review;
  const sectionTitle = steps?.sections.find((s) => s.id === section)?.label ?? "";
  const panelTitle = side?.kind === "panel" ? (side.panel === "team" ? "Team" : "Board form") : side?.kind === "source" ? (side.target.title ?? "Report") : side?.kind === "review" ? "Please check" : side?.kind === "request" ? "Change the message" : side?.kind === "ask" ? "Ask about this patient" : "";
  const reviewSlot = side?.kind === "review" ? slotById(side.slotId) : null;
  const requestSlot = side?.kind === "request" ? slotById(side.slotId) : null;

  let body: ReactNode = <div className="surface p-4"><SkeletonLines n={8} /></div>;
  if (stepsq.error && !steps) body = <ErrorState error={stepsq.error} retry={() => void stepsq.refetch()} />;
  else if (steps) {
    if (section === "overview") {
      body = <Overview steps={steps} h={overviewH} signoffs={!resident && proposalsq.proposals.length ? <div id="signoffs"><ProposalsStrip caseId={id} proposals={proposalsq.proposals} onChanged={refresh} labelOf={(sid) => slotById(sid)?.label} /></div> : null} />;
    } else if (section === "question") {
      body = <QuestionStep steps={steps} canEdit={prepare} resident={resident} consultantName={consultantName} onOpen={openSource} onNext={() => go("reports")}
        onSaveQuestion={(t) => typed("fact:clinical_question", t, `Question for the board: ${t}`)}
        onReason={async (v) => { await putReason(id, v); await refresh(); }}
        onUrgency={async (n) => { const r = await setUrgency(id, n); if (r.proposal) notify.success(`Dr ${consultantName} asked to set urgency ${n}`); await refresh(); }}
        onSaveFact={(sid, v) => typed(sid, v, `${slotById(sid)?.label ?? "Value"}: ${v}`)} />;
    } else if (section === "reports") {
      body = <ReportsStep steps={steps} cf={cf} caseId={id} onOpen={openSource} onCheckDoc={checkDoc} onChanged={refresh} onNext={() => go("check")} />;
    } else if (section === "check") {
      body = <CheckStep steps={steps} caseId={id} docs={cf.documents} h={checkH} canConfirm={canConfirm} consultantName={consultantName} target={target} onNext={() => go("pre_authorization")} />;
    } else if (section === "pre_authorization") {
      body = <PreAuthStep steps={steps} h={preAuthH} canAct={prepare} resident={resident} consultantName={consultantName} onNext={() => go("summary")} />;
    } else {
      body = <SummaryStep steps={steps} docs={cf.documents} h={slotHandlers} canWrite={!!canWrite} canRead={!resident && !!cf.permissions?.review} busy={writing} reading={reading} resident={resident} consultantName={consultantName}
        onWrite={() => void (async () => { setWriting(true); try { await buildSummary(id, true); await refresh(); } catch (e) { notify.error("Could not write the summary", errorText(e)); } finally { setWriting(false); } })()}
        onRead={() => void (async () => { setReading(true); try { await reviewArtefact(id, "summary", "reviewed"); await refresh(); } catch (e) { notify.error("Could not save", errorText(e)); } finally { setReading(false); } })()}
        onSend={() => setReadyOpen(true)}
        briefs={<HelpersPanel caseId={id} cf={cf} onOpenSource={openSource} onCaseChanged={refresh} />}
        published={<PublishedPanel caseId={id} resident={resident} consultantName={consultantName} onPropose={(payload, label) => propose("published_case", payload, label)} />} />;
    }
  }

  return (
    <div id="casefile-print" className="space-y-3 pb-24 lg:pb-8" data-testid="casefile-page" data-section={section}>
      {liveNode}
      <AnimatePresence>
        {cfq.stale ? (
          <motion.div key="stale" initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} role="status" className="sticky top-16 z-30 flex items-center gap-2 rounded-md border border-primary/50 bg-secondary px-3 py-2 text-sm shadow-[var(--shadow-outer)] print:hidden" data-testid="stale-banner">
            <BellRing className="size-4 text-brand" aria-hidden />
            <span className="flex-1">{plural(cfq.newCount, "new report")} since you looked.</span>
            <Button size="sm" onClick={() => { cfq.show(); void refresh(); announce("Showing the latest reports."); }}><Eye className="size-4" />Show</Button>
          </motion.div>
        ) : null}
      </AnimatePresence>

      <CaseHeader cf={cf} team={teamq.data} steps={steps} resident={resident} consultantName={consultantName} onSend={() => setReadyOpen(true)}
        onPanel={(p) => setSide({ kind: "panel", panel: p })} onPrint={() => window.print()} deckHref={deckUrl(id)} exportHref={exportVtbUrl(id)} exportAllowed={exportAllowed}
        onArchive={teamq.data?.can?.archive && !teamq.data?.archived ? () => setArchiveOpen(true) : undefined} />

      {teamq.data?.archived ? <p role="status" className="rounded-md border border-border bg-muted px-3 py-2 text-sm">Archived{teamq.data.archived.reason ? `: ${teamq.data.archived.reason}` : ""}. Read only.</p> : null}

      {steps ? (
        wide ? (
          <div className="grid items-start gap-5 lg:grid-cols-[248px_minmax(0,1fr)]">
            <aside className="sticky top-[4.5rem] print:hidden"><SectionNav steps={steps} active={section} leftOff={leftOff} onOpen={(s) => go(s)} onGo={go} /></aside>
            <main className="min-w-0" aria-label={sectionTitle} data-print-area>
              <h2 className="sr-only">{sectionTitle}</h2>
              {body}
            </main>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="sticky top-14 z-20 -mx-4 border-b border-border bg-background/95 px-4 py-2 backdrop-blur print:hidden"><SectionChips steps={steps} active={section} onOpen={(s) => go(s)} onGo={go} /></div>
            {body}
          </div>
        )
      ) : body}

      <button type="button" onClick={() => setSide({ kind: "ask" })} data-testid="ask-bubble" aria-label="Ask about this patient"
        className="fixed bottom-28 right-4 z-40 inline-flex size-12 items-center justify-center gap-2 rounded-full bg-foreground text-sm font-semibold text-background shadow-[var(--shadow-lift)] transition hover:brightness-110 active:scale-95 lg:bottom-6 lg:right-6 lg:size-auto lg:px-4 lg:py-3 print:hidden">
        <MessageSquareText className="size-5" aria-hidden /><span className="hidden lg:inline">Ask about this patient</span>
      </button>

      <SidePanel open={!!side} onClose={() => setSide(null)} title={panelTitle} width={side?.kind === "source" ? "wide" : "normal"}
        subtitle={side?.kind === "source" ? "Shown as printed; nothing is interpreted." : side?.kind === "ask" ? "Answers come only from this patient's reports, each with the line it came from." : undefined}>
        {side?.kind === "panel" && side.panel === "team" ? <TeamPanel caseId={id} team={teamq.data} derived={teamq.derived} isOwner={teamq.data?.can?.manage ?? !!cf.permissions?.manage_participants} resident={resident} onChanged={refresh} me={role.me?.user ?? ""} /> : null}
        {side?.kind === "panel" && side.panel === "board" ? <BoardFormPanel cf={cf} coordinator={role.coordinator} /> : null}
        {side?.kind === "source" ? <SourceViewer caseId={id} target={side.target} doc={cf.documents.find((d) => d.doc_id === side.target.docId)} /> : null}
        {side?.kind === "review" ? (reviewSlot ? <ReviewPanel caseId={id} cf={cf} slot={reviewSlot} queue={allSlots.filter((s) => s.status === "needs_confirmation")} derived={slotsq.derived} resident={resident} consultantName={consultantName}
          onOpenSource={openSource} onDone={refresh} onPropose={propose} onNext={(n) => setSide(n ? { kind: "review", slotId: n.id } : null)} /> : <EmptyState title="Nothing left to check here" className="py-6" />) : null}
        {side?.kind === "request" ? (requestSlot ? <RequestEditPanel caseId={id} slot={requestSlot} action={side.action} onSent={async () => { setSide(null); announce("Request sent."); await refresh(); }} /> : null) : null}
        {side?.kind === "ask" ? <AskPanel caseId={id} docs={cf.documents} onOpenSource={openSource} compact /> : null}
      </SidePanel>

      <ArchiveDialog open={archiveOpen} onOpenChange={setArchiveOpen} patient={cf.case.patient?.name || id} onConfirm={async (reason) => { await archiveCase(id, reason); nav("/cases", { replace: true }); }} />
      <MarkReadyDialog open={readyOpen} onOpenChange={setReadyOpen} slots={slotsq.data} resident={resident} consultantName={consultantName} onConfirm={onMarkReady}
        boardQuestionMissing={!steps?.question.text} />
      <ChangeCancerDialog open={cancerOpen} onOpenChange={setCancerOpen} caseId={id} current={steps?.protocol ?? cf.case.protocol ?? ""} onChanged={() => { announce("Reading the reports again for the new cancer."); void refresh(); }} />
      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} caseId={id} hisCase={!!cf.his} onStarted={() => { announce("Upload started; reading the files."); window.setTimeout(() => void refresh(), 4000); }} />
    </div>
  );
}
