// Step 3: the logistics, pre-filled as recommendations: the fetch window (12 months), the board question (needed
// before the Case File can be marked ready), the urgency tag 1 to 5 (required, no default: the consultant's own call),
// the board date (the next planned meeting when there is one), the presenter (you), a join code for residents, and the
// consent to discuss with outside experts. A read-back of the whole Case File sits at the end; for a cancer with no checklist
// yet it says what the generic rule checks (four core records, owner decision R05-Q04; the blood cancer rule for "generic_haem").
// The board question takes dictation (night-v3 4.4): the words go into the box as an edit, kept with the form like typed text.
import { useEffect, useMemo, useRef } from "react";
import { motion } from "motion/react";
import { CalendarDays, ClipboardList, Flame, KeyRound, ShieldCheck, TriangleAlert, UserRound } from "lucide-react";
import { Textarea } from "@/components/ui/textarea";
import { MicButton } from "@/components/MicButton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Field } from "@/components/Field";
import { DateInput } from "@/components/DateInput";
import { SwitchRow } from "@/components/SwitchRow";
import { KeyValue, KeyValueList } from "@/components/KeyValue";
import { useMeetings, useOrg } from "@/hooks/useQueries";
import { useSession } from "@/lib/session";
import { ageSex, drName, formatDate, parseDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { NO_CHECKLIST_WORDS, cleanCancerName, genericRecords, genericRule, isGeneric } from "@/lib/cancers";
import { WINDOW_CHOICES, type NewCaseForm } from "@/features/newcase/form";
import { NOT_RECORDED } from "@/features/newcase/StepCancer";

const URGENCY: Array<{ level: number; word: string }> = [
  { level: 1, word: "Least urgent" },
  { level: 2, word: "" },
  { level: 3, word: "" },
  { level: 4, word: "Urgent" },
  { level: 5, word: "Most urgent" },
];

function isoDay(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** How the read-back names the cancer: "<name> (no checklist yet)" under the generic rule, else the checklist, with the picked name
 * when the checklist is named differently (Tongue uses the oral cavity checklist). */
export function cancerWords(form: NewCaseForm, protocolLabel?: string): string {
  const name = cleanCancerName(form.cancerName);
  if (isGeneric(form.protocol)) return name ? `${name} (${NO_CHECKLIST_WORDS})` : "";
  if (!protocolLabel) return name;  // the checklist list has not arrived yet
  return name && !protocolLabel.toLowerCase().includes(name.toLowerCase()) ? `${name} (${protocolLabel} checklist)` : `${protocolLabel} checklist`;
}

/** The treating departments this person may own a Case File for: their own, or every treating department for a coordinator. */
export function useOwnerChoices() {
  const { me } = useSession();
  const org = useOrg();
  return useMemo(() => {
    const treating = me?.roles.treating ?? [];
    const names = new Map((org.data?.departments ?? []).map((d) => [d.id, d.name]));
    if (treating.length) return treating.map((id) => ({ id, name: names.get(id) ?? id }));
    if (me?.roles.coordinator) return (org.data?.departments ?? []).filter((d) => d.group === "treating").map((d) => ({ id: d.id, name: d.name }));
    return [];
  }, [me, org.data]);
}

export function StepLogistics({ form, onChange, settingLabel, protocolLabel }: {
  form: NewCaseForm;
  onChange: (patch: Partial<NewCaseForm>) => void;
  settingLabel?: string;
  protocolLabel?: string;
}) {
  const { me } = useSession();
  const questionRef = useRef<HTMLTextAreaElement>(null);
  const meetings = useMeetings();
  const owners = useOwnerChoices();
  const needOwner = owners.length > 1;
  const today = new Date(new Date().getFullYear(), new Date().getMonth(), new Date().getDate());
  const nextMeeting = (meetings.data?.meetings ?? [])
    .filter((m) => m.status === "planned" && (parseDate(m.date) ?? today) >= today)
    .sort((a, b) => (parseDate(a.date)?.getTime() ?? 0) - (parseDate(b.date)?.getTime() ?? 0))[0];

  // Recommendations: the next planned meeting as the board date, and the only owning department.
  useEffect(() => {
    if (!form.boardDate && nextMeeting) {
      const d = parseDate(nextMeeting.date);
      if (d) onChange({ boardDate: isoDay(d) });
    }
  }, [nextMeeting?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!form.department && owners.length === 1) onChange({ department: owners[0].id });
  }, [owners.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const p = form.lookup?.patient;
  const generic = isGeneric(form.protocol);
  const meName = me?.display_name ? drName(me.display_name) : me?.user ?? "you";
  const guest = Boolean(me?.real_data);  // a guest reviewer: a private Case File from their own files (no fetch, no team, no outside experts)
  return (
    <div className="grid gap-5">
      <div className="grid gap-5 md:grid-cols-2">
        {guest ? null : <Field id="window" label="Records to fetch" hint="Older reports can be fetched later from the Case File.">
          <Select value={String(form.windowMonths)} onValueChange={(v) => onChange({ windowMonths: v === "all" ? "all" : Number(v) })}>
            <SelectTrigger className="w-full" id="window" aria-label="Records to fetch"><SelectValue /></SelectTrigger>
            <SelectContent>{WINDOW_CHOICES.map((w) => <SelectItem key={String(w.value)} value={String(w.value)}>{w.label}</SelectItem>)}</SelectContent>
          </Select>
        </Field>}
        <Field id="board-date" label="Board date" optional hint={nextMeeting ? `Next planned meeting: ${formatDate(nextMeeting.date)}. Change it if needed.` : "Leave empty if not known; the coordinator schedules it."}>
          <DateInput value={form.boardDate} min={isoDay(today)} onChange={(v) => onChange({ boardDate: v })} />
        </Field>
      </div>

      <fieldset className="grid gap-2">
        <legend className="mb-1 flex items-baseline gap-2 text-sm font-medium">Urgency tag <span className="text-xs font-normal text-bad">required</span></legend>
        <p className="-mt-1 text-xs text-muted-foreground">Your call as the treating consultant, 5 the most urgent. It orders lists and agendas; you can change it later.</p>
        <div role="radiogroup" aria-label="Urgency" className="grid grid-cols-5 gap-2 sm:max-w-md">
          {URGENCY.map((u) => {
            const on = form.urgency === u.level;
            const tone = u.level === 5 ? "status-bad" : u.level === 4 ? "status-warn" : "bg-secondary text-secondary-foreground";
            return (
              <motion.button
                key={u.level}
                type="button"
                role="radio"
                aria-checked={on}
                aria-label={`Urgency ${u.level}${u.word ? `, ${u.word.toLowerCase()}` : ""}`}
                whileTap={{ scale: 0.94 }}
                onClick={() => onChange({ urgency: u.level })}
                className={cn(
                  "flex h-14 flex-col items-center justify-center rounded-md border text-lg font-bold tabular-nums outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
                  on ? cn(tone, "border-current shadow-[var(--shadow-inner)]") : "border-border bg-card text-foreground hover:border-border-strong hover:bg-accent",
                )}
              >
                <span className="flex items-center gap-0.5">
                  {u.level === 5 ? <Flame className="size-4" aria-hidden /> : u.level === 4 ? <TriangleAlert className="size-4" aria-hidden /> : null}
                  {u.level}
                </span>
                {u.word ? <span className="text-[10px] font-medium leading-none">{u.word}</span> : null}
              </motion.button>
            );
          })}
        </div>
      </fieldset>

      <Field id="board-question" label="The question for the board"
        hint={generic ? "One of the four core records of a cancer with no checklist yet: needed before the Case File can be marked ready. You can type it later." : "Needed before the Case File can be marked ready. You can type it later."}
        trailing={<div className="flex justify-end"><MicButton target={questionRef} screen="board-question" context="question" label="Dictate the question" onInsert={(next) => { if (next.length > 600) onChange({ boardQuestion: next.slice(0, 600) }); }} /></div>}>
        <Textarea ref={questionRef} rows={3} value={form.boardQuestion} onChange={(e) => onChange({ boardQuestion: e.target.value })} placeholder="e.g. Upfront surgery or neoadjuvant therapy?" maxLength={600} />
      </Field>

      {needOwner ? (
        <Field id="owner" label="Responsible Department" required hint="The treating department that owns this Case File.">
          <Select value={form.department} onValueChange={(v) => onChange({ department: v })}>
            <SelectTrigger className="w-full" id="owner" aria-label="Responsible Department"><SelectValue placeholder="Choose the department" /></SelectTrigger>
            <SelectContent>{owners.map((d) => <SelectItem key={d.id} value={d.id}>{d.name}</SelectItem>)}</SelectContent>
          </Select>
        </Field>
      ) : null}

      <div className="surface-inner grid gap-1 p-4">
        <p className="flex items-center gap-2 text-sm"><UserRound className="size-4 text-muted-foreground" aria-hidden /> Presenter: <span className="font-medium text-foreground">{meName} (you)</span></p>
        {guest ? null : <>
        <SwitchRow id="join-code" label="Make a join code for residents" hint="A 6-digit code you can give your residents; one from your department joins at once." checked={form.joinCode} onCheckedChange={(v) => onChange({ joinCode: v })} />
        <SwitchRow id="consent" label="Patient consents to discussion with outside experts" hint="Without it, outside experts see initials, age and sex only." checked={form.outsideConsent} onCheckedChange={(v) => onChange({ outsideConsent: v })} />
        </>}
      </div>

      <section className="rounded-md border border-tint-line bg-muted p-4" aria-label="Read-back">
        <p className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground"><ShieldCheck className="size-4" aria-hidden /> What will be created</p>
        <KeyValueList>
          <KeyValue label="Patient" value={guest ? [form.manualLabel.trim(), ageSex(Number(form.manualAge), form.manualSex)].filter(Boolean).join(", ") : p ? `${p.name ?? ""}, ${ageSex(p.age, p.sex)}` : form.identifier} />
          <KeyValue label="UHID" value={guest ? "none (private Case File)" : p?.uhid} mono={!guest} />
          <KeyValue label="Cancer" value={cancerWords(form, protocolLabel)} />
          {generic ? (
            <KeyValue label="Checked" value={<span className="inline-flex items-start gap-1" data-testid="generic-readback"><ClipboardList className="mt-0.5 size-3.5 shrink-0" aria-hidden /> {genericRule(form.protocol)}</span>}
              hint={<span className="mt-0.5 block" data-testid="generic-records">{genericRecords(form.protocol).join("; ")}</span>} />
          ) : (
            <KeyValue label="Setting" value={form.setting === NOT_RECORDED ? "not recorded yet" : settingLabel} fallback="none" />
          )}
          <KeyValue label="Records" value={guest ? "you add the files after Create" : form.windowMonths === "all" ? "everything on record" : `last ${form.windowMonths} months`} />
          <KeyValue label="Board date" value={form.boardDate ? <span className="inline-flex items-center gap-1"><CalendarDays className="size-3.5" aria-hidden /> {formatDate(form.boardDate)}</span> : ""} fallback="not set" />
          <KeyValue label="Urgency" value={form.urgency ? String(form.urgency) : ""} fallback="choose one above" />
          {guest ? <KeyValue label="Who sees it" value="only you (private)" /> : null}
          {guest ? null : <KeyValue label="Join code" value={form.joinCode ? <span className="inline-flex items-center gap-1"><KeyRound className="size-3.5" aria-hidden /> made after creation</span> : "no"} />}
        </KeyValueList>
      </section>
    </div>
  );
}

export function logisticsDone(form: NewCaseForm, needOwner: boolean): boolean {
  return form.urgency !== null && (!needOwner || Boolean(form.department));
}
