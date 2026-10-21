// Check (B5): side by side. On the left the values with a problem (two reports differ, an unclear scan line), one at a time, then the key
// values (histology, grade, receptors and biomarkers, stage as written) each with a one-tap Confirm that names the value; on the right
// the report, scrolled to the line with it highlighted. "This is wrong" offers both: correct it (the right value and a reason, shown
// "corrected by Dr X", the report line kept) or send a request to the department to amend the report.
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ArrowRight, Check, CheckCircle2, ShieldQuestion, Undo2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { CaseDocument } from "../types";
import { SourceViewer, type SourceTarget } from "../components/SourceViewer";
import { LoadingButton, errorText, fmtDateTime, niceTitle } from "../components/common";
import type { CheckItem, Steps } from "./types";

export interface CheckHandlers {
  confirmKey: (k: CheckItem) => Promise<void>;
  undoKey: (k: CheckItem) => Promise<void>;
  correct: (k: CheckItem, value: string, reason: string) => Promise<void>;
  askAmend: (k: CheckItem) => Promise<void>;
  /** The review of a problem value (pick between the reports), from the existing review panel. */
  review: (slotId: string, onDone: () => void) => ReactNode;
}

const targetOf = (it?: CheckItem | null): SourceTarget | null => (it?.quote?.doc_id ? { docId: it.quote.doc_id, page: it.quote.page ?? 0, quote: it.quote.text || undefined, factId: it.fact_id ?? undefined, title: it.quote.doc_title } : null);

function WrongValue({ k, h, deptLabel }: { k: CheckItem; h: CheckHandlers; deptLabel: string }) {
  const [mode, setMode] = useState<"idle" | "correct">("idle");
  const [value, setValue] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const run = async (key: string, fn: () => Promise<void>) => { setBusy(key); setErr(null); try { await fn(); } catch (e) { setErr(errorText(e)); } finally { setBusy(null); } };
  if (sent) return <p className="text-xs text-ok">Request sent to {deptLabel} to amend the report.</p>;
  return (
    <div className="space-y-1.5">
      {mode === "idle" ? (
        <div className="flex flex-wrap gap-1.5">
          <Button size="xs" variant="ghost" onClick={() => setMode("correct")}>This is wrong: correct it</Button>
          <LoadingButton size="xs" variant="ghost" loading={busy === "amend"} onClick={() => void run("amend", async () => { await h.askAmend(k); setSent(true); })}>Send request to {deptLabel} to amend the report</LoadingButton>
        </div>
      ) : (
        <form className="space-y-1.5 rounded-md border border-border bg-muted/40 p-2" onSubmit={(e) => { e.preventDefault(); void run("correct", () => h.correct(k, value.trim(), reason.trim())); }}>
          <Input autoFocus value={value} onChange={(e) => setValue(e.target.value)} placeholder="The right value, as the report should say it" className="h-8 text-sm" maxLength={200} aria-label="The right value" />
          <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why (recorded with your name)" className="h-8 text-sm" maxLength={200} aria-label="Why" />
          <div className="flex gap-1.5">
            <LoadingButton size="xs" type="submit" loading={busy === "correct"} disabled={!value.trim() || reason.trim().length < 3}>Save the correction</LoadingButton>
            <Button size="xs" variant="ghost" type="button" onClick={() => setMode("idle")}>Cancel</Button>
          </div>
        </form>
      )}
      {err ? <p role="alert" className="text-xs text-bad">{err}</p> : null}
    </div>
  );
}

function KeyRow({ k, selected, onSelect, h, canConfirm, deptLabel, consultantName }: { k: CheckItem; selected: boolean; onSelect: () => void; h: CheckHandlers; canConfirm: boolean; deptLabel: string; consultantName: string }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const run = async (fn: () => Promise<void>) => { setBusy(true); setErr(null); try { await fn(); } catch (e) { setErr(errorText(e)); } finally { setBusy(false); } };
  return (
    <li className={cn("rounded-lg border p-3 transition", selected ? "border-primary bg-secondary/40" : "border-border bg-card hover:border-border-strong")} data-testid="key-row" data-confirmed={k.confirmed ? "yes" : "no"}>
      <button type="button" onClick={onSelect} className="block w-full text-left">
        <span className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">{k.label}{k.confirmed ? <CheckCircle2 className="size-3.5 text-ok" aria-hidden /> : null}</span>
        <span className="mt-0.5 block text-[1.05rem] font-semibold text-foreground">{k.value}{k.unit ? ` ${k.unit}` : ""}</span>
        {k.quote?.text ? <span className="mt-1 block border-l-2 border-primary/60 pl-2 text-sm text-body">"{k.quote.text}"</span> : null}
        {k.quote?.doc_title ? <span className="mt-0.5 block text-xs text-muted-foreground">{niceTitle(k.quote.doc_title)}</span> : null}
      </button>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {k.confirmed ? (
          <>
            <span className="text-xs text-ok">Confirmed by {k.confirmed_by}{k.confirmed_at ? `, ${fmtDateTime(k.confirmed_at)}` : ""}</span>
            {canConfirm ? <Button size="xs" variant="ghost" onClick={() => void run(() => h.undoKey(k))} disabled={busy}><Undo2 className="size-3" />Undo</Button> : null}
          </>
        ) : canConfirm ? (
          <LoadingButton size="sm" loading={busy} onClick={() => void run(() => h.confirmKey(k))} data-testid="confirm-key"><Check className="size-4" />Confirm {k.value.length <= 32 ? k.value : k.label.replace(/\s*\(.*\)$/, "")}</LoadingButton>
        ) : <span className="text-xs text-muted-foreground">Dr {consultantName} confirms the key values.</span>}
      </div>
      {canConfirm && !k.confirmed ? <div className="mt-1"><WrongValue k={k} h={h} deptLabel={deptLabel} /></div> : null}
      {err ? <p role="alert" className="mt-1 text-xs text-bad">{err}</p> : null}
    </li>
  );
}

