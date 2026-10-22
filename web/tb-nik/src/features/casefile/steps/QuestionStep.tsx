// Question (B3): what the board should decide, in the doctor's own words (free text only; Vaidyx suggests nothing). The reason for
// discussion in one tap, the urgency 1 to 5, and three facts reports rarely carry (the patient's wishes, comorbidities, whether the
// patient knows the diagnosis), each shown "entered by Dr X, no report".
import { useEffect, useState } from "react";
import { ArrowRight, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import type { SourceTarget } from "../components/SourceViewer";
import { LoadingButton, errorText, fmtDateTime } from "../components/common";
import { Card } from "./Overview";
import type { StepRow, Steps } from "./types";
import { SourceChip } from "./Value";

const URGENCY = [1, 2, 3, 4, 5];
const URGENCY_WORD: Record<number, string> = { 1: "Routine", 2: "Low", 3: "Normal", 4: "Urgent", 5: "Most urgent" };

function Choice<T extends string | number>({ options, value, onPick, label, disabled }: { options: Array<{ id: T; label: string }>; value: T | null | undefined; onPick: (v: T) => void; label: string; disabled?: boolean }) {
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-1.5">
      {options.map((o) => (
        <button key={String(o.id)} type="button" role="radio" aria-checked={value === o.id} disabled={disabled} onClick={() => onPick(o.id)}
          className={cn("inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition active:scale-[0.98] disabled:opacity-60",
            value === o.id ? "border-primary bg-secondary font-semibold text-secondary-foreground" : "border-border bg-card hover:bg-accent")}>
          {value === o.id ? <Check className="size-3.5" aria-hidden /> : null}{o.label}
        </button>
      ))}
    </div>
  );
}

