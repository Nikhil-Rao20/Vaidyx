// Check (B5): side by side. On the left the values with a problem (two reports differ, an unclear scan line), one at a time, then the key
// values (histology, grade, receptors and biomarkers, stage as written) each with a one-tap Confirm that names the value; on the right
// the report, scrolled to the line with it highlighted. "This is wrong" offers both: correct it (the right value and a reason, shown
// "corrected by Dr X", the report line kept) or send a request to the department to amend the report. A resident on the team sends
// each key value to the treating consultant for sign-off instead (night-v3 item 1.8). Two reports that differ stay listed after the
// doctor picks the value the board uses ("Picked: 4.6 cm from the CT report, by Dr X", with Undo); they no longer count (item 1.7). A pick
// that no longer matches its report is said on the row ("Your pick of 4.6 cm from the CT report no longer matches the report: pick again").
// Voice (night-v3 item 4.4): a mic beside the "Why" box of a correction fills it as an editable edit; the corrected value is typed.
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ArrowRight, Check, CheckCircle2, Clock, Send, ShieldQuestion, Undo2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MicButton } from "@/components/MicButton";
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
  /** Take back the value picked for the board when two reports differ (night-v3 item 1.7). */
  undoPick: (k: CheckItem) => Promise<void>;
}

function PickedLine({ p, h, canUndo }: { p: CheckItem; h: CheckHandlers; canUndo: boolean }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  if (!p.picked) return null;
  return (
    <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs" data-testid="problem-picked">
      <span className="text-ok">Picked: {p.picked.value} from {niceTitle(p.picked.doc_title) || "the report"}, by {p.picked.by_name || p.picked.by || "a doctor"}</span>
      {canUndo ? (
        <Button size="xs" variant="ghost" disabled={busy} onClick={() => void (async () => { setBusy(true); setErr(null); try { await h.undoPick(p); } catch (e) { setErr(errorText(e)); } finally { setBusy(false); } })()}>
          <Undo2 className="size-3" />Undo
        </Button>
      ) : null}
      {err ? <span role="alert" className="basis-full text-bad">{err}</span> : null}
    </span>
  );
}

const targetOf = (it?: CheckItem | null): SourceTarget | null => (it?.quote?.doc_id ? { docId: it.quote.doc_id, page: it.quote.page ?? 0, quote: it.quote.text || undefined, factId: it.fact_id ?? undefined, title: it.quote.doc_title } : null);

function WrongValue({ k, h, deptLabel, caseId }: { k: CheckItem; h: CheckHandlers; deptLabel: string; caseId: string }) {
  const [mode, setMode] = useState<"idle" | "correct">("idle");
  const [value, setValue] = useState("");
  const [reason, setReason] = useState("");
  const reasonRef = useRef<HTMLInputElement>(null);
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
          <div className="flex items-start gap-1">
            <Input ref={reasonRef} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why (recorded with your name)" className="h-8 min-w-0 flex-1 text-sm" maxLength={200} aria-label="Why" />
            <MicButton target={reasonRef} screen="check-why" context="reason" caseId={caseId} size="icon-xs" label="Dictate the reason"
              onInsert={(next) => { if (next.length > 200) setReason(next.slice(0, 200)); }} />
          </div>
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

function KeyRow({ k, selected, onSelect, h, canConfirm, canPropose, deptLabel, consultantName, caseId }: { k: CheckItem; selected: boolean; onSelect: () => void; h: CheckHandlers; canConfirm: boolean; canPropose: boolean; deptLabel: string; consultantName: string; caseId: string }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [sent, setSent] = useState<string | null>(null); // the value sent for sign-off (until the page shows it confirmed)
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
        ) : canPropose && sent === k.value ? (
          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground" data-testid="key-waiting"><Clock className="size-3.5" aria-hidden />Waiting for Dr {consultantName}'s sign-off</span>
        ) : canPropose ? (
          <LoadingButton size="sm" variant="outline" loading={busy} onClick={() => void run(async () => { await h.confirmKey(k); setSent(k.value); })} data-testid="propose-key"><Send className="size-4" />Send to Dr {consultantName} for sign-off</LoadingButton>
        ) : <span className="text-xs text-muted-foreground">Dr {consultantName} confirms the key values.</span>}
      </div>
      {canConfirm && !k.confirmed ? <div className="mt-1"><WrongValue k={k} h={h} deptLabel={deptLabel} caseId={caseId} /></div> : null}
      {err ? <p role="alert" className="mt-1 text-xs text-bad">{err}</p> : null}
    </li>
  );
}