export function CheckStep({ steps, caseId, docs, h, canConfirm, consultantName, target, onNext }: {
  steps: Steps; caseId: string; docs: CaseDocument[]; h: CheckHandlers; canConfirm: boolean; consultantName: string; target?: string | null; onNext: () => void;
}) {
  const { problems, keys } = steps.check;
  const all = useMemo(() => [...problems, ...keys], [problems, keys]);
  const [sel, setSel] = useState<string | null>(target ?? problems[0]?.slot_id ?? keys.find((k) => !k.confirmed)?.slot_id ?? keys[0]?.slot_id ?? null);
  useEffect(() => { if (target) setSel(target); }, [target]);
  const current = all.find((x) => x.slot_id === sel) ?? null;
  const t = targetOf(current);
  const deptOf = (k: CheckItem) => {
    const d = steps.documents.find((x) => x.doc_id === k.quote?.doc_id);
    const n = (d?.department || "").replace(/_/g, " ");
    return n ? `${n.charAt(0).toUpperCase()}${n.slice(1)} department` : "the department";
  };
  const open = problems.length + keys.filter((k) => !k.confirmed).length;
  if (!all.length) {
    return (
      <div className="space-y-4" data-testid="section-check">
        <div className="surface px-4 py-6 text-center text-sm text-muted-foreground">Nothing to check: no key value has been read from a final report yet.</div>
        <div className="flex justify-end"><Button variant="outline" onClick={onNext}>Next: Pre-Authorization<ArrowRight className="size-4" /></Button></div>
      </div>
    );
  }
  return (
    <div className="space-y-4" data-testid="section-check">
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(320px,0.95fr)_minmax(0,1.05fr)]">
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">{open ? `${open} to do. Read each value against its report line on the right.` : "Every value here is confirmed."}</p>
          {problems.length ? (
            <section className="space-y-2" aria-labelledby="h-problems">
              <h2 id="h-problems" className="flex items-center gap-1.5 text-[15px]"><ShieldQuestion className="size-4 text-warn" aria-hidden />Please check ({problems.length})</h2>
              <ul className="space-y-2">
                {problems.map((p) => (
                  <li key={p.slot_id} className={cn("rounded-lg border p-3", sel === p.slot_id ? "border-primary bg-secondary/40" : "border-border bg-card")} data-testid="problem-row">
                    <button type="button" className="block w-full text-left" onClick={() => setSel(p.slot_id)}>
                      <span className="block text-sm font-semibold text-foreground">{p.label}</span>
                      {sel !== p.slot_id ? <span className="block text-xs text-muted-foreground">{p.why || "Please check against the report"}</span> : null}
                    </button>
                    {sel === p.slot_id ? <div className="mt-2 border-t border-border pt-2">{h.review(p.slot_id, () => setSel(problems.find((x) => x.slot_id !== p.slot_id)?.slot_id ?? keys.find((k) => !k.confirmed)?.slot_id ?? null))}</div> : null}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
          {keys.length ? (
            <section className="space-y-2" aria-labelledby="h-keys">
              <h2 id="h-keys" className="text-[15px]">Key values ({keys.filter((k) => k.confirmed).length} of {keys.length} confirmed)</h2>
              <ul className="space-y-2">{keys.map((k) => <KeyRow key={k.slot_id} k={k} selected={sel === k.slot_id} onSelect={() => setSel(k.slot_id)} h={h} canConfirm={canConfirm} deptLabel={deptOf(k)} consultantName={consultantName} />)}</ul>
            </section>
          ) : null}
        </div>
        <aside className="surface p-3 lg:sticky lg:top-20" aria-label="The report" data-testid="check-source">
          {t ? <SourceViewer caseId={caseId} target={t} doc={docs.find((d) => d.doc_id === t.docId)} />
            : <p className="py-8 text-center text-sm text-muted-foreground">Pick a value to see its report line here.</p>}
        </aside>
      </div>
      <div className="flex justify-end"><Button variant="outline" onClick={onNext}>Next: Pre-Authorization<ArrowRight className="size-4" /></Button></div>
    </div>
  );
}
