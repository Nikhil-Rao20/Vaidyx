// The Specialty agents (night-v3 item 6.5, owner decision D2; formerly the six "<Specialty> records check" helpers): one AI agent per
// specialty, support only, never a member of the board. Pick one: its brief (prepared at the ready mark for the five heads, on request
// for Nuclear Medicine, or all at once with "Prepare all") with sections, points for review and what is not documented, then the one
// thread per Case File and role that the board meetings share (each meeting exchange labelled with the meeting's date). Everything comes
// from the records and guideline points; never a decision or treatment advice.
// Voice (night-v3 item 4.4): the mic fills the question box as an editable edit (nothing is sent until Ask); "Read aloud" on each
// saved answer reads its statements as shown.
// The Summary section opens a given agent from the address (?item=<role>), which the Overview card's chips use (AgentsCard.tsx).
import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Bot, Loader2, SendHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { MicButton } from "@/components/MicButton";
import { SpeakButton } from "@/components/SpeakButton";
import { askAgentOld, getHelperChat, getHelpers, getRoles, notBuiltYet, postHelperChat, prepareAllHelpers, prepareHelper, streamAgentOld } from "../api";
import { useJob } from "../hooks";
import type { CaseFile, Helper, HelperMessage } from "../types";
import type { SourceTarget } from "./SourceViewer";
import { ErrorState, LoadingButton, NotYetState, SkeletonLines, StatusChip, docTitleOf, errorText, fmtDate, fmtDateTime, indianDates, modelLabel } from "./common";
import { cn } from "@/lib/utils";

const MAX_Q = 1000;
const HEARD = "Heard this. Check it before asking.";

export const ORDER = ["radiology", "pathology", "medical_oncology", "surgical_oncology", "radiation_oncology", "nuclear_medicine"];
export const NAMES: Record<string, string> = { radiology: "Radiology", pathology: "Pathology", medical_oncology: "Medical Oncology", surgical_oncology: "Surgical Oncology", radiation_oncology: "Radiation Oncology", nuclear_medicine: "Nuclear Medicine" };
/** The labels of owner decision D2, shown wherever an agent is named. */
export const AGENT_LABEL = "AI agent, support only";
export const AGENT_LINE = "Reads this Case File and the guidelines. Does not decide or advise. Not a member of the board.";
const ANSWER_FOOTER = "AI agent, support only. From the records and guidelines only. Check the source.";

export const agentName = (h: Pick<Helper, "role" | "label" | "department">) => NAMES[h.role] ?? h.department ?? h.label;
/** "Radiology, AI agent". */
export const agentTitle = (h: Pick<Helper, "role" | "label" | "department" | "title">) => h.title || `${agentName(h)}, AI agent`;
const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
/** The counts of the badges (the server's, or worked out from the brief on an older server). */
export function agentCounts(h: Helper) {
  const live = h.brief.status === "ready" || h.brief.status === "stale";
  return {
    points: live ? (h.points_count ?? (h.brief.points_for_review ?? []).length) : 0,
    notDocumented: live ? (h.not_documented_count ?? (h.brief.not_documented ?? []).length) : 0,
    questions: h.thread_count ?? 0,
  };
}

/** The agent's state in words: a spinner and "Reading the records" while its brief is prepared, "Records changed" for a brief the
 *  records have moved past, "Not prepared" when there is none. */
export function AgentState({ h, className }: { h: Helper; className?: string }) {
  const st = h.brief.status;
  if (st === "preparing") {
    return (
      <span className={cn("inline-flex items-center gap-1 rounded-full bg-secondary px-2 py-0.5 text-xs font-medium whitespace-nowrap text-secondary-foreground", className)} title={h.brief.message || undefined} data-testid="agent-state" data-state="preparing">
        <Loader2 className="size-3.5 shrink-0 animate-spin motion-reduce:animate-none" aria-hidden />Reading the records
      </span>
    );
  }
  if (st === "stale") return <span data-testid="agent-state" data-state="stale"><StatusChip kind="warn" className={className} title={h.brief.stale_reason || undefined}>Records changed</StatusChip></span>;
  if (st === "none") return <span data-testid="agent-state" data-state="none"><StatusChip kind="muted" className={className}>Not prepared</StatusChip></span>;
  return null;
}

