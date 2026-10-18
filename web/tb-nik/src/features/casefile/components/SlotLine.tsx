// One line of the fill-in summary: the label, then either the verified value with its quote chip, or the blank with
// its actions in place. Small steps act here with Undo; evidence steps open the side panel; residents ask the consultant.
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { Bell, FileText, PenLine, Send, ShieldCheck, Trash2, UserRoundCheck, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import type { Slot, SlotAction, SlotQuote } from "../types";
import type { SourceTarget } from "./SourceViewer";
import { LoadingButton, StatusChip, fmtDate } from "./common";
import { UndoBar, type Pending } from "./deferred";

export interface SlotHandlers {
  openSource: (t: SourceTarget) => void;
  review: (slot: Slot) => void;
  editRequest: (slot: Slot, action: SlotAction) => void;
  /** The real calls; SlotLine shows the step as done at once and calls these when the Undo window closes. */
  ask: (slot: Slot, action: SlotAction) => Promise<void>;
  notNeeded: (slot: Slot, reason: string) => Promise<void>;
  remind: (slot: Slot) => Promise<void>;
  enterValue: (slot: Slot, value: string) => Promise<void>;
  clearValue: (slot: Slot) => Promise<void>;
  /** A resident's "Ask Dr X to sign off". */
  propose: (action: string, payload: Record<string, unknown>, label: string) => Promise<void>;
  schedule: (key: string, label: string, run: () => Promise<void>, opts?: { onUndo?: () => void; onDone?: () => void }) => void;
  undo: (key: string) => void;
  pending: (key: string) => Pending | undefined;
}

export interface SlotContext {
  resident: boolean;
  canAct: boolean;
  consultantName: string;
  /** Whether the server has slots.py (false: the old checklist drives the line). */
  derived: boolean;
}

export function QuoteChip({ quote, onOpen, className }: { quote: SlotQuote; onOpen: (t: SourceTarget) => void; className?: string }) {
  const page = (quote.page ?? 0) + 1;
  const title = `${quote.doc_title || "record"}, page ${page}`;
  return (
    <button
      type="button"
      onClick={() => onOpen({ docId: quote.doc_id, page: quote.page ?? 0, quote: quote.text || undefined, factId: quote.fact_id ?? undefined, title: quote.doc_title })}
      className={cn("quote-chip hover:brightness-95 active:scale-95 transition max-w-full", className)}
      title={quote.text ? `"${quote.text}"\nOpen ${title} with the quote marked` : `Open ${title}`}
      aria-label={`Open the source: ${title}`}
      data-testid="quote-chip"
    >
      <FileText className="size-3 shrink-0" aria-hidden />
      <span className="truncate">{quote.doc_title || "record"}</span>
      <span className="opacity-80 shrink-0">p. {page}</span>
    </button>
  );
}

const VALUE_RULES: Record<string, { kind: "select" | "number" | "text"; options?: string[]; min?: number; max?: number; unit?: string; help: string; maxLen?: number }> = {
  ecog: { kind: "select", options: ["0", "1", "2", "3", "4"], help: "ECOG 0 to 4 as assessed in clinic" },
  menopausal_status: { kind: "select", options: ["premenopausal", "perimenopausal", "postmenopausal"], help: "As stated by the patient or the clinic note" },
  weight: { kind: "number", min: 1, max: 300, unit: "kg", help: "1 to 300 kg" },
  height: { kind: "number", min: 30, max: 250, unit: "cm", help: "30 to 250 cm" },
  clinical_question: { kind: "text", help: "What the board should answer, 5 to 500 characters", maxLen: 500 },
};

function validate(factId: string, raw: string): string | null {
  const rule = VALUE_RULES[factId] ?? { kind: "text", help: "", maxLen: 200 };
  const v = raw.trim();
  if (!v) return "Enter a value first.";
  if (rule.kind === "select" && !rule.options?.includes(v)) return "Pick one of the listed values.";
  if (rule.kind === "number") {
    const n = Number(v.replace(",", "."));
    if (!Number.isFinite(n)) return "Enter a number.";
    if (rule.min !== undefined && n < rule.min) return `Must be at least ${rule.min} ${rule.unit ?? ""}`.trim() + ".";
    if (rule.max !== undefined && n > rule.max) return `Must be at most ${rule.max} ${rule.unit ?? ""}`.trim() + ".";
  }
  if (rule.kind === "text") {
    if (factId === "clinical_question" && v.length < 5) return "Write at least a few words.";
    if (v.length > (rule.maxLen ?? 200)) return `At most ${rule.maxLen ?? 200} characters.`;
  }
  return null;
}

function Blank({ children, kind = "muted", testId }: { children: ReactNode; kind?: "muted" | "warn" | "review" | "ok"; testId?: string }) {
  const cls = kind === "warn" ? "border-warn/50 text-warn bg-warn-soft/60" : kind === "review" ? "border-review/50 text-review bg-review-soft/60" : kind === "ok" ? "border-ok/40 text-ok bg-ok-soft/60" : "border-border-strong text-muted-foreground bg-muted/60";
  return <span data-testid={testId} className={cn("inline-flex items-center gap-1 rounded-md border border-dashed px-2 py-0.5 text-sm font-mono", cls)}>[ {children} ]</span>;
}

export function SlotLine({ slot, ctx, h }: { slot: Slot; ctx: SlotContext; h: SlotHandlers }) {
  const reduce = useReducedMotion();
  const [mode, setMode] = useState<"idle" | "reason" | "value">("idle");
  const [reason, setReason] = useState("");
  const [value, setValue] = useState("");
  const [valueErr, setValueErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [optimistic, setOptimistic] = useState<null | { status: "waiting" | "not_needed" | "reminded"; label: string; department?: string }>(null);
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>(null);
  const fieldId = useId();
  const key = `slot:${slot.id}`;
  const pending = h.pending(key);

  useEffect(() => { if (mode === "reason" || mode === "value") inputRef.current?.focus(); }, [mode]);
  useEffect(() => { setOptimistic(null); setMode("idle"); setErr(null); }, [slot.status, slot.value, slot.request?.sent_at]);

  const factId = slot.fact_id ?? slot.id.replace(/^fact:/, "");
  const rule = VALUE_RULES[factId];
  const actions = slot.actions ?? [];
  const typable = actions.some((a) => a.kind === "enter_value") || (ctx.derived && (!!slot.typable || !!VALUE_RULES[factId]));
  const askAction = actions.find((a) => a.kind === "ask_department");
  const canNotNeeded = actions.some((a) => a.kind === "not_needed");
  const dept = askAction?.department_label ?? askAction?.department ?? slot.request?.department_label ?? slot.department ?? "the department";
  const valueSlot = ctx.derived ? factId : slot.id;

  const residentAsk = (label: string) => (
    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground"><UserRoundCheck className="size-3.5" aria-hidden />{label}</span>
  );

  // ---- in-place steps --------------------------------------------------------------------------------------------
  const doAsk = async () => {
    if (!askAction) return;
    setErr(null);
    if (ctx.resident) {
      setBusy(true);
      const payload = askAction.action_id ? { action_id: askAction.action_id } : { department: askAction.department_id ?? askAction.department, label: slot.label };
      try { await h.propose("send_request", payload, `Ask ${dept} for ${slot.label}`); }
      catch (e) { setErr(e instanceof Error ? e.message : "Could not send the proposal."); }
      finally { setBusy(false); }
      return;
    }
    setOptimistic({ status: "waiting", label: `Asked ${dept} for ${slot.label}`, department: dept });
    h.schedule(key, `Asked ${dept}`, () => h.ask(slot, askAction), { onUndo: () => setOptimistic(null) });
  };
  const doNotNeeded = async () => {
    const r = reason.trim();
    if (r.length < 3) { setErr("Give a short reason: it is recorded with your name."); return; }
    setErr(null);
    if (ctx.resident) {
      setBusy(true);
      const payload = ctx.derived ? { key: slot.id, reason: r } : { slot: slot.id, reason: r };
      try { await h.propose("not_needed", payload, `Not needed: ${slot.label}`); setMode("idle"); setReason(""); }
      catch (e) { setErr(e instanceof Error ? e.message : "Could not send the proposal."); }
      finally { setBusy(false); }
      return;
    }
    setMode("idle"); setReason("");
    setOptimistic({ status: "not_needed", label: `Not needed: ${r}` });
    h.schedule(key, "Marked not needed", () => h.notNeeded(slot, r), { onUndo: () => setOptimistic(null) });
  };
  const doRemind = () => {
    setErr(null);
    setOptimistic({ status: "reminded", label: `Reminder to ${dept}` });
    h.schedule(key, `Reminder to ${dept}`, () => h.remind(slot), { onUndo: () => setOptimistic(null) });
  };
  const doEnter = async () => {
    const v = value.trim();
    const problem = validate(factId, v);
    setValueErr(problem);
    if (problem) { inputRef.current?.focus(); return; }
    setBusy(true); setErr(null);
    try {
      if (ctx.resident) await h.propose("typed_value", { slot: valueSlot, value: v }, `Enter ${slot.label}: ${v}`);
      else await h.enterValue(slot, v);
      setMode("idle"); setValue("");
    } catch (e) { setErr(e instanceof Error ? e.message : "Could not save the value."); }
    finally { setBusy(false); }
  };
  const doClear = async () => {
    setBusy(true); setErr(null);
    try { await h.clearValue(slot); } catch (e) { setErr(e instanceof Error ? e.message : "Could not remove the value."); } finally { setBusy(false); }
  };

  // ---- what the line shows --------------------------------------------------------------------------------------
  const status = optimistic?.status === "waiting" ? "waiting" : optimistic?.status === "not_needed" ? "not_needed" : slot.status;
  const notNeededBtn = canNotNeeded && ctx.canAct && mode === "idle" ? <Button size="xs" variant="outline" onClick={() => { setMode("reason"); setErr(null); }} disabled={!!pending}>Not needed</Button> : null;
  const valueBtn = (label = "Enter a value") => (typable && ctx.canAct && mode === "idle" ? <Button size="xs" variant="outline" onClick={() => { setMode("value"); setValueErr(null); setValue(slot.status === "entered" ? String(slot.value ?? "") : ""); }} disabled={!!pending}><PenLine className="size-3" />{label}</Button> : null);

  let body: ReactNode;
  if (status === "found") {
    body = (
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 min-w-0">
        <span className="text-foreground">{slot.value}{slot.unit ? ` ${slot.unit}` : ""}</span>
        {slot.as_of ? <span className="text-xs text-muted-foreground">{fmtDate(slot.as_of)}</span> : null}
        {slot.quote ? <QuoteChip quote={slot.quote} onOpen={h.openSource} /> : <span className="text-xs text-muted-foreground">{slot.note || "no quote on file"}</span>}
        {slot.quote && slot.note ? <span className="text-xs text-muted-foreground basis-full">{slot.note}</span> : null}
      </div>
    );
  } else if (status === "entered") {
    body = (
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="text-foreground">{slot.value}{slot.unit ? ` ${slot.unit}` : ""}</span>
        <StatusChip kind="info" icon={PenLine}>entered by {slot.typed_by_name || slot.typed_by || "a doctor"}, no report</StatusChip>
        {valueBtn("Change")}
        {ctx.canAct && !ctx.resident && mode === "idle" ? <Button variant="ghost" size="xs" onClick={doClear} disabled={busy} aria-label={`Remove the entered ${slot.label}`}><Trash2 className="size-3" />Remove</Button> : null}
      </div>
    );
  } else if (status === "not_needed") {
    body = (
      <div className="flex flex-wrap items-center gap-2">
        <Blank kind="muted" testId="slot-not-needed">not needed</Blank>
        <span className="text-xs text-muted-foreground">{optimistic?.label ?? slot.note ?? ""}</span>
      </div>
    );
  } else if (status === "waiting") {
    const askedOn = optimistic ? "just now" : slot.request?.sent_at ? fmtDate(slot.request.sent_at) : "";
    const who = optimistic?.department ?? slot.request?.department_label ?? slot.request?.department ?? dept;
    const overdue = slot.request?.status === "overdue";
    const canRemind = actions.some((a) => a.kind === "remind") || !!slot.request?.action_id;
    body = (
      <div className="flex flex-wrap items-center gap-2">
        <Blank kind="warn" testId="slot-waiting">waiting on {who}{askedOn ? `, asked ${askedOn}` : ""}</Blank>
        {slot.request?.due ? <span className={cn("text-xs", overdue ? "text-bad font-medium" : "text-muted-foreground")}>{overdue ? "overdue, was due" : "due"} {fmtDate(slot.request.due)}</span> : null}
        {slot.request?.reminders ? <span className="text-xs text-muted-foreground">{slot.request.reminders} reminder{slot.request.reminders === 1 ? "" : "s"} sent</span> : null}
        {!optimistic && ctx.canAct && !ctx.resident && canRemind && mode === "idle" ? <Button variant="outline" size="xs" onClick={doRemind} disabled={!!pending}><Bell className="size-3" />Remind</Button> : null}
        {optimistic?.status === "reminded" ? <StatusChip kind="ok">reminder sent</StatusChip> : null}
        {!optimistic ? notNeededBtn : null}
        {!optimistic ? valueBtn() : null}
      </div>
    );
  } else if (status === "needs_confirmation") {
    body = (
      <div className="flex flex-wrap items-center gap-2">
        <Blank kind="review" testId="slot-needs-confirmation">needs your confirmation</Blank>
        {slot.value ? <span className="text-sm text-foreground">{slot.value}</span> : null}
        {slot.quote ? <QuoteChip quote={slot.quote} onOpen={h.openSource} /> : null}
        <Button variant="secondary" size="xs" onClick={() => h.review(slot)} data-testid="slot-review"><ShieldCheck className="size-3" />{ctx.resident ? "Review and ask to sign off" : "Review"}</Button>
        {slot.note || slot.confirmation?.why ? <span className="text-xs text-muted-foreground basis-full">{slot.confirmation?.why || slot.note}</span> : null}
      </div>
    );
  } else if (status === "pending_ready") {
    body = (
      <div className="flex flex-wrap items-center gap-2">
        <Blank kind="muted">prepared at the ready mark</Blank>
        {slot.note ? <span className="text-xs text-muted-foreground">{slot.note}</span> : null}
      </div>
    );
  } else {
    // not found in the file
    body = (
      <div className="flex flex-col gap-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <Blank kind="muted" testId="slot-not-found">not found in the file</Blank>
          {slot.note && slot.note !== "Not found in the file" ? <span className="text-xs text-muted-foreground">{slot.note}</span> : null}
          {slot.draft?.doc_id ? <button type="button" className="quote-chip hover:brightness-95" onClick={() => h.openSource({ docId: slot.draft!.doc_id!, page: 0, title: slot.draft!.doc_title })}>{slot.draft.doc_title ?? "report"}: {String(slot.draft.status ?? "not final").toLowerCase()}</button> : null}
        </div>
        {mode === "idle" && ctx.canAct ? (
          <div className="flex flex-wrap items-center gap-1.5">
            {askAction ? (
              <LoadingButton size="xs" variant="default" loading={busy} onClick={doAsk} disabled={!!pending} title={ctx.resident ? `Dr ${ctx.consultantName} will be asked to sign off` : `Drafts the request and sends it; Undo for 10 s`} data-testid="slot-ask">
                <Send className="size-3" />{ctx.resident ? `Ask ${dept} (via Dr ${ctx.consultantName})` : `Ask ${dept}`}
              </LoadingButton>
            ) : null}
            {askAction?.action_id && !ctx.resident ? <Button size="xs" variant="ghost" onClick={() => h.editRequest(slot, askAction)} disabled={!!pending}>Edit request</Button> : null}
            {notNeededBtn}
            {valueBtn()}
            {ctx.resident && (askAction || canNotNeeded || typable) ? residentAsk(`Dr ${ctx.consultantName} signs off`) : null}
          </div>
        ) : null}
        {mode === "idle" && !ctx.canAct ? <span className="text-xs text-muted-foreground">Only the owner's team acts on this line.</span> : null}
      </div>
    );
  }

  return (
    <motion.div layout="position" className="group grid gap-x-3 gap-y-1 py-2.5 border-b border-border last:border-b-0 sm:grid-cols-[minmax(140px,11rem)_1fr]" data-slot-id={slot.id} data-slot-status={status}>
      <dt className="text-sm font-medium text-muted-foreground sm:pt-0.5">{slot.label}</dt>
      <dd className="min-w-0 space-y-1.5">
        {body}
        <AnimatePresence initial={false}>
          {mode === "reason" ? (
            <motion.form key="reason" initial={reduce ? false : { opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="flex flex-wrap items-center gap-1.5" onSubmit={(e) => { e.preventDefault(); void doNotNeeded(); }}>
              <label htmlFor={fieldId} className="sr-only">Why is {slot.label} not needed?</label>
              <Input id={fieldId} ref={inputRef as React.RefObject<HTMLInputElement>} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why is it not needed? (recorded with your name)" className="h-8 max-w-sm text-sm" maxLength={200} aria-invalid={!!err} />
              <LoadingButton size="xs" type="submit" loading={busy}>{ctx.resident ? `Ask Dr ${ctx.consultantName} to sign off` : "Done"}</LoadingButton>
              <Button size="xs" variant="ghost" type="button" onClick={() => { setMode("idle"); setErr(null); }} aria-label="Cancel"><X className="size-3" />Cancel</Button>
            </motion.form>
          ) : null}
          {mode === "value" ? (
            <motion.form key="value" initial={reduce ? false : { opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="flex flex-col gap-1" onSubmit={(e) => { e.preventDefault(); void doEnter(); }}>
              <div className="flex flex-wrap items-center gap-1.5">
                <label htmlFor={fieldId} className="sr-only">{slot.label}</label>
                {rule?.kind === "select" ? (
                  <select id={fieldId} ref={inputRef as React.RefObject<HTMLSelectElement>} value={value} onChange={(e) => setValue(e.target.value)} className="h-8 rounded-md border border-input bg-card px-2 text-sm" aria-invalid={!!valueErr} aria-describedby={`${fieldId}-help`}>
                    <option value="">Choose</option>
                    {rule.options!.map((o) => <option key={o} value={o}>{o}</option>)}
                  </select>
                ) : rule?.kind === "text" || factId === "clinical_question" ? (
                  <Textarea id={fieldId} ref={inputRef as React.RefObject<HTMLTextAreaElement>} value={value} onChange={(e) => setValue(e.target.value)} className="min-h-16 max-w-xl text-sm" maxLength={rule?.maxLen ?? 500} aria-invalid={!!valueErr} aria-describedby={`${fieldId}-help`} />
                ) : (
                  <Input id={fieldId} ref={inputRef as React.RefObject<HTMLInputElement>} value={value} onChange={(e) => setValue(e.target.value)} inputMode={rule?.kind === "number" ? "decimal" : "text"} placeholder={rule?.unit ? `in ${rule.unit}` : ""} className="h-8 w-40 text-sm" aria-invalid={!!valueErr} aria-describedby={`${fieldId}-help`} />
                )}
                {rule?.unit ? <span className="text-sm text-muted-foreground">{rule.unit}</span> : null}
                <LoadingButton size="xs" type="submit" loading={busy}>{ctx.resident ? `Ask Dr ${ctx.consultantName} to sign off` : "Save"}</LoadingButton>
                <Button size="xs" variant="ghost" type="button" onClick={() => { setMode("idle"); setValueErr(null); }}><X className="size-3" />Cancel</Button>
              </div>
              <p id={`${fieldId}-help`} className={cn("text-xs", valueErr ? "text-bad" : "text-muted-foreground")}>{valueErr ?? `${rule?.help ? `${rule.help}. ` : ""}Shown as "entered by you, no report".`}</p>
            </motion.form>
          ) : null}
        </AnimatePresence>
        {pending ? <UndoBar pending={pending} onUndo={() => h.undo(key)} className="max-w-md" /> : null}
        {err ? <p role="alert" className="text-xs text-bad">{err}</p> : null}
      </dd>
    </motion.div>
  );
}
