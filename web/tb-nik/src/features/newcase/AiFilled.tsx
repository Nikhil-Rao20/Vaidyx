// What the AI pre-fill (usePrefill, docs/new-case/DESIGN.md N6) shows on the New Case File: the line at the top of the Cancer step
// (reading, filled, nothing found, not available), a small "Filled by AI from <report>, check it" note under each field it filled with
// the quote one tap away (the proof: the words checked against that report), and the urgency suggestion with a one-tap Use (never
// pre-selected). The department chosen from the visits says so (no model was involved). Each renders nothing without the pre-fill.
import { useState, type ReactNode } from "react";
import { motion } from "motion/react";
import { Hospital, LoaderCircle, Sparkles, Undo2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatDate, plural } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { PrefillResult, PrefillSource } from "@/lib/types";
import { modelLabel } from "@/features/casefile/components/common";
import { usePrefillContext, type AiField } from "@/features/newcase/usePrefill";

function sourceWords(s?: PrefillSource): string {
  if (!s) return "the records";
  return [s.title, s.date ? formatDate(s.date) : ""].filter(Boolean).join(", ");
}

/** "Gemma-4-31B (non-medical)": the model as the project labels it everywhere. */
function modelWords(m?: PrefillResult["model"]): string {
  const label = modelLabel(m?.label) || m?.label || "a model";
  return m?.medical === false && !/non-medical/i.test(label) ? `${label} (non-medical)` : label;
}

function AiChip() {
  return (
    <span className="inline-flex shrink-0 items-center gap-1 rounded-sm status-review px-1.5 py-0.5 text-[11px] font-semibold leading-4">
      <Sparkles className="size-3" aria-hidden />AI
    </span>
  );
}

function Proof({ quote, source, basis, model }: { quote?: string; source?: PrefillSource; basis?: PrefillSource[]; model?: PrefillResult["model"] }) {
  return (
    <motion.div initial={{ opacity: 0, y: -2 }} animate={{ opacity: 1, y: 0 }} className="mt-1 grid gap-1 border-l-2 border-current pl-2 text-xs text-review" data-testid="ai-proof">
      {quote ? <q className="break-words text-foreground italic">{quote}</q> : null}
      {basis?.length ? <span className="text-foreground">Rests on: {basis.map(sourceWords).join("; ")}</span> : null}
      <span className="text-muted-foreground">
        {quote ? `Found word for word in ${sourceWords(source)}. ` : "A draft written from the reports; edit it to your own words. "}
        Read by {modelWords(model)}.
      </span>
    </motion.div>
  );
}

/** The note under a field the AI filled; nothing when the field is not (or no longer) AI-filled. */
export function AiFilled({ field, className }: { field: AiField; className?: string }) {
  const ctx = usePrefillContext();
  const [open, setOpen] = useState(false);
  const mark = ctx?.marks[field];
  if (!ctx || !mark) return null;
  if (field === "department") {
    return (
      <p className={cn("flex items-start gap-1.5 text-xs text-muted-foreground", className)} data-testid="ai-filled-department">
        <Hospital className="mt-0.5 size-3.5 shrink-0" aria-hidden />
        <span>Chosen from the patient's visits ({mark.why?.replace(/^Your department in the patient's visits:?\s*/i, "") || "your department"}). Check it.</span>
      </p>
    );
  }
  const what = field === "boardQuestion"
    ? <>Drafted by AI from {plural(mark.basis?.length || ctx.result?.reports_read || 0, "report")}, check and edit it</>
    : <>Filled by AI{mark.value ? <> as <span className="font-medium text-foreground">{mark.value}</span></> : null} from <span className="font-medium text-foreground">{sourceWords(mark.source)}</span>, check it</>;
  return (
    <div className={cn("text-xs", className)} data-testid={`ai-filled-${field}`}>
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-muted-foreground">
        <AiChip />
        <span className="min-w-0 break-words">{what}</span>
        <button type="button" className="font-medium text-primary underline-offset-2 hover:underline focus-visible:underline focus-visible:outline-none" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
          {open ? "Hide" : field === "boardQuestion" ? "Show the reports" : "Show the quote"}
        </button>
      </p>
      {open ? <Proof quote={mark.quote} source={mark.source} basis={mark.basis} model={ctx.result?.model} /> : null}
    </div>
  );
}

