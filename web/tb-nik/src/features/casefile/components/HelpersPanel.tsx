// Specialty helpers: six "<Specialty> records check" cards. Pick one: its brief (prepared at the ready mark for the five
// heads, on click for Nuclear Medicine) with sections and points for review, then a chat thread with that helper.
// Everything comes from the records and guideline points; never an opinion.
import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Bot, Loader2, SendHorizontal, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { askAgentOld, getHelperChat, getHelpers, getRoles, notBuiltYet, postHelperChat, prepareHelper, streamAgentOld } from "../api";
import { useJob } from "../hooks";
import type { CaseFile, Helper, HelperMessage } from "../types";
import type { SourceTarget } from "./SourceViewer";
import { ErrorState, LoadingButton, NotYetState, SkeletonLines, StatusChip, docTitleOf, errorText, fmtDateTime, indianDates, modelLabel } from "./common";
import { cn } from "@/lib/utils";

const ORDER = ["radiology", "pathology", "medical_oncology", "surgical_oncology", "radiation_oncology", "nuclear_medicine"];
export const NAMES: Record<string, string> = { radiology: "Radiology", pathology: "Pathology", medical_oncology: "Medical Oncology", surgical_oncology: "Surgical Oncology", radiation_oncology: "Radiation Oncology", nuclear_medicine: "Nuclear Medicine" };

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
  const [picked, setPicked] = useState<string | null>(null);
  const h = helpers.find((x) => x.role === picked) ?? null;
  if (isLoading) return <SkeletonLines n={6} />;
  if (error) return <ErrorState error={error} retry={() => void refetch()} compact />;
  if (h) return <HelperDetail caseId={caseId} helper={h} notBuilt={notBuilt} docs={cf.documents} onBack={() => setPicked(null)} onOpenSource={onOpenSource} onChanged={async () => { await refetch(); await onCaseChanged(); }} />;
  return (
    <div className="space-y-3" data-testid="helpers-list">
      {notBuilt ? <NotYetState what="Specialty helper briefs" fallback="Showing the briefs the old route already prepared; Prepare uses the old helper stream." /> : null}
      <p className="text-sm text-muted-foreground">Each helper checks the records for its specialty and lists points for review. Records and guideline points only, never opinions. Briefs for the five board heads are prepared at the ready mark; Nuclear Medicine on request.</p>
      <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1">
        {helpers.map((x) => {
          const st = x.brief.status;
          return (
            <li key={x.role}>
              <button type="button" onClick={() => setPicked(x.role)} className="row-lift w-full text-left rounded-md border border-border bg-card p-3 hover:border-primary/60 focus-visible:outline-2" data-testid={`helper-${x.role}`}>
                <div className="flex items-center gap-2">
                  <Sparkles className="size-4 text-brand shrink-0" aria-hidden />
                  <span className="font-medium text-foreground">{NAMES[x.role] ?? x.label} records check</span>
                  <span className="ml-auto">
                    {st === "ready" ? <StatusChip kind="ok">brief ready</StatusChip> : st === "preparing" ? <StatusChip kind="info" icon={Loader2}>preparing</StatusChip> : st === "stale" ? <StatusChip kind="warn">records changed</StatusChip> : <StatusChip kind="muted">not prepared</StatusChip>}
                  </span>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{x.thread_count ? `${x.thread_count} question${x.thread_count === 1 ? "" : "s"} asked` : "No questions yet"}{x.brief.at ? `, brief ${fmtDateTime(x.brief.at)}` : ""}</p>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
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
          if (ev.type === "error") setPrepErr(String(ev.text ?? ev.message ?? "The helper stopped."));
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
    },
  });
  const messages = useMemo(() => [...(chatQ.data?.messages ?? []), ...local], [chatQ.data, local]);
  const busy = prepare.isPending || streaming || !!jobId || brief.status === "preparing";
  const name = NAMES[role] ?? helper.label;

  return (
    <div className="space-y-3" data-testid="helper-detail">
      <Button variant="ghost" size="sm" onClick={onBack} className="-ml-2"><ArrowLeft className="size-4" />All helpers</Button>
      <div className="flex items-start gap-2">
        <Sparkles className="size-5 text-brand shrink-0 mt-0.5" aria-hidden />
        <div className="flex-1 min-w-0">
          <h3 className="text-base">{name} records check</h3>
          <p className="text-xs text-muted-foreground">From the records and guideline points only. The brief is an AI draft until a doctor reviews it.{brief.model ? ` Model: ${modelLabel(brief.model)}.` : ""}</p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {brief.status === "ready" ? <StatusChip kind="ok">brief ready{brief.at ? `, ${fmtDateTime(brief.at)}` : ""}</StatusChip> : null}
        {brief.status === "stale" ? <StatusChip kind="warn">records changed since this brief</StatusChip> : null}
        {brief.status === "none" ? <StatusChip kind="muted">not prepared yet</StatusChip> : null}
        {busy ? <StatusChip kind="info" icon={Loader2}>preparing</StatusChip> : null}
        {brief.reviewed_by ? <StatusChip kind="ok">reviewed by {brief.reviewed_by}</StatusChip> : <StatusChip kind="review" icon={Bot}>AI draft</StatusChip>}
        <span className="flex-1" />
        {helper.prepare_allowed ? <LoadingButton size="sm" variant={brief.status === "ready" ? "outline" : "default"} loading={busy} loadingText="Preparing" onClick={() => prepare.mutate()}>{brief.status === "ready" ? "Prepare again" : "Prepare"}</LoadingButton> : null}
      </div>
      {busy ? (
        <div className="rounded-md border border-border bg-muted/60 p-2 text-xs" role="status" aria-live="polite">
          <p className="font-medium text-foreground">Reading the records for {name}</p>
          <p className="text-muted-foreground">You can go back to the other helpers or close this panel: it keeps preparing, and you are told when the brief is ready.</p>
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

      <section className="border-t border-border pt-3" aria-label={`Questions to the ${name} helper`}>
        <h4 className="text-sm font-semibold text-foreground mb-1">Ask the {name} helper</h4>
        {notBuilt ? <p className="text-xs text-muted-foreground mb-1">Saved helper threads are not on this server yet; answers here are not kept.</p> : null}
        {chatQ.isLoading ? <SkeletonLines n={2} /> : null}
        <ul className="space-y-2 max-h-[40dvh] overflow-y-auto">
          {messages.map((m, i) => (
            <li key={m.id ?? i} className="rounded-md border border-border p-2">
              <p className="text-sm font-medium text-foreground">{m.question}</p>
              <p className="text-xs text-muted-foreground">{m.by_name ?? m.by ?? ""}{m.at ? ` ${fmtDateTime(m.at)}` : ""}</p>
              {m.answer ? <p className="text-sm mt-1">{m.answer}</p> : null}
              {(m.statements ?? []).map((s, j) => (
                <p key={j} className="text-sm mt-1 text-foreground">{indianDates(s.text)}{(s.citations ?? []).map((c, k) => <button key={k} type="button" className="quote-chip ml-1 align-middle hover:brightness-95" onClick={() => onOpenSource({ docId: c.doc_id, page: c.page ?? 0, quote: c.quote, title: docTitleOf(docs, c.doc_id, c.doc_title) })}>{docTitleOf(docs, c.doc_id, c.doc_title)}{typeof c.page === "number" ? ` p. ${c.page + 1}` : ""}</button>)}</p>
              ))}
              {!m.answer && !(m.statements ?? []).length ? <p className="text-sm text-muted-foreground mt-1">{m.message ?? "Nothing in the records answers this."}</p> : null}
            </li>
          ))}
        </ul>
        <form className="mt-2 flex flex-col gap-1.5" onSubmit={(e) => { e.preventDefault(); if (question.trim().length >= 3) ask.mutate(question.trim()); }}>
          <label htmlFor={`helper-q-${role}`} className="sr-only">Question for the {name} helper</label>
          <Textarea id={`helper-q-${role}`} value={question} onChange={(e) => setQuestion(e.target.value)} className={cn("min-h-12 text-sm")} placeholder={`Ask the ${name} helper about the records`} maxLength={1000} disabled={ask.isPending} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (question.trim().length >= 3) ask.mutate(question.trim()); } }} />
          <div className="flex items-center gap-2">
            {ask.isError ? <p role="alert" className="text-xs text-bad flex-1">{errorText(ask.error)}</p> : <span className="flex-1" />}
            <LoadingButton size="sm" type="submit" loading={ask.isPending} loadingText="Reading" disabled={question.trim().length < 3}><SendHorizontal className="size-4" />Ask</LoadingButton>
          </div>
        </form>
      </section>
    </div>
  );
}