/** The count badges: points for review, items not documented, questions on the shared thread. */
export function AgentBadges({ h, className }: { h: Helper; className?: string }) {
  const c = agentCounts(h);
  const live = h.brief.status === "ready" || h.brief.status === "stale";
  const pill = "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap";
  return (
    <span className={cn("inline-flex flex-wrap items-center gap-1", className)} data-testid="agent-badges">
      {live ? <span className={cn(pill, c.points ? "status-review" : "bg-muted text-muted-foreground")} data-testid="badge-points">{plural(c.points, "point", "points")}</span> : null}
      {c.notDocumented ? <span className={cn(pill, "status-warn")} data-testid="badge-not-documented">{c.notDocumented} not documented</span> : null}
      {c.questions ? <span className={cn(pill, "bg-secondary text-secondary-foreground")} data-testid="badge-questions">{plural(c.questions, "question", "questions")}</span> : null}
    </span>
  );
}

/** "Prepare all": every agent without a brief that stands for the Case File, one after the other in the background (useHelpers polls). */
export function usePrepareAll(caseId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => prepareAllHelpers(caseId),
    onSettled: () => qc.invalidateQueries({ queryKey: ["helpers", caseId] }),
  });
}

/** Whether "Prepare all" has anything to do and may be offered. */
export const canPrepareAll = (helpers: Helper[], notBuilt: boolean) =>
  !notBuilt && helpers.some((h) => h.prepare_allowed) && helpers.some((h) => h.brief.status === "none" || h.brief.status === "stale");

export function useHelpers(caseId: string, cf: CaseFile | null, enabled: boolean) {
  const q = useQuery({ queryKey: ["helpers", caseId], queryFn: () => getHelpers(caseId), retry: false, enabled, refetchInterval: (query) => (query.state.data?.helpers.some((h) => h.brief.status === "preparing") ? 4000 : false) });
  const notBuilt = q.isError && notBuiltYet(q.error);
  const rolesQ = useQuery({ queryKey: ["roles"], queryFn: getRoles, enabled: notBuilt, staleTime: 600_000 });
  const helpers: Helper[] = useMemo(() => {
    if (q.data?.helpers) return [...q.data.helpers].sort((a, b) => ORDER.indexOf(a.role) - ORDER.indexOf(b.role));
    if (!notBuilt) return [];
    const roles = rolesQ.data ?? Object.fromEntries(ORDER.map((r) => [r, { label: `${NAMES[r]} support`, department: NAMES[r] }]));
    return ORDER.filter((r) => roles[r]).map((r) => {
      const art = cf?.state?.artefacts?.[`brief_${r}`];
      const stale = cf?.stale?.[`brief_${r}`];
      return {
        role: r, label: roles[r].label, department: roles[r].department,
        brief: art ? { status: stale ? "stale" : "ready", sections: art.sections as Helper["brief"]["sections"], points_for_review: art.points_for_review, reviewed_by: art.review?.status === "reviewed" ? art.review?.by : undefined, at: art.review?.at, model: art.model } : { status: "none" },
        thread_count: 0, prepare_allowed: true,
      } satisfies Helper;
    });
  }, [q.data, notBuilt, rolesQ.data, cf]);
  return { helpers, notBuilt, isLoading: q.isLoading, error: notBuilt ? null : q.error, refetch: q.refetch };
}