/** The urgency the AI suggests, with its reason and quote: one tap uses it. Never selected for the doctor. */
export function AiUrgency({ current, onUse }: { current: number | null; onUse: (level: number) => void }) {
  const ctx = usePrefillContext();
  const [open, setOpen] = useState(false);
  const u = ctx?.urgency;
  if (!ctx || !u) return null;
  return (
    <div className="rounded-md border border-dashed border-tint-line bg-card p-2.5 text-xs sm:max-w-md" data-testid="ai-urgency">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
        <AiChip />
        <span className="min-w-0 flex-1 break-words text-foreground"><span className="font-semibold">AI suggests {u.level}</span>{u.reason ? `: ${u.reason}` : ""}</span>
        {current === u.level ? <span className="text-muted-foreground">In use</span> : (
          <Button type="button" size="xs" variant="outline" onClick={() => onUse(u.level)}>Use {u.level}</Button>
        )}
      </div>
      <p className="mt-1 flex flex-wrap gap-x-2 text-muted-foreground">
        <span>Your call: pick any level above.</span>
        <button type="button" className="font-medium text-primary underline-offset-2 hover:underline focus-visible:underline focus-visible:outline-none" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
          {open ? "Hide" : "Show the quote"}
        </button>
      </p>
      {open ? <Proof quote={u.quote} source={u.report} model={ctx.result?.model} /> : null}
    </div>
  );
}

/** The line at the top of the Cancer step: reading, filled (with Clear AI suggestions), nothing found, or not available. */
export function PrefillStatus() {
  const ctx = usePrefillContext();
  if (!ctx || ctx.status === "off") return null;
  const r = ctx.result;
  const read = r?.reports_read ?? 0;
  const filled = Object.keys(ctx.marks).length;
  const dropped = r?.dropped?.length ?? 0;
  const found = Boolean(r && (r.cancer || r.setting || r.board_question?.text || r.department));  // suggested, though maybe not filled
  let line: ReactNode;
  if (ctx.status === "running") {
    line = <><LoaderCircle className="size-3.5 shrink-0 animate-spin" aria-hidden /><span>{ctx.expected ? `Reading ${plural(ctx.expected, "report")} to fill this in.` : "Reading the records to fill this in."} You can carry on.</span></>;
  } else if (ctx.status === "failed") {
    return <p className="text-xs text-muted-foreground" data-testid="prefill-status" role="status">{ctx.error}</p>;
  } else if (ctx.status === "cleared") {
    return <p className="text-xs text-muted-foreground" data-testid="prefill-status" role="status">AI suggestions cleared.</p>;
  } else if (!read) {
    return <p className="text-xs text-muted-foreground" data-testid="prefill-status" role="status">No report in the window had text the AI could read. Fill the steps yourself.</p>;
  } else if (!filled && !ctx.urgency && found) {
    line = <><Sparkles className="size-3.5 shrink-0" aria-hidden /><span>The AI read {plural(read, "report")}. Your own entries were kept: the AI fills only empty fields.</span></>;
  } else if (!filled && !ctx.urgency) {
    line = <><Sparkles className="size-3.5 shrink-0" aria-hidden /><span>The AI read {plural(read, "report")} and found nothing it could show proof for. Fill the steps yourself.</span></>;
  } else {
    line = <><Sparkles className="size-3.5 shrink-0" aria-hidden /><span>Filled from {plural(read, "report")}. Check each value.</span></>;
  }
  return (
    <motion.div initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} role="status" data-testid="prefill-status"
      className="flex flex-col gap-2 rounded-md status-review px-3 py-2 text-sm sm:flex-row sm:items-center sm:justify-between">
      <div className="grid gap-0.5">
        <p className="flex items-center gap-2">{line}</p>
        {ctx.status === "done" && read ? (
          <p className="text-xs opacity-90">
            Read by {modelWords(r?.model)}. Every value shows the words it was taken from.
            {dropped ? ` ${plural(dropped, "suggestion")} left out: the reports did not prove ${dropped === 1 ? "it" : "them"}.` : ""}
          </p>
        ) : null}
      </div>
      {ctx.status === "done" && (filled || ctx.urgency) ? (
        <Button type="button" size="sm" variant="outline" className="w-fit shrink-0 bg-card" onClick={ctx.clear}>
          <Undo2 className="size-4" aria-hidden /> Clear AI suggestions
        </Button>
      ) : null}
    </motion.div>
  );
}
