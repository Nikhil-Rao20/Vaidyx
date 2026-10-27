// The decision form the coordinator fills during the meeting, in six steps (night-v3 3.1, the decision record v2). The fields,
// labels, limits, choices and the outcome rules come from decision_fields.json (tumour_board/decision_record.py spec()), so the
// form and the server never disagree. The form records what the board said: nothing is chosen for the coordinator (no intent,
// no modality, no decision). The decision text shows live at the bottom of the room screen (sent 400 ms after the last
// keystroke, marked "not saved") and is saved after the read-back.
// mode="correct" (night-v3 3.2): the same six steps open on a saved board record from the Case File's Board decisions panel. The
// outcome is fixed, there is no live strip, a reason is asked on the last step, and only the changed fields are sent as a new version.
// Voice (night-v3 4.4): the sentence boxes have a dictation button under them on the right, and the decision a "Read back" speaker;
// the words heard go into the box as an edit, never saved by themselves. Voice off draws nothing.
import { useEffect, useId, useMemo, useRef, useState, type ReactNode, type RefObject } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Check, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { DateInput } from "@/components/DateInput";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { MicButton } from "@/components/MicButton";
import { SpeakButton } from "@/components/SpeakButton";
import type { Attendee } from "@/lib/live";
import type { SttContext } from "@/lib/voice";
import { cn } from "@/lib/utils";
import { correctBoardRecord, decisionLive, getMeeting, saveDecision } from "../api";
import specJson from "../decision_fields.json";
import type { DecisionBody, DecisionChoice, DecisionField, DecisionSpec } from "../types";
import type { BoardRecord } from "@/features/casefile/types";
import { LoadingButton, errorText, useAnnounce } from "@/features/casefile/components/common";

/** The field table, the same one the server checks against. */
export const DECISION_SPEC = specJson as DecisionSpec;
const STEPS = DECISION_SPEC.steps;
const BY_KEY = new Map(DECISION_SPEC.fields.map((x) => [x.key, x]));
const LIST_KINDS = new Set(["multi", "people", "concerns", "investigations", "referrals"]);

type Form = Required<DecisionBody>;
type Key = keyof Form;

export const fieldOf = (k: string): DecisionField => BY_KEY.get(k) ?? { key: k, label: k.replace(/_/g, " "), kind: "short", step: STEPS[0]?.id ?? "outcome" };
const limitOf = (k: string, part?: string): number | undefined => {
  const l = fieldOf(k).limit;
  if (typeof l === "number") return l;
  return l && part ? l[part] : undefined;
};
export const choicesOf = (k: string): DecisionChoice[] => {
  if (k === "outcome") return DECISION_SPEC.outcomes.map((o) => ({ id: o.id, label: o.label }));
  const fd = fieldOf(k);
  if (fd.kind === "yn") return DECISION_SPEC.yn.filter((c) => c.id);
  return DECISION_SPEC.choices[fd.choices ?? k] ?? [];
};
const OUTCOME_HINT = new Map(DECISION_SPEC.outcomes.map((o) => [o.id, o.hint ?? ""]));
const requiredFor = (k: string, outcome: string) => (fieldOf(k).required ?? []).includes(outcome);
const stepIndex = (id: string) => Math.max(0, STEPS.findIndex((s) => s.id === id));

/** The plain message for a required field left empty; the step number is put in front. */
const NEED: Record<string, string> = {
  decision_text: "write the board's decision (at least 5 characters).",
  intent: "record the treatment intent as the board stated it (or Not stated by the board).",
  responsible_doctor: "name the responsible clinician.",
  awaited: "say what is awaited.",
  awaited_from: "say from which department.",
  referred_to: "say where it is referred.",
  not_discussed_reason: "say why it was not discussed.",
};

function emptyForm(members: string[], owner: string): Form {
  return {
    outcome: "decision", decision_text: "", awaited: "", awaited_from: "", referred_to: "", not_discussed_reason: "",
    rationale: "", intent: "", intent_as_stated: "", modalities: [], sequence: "", alternatives_discussed: "", concerns: [], stage_as_agreed: "", stage_source: "", report_corrections_raised: "",
    patient_preference: "", patient_preference_note: "", fitness_considered: "", trial_considered: "", trial_name: "", genomic_considered: "", supportive_needs: [], consent_recorded: "",
    investigations: [], referrals: [], next_step: "", next_step_date: "", next_review: "", next_review_trigger: "",
    responsible_doctor: owner, key_worker: "", informed_by: "", inform_by_date: "", patient_informed_date: "", gp_informed_date: "",
    pmjay_plan_approval: "", pmjay_plan_note: "", members_present: members,
  };
}

/** The outcome of a saved record, as the server reads it (outcome_type first; the oldest records keep only outcome). */
export function recordOutcome(rec: BoardRecord | null | undefined): string {
  return String(rec?.outcome_type || rec?.outcome || rec?.meeting_outcome || "decision");
}