export function HelpersPanel({ caseId, cf, onOpenSource, onCaseChanged }: { caseId: string; cf: CaseFile; onOpenSource: (t: SourceTarget) => void; onCaseChanged: () => Promise<void> }) {
  const { helpers, notBuilt, isLoading, error, refetch } = useHelpers(caseId, cf, true);
  const [search, setSearch] = useSearchParams();
  const asked = search.get("item");
  const fromAddress = asked && ORDER.includes(asked) ? asked : null;
  const [picked, setPicked] = useState<string | null>(fromAddress);
  const box = useRef<HTMLDivElement>(null);
  const all = usePrepareAll(caseId);
  // An agent chip on the Overview opens its agent here (?item=<role>): open it and bring the card into view.
  useEffect(() => {
    if (!fromAddress) return;
    setPicked(fromAddress);
    const t = window.setTimeout(() => box.current?.scrollIntoView({ block: "start" }), 80);
    return () => window.clearTimeout(t);
  }, [fromAddress]);
  const back = () => {
    setPicked(null);
    if (fromAddress) { const next = new URLSearchParams(search); next.delete("item"); setSearch(next, { replace: true }); }
  };
  const h = helpers.find((x) => x.role === picked) ?? null;
  let body;
  if (isLoading) body = <SkeletonLines n={6} />;
  else if (error) body = <ErrorState error={error} retry={() => void refetch()} compact />;
  else if (h) body = <HelperDetail caseId={caseId} helper={h} notBuilt={notBuilt} docs={cf.documents} onBack={back} onOpenSource={onOpenSource} onChanged={async () => { await refetch(); await onCaseChanged(); }} />;
  else body = (
    <div className="space-y-3" data-testid="helpers-list">
      {notBuilt ? <NotYetState what="Specialty agent briefs" fallback="Showing the briefs the old route already prepared; Prepare uses the old helper stream." /> : null}
      <div className="flex flex-wrap items-start gap-x-3 gap-y-2">
        <p className="min-w-[14rem] flex-1 text-sm text-muted-foreground">One AI agent per specialty, support only. Each reads this Case File and its specialty&apos;s guidelines and lists points for review; it never decides or advises and is not a member of the board. Briefs for the five board heads are prepared at the ready mark; Nuclear Medicine on request.</p>
        {canPrepareAll(helpers, notBuilt) ? <LoadingButton size="sm" variant="outline" loading={all.isPending} loadingText="Starting" onClick={() => all.mutate()} data-testid="agents-prepare-all">Prepare all</LoadingButton> : null}
      </div>
      {all.isError ? <p role="alert" className="text-xs text-bad">{errorText(all.error)}</p> : null}
      <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1">
        {helpers.map((x) => (
          <li key={x.role}>
            <button type="button" onClick={() => setPicked(x.role)} className="row-lift w-full text-left rounded-md border border-border bg-card p-3 hover:border-primary/60 focus-visible:outline-2" data-testid={`helper-${x.role}`}>
              <div className="flex flex-wrap items-center gap-2">
                <Bot className="size-4 text-brand shrink-0" aria-hidden />
                <span className="font-medium text-foreground">{agentTitle(x)}</span>
                <span className="inline-flex flex-wrap items-center gap-1 sm:ml-auto"><AgentState h={x} /><AgentBadges h={x} /></span>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                <span className="font-medium text-review">{AGENT_LABEL}</span>
                {x.brief.at && x.brief.status !== "preparing" ? `. Brief of ${fmtDateTime(x.brief.at)}` : ""}
                {x.meeting_exchanges ? `. ${plural(x.meeting_exchanges, "question", "questions")} from board meetings` : ""}
              </p>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
  return <div ref={box} className="scroll-mt-24">{body}</div>;
}

function HelperDetail({ caseId, helper, notBuilt, docs, onBack, onOpenSource, onChanged }: { caseId: string; helper: Helper; notBuilt: boolean; docs: CaseFile["documents"]; onBack: () => void; onOpenSource: (t: SourceTarget) => void; onChanged: () => Promise<void> }) {
  const qc = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(null);
  const [steps, setSteps] = useState<string[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [prepErr, setPrepErr] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [local, setLocal] = useState<HelperMessage[]>([]);
  const abort = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  /** The text in the box came from the mic and the box has not been cleared or sent since. */
  const [dictated, setDictated] = useState(false);
  const role = helper.role;
  const brief = helper.brief;

  const job = useJob(jobId, async () => { setJobId(null); await onChanged(); });
  useEffect(() => () => abort.current?.abort(), []);

  const prepare = useMutation({
    mutationFn: async () => {
      setPrepErr(null); setSteps([]);
      if (!notBuilt) { const r = await prepareHelper(caseId, role, brief.status === "ready" || brief.status === "stale"); if (r.job && r.status !== "ready") setJobId(r.job); else await onChanged(); return; }
      setStreaming(true);
      abort.current = new AbortController();
      try {
        await streamAgentOld(caseId, role, (ev) => {
          if (ev.type === "step") setSteps((s) => [...s, String(ev.text ?? ev.step ?? "working")].slice(-6));
          if (ev.type === "error") setPrepErr(String(ev.text ?? ev.message ?? "The agent stopped."));
        }, abort.current.signal);
      } finally { setStreaming(false); }
      await onChanged();
    },
    onError: (e) => setPrepErr(errorText(e)),
  });

  const chatQ = useQuery({ queryKey: ["helper-chat", caseId, role], queryFn: () => getHelperChat(caseId, role), retry: false, enabled: !notBuilt });
  const ask = useMutation({
    mutationFn: async (text: string) => (notBuilt ? askAgentOld(caseId, role, text) : postHelperChat(caseId, role, text)),
    onSuccess: (m) => {
      if (notBuilt) setLocal((l) => [...l, { ...m, question: m.question || question, at: new Date().toISOString() }]);
      else void qc.invalidateQueries({ queryKey: ["helper-chat", caseId, role] });
      setQuestion("");
      setDictated(false);
    },
  });
  const messages = useMemo(() => [...(chatQ.data?.messages ?? []), ...local], [chatQ.data, local]);
  const busy = prepare.isPending || streaming || !!jobId || brief.status === "preparing";
  const name = agentName(helper);

  return (
    <div className="space-y-3" data-testid="helper-detail">
      <Button variant="ghost" size="sm" onClick={onBack} className="-ml-2"><ArrowLeft className="size-4" />All agents</Button>
      <div className="flex items-start gap-2">
        <Bot className="size-5 text-brand shrink-0 mt-0.5" aria-hidden />
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <h3 className="text-base">{agentTitle(helper)}</h3>
            <StatusChip kind="review" icon={Bot}>{AGENT_LABEL}</StatusChip>
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">{AGENT_LINE} The brief is an AI draft until a doctor reviews it.{brief.model ? ` Model: ${modelLabel(brief.model)}.` : ""}</p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {brief.status === "ready" ? <StatusChip kind="ok">brief ready{brief.at ? `, ${fmtDateTime(brief.at)}` : ""}</StatusChip> : null}
        {brief.status === "stale" ? <StatusChip kind="warn">records changed since this brief</StatusChip> : null}
        {brief.status === "none" ? <StatusChip kind="muted">not prepared yet</StatusChip> : null}
        {busy ? <AgentState h={{ ...helper, brief: { ...brief, status: "preparing" } }} /> : null}
        <AgentBadges h={helper} />
        {brief.reviewed_by ? <StatusChip kind="ok">reviewed by {brief.reviewed_by}</StatusChip> : <StatusChip kind="review" icon={Bot}>AI draft</StatusChip>}
        <span className="flex-1" />
        {helper.prepare_allowed ? <LoadingButton size="sm" variant={brief.status === "ready" ? "outline" : "default"} loading={busy} loadingText="Preparing" onClick={() => prepare.mutate()}>{brief.status === "ready" ? "Prepare again" : "Prepare"}</LoadingButton> : null}
      </div>
      {busy ? (
        <div className="rounded-md border border-border bg-muted/60 p-2 text-xs" role="status" aria-live="polite">
          <p className="font-medium text-foreground">Reading the records for {name}</p>
          <p className="text-muted-foreground">You can go back to the other agents or close this panel: it keeps preparing, and you are told when the brief is ready.</p>
          <ul className="mt-1 space-y-0.5 text-muted-foreground">
            {(job ? job.events.slice(-5).map((e) => e.text ?? `${e.doc_id ?? ""} ${e.state ?? ""}`) : steps).map((s, i) => <li key={i}>{s}</li>)}
          </ul>
          <SkeletonLines n={3} className="mt-2" />
        </div>
      ) : null}
      {prepErr ? <p role="alert" className="text-xs text-bad">{prepErr}</p> : null}

      {(brief.status === "ready" || brief.status === "stale") && !busy ? (
        <div className="space-y-3" data-testid="helper-brief">
          {(brief.sections ?? []).map((s, i) => (
            <section key={i}>
              <h4 className="text-sm font-semibold text-foreground">{s.heading ?? s.title}</h4>
              {s.text ? <p className="text-sm">{indianDates(s.text)}</p> : null}
              <ul className="mt-1 space-y-1">
                {(s.items ?? []).map((it, j) => (
                  <li key={j} className="text-sm text-foreground">
                    {indianDates(it.text)}
                    {(it.citations ?? []).map((c, k) => (
                      <button key={k} type="button" className="quote-chip ml-1 align-middle hover:brightness-95" onClick={() => onOpenSource({ docId: c.doc_id, page: c.page ?? 0, quote: c.quote, title: docTitleOf(docs, c.doc_id, c.doc_title) })}>{docTitleOf(docs, c.doc_id, c.doc_title)}{typeof c.page === "number" ? ` p. ${c.page + 1}` : ""}</button>
                    ))}
                  </li>
                ))}
              </ul>
            </section>
          ))}
          {(brief.points_for_review ?? []).length ? (
            <section>
              <h4 className="text-sm font-semibold text-foreground">Points for review</h4>
              <ol className="mt-1 list-decimal pl-5 space-y-1">
                {brief.points_for_review!.map((p, i) => (
                  <li key={i} className="text-sm text-foreground">{indianDates(p.text)}{(p.citations ?? []).map((c, k) => <button key={k} type="button" className="quote-chip ml-1 align-middle hover:brightness-95" onClick={() => onOpenSource({ docId: c.doc_id, page: c.page ?? 0, quote: c.quote, title: docTitleOf(docs, c.doc_id, c.doc_title) })}>{docTitleOf(docs, c.doc_id, c.doc_title)}{typeof c.page === "number" ? ` p. ${c.page + 1}` : ""}</button>)}</li>
                ))}
              </ol>
            </section>
          ) : null}
          {(brief.not_documented ?? []).length ? (
            <section>
              <h4 className="text-sm font-semibold text-foreground">Not documented</h4>
              <ul className="mt-1 list-disc pl-5 text-sm text-muted-foreground">{brief.not_documented!.map((t, i) => <li key={i}>{t}</li>)}</ul>
            </section>
          ) : null}
          {!(brief.sections ?? []).length && !(brief.points_for_review ?? []).length ? <p className="text-sm text-muted-foreground">The brief is empty: nothing for this specialty could be said with a verified quote.</p> : null}
        </div>
      ) : null}

      <section className="border-t border-border pt-3" aria-label={`Questions to the ${name} AI agent`}>
        <h4 className="text-sm font-semibold text-foreground">Ask the {name} AI agent</h4>
        <p className="text-xs text-muted-foreground mb-1">{notBuilt ? "Saved agent threads are not on this server yet; answers here are not kept." : "One thread for this Case File, shared with the board meetings."}</p>
        {chatQ.isLoading ? <SkeletonLines n={2} /> : null}
        <ul className="space-y-2 max-h-[40dvh] overflow-y-auto">
          {messages.map((m, i) => (
            <li key={m.id ?? i} className="rounded-md border border-border p-2" data-testid="agent-exchange" data-source={(m.source ?? "case").startsWith("meeting:") ? "meeting" : "case"}>
              {(m.source ?? "").startsWith("meeting:") ? (
                <p className="mb-1 inline-flex items-center gap-1 rounded-md bg-secondary px-2 py-0.5 text-xs font-medium text-secondary-foreground" data-testid="meeting-exchange">
                  Asked of the {name} AI agent in {m.meeting_date ? `the board meeting of ${fmtDate(m.meeting_date)}` : "a board meeting"}
                </p>
              ) : null}
              <div className="flex items-start gap-2">
                <p className="flex-1 text-sm font-medium text-foreground">{m.question}</p>
                {m.id && !notBuilt ? <SpeakButton source={{ ref: { kind: "agent", case_id: caseId, role, id: m.id } }} screen={`helper-${role}`} size="icon-xs" className="justify-end" /> : null}
              </div>
              <p className="text-xs text-muted-foreground">{m.by_name ?? m.by ?? ""}{m.at ? ` ${fmtDateTime(m.at)}` : ""}</p>
              {m.answer ? <p className="text-sm mt-1">{m.answer}</p> : null}
              {(m.statements ?? []).map((s, j) => (
                <p key={j} className="text-sm mt-1 text-foreground">{indianDates(s.text)}{(s.citations ?? []).map((c, k) => <button key={k} type="button" className="quote-chip ml-1 align-middle hover:brightness-95" onClick={() => onOpenSource({ docId: c.doc_id, page: c.page ?? 0, quote: c.quote, title: docTitleOf(docs, c.doc_id, c.doc_title) })}>{docTitleOf(docs, c.doc_id, c.doc_title)}{typeof c.page === "number" ? ` p. ${c.page + 1}` : ""}</button>)}</p>
              ))}
              {!m.answer && !(m.statements ?? []).length ? <p className="text-sm text-muted-foreground mt-1">{m.message || "Nothing in the records answers this."}</p> : null}
              {m.stale ? <p className="mt-1 text-xs text-warn">Records changed since this answer.</p> : null}
              <p className="mt-1 text-[11px] text-muted-foreground" data-testid="agent-footer">{ANSWER_FOOTER}{m.model ? ` ${modelLabel(m.model)}.` : ""}</p>
            </li>
          ))}
        </ul>
        <form className="mt-2 flex flex-col gap-1.5" onSubmit={(e) => { e.preventDefault(); if (question.trim().length >= 3) ask.mutate(question.trim()); }}>
          <label htmlFor={`helper-q-${role}`} className="sr-only">Question for the {name} AI agent</label>
          <Textarea ref={inputRef} id={`helper-q-${role}`} value={question} onChange={(e) => { setQuestion(e.target.value); if (!e.target.value.trim()) setDictated(false); }} className={cn("min-h-12 text-sm")} placeholder={`Ask ${name} about this Case File`} maxLength={MAX_Q} disabled={ask.isPending} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (question.trim().length >= 3) ask.mutate(question.trim()); } }} />
          <div className="flex items-center gap-2">
            {ask.isError ? <p role="alert" className="text-xs text-bad flex-1">{errorText(ask.error)}</p>
              : dictated && question.trim() ? <span className="text-xs text-muted-foreground flex-1" data-testid="helper-heard">{HEARD}</span> : <span className="flex-1" />}
            <MicButton target={inputRef} screen={`helper-${role}`} context="question" caseId={caseId} label="Dictate the question" hint={false}
              onInsert={(next) => { setDictated(true); if (next.length > MAX_Q) setQuestion(next.slice(0, MAX_Q)); }} />
            <LoadingButton size="sm" type="submit" loading={ask.isPending} loadingText="Reading" disabled={question.trim().length < 3}><SendHorizontal className="size-4" />Ask</LoadingButton>
          </div>
        </form>
      </section>
    </div>
  );
}