function Extra({ row, onSave, onOpen, canEdit, choices }: { row: StepRow; onSave: (v: string) => Promise<void>; onOpen: (t: SourceTarget) => void; canEdit: boolean; choices?: string[] }) {
  const [v, setV] = useState(row.status === "entered" ? row.value : "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { setV(row.status === "entered" ? row.value : ""); }, [row.status, row.value]);
  const save = async (value: string) => {
    setBusy(true); setErr(null);
    try { await onSave(value); } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  };
  const fromReport = row.status === "found" ? row : row.report_value ? { value: row.report_value.value, quote: row.report_value.quote } : null;
  return (
    <div className="space-y-1.5 py-3" data-testid={`extra-${row.fact_id}`}>
      <p className="text-sm font-medium text-foreground">{row.label}</p>
      {fromReport?.value ? (
        <p className="flex flex-wrap items-baseline gap-2 text-sm text-muted-foreground">In the reports: <span className="text-foreground">{fromReport.value}</span>{fromReport.quote?.doc_id ? <SourceChip quote={fromReport.quote} onOpen={onOpen} /> : null}</p>
      ) : null}
      {choices ? (
        <Choice options={choices.map((c) => ({ id: c, label: c }))} value={row.status === "entered" ? row.value : null} label={row.label} disabled={!canEdit || busy} onPick={(c) => void save(c)} />
      ) : (
        <div className="flex flex-col gap-1.5 sm:flex-row sm:items-start">
          <Textarea value={v} onChange={(e) => setV(e.target.value)} disabled={!canEdit} maxLength={1000} className="min-h-14 flex-1 text-sm" aria-label={row.label}
            placeholder={row.fact_id === "patient_preference" ? "What the patient wants or will not accept, in a few words" : "For example: type 2 diabetes on metformin, hypertension"} />
          {canEdit ? <LoadingButton size="sm" variant="outline" loading={busy} disabled={v.trim().length < 2 || v.trim() === (row.status === "entered" ? row.value : "")} onClick={() => void save(v.trim())}>Save</LoadingButton> : null}
        </div>
      )}
      {row.status === "entered" ? <p className="text-xs text-muted-foreground">Entered by {row.entered_by || "the treating doctor"}{row.entered_at ? `, ${fmtDateTime(row.entered_at)}` : ""}, no report.</p> : null}
      {err ? <p role="alert" className="text-xs text-bad">{err}</p> : null}
    </div>
  );
}

export function QuestionStep({ steps, canEdit, onSaveQuestion, onReason, onUrgency, onSaveFact, onOpen, onNext, resident, consultantName }: {
  steps: Steps; canEdit: boolean; resident: boolean; consultantName: string;
  onSaveQuestion: (text: string) => Promise<void>; onReason: (v: string) => Promise<void>; onUrgency: (n: number) => Promise<void>;
  onSaveFact: (factId: string, v: string) => Promise<void>; onOpen: (t: SourceTarget) => void; onNext: () => void;
}) {
  const q = steps.question;
  const [text, setText] = useState(q.text);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { setText(q.text); }, [q.text]);
  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key); setErr(null);
    try { await fn(); } catch (e) { setErr(errorText(e)); } finally { setBusy(null); }
  };
  const saved = !!q.text && text.trim() === q.text;
  return (
    <div className="space-y-4" data-testid="section-question">
      <Card title="What should the board decide?" testId="question-text">
        <div className="space-y-2 py-2">
          <Textarea value={text} onChange={(e) => setText(e.target.value)} disabled={!canEdit} maxLength={1000} className="min-h-24 text-[1rem]" aria-label="The question for the board"
            placeholder="In your own words, for example: Is she fit for breast conservation surgery, or should she get chemotherapy first?" data-testid="question-input" />
          <div className="flex flex-wrap items-center gap-2">
            {canEdit ? (
              <LoadingButton loading={busy === "q"} disabled={text.trim().length < 5 || saved} onClick={() => void run("q", () => onSaveQuestion(text.trim()))} data-testid="question-save">
                {saved ? <><Check className="size-4" />Saved</> : resident ? `Send to Dr ${consultantName} for sign-off` : "Save the question"}
              </LoadingButton>
            ) : null}
            {q.text ? <span className="text-xs text-muted-foreground">Written by {q.by || "the treating doctor"}{q.at ? `, ${fmtDateTime(q.at)}` : ""}</span> : <span className="text-xs text-muted-foreground">The board sees exactly these words.</span>}
          </div>
        </div>
      </Card>

      <Card title="Reason for discussion" testId="question-reason">
        <div className="py-2">
          <Choice options={steps.reasons} value={q.reason?.value ?? null} label="Reason for discussion" disabled={!canEdit || busy === "r"} onPick={(v) => void run("r", () => onReason(v))} />
        </div>
      </Card>

      <Card title="Urgency" testId="question-urgency">
        <div className="space-y-1.5 py-2">
          <Choice options={URGENCY.map((n) => ({ id: n, label: `${n} ${URGENCY_WORD[n]}` }))} value={q.urgency?.level ?? null} label="Urgency, 1 routine to 5 most urgent" disabled={!canEdit || busy === "u"} onPick={(n) => void run("u", () => onUrgency(n))} />
          {resident && canEdit ? <p className="text-xs text-muted-foreground">Dr {consultantName} signs off the urgency.</p> : null}
        </div>
      </Card>

      {q.extras.length ? (
        <Card title="What the reports rarely say" testId="question-extras">
          <p className="pt-2 text-sm text-muted-foreground">Optional. Shown to the board as entered by you, never as a report.</p>
          <div className="divide-y divide-border">
            {q.extras.map((r) => (
              <Extra key={r.slot_id} row={r} canEdit={canEdit} onOpen={onOpen} choices={r.fact_id === "patient_awareness" ? ["Yes", "No", "Partly"] : undefined}
                onSave={(v) => onSaveFact(r.slot_id, v)} />
            ))}
          </div>
        </Card>
      ) : null}

      {err ? <p role="alert" className="text-sm text-bad">{err}</p> : null}
      <div className="flex justify-end"><Button variant="outline" onClick={onNext}>Next: Reports<ArrowRight className="size-4" /></Button></div>
    </div>
  );
}