const str = (v: unknown) => (typeof v === "string" ? v : v == null ? "" : String(v));

/** Every field of a saved record, for a correction; the intent falls back to intent_as_recorded as on the server. */
function formFromRecord(rec: BoardRecord | undefined): Form {
  const base = emptyForm([], "");
  if (!rec) return base;
  const r = rec as unknown as Record<string, unknown>;
  const out: Record<string, unknown> = { ...base };
  for (const k of Object.keys(base)) {
    const v = r[k];
    if (Array.isArray((base as unknown as Record<string, unknown>)[k])) { if (Array.isArray(v)) out[k] = v.filter((x) => x != null); }
    else if (typeof v === "string") out[k] = v;
  }
  const f = out as unknown as Form;
  f.outcome = recordOutcome(rec) as Form["outcome"];
  if (!f.intent && rec.intent_as_recorded) f.intent = rec.intent_as_recorded;
  f.modalities = f.modalities.map(str);
  f.supportive_needs = f.supportive_needs.map(str);
  f.members_present = f.members_present.map(str).filter(Boolean);
  f.concerns = (f.concerns as unknown[]).filter((c) => c && typeof c === "object").map((c) => { const x = c as Record<string, unknown>; return { by: str(x.by), text: str(x.text) }; });
  f.investigations = (f.investigations as unknown[]).filter((c) => c && typeof c === "object").map((c) => { const x = c as Record<string, unknown>; return { item: str(x.item), department: str(x.department), due: str(x.due) }; });
  f.referrals = (f.referrals as unknown[]).filter((c) => c && typeof c === "object").map((c) => { const x = c as Record<string, unknown>; return { kind: str(x.kind), department: str(x.department), note: str(x.note) }; });
  return f;
}

/** Values compared as the server compares them: whitespace folded, an absent value equal to "". */
const norm = (v: unknown) => JSON.stringify(v ?? "", (_k, x) => (typeof x === "string" ? x.split(/\s+/).filter(Boolean).join(" ") : x === undefined || x === null ? "" : x));

/** The keys a correction changes, against the record as opened. */
function changedKeys(f: Form, init: Form): string[] {
  const a = bodyOf(f) as unknown as Record<string, unknown>;
  const b = bodyOf(init) as unknown as Record<string, unknown>;
  return DECISION_SPEC.fields.map((x) => x.key).filter((k) => k !== "outcome" && norm(a[k]) !== norm(b[k]));
}

/** The outcome step shows only the fields its outcome needs; the trial name only when a trial was considered. */
function visible(fd: DecisionField, f: Form): boolean {
  if (fd.step === STEPS[0]?.id && fd.key !== "outcome") return (fd.required ?? []).includes(f.outcome);
  if (fd.key === "trial_name") return f.trial_considered === "yes";
  return true;
}

const blank = (v: unknown) => (Array.isArray(v) ? v.length === 0 : !String(v ?? "").trim());

type Problem = { step: number; key: string; text: string };
function problemsOf(f: Form): Problem[] {
  const out: Problem[] = [];
  for (const fd of DECISION_SPEC.fields) {
    if (fd.key === "outcome" || !requiredFor(fd.key, f.outcome) || !visible(fd, f)) continue;
    const v = f[fd.key as Key];
    if (fd.key === "decision_text" ? String(v ?? "").trim().length < 5 : blank(v)) out.push({ step: stepIndex(fd.step), key: fd.key, text: NEED[fd.key] ?? `fill in ${fd.label.toLowerCase()}.` });
  }
  if (f.concerns.some((c) => !c.by.trim() !== !c.text.trim())) out.push({ step: stepIndex(fieldOf("concerns").step), key: "concerns", text: "each concern needs a name and the words." });
  if (f.investigations.some((r) => !r.item.trim() && (r.department.trim() || r.due))) out.push({ step: stepIndex(fieldOf("investigations").step), key: "investigations", text: "each investigation needs what is to be done." });
  if (f.referrals.some((r) => !r.kind && (r.department.trim() || r.note?.trim()))) out.push({ step: stepIndex(fieldOf("referrals").step), key: "referrals", text: "each referral needs its kind." });
  return out.sort((a, b) => a.step - b.step);
}

/** What is sent: hidden fields emptied, empty rows dropped, an empty date left out. */
function bodyOf(f: Form): DecisionBody {
  const b: Record<string, unknown> = { ...f };
  for (const fd of DECISION_SPEC.fields) {
    if (!visible(fd, f)) b[fd.key] = LIST_KINDS.has(fd.kind) ? [] : "";
    if (fd.kind === "date") b[fd.key] = (b[fd.key] as string) || undefined;
  }
  b.concerns = f.concerns.filter((c) => c.by.trim() || c.text.trim());
  b.investigations = f.investigations.filter((r) => r.item.trim()).map((r) => ({ item: r.item, department: r.department, due: r.due || undefined }));
  b.referrals = f.referrals.filter((r) => r.kind).map((r) => ({ kind: r.kind, department: r.department, note: r.note ?? "" }));
  return b as unknown as DecisionBody;
}

