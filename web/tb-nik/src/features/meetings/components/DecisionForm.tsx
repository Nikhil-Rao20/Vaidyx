// The decision form the coordinator fills during the meeting. The decision text shows live at the bottom of the room
// screen (sent 400 ms after the last keystroke, marked "not saved") and is saved after the read-back.
import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Check, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { DateInput } from "@/components/DateInput";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { Attendee } from "@/lib/live";
import { decisionLive, saveDecision } from "../api";
import type { DecisionBody, Outcome } from "../types";
import { LoadingButton, errorText, useAnnounce } from "@/features/casefile/components/common";

const OUTCOMES: Array<{ id: Outcome; label: string; hint: string }> = [
  { id: "decision", label: "Decision", hint: "The board decided" },
  { id: "deferred", label: "Deferred", hint: "Something is awaited" },
  { id: "referred", label: "Referred", hint: "To another board or centre" },
  { id: "not_discussed", label: "Not discussed", hint: "Moves to the next meeting" },
  { id: "noted", label: "Noted", hint: "For noting only" },
];

const empty = (): DecisionBody => ({ outcome: "decision", decision_text: "", rationale: "", intent_as_stated: "", responsible_doctor: "", next_step: "", next_step_date: "", awaited: "", awaited_from: "", referred_to: "", members_present: [], concerns: [] });