export function CheckStep({ steps, caseId, docs, h, canConfirm, consultantName, target, onNext }: {
  steps: Steps; caseId: string; docs: CaseDocument[]; h: CheckHandlers; canConfirm: boolean; consultantName: string; target?: string | null; onNext: () => void;
}) {
  const { problems, keys } = steps.check;
  const resident = steps.mode === "prepare" && steps.role === "resident";
  const all = useMemo(() => [...problems, ...keys], [problems, keys]);
  const openProblems = problems.filter((p) => !p.resolved);
  const [sel, setSel] = useState<string | null>(target ?? openProblems[0]?.slot_id ?? keys.find((k) => !k.confirmed)?.slot_id ?? problems[0]?.slot_id ?? keys[0]?.slot_id ?? null);
  useEffect(() => { if (target) setSel(target); }, [target]);
  const current = all.find((x) => x.slot_id === sel) ?? null;
  const t = targetOf(current);
  const deptOf = (k: CheckItem) => {
    const d = steps.documents.find((x) => x.doc_id === k.quote?.doc_id);
    const n = (d?.department || "").replace(/_/g, " ");
    return n ? `${n.charAt(0).toUpperCase()}${n.slice(1)} department` : "the department";
  };
  const open = openProblems.length + keys.filter((k) => !k.confirmed).length;
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
              <h2 id="h-problems" className="flex items-center gap-1.5 text-[15px]"><ShieldQuestion className="size-4 text-warn" aria-hidden />Please check ({openProblems.length}{openProblems.length !== problems.length ? ` of ${problems.length}` : ""})</h2>
              <ul className="space-y-2">
                {problems.map((p) => (
                  <li key={p.slot_id} className={cn("rounded-lg border p-3", sel === p.slot_id ? "border-primary bg-secondary/40" : "border-border bg-card")} data-testid="problem-row" data-resolved={p.resolved ? "yes" : "no"}>
                    <button type="button" className="block w-full text-left" onClick={() => setSel(p.slot_id)}>
                      <span className="flex items-center gap-2 text-sm font-semibold text-foreground">{p.label}{p.resolved ? <CheckCircle2 className="size-3.5 text-ok" aria-hidden /> : null}</span>
                      {sel !== p.slot_id && !p.picked ? <span className={cn("block text-xs", p.pick_stale ? "text-warn" : "text-muted-foreground")} data-testid={p.pick_stale ? "problem-pick-stale" : undefined}>{p.why || "Please check against the report"}</span> : null}
                    </button>
                    {p.picked && sel !== p.slot_id ? <PickedLine p={p} h={h} canUndo={canConfirm} /> : null}
                    {sel === p.slot_id ? <div className="mt-2 border-t border-border pt-2">{h.review(p.slot_id, () => setSel(openProblems.find((x) => x.slot_id !== p.slot_id)?.slot_id ?? keys.find((k) => !k.confirmed)?.slot_id ?? null))}</div> : null}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
          {keys.length ? (
            <section className="space-y-2" aria-labelledby="h-keys">
              <h2 id="h-keys" className="text-[15px]">Key values ({keys.filter((k) => k.confirmed).length} of {keys.length} confirmed)</h2>
              {resident && !canConfirm ? <p className="text-xs text-muted-foreground">Dr {consultantName} confirms the key values. Read each one against its report line, then send it for sign-off.</p> : null}
              <ul className="space-y-2">{keys.map((k) => <KeyRow key={k.slot_id} k={k} selected={sel === k.slot_id} onSelect={() => setSel(k.slot_id)} h={h} canConfirm={canConfirm} canPropose={resident && !canConfirm} deptLabel={deptOf(k)} consultantName={consultantName} caseId={caseId} />)}</ul>
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