const pill = (on: boolean) => cn("rounded-md border px-2.5 py-1 text-sm transition active:scale-95", on ? "border-primary bg-secondary text-secondary-foreground font-medium" : "border-border hover:bg-muted");

/** The label line: the field's label, "needed" when its outcome needs it. */
function Need({ on }: { on: boolean }) {
  return on ? <span className="ml-1 text-xs font-normal text-muted-foreground">(needed)</span> : null;
}

/** The hint and the "usually filled after the meeting" note under a field. */
function Notes({ id, fd, extra }: { id: string; fd: DecisionField; extra?: ReactNode }) {
  if (!fd.hint && !fd.after && !extra) return null;
  return (
    <p id={id} className="mt-0.5 text-xs text-muted-foreground">
      {[fd.hint, extra, fd.after ? "Usually filled after the meeting." : null].filter(Boolean).map((t, i) => <span key={i}>{i ? " " : ""}{t}{typeof t === "string" && !/[.!?]$/.test(t) ? "." : ""}</span>)}
    </p>
  );
}

/** One choice as radio pills (as the outcome today). An optional choice can be cleared by pressing it again. */
function Pills({ fd, value, onChange, need, invalid, clearable = true }: { fd: DecisionField; value: string; onChange: (v: string) => void; need: boolean; invalid?: boolean; clearable?: boolean }) {
  const noteId = `d-${fd.key}-note`;
  return (
    <fieldset aria-describedby={fd.hint || fd.after ? noteId : undefined} data-field={fd.key}>
      <legend className="text-sm font-medium">{fd.label}<Need on={need} /></legend>
      <div className="mt-1 flex flex-wrap gap-1.5" role="radiogroup" aria-label={fd.label} aria-invalid={invalid || undefined} aria-required={need || undefined}>
        {choicesOf(fd.key).map((o) => (
          <button key={o.id} type="button" role="radio" aria-checked={value === o.id} onClick={() => onChange(clearable && value === o.id ? "" : o.id)} title={fd.key === "outcome" ? OUTCOME_HINT.get(o.id) || undefined : undefined} className={cn(pill(value === o.id), invalid && "border-bad")}>{o.label}</button>
        ))}
      </div>
      {invalid ? <span className="sr-only">Needed.</span> : null}
      <Notes id={noteId} fd={fd} />
    </fieldset>
  );
}

/** Several choices as toggle pills. */
function MultiPills({ fd, value, onChange }: { fd: DecisionField; value: string[]; onChange: (v: string[]) => void }) {
  const noteId = `d-${fd.key}-note`;
  return (
    <fieldset aria-describedby={fd.hint || fd.after ? noteId : undefined} data-field={fd.key}>
      <legend className="text-sm font-medium">{fd.label}</legend>
      <div className="mt-1 flex flex-wrap gap-1.5" role="group" aria-label={fd.label}>
        {choicesOf(fd.key).map((o) => {
          const on = value.includes(o.id);
          return <button key={o.id} type="button" aria-pressed={on} onClick={() => onChange(on ? value.filter((x) => x !== o.id) : [...value, o.id])} className={pill(on)}>{o.label}</button>;
        })}
      </div>
      <Notes id={noteId} fd={fd} />
    </fieldset>
  );
}

type BoxRef = RefObject<HTMLTextAreaElement | HTMLInputElement>;
const asTextarea = (r?: BoxRef) => r as RefObject<HTMLTextAreaElement> | undefined;
const asInput = (r?: BoxRef) => r as RefObject<HTMLInputElement> | undefined;

/** The sentence boxes that take dictation, by field (the audit's screen id). Names, dates, choices, values and short structured
 *  lines get no microphone (research 08 section 7). */
const MIC_SCREEN: Record<string, string> = {
  decision_text: "decision", rationale: "rationale", alternatives_discussed: "alternatives", report_corrections_raised: "report-corrections",
  patient_preference_note: "preference",
};

/** A sentence box with the dictation button just under it on the right, beside the box's note. The words go in through the box's
 *  own onChange (the live strip sees them as typed); the box's limit is kept here, as the button does not know it. */