export function DecisionForm({ mid, caseId, attendance, onSaved, liveText, canRecord = true }: { mid: string; caseId: string; attendance: Attendee[]; onSaved: () => void; liveText?: string; canRecord?: boolean }) {
  const [f, setF] = useState<DecisionBody>(() => ({ ...empty(), members_present: attendance.filter((a) => a.status === "present" || a.status === "remote").map((a) => a.name) }));
  const [saved, setSaved] = useState(false);
  const [liveErr, setLiveErr] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const [announce, liveNode] = useAnnounce();
  const liveTimer = useRef<number | null>(null);
  const lastSent = useRef<string>("");

  useEffect(() => { setF({ ...empty(), members_present: attendance.filter((a) => a.status === "present" || a.status === "remote").map((a) => a.name) }); setSaved(false); setTouched(false); lastSent.current = ""; }, [caseId]); // eslint-disable-line react-hooks/exhaustive-deps

  // live strip: 400 ms after the last keystroke
  useEffect(() => {
    if (f.decision_text === lastSent.current) return;
    if (liveTimer.current) window.clearTimeout(liveTimer.current);
    liveTimer.current = window.setTimeout(() => { lastSent.current = f.decision_text; void decisionLive(mid, f.decision_text).then(() => setLiveErr(null), (e) => setLiveErr(errorText(e))); }, 400);
    return () => { if (liveTimer.current) window.clearTimeout(liveTimer.current); };
  }, [f.decision_text, mid]);

  const save = useMutation({
    mutationFn: () => saveDecision(mid, caseId, { ...f, next_step_date: f.next_step_date || undefined }),
    onSuccess: () => { setSaved(true); announce("Decision saved."); onSaved(); },
  });
  const set = <K extends keyof DecisionBody>(k: K, v: DecisionBody[K]) => { setF((x) => ({ ...x, [k]: v })); setSaved(false); };
  const needText = f.outcome !== "not_discussed" && f.decision_text.trim().length < 5;
  const needAwaited = f.outcome === "deferred" && !f.awaited?.trim();
  const needReferred = f.outcome === "referred" && !f.referred_to?.trim();
  const problems = [needText ? "Write the decision in the board's words." : null, needAwaited ? "Say what is awaited." : null, needReferred ? "Say where it is referred." : null].filter(Boolean) as string[];
  const members = attendance.filter((a) => a.status !== "waiting");

  return (
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); setTouched(true); if (!problems.length) save.mutate(); }} data-testid="decision-form">
      {liveNode}
      <fieldset>
        <legend className="text-sm font-medium">Outcome</legend>
        <div className="mt-1 flex flex-wrap gap-1.5" role="radiogroup">
          {OUTCOMES.map((o) => (
            <button key={o.id} type="button" role="radio" aria-checked={f.outcome === o.id} onClick={() => set("outcome", o.id)} title={o.hint} className={`rounded-md border px-2.5 py-1 text-sm transition active:scale-95 ${f.outcome === o.id ? "border-primary bg-secondary text-secondary-foreground font-medium" : "border-border hover:bg-muted"}`}>{o.label}</button>
          ))}
        </div>
      </fieldset>
      <div>
        <Label htmlFor="d-text">Decision, in the board's words</Label>
        <Textarea id="d-text" value={f.decision_text} onChange={(e) => set("decision_text", e.target.value)} className="mt-1 min-h-24 text-sm" maxLength={4000} aria-invalid={touched && needText} placeholder="Type as the chair states it; it shows live on the room screen marked not saved" />
        <p className={`text-xs mt-0.5 ${liveErr ? "text-warn" : "text-muted-foreground"}`} data-testid="live-strip-note">{liveErr ? `The room screen did not get the text: ${liveErr}` : f.decision_text && liveText === f.decision_text ? "Shown on the room screen, marked not saved" : "Appears on the room screen as you type, marked not saved"}</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div><Label htmlFor="d-rat">Rationale as discussed</Label><Textarea id="d-rat" value={f.rationale} onChange={(e) => set("rationale", e.target.value)} className="mt-1 min-h-16 text-sm" maxLength={2000} /></div>
        <div><Label htmlFor="d-intent">Treatment intent as stated by the board</Label><Input id="d-intent" value={f.intent_as_stated} onChange={(e) => set("intent_as_stated", e.target.value)} className="mt-1 text-sm" maxLength={200} placeholder="as stated, never computed" /></div>
        <div><Label htmlFor="d-resp">Responsible doctor</Label><Input id="d-resp" list="d-members" value={f.responsible_doctor} onChange={(e) => set("responsible_doctor", e.target.value)} className="mt-1 text-sm" maxLength={120} /><datalist id="d-members">{members.map((m) => <option key={m.user} value={m.name} />)}</datalist></div>
        <div className="grid grid-cols-[1fr_9rem] gap-2">
          <div><Label htmlFor="d-next">Next step</Label><Input id="d-next" value={f.next_step} onChange={(e) => set("next_step", e.target.value)} className="mt-1 text-sm" maxLength={300} /></div>
          <div><Label htmlFor="d-date">By date</Label><DateInput id="d-date" value={f.next_step_date ?? ""} onChange={(v) => set("next_step_date", v)} wrapperClassName="mt-1" className="text-sm" /></div>
        </div>
        {f.outcome === "deferred" ? (
          <>
            <div><Label htmlFor="d-await">What is awaited</Label><Input id="d-await" value={f.awaited} onChange={(e) => set("awaited", e.target.value)} className="mt-1 text-sm" maxLength={300} aria-invalid={touched && needAwaited} /></div>
            <div><Label htmlFor="d-from">From whom</Label><Input id="d-from" value={f.awaited_from} onChange={(e) => set("awaited_from", e.target.value)} className="mt-1 text-sm" maxLength={120} /></div>
          </>
        ) : null}
        {f.outcome === "referred" ? <div className="sm:col-span-2"><Label htmlFor="d-ref">Referred to</Label><Input id="d-ref" value={f.referred_to} onChange={(e) => set("referred_to", e.target.value)} className="mt-1 text-sm" maxLength={200} aria-invalid={touched && needReferred} /></div> : null}
      </div>
      <fieldset>
        <legend className="text-sm font-medium">Members present</legend>
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
      </fieldset>
      <fieldset>
        <legend className="text-sm font-medium">Concerns (named, own words)</legend>
        <ul className="mt-1 space-y-1.5">
          {f.concerns.map((c, i) => (
            <li key={i} className="flex gap-1.5">
              <Input list="d-members" value={c.by} onChange={(e) => set("concerns", f.concerns.map((x, j) => (j === i ? { ...x, by: e.target.value } : x)))} placeholder="Who" className="w-40 text-sm" aria-label="Who raised it" maxLength={120} />
              <Input value={c.text} onChange={(e) => set("concerns", f.concerns.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)))} placeholder="The concern, in their words" className="flex-1 text-sm" aria-label="The concern" maxLength={1000} />
              <Button type="button" size="icon-sm" variant="ghost" aria-label="Remove this concern" onClick={() => set("concerns", f.concerns.filter((_, j) => j !== i))}><Trash2 className="size-4" /></Button>
            </li>
          ))}
        </ul>
        <Button type="button" size="xs" variant="outline" className="mt-1.5" onClick={() => set("concerns", [...f.concerns, { by: "", text: "" }])}><Plus className="size-3" />Add a concern</Button>
      </fieldset>
      {touched && problems.length ? <ul role="alert" className="text-sm text-bad list-disc pl-5">{problems.map((p) => <li key={p}>{p}</li>)}</ul> : null}
      {save.isError ? <p role="alert" className="text-sm text-bad">{errorText(save.error)}</p> : null}
      <div className="flex items-center gap-2">
        <LoadingButton type="submit" loading={save.isPending} loadingText="Saving" disabled={saved || !canRecord} title={canRecord ? undefined : "Only the MDT Coordinator records the decision"} data-testid="save-decision"><Check className="size-4" />{saved ? "Saved" : "Read back done, save"}</LoadingButton>
        <span className="text-xs text-muted-foreground">{saved ? "Recorded; the owner is told." : "Read the decision back to the board, then save."}</span>
      </div>
    </form>
  );
}