function Voiced({ box, screen, label, context = "decision", caseId, max, onValue, note, extra, className }: {
  box: (ref: BoxRef) => ReactNode; screen: string; label: string; context?: SttContext; caseId?: string; max?: number; onValue: (v: string) => void;
  note?: ReactNode; extra?: ReactNode; className?: string;
}) {
  const ref = useRef<HTMLTextAreaElement | HTMLInputElement>(null);
  return (
    <div className={className}>
      {box(ref)}
      <div className="flex items-start justify-end gap-2">
        <div className="min-w-0 flex-1">{note}</div>
        <span className="flex max-w-[70%] shrink-0 items-start justify-end gap-1">
          {extra}
          <MicButton target={ref} screen={screen} label={label} context={context} caseId={caseId || undefined} onInsert={(next) => { if (max && next.length > max) onValue(next.slice(0, max)); }} />
        </span>
      </div>
    </div>
  );
}

export function DecisionForm({ mid, caseId, attendance, onSaved, liveText, canRecord = true, compact = false, mode = "record", initial }: {
  mid: string; caseId: string; attendance: Attendee[];
  /** Called after a save with the server's answer (a correction answers {record}). */
  onSaved: (result?: unknown) => void;
  liveText?: string; canRecord?: boolean; compact?: boolean;
  /** "correct": a later correction of `initial`, a saved board record. */
  mode?: "record" | "correct"; initial?: BoardRecord;
}) {
  const correcting = mode === "correct";
  const uid = useId().replace(/:/g, "");
  const listMembers = `d-members-${uid}`;
  const listDepts = `d-depts-${uid}`;
  // The meeting state the page already polls (no extra request): the agenda row's owner doctor, the departments, the date.
  const meeting = useQuery({ queryKey: ["meeting", mid], queryFn: () => getMeeting(mid), enabled: false, staleTime: Infinity }).data;
  const row = useMemo(() => [...(meeting?.agenda?.discussion ?? []), ...(meeting?.agenda?.noting ?? [])].find((r) => r.case_id === caseId), [meeting, caseId]);
  const owner = !correcting && row?.owner_name && row.owner_name !== row.owner_department_name ? row.owner_name : ""; // a person only: a Case File without a team owner carries its department name here
  const boardDate = correcting ? String(initial?.board_date ?? "").slice(0, 10) : meeting?.meeting?.date ?? "";
  const departments = useMemo(() => {
    const names = new Set<string>();
    if (correcting) {  // no meeting state here: the departments the record itself names
      for (const d of [initial?.awaited_from, ...(initial?.investigations ?? []).map((x) => x?.department), ...(initial?.referrals ?? []).map((x) => x?.department), ...(initial?.actions ?? []).map((x) => x?.department)]) if (typeof d === "string" && d.trim()) names.add(d.trim());
    }
    for (const a of attendance) { const d = a.department_name || (a.department ? a.department.replace(/_/g, " ") : ""); if (d) names.add(d); }
    for (const r of [...(meeting?.agenda?.discussion ?? []), ...(meeting?.agenda?.noting ?? []), ...(meeting?.agenda?.not_ready ?? [])]) if (r.owner_department_name) names.add(r.owner_department_name);
    return [...names].sort((a, b) => a.localeCompare(b));
  }, [attendance, meeting, correcting, initial]);
  const admitted = () => attendance.filter((a) => a.status === "present" || a.status === "remote").map((a) => a.name);

  const start = (): Form => (correcting ? formFromRecord(initial) : emptyForm(admitted(), owner));
  const [f, setF] = useState<Form>(start);
  const [init, setInit] = useState<Form>(start);
  const [reason, setReason] = useState("");
  const [step, setStep] = useState(0);
  const [saved, setSaved] = useState(false);
  const [liveErr, setLiveErr] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const [announce, liveNode] = useAnnounce();
  const liveTimer = useRef<number | null>(null);
  const lastSent = useRef<string>("");
  const heading = useRef<HTMLHeadingElement | null>(null);
  const stepButtons = useRef<Array<HTMLButtonElement | null>>([]);

  useEffect(() => { const s0 = start(); setF(s0); setInit(s0); setReason(""); setStep(0); setSaved(false); setTouched(false); lastSent.current = ""; }, [caseId, initial?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  // The owner doctor may arrive after the form opened: fill the responsible clinician only while it is still empty.
  useEffect(() => { if (owner) setF((x) => (x.responsible_doctor ? x : { ...x, responsible_doctor: owner })); }, [caseId, owner]);
  useEffect(() => { stepButtons.current[step]?.scrollIntoView?.({ block: "nearest", inline: "nearest" }); }, [step]);

  // live strip: 400 ms after the last keystroke
  useEffect(() => {
    if (correcting || f.decision_text === lastSent.current) return;
    if (liveTimer.current) window.clearTimeout(liveTimer.current);
    liveTimer.current = window.setTimeout(() => { lastSent.current = f.decision_text; void decisionLive(mid, f.decision_text).then(() => setLiveErr(null), (e) => setLiveErr(errorText(e))); }, 400);
    return () => { if (liveTimer.current) window.clearTimeout(liveTimer.current); };
  }, [f.decision_text, mid, correcting]);

  const changed = correcting ? changedKeys(f, init) : [];
  const needReason = changed.filter((k) => fieldOf(k).reason);
  const save = useMutation({
    mutationFn: () => {
      if (!correcting) return saveDecision(mid, caseId, bodyOf(f));
      const b = bodyOf(f) as unknown as Record<string, unknown>;
      const changes = Object.fromEntries(changed.map((k) => [k, b[k] ?? ""])) as Partial<DecisionBody>;
      return correctBoardRecord(caseId, String(initial?.id ?? ""), changes, reason.trim());
    },
    onSuccess: (r) => { if (!correcting) { setSaved(true); announce("Decision saved."); } onSaved(r); },
  });
  const set = <K extends Key>(k: K, v: Form[K]) => { setF((x) => ({ ...x, [k]: v })); setSaved(false); };
  const problems = problemsOf(f);
  if (correcting) {
    if (needReason.length && !reason.trim()) problems.push({ step: STEPS.length - 1, key: "_reason", text: `give the reason for the correction (a change to ${needReason.map((k) => fieldOf(k).label.toLowerCase()).join(", ")} needs one).` });
    if (!changed.length) problems.push({ step: -1, key: "_nothing", text: "Nothing is changed yet." });
  }
  const badKeys = new Set(touched ? problems.map((p) => p.key) : []);
  const missingSteps = new Set(problems.map((p) => p.step));
  const members: Attendee[] = correcting ? init.members_present.map((n) => ({ user: n, name: n, status: "present" })) : attendance.filter((a) => a.status !== "waiting");
  const go = (i: number, focus = false) => { setStep(i); announce(`Step ${i + 1} of ${STEPS.length}: ${STEPS[i].title}.`); if (focus) window.setTimeout(() => heading.current?.focus(), 0); };
  const wide = compact ? "" : "sm:col-span-2";

  const textField = (fd: DecisionField) => {
    const k = fd.key as Key;
    const id = fd.key === "decision_text" ? "d-text" : `d-${fd.key}`;
    const need = requiredFor(fd.key, f.outcome);
    const invalid = badKeys.has(fd.key);
    const value = String(f[k] ?? "");
    const noteId = `${id}-note`;
    const ownerNote = fd.key === "responsible_doctor" && owner && value === owner ? "Filled from the Case File's owner doctor; change it if the board named another." : undefined;
    const described = fd.hint || fd.after || ownerNote ? noteId : undefined;
    const on = (v: string) => set(k, v as Form[typeof k]);
    const control = (ref?: BoxRef): ReactNode => {
      if (fd.kind === "long") {
        return fd.key === "decision_text" && !correcting
          ? <Textarea ref={asTextarea(ref)} id={id} value={value} onChange={(e) => on(e.target.value)} className="mt-1 min-h-24 text-sm" maxLength={limitOf(fd.key)} aria-invalid={invalid} aria-required={need || undefined} placeholder="Type as the chair states it; it shows live on the room screen marked not saved" />
          : <Textarea ref={asTextarea(ref)} id={id} value={value} onChange={(e) => on(e.target.value)} className="mt-1 min-h-16 text-sm" maxLength={limitOf(fd.key)} aria-describedby={described} />;
      }
      if (fd.kind === "date") {
        return <DateInput id={id} value={value} onChange={on} wrapperClassName="mt-1" className="text-sm" min={fd.key === "patient_informed_date" && boardDate ? boardDate : undefined} aria-describedby={described} />;
      }
      const list = fd.kind === "person" ? listMembers : fd.kind === "dept" ? listDepts : undefined;
      return <Input ref={asInput(ref)} id={id} list={list} value={value} onChange={(e) => on(e.target.value)} className="mt-1 text-sm" maxLength={limitOf(fd.key)} aria-invalid={invalid} aria-required={need || undefined} aria-describedby={described} placeholder={fd.key === "intent_as_stated" ? "as stated, never computed" : undefined} />;
    };
    const note = fd.key === "decision_text" && !correcting ? (
      <p className={`text-xs mt-0.5 ${liveErr ? "text-warn" : "text-muted-foreground"}`} data-testid="live-strip-note">{liveErr ? `The room screen did not get the text: ${liveErr}` : f.decision_text && liveText === f.decision_text ? "Shown on the room screen, marked not saved" : "Appears on the room screen as you type, marked not saved"}</p>
    ) : <Notes id={noteId} fd={fd} extra={ownerNote} />;
    const screen = fd.kind === "date" ? undefined : MIC_SCREEN[fd.key];
    // "Read back": the decision as it stands in the box, read aloud so the coordinator hears what will be recorded.
    const readBack = fd.key === "decision_text" && value.trim() ? <SpeakButton source={{ text: value }} screen="decision" label="Read back" /> : null;
    return (
      <div key={fd.key} className={fd.kind === "long" ? wide : ""} data-field={fd.key}>
        <Label htmlFor={id}>{fd.label}<Need on={need} /></Label>
        {screen ? <Voiced box={control} screen={screen} label={`Dictate: ${fd.label}`} caseId={caseId} max={limitOf(fd.key)} onValue={on} note={note} extra={readBack} /> : <>{control()}{note}</>}
      </div>
    );
  };

  const listField = (fd: DecisionField) => {
    if (fd.kind === "concerns") return (
      <fieldset key={fd.key} className={wide} data-field={fd.key}>
        <legend className="text-sm font-medium">{fd.label}</legend>
        <ul className="mt-1 space-y-1.5">
          {f.concerns.map((c, i) => (
            <li key={i} className="flex gap-1.5">
              <Input list={listMembers} value={c.by} onChange={(e) => set("concerns", f.concerns.map((x, j) => (j === i ? { ...x, by: e.target.value } : x)))} placeholder="Who" className="w-40 text-sm" aria-label="Who raised it" maxLength={limitOf(fd.key, "by")} aria-invalid={badKeys.has(fd.key) && !c.by.trim()} />
              <Voiced className="min-w-0 flex-1" screen="concern" label={`Dictate concern ${i + 1}`} caseId={caseId} max={limitOf(fd.key, "text")} onValue={(v) => set("concerns", f.concerns.map((x, j) => (j === i ? { ...x, text: v } : x)))}
                box={(ref) => <Input ref={asInput(ref)} value={c.text} onChange={(e) => set("concerns", f.concerns.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)))} placeholder="The concern, in their words" className="text-sm" aria-label="The concern" maxLength={limitOf(fd.key, "text")} aria-invalid={badKeys.has(fd.key) && !c.text.trim()} />} />
              <Button type="button" size="icon-sm" variant="ghost" aria-label="Remove this concern" onClick={() => set("concerns", f.concerns.filter((_, j) => j !== i))}><Trash2 className="size-4" /></Button>
            </li>
          ))}
        </ul>
        <Button type="button" size="xs" variant="outline" className="mt-1.5" onClick={() => set("concerns", [...f.concerns, { by: "", text: "" }])}><Plus className="size-3" />Add a concern</Button>
      </fieldset>
    );
    if (fd.kind === "investigations") return (
      <fieldset key={fd.key} className={wide} data-field={fd.key} aria-describedby={`d-${fd.key}-note`}>
        <legend className="text-sm font-medium">{fd.label}</legend>
        <p id={`d-${fd.key}-note`} className="text-xs text-muted-foreground">Each one becomes a board action for its department. Leave the date empty for the protocol's usual time.</p>
        <ul className="mt-1 space-y-1.5" data-testid="investigation-rows">
          {f.investigations.map((r, i) => {
            const upd = (p: Partial<typeof r>) => set("investigations", f.investigations.map((x, j) => (j === i ? { ...x, ...p } : x)));
            return (
              <li key={i} className="space-y-1.5 rounded-md border border-border p-2">
                <div className="flex items-center gap-1.5">
                  <Input value={r.item} onChange={(e) => upd({ item: e.target.value })} placeholder="What is to be done, as the board said" className="min-w-0 flex-1 text-sm" aria-label={`Investigation ${i + 1}`} maxLength={limitOf(fd.key, "item")} aria-invalid={badKeys.has(fd.key) && !r.item.trim()} />
                  <Button type="button" size="icon-sm" variant="ghost" aria-label={`Remove investigation ${i + 1}`} onClick={() => set("investigations", f.investigations.filter((_, j) => j !== i))}><Trash2 className="size-4" /></Button>
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  <Input list={listDepts} value={r.department} onChange={(e) => upd({ department: e.target.value })} placeholder="Department" className="min-w-0 flex-1 basis-36 text-sm" aria-label={`Department for investigation ${i + 1}`} maxLength={limitOf(fd.key, "department")} />
                  <DateInput value={r.due ?? ""} onChange={(v) => upd({ due: v })} wrapperClassName="w-36 shrink-0" className="text-sm" aria-label={`Due date for investigation ${i + 1}`} />
                </div>
              </li>
            );
          })}
        </ul>
        <Button type="button" size="xs" variant="outline" className="mt-1.5" onClick={() => set("investigations", [...f.investigations, { item: "", department: "", due: "" }])} data-testid="add-investigation"><Plus className="size-3" />Add an investigation</Button>
      </fieldset>
    );
    if (fd.kind === "referrals") return (
      <fieldset key={fd.key} className={wide} data-field={fd.key} aria-describedby={`d-${fd.key}-note`}>
        <legend className="text-sm font-medium">{fd.label}</legend>
        <p id={`d-${fd.key}-note`} className="text-xs text-muted-foreground">A referral with a department becomes a board action for it.</p>
        <ul className="mt-1 space-y-1.5" data-testid="referral-rows">
          {f.referrals.map((r, i) => {
            const upd = (p: Partial<typeof r>) => set("referrals", f.referrals.map((x, j) => (j === i ? { ...x, ...p } : x)));
            return (
              <li key={i} className="space-y-1.5 rounded-md border border-border p-2">
                <div className="flex items-center gap-1.5">
                  <select value={r.kind} onChange={(e) => upd({ kind: e.target.value })} className="h-9 min-w-0 flex-1 rounded-md border border-input bg-card px-2 text-sm" aria-label={`Kind of referral ${i + 1}`} aria-invalid={badKeys.has(fd.key) && !r.kind}>
                    <option value="">Kind of referral</option>
                    {choicesOf(fd.key).map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
                  </select>
                  <Button type="button" size="icon-sm" variant="ghost" aria-label={`Remove referral ${i + 1}`} onClick={() => set("referrals", f.referrals.filter((_, j) => j !== i))}><Trash2 className="size-4" /></Button>
                </div>
                <div className="flex flex-wrap items-start gap-1.5">
                  <Input list={listDepts} value={r.department} onChange={(e) => upd({ department: e.target.value })} placeholder="Department" className="min-w-0 flex-1 basis-36 text-sm" aria-label={`Department for referral ${i + 1}`} maxLength={limitOf(fd.key, "department")} />
                  <Voiced className="min-w-0 flex-[2] basis-48" screen="referral-reason" label={`Dictate the note for referral ${i + 1}`} caseId={caseId} max={limitOf(fd.key, "note")} onValue={(v) => upd({ note: v })}
                    box={(ref) => <Input ref={asInput(ref)} value={r.note ?? ""} onChange={(e) => upd({ note: e.target.value })} placeholder="Note, in the board's words" className="text-sm" aria-label={`Note for referral ${i + 1}`} maxLength={limitOf(fd.key, "note")} />} />
                </div>
              </li>
            );
          })}
        </ul>
        <Button type="button" size="xs" variant="outline" className="mt-1.5" onClick={() => set("referrals", [...f.referrals, { kind: "", department: "", note: "" }])} data-testid="add-referral"><Plus className="size-3" />Add a referral</Button>
      </fieldset>
    );
    // people: the members present, ticked from the admitted members (as today)
    return (
      <fieldset key={fd.key} className={wide} data-field={fd.key}>
        <legend className="text-sm font-medium">{fd.label}</legend>
        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
          {members.length === 0 ? <p className="text-xs text-muted-foreground">No one has joined yet.</p> : null}
          {members.map((m) => {
            const on = f.members_present.includes(m.name);
            return (
              <label key={m.user} className="inline-flex items-center gap-1.5 text-sm">
                <Checkbox checked={on} onCheckedChange={(v) => set("members_present", v ? [...f.members_present, m.name] : f.members_present.filter((x) => x !== m.name))} />{m.name}{m.department_name || m.department ? <span className="text-xs text-muted-foreground">({m.department_name || m.department!.replace(/_/g, " ")})</span> : null}
              </label>
            );
          })}
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground">The AI agents are not members and are never counted.</p>
      </fieldset>
    );
  };

  const renderField = (fd: DecisionField) => {
    if (!visible(fd, f)) return null;
    const k = fd.key as Key;
    if (fd.key === "outcome" && correcting) {
      const label = DECISION_SPEC.outcomes.find((o) => o.id === f.outcome)?.label ?? f.outcome.replace(/_/g, " ");
      return (
        <div key={fd.key} className={wide} data-field="outcome" data-testid="correct-outcome">
          <p className="text-sm"><span className="font-medium">{fd.label}:</span> {label}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">The outcome cannot be changed by a correction; record a new outcome in a meeting instead.</p>
        </div>
      );
    }
    if (fd.kind === "choice" || fd.kind === "yn") {
      return <div key={fd.key} className={wide}><Pills fd={fd} value={String(f[k] ?? "")} onChange={(v) => set(k, v as Form[typeof k])} need={fd.key !== "outcome" && requiredFor(fd.key, f.outcome)} invalid={badKeys.has(fd.key)} clearable={fd.key !== "outcome"} /></div>;
    }
    if (fd.kind === "multi") return <div key={fd.key} className={wide}><MultiPills fd={fd} value={(f[k] as string[]) ?? []} onChange={(v) => set(k, v as Form[typeof k])} /></div>;
    if (LIST_KINDS.has(fd.kind)) return listField(fd);
    return textField(fd);
  };

  const current = STEPS[step];
  const last = STEPS.length - 1;

  return (
    <form className="min-w-0 space-y-3" onSubmit={(e) => { e.preventDefault(); setTouched(true); if (!problems.length) save.mutate(); }} data-testid="decision-form" data-step={current?.id}>
      {liveNode}
      <datalist id={listMembers}>{members.map((m) => <option key={m.user} value={m.name} />)}</datalist>
      <datalist id={listDepts}>{departments.map((d) => <option key={d} value={d} />)}</datalist>
      <nav aria-label="Steps of the decision record">
        <ol className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1 scroll-thin">
          {STEPS.map((s, i) => {
            const miss = missingSteps.has(i);
            return (
              <li key={s.id} className="shrink-0">
                <button type="button" ref={(el) => { stepButtons.current[i] = el; }} onClick={() => go(i)} aria-current={i === step ? "step" : undefined} data-testid={`decision-step-${i + 1}`} data-missing={miss || undefined}
                  className={cn("inline-flex items-center gap-1.5 whitespace-nowrap", pill(i === step))}>
                  <span className="text-xs tabular-nums text-muted-foreground">{i + 1}</span>{s.title}
                  {miss ? <><span className="size-1.5 rounded-full bg-bad" aria-hidden /><span className="sr-only"> (something needed)</span></> : null}
                </button>
              </li>
            );
          })}
        </ol>
      </nav>
      <section aria-labelledby={`d-step-title-${uid}`} data-testid={`decision-panel-${step + 1}`} className="space-y-3">
        <h4 id={`d-step-title-${uid}`} ref={heading} tabIndex={-1} className="text-sm font-semibold text-foreground outline-none">Step {step + 1} of {STEPS.length}: {current?.title}</h4>
        <div className={compact ? "grid gap-3" : "grid gap-3 sm:grid-cols-2"}>
          {DECISION_SPEC.fields.filter((x) => x.step === current?.id).map(renderField)}
          {correcting && step === last ? (
            <div className={wide} data-field="correction_reason">
              <Label htmlFor={`d-reason-${uid}`}>Reason for the correction<Need on={needReason.length > 0} /></Label>
              <Voiced screen="correction-reason" label="Dictate the reason" context="reason" caseId={caseId} max={DECISION_SPEC.limits.note ?? 2000} onValue={setReason}
                box={(ref) => <Textarea ref={asTextarea(ref)} id={`d-reason-${uid}`} value={reason} onChange={(e) => setReason(e.target.value)} className="mt-1 min-h-16 text-sm" maxLength={DECISION_SPEC.limits.note ?? 2000} aria-required={needReason.length > 0 || undefined} aria-invalid={badKeys.has("_reason") || undefined} aria-describedby={`d-reason-${uid}-note`} data-testid="correction-reason" />}
                note={<p id={`d-reason-${uid}-note`} className="mt-0.5 text-xs text-muted-foreground">{needReason.length ? "Needed: a change to what the board decided is kept with its reason." : "Kept with the new version; a change to what the board decided needs one."}</p>} />
            </div>
          ) : null}
        </div>
      </section>
      <div className="flex items-center justify-between gap-2">
        <Button type="button" size="sm" variant="outline" disabled={step === 0} onClick={() => go(step - 1, true)} data-testid="decision-back"><ArrowLeft className="size-4" />Back</Button>
        <Button type="button" size="sm" variant="outline" disabled={step === last} onClick={() => go(step + 1, true)} data-testid="decision-next">Next<ArrowRight className="size-4" /></Button>
      </div>
      {touched && problems.length ? (
        <ul role="alert" className="text-sm text-bad list-disc pl-5" data-testid="decision-problems">
          {problems.map((p) => <li key={`${p.step}-${p.key}-${p.text}`}>{p.step < 0 ? p.text : <button type="button" className="text-left underline-offset-2 hover:underline" onClick={() => go(p.step)}>Step {p.step + 1}: {p.text}</button>}</li>)}
        </ul>
      ) : null}
      {save.isError ? <p role="alert" className="text-sm text-bad">{errorText(save.error)}</p> : null}
      {correcting ? (
        <div className="flex flex-wrap items-center gap-2">
          <LoadingButton type="submit" loading={save.isPending} loadingText="Saving" disabled={!canRecord} data-testid="save-correction"><Check className="size-4" />Save the correction</LoadingButton>
          <span className="text-xs text-muted-foreground">Only the fields you changed are saved, as a new version; the earlier versions are kept.</span>
        </div>
      ) : (
      <div className="flex flex-wrap items-center gap-2">
        <LoadingButton type="submit" loading={save.isPending} loadingText="Saving" disabled={saved || !canRecord} title={canRecord ? undefined : "Only the MDT Coordinator records the decision"} data-testid="save-decision"><Check className="size-4" />{saved ? "Saved" : "Read back done, save"}</LoadingButton>
        <span className="text-xs text-muted-foreground">{saved ? "Recorded; the owner is told." : "Read the decision back to the board, then save."}</span>
      </div>
      )}
    </form>
  );
}
