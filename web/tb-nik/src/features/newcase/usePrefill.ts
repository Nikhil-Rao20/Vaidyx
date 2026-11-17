// The AI pre-fill of the New Case File (docs/new-case/DESIGN.md N6). When the lookup finds a patient (a new UHID), POST /his/prefill
// starts a short job on the server (tumour_board/case_prefill.py: the reasoning model reads the patient's reports in the window, every
// value comes with a quote checked word for word against its report) and this hook polls it every 1.5 s until done or failed (or the
// page goes). Then it fills ONLY the fields the doctor has not touched since the lookup AND that are still empty at that moment (a
// value typed before a second lookup is the doctor's, though the touched set starts again with each patient), the same way a click
// would (the cancer through StepCancer's own cancerPatch), and marks each one AI-filled; the mark goes when the doctor edits that field. Urgency is never filled:
// it is offered as a suggestion with a one-tap "Use" (owner rule: the consultant's own call). The department is filled only for a
// doctor of several treating departments while it is still empty (chosen by the server from the visits, without the model).
// "Clear AI suggestions" puts back what was there before. A failure changes nothing but one quiet line. Guest reviewers and the Vaidyx
// admin never run it (the admin has no clinical access, admin consoles D5; the server refuses it too).
import { createContext, useCallback, useContext, useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { useProtocols } from "@/hooks/useQueries";
import { api } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import { isVaidyxAdmin, useSession } from "@/lib/session";
import { CANCERS, CANCER_NAME_MAX, GENERIC_SETTING, cancerById, cancersFor, cleanCancerName, groupFor, isGeneric, type CancerEntry } from "@/lib/cancers";
import type { HisPatient, PrefillJob, PrefillResult, PrefillSource } from "@/lib/types";
import type { NewCaseForm } from "@/features/newcase/form";
import { cancerPatch } from "@/features/newcase/StepCancer";
import { useOwnerChoices } from "@/features/newcase/StepLogistics";

export type AiField = "cancer" | "setting" | "boardQuestion" | "department";

export interface AiMark {
  field: AiField;
  /** What was filled, as the doctor reads it ("Invasive breast carcinoma"). */
  value?: string;
  quote?: string;
  source?: PrefillSource;
  /** The board question: the reports it rests on (a draft, no quote). */
  basis?: PrefillSource[];
  /** The department: why (the visits), no model involved. */
  why?: string;
}

export type PrefillStatus = "off" | "running" | "done" | "failed" | "cleared";

export interface Prefill {
  status: PrefillStatus;
  /** Reports being read while running (the window's count, at most 12). */
  expected: number;
  result: PrefillResult | null;
  error: string;
  marks: Partial<Record<AiField, AiMark>>;
  /** Shown as "AI suggests n" with a one-tap Use; never pre-selected. */
  urgency: PrefillResult["urgency"] | null;
  clear: () => void;
  /** Called with every change the doctor makes, before it is applied. */
  touch: (patch: Partial<NewCaseForm>) => void;
}

export const POLL_MS = 1500;
const MAX_REPORTS = 12;
const QUIET_ERROR = "AI suggestions are not available just now. Fill the steps yourself.";

/** The form keys behind each AI field (what "Clear AI suggestions" puts back). */
const KEYS: Record<AiField, Array<keyof NewCaseForm>> = {
  cancer: ["cancerId", "cancerName", "protocol", "variant", "setting"],
  setting: ["setting"],
  boardQuestion: ["boardQuestion"],
  department: ["department"],
};
const CANCER_KEYS: Array<keyof NewCaseForm> = ["cancerId", "cancerName", "protocol", "variant"];

export const PrefillContext = createContext<Prefill | null>(null);
export const usePrefillContext = () => useContext(PrefillContext);

/** The fields a change of the doctor's touches. A cancer pick also resets the setting: that is the pick's doing, not a setting chosen,
 * so the setting stays open to the AI (it is filled only when the AI's cancer is the one picked). */
export function touchedBy(patch: Partial<NewCaseForm>): { touched: AiField[]; changed: AiField[] } {
  const has = (k: keyof NewCaseForm) => Object.prototype.hasOwnProperty.call(patch, k);
  const cancer = CANCER_KEYS.some(has);
  const touched: AiField[] = [];
  const changed: AiField[] = [];
  if (cancer) { touched.push("cancer"); changed.push("cancer"); }
  if (has("setting")) { changed.push("setting"); if (!cancer) touched.push("setting"); }
  if (has("boardQuestion")) { touched.push("boardQuestion"); changed.push("boardQuestion"); }
  if (has("department")) { touched.push("department"); changed.push("department"); }
  return { touched, changed };
}

const words = (s: string) => ` ${s.toLowerCase().replace(/[^a-z0-9]+/g, " ")} `;
const mentions = (name: string, c: CancerEntry) => [c.label, ...(c.keywords ?? [])].some((k) => k.length > 2 && words(name).includes(words(k)));

/** The list entry the AI's cancer is: the variant entry it names (Colorectal, Kidney, Liver), else an entry with that checklist (the one
 * the records' name mentions, else one of the patient's group, else the first), else for a cancer with no checklist an entry with
 * none that the name mentions (Thyroid). null: a typed name. */
export function entryFor(cancer: NonNullable<PrefillResult["cancer"]>, patient?: HisPatient | null): CancerEntry | null {
  if (cancer.entry) return cancerById(cancer.entry) ?? null;
  const name = cancer.name || cancer.label || "";
  if (isGeneric(cancer.protocol)) {
    return CANCERS.find((c) => !c.protocol && !c.variants?.length && c.id !== "other_child" && Boolean(c.blood) === (cancer.protocol === "generic_haem") && mentions(name, c)) ?? null;
  }
  const same = CANCERS.filter((c) => !c.variants?.length && c.protocol === cancer.protocol);
  if (same.length <= 1) return same[0] ?? null;
  const group = cancersFor(groupFor(patient?.sex, patient?.age)).map((c) => c.id);
  return same.find((c) => mentions(name, c)) ?? same.find((c) => group.includes(c.id)) ?? same[0];
}

/** The form change of the AI's cancer: what a click on its entry does, or a typed name under the generic rule. */
export function cancerChange(cancer: NonNullable<PrefillResult["cancer"]>, known: { has(id: string): boolean } | null, patient?: HisPatient | null): Partial<NewCaseForm> | null {
  const entry = entryFor(cancer, patient);
  if (entry) return cancerPatch(entry, known, patient?.age, cancer.variant);
  if (!isGeneric(cancer.protocol)) return null;
  const name = cleanCancerName(cancer.name).slice(0, CANCER_NAME_MAX);
  return name.length >= 2 ? { cancerId: "custom", cancerName: name, protocol: cancer.protocol, variant: "", setting: GENERIC_SETTING } : null;
}

/** The fields the AI may still fill: those at their default right now (the cancer: nothing picked or typed). */
export function emptyFields(f: NewCaseForm): Set<AiField> {
  const out = new Set<AiField>();
  if (f.cancerId == null && !f.protocol && !f.cancerName.trim()) out.add("cancer");
  if (!f.setting) out.add("setting");
  if (!f.boardQuestion.trim()) out.add("boardQuestion");
  if (!f.department) out.add("department");
  return out;
}

export function usePrefill(form: NewCaseForm, setForm: Dispatch<SetStateAction<NewCaseForm>>, enabledIn: boolean): Prefill {
  const { me } = useSession();
  const enabled = enabledIn && !isVaidyxAdmin(me);
  const protocols = useProtocols();
  const owners = useOwnerChoices();
  const [status, setStatus] = useState<PrefillStatus>("off");
  const [result, setResult] = useState<PrefillResult | null>(null);
  const [error, setError] = useState("");
  const [marks, setMarks] = useState<Partial<Record<AiField, AiMark>>>({});
  const touched = useRef(new Set<AiField>());
  const before = useRef<Partial<NewCaseForm>>({});
  const marksRef = useRef(marks);
  marksRef.current = marks;
  const formRef = useRef(form);
  formRef.current = form;
  const ctx = useRef({ protocols: protocols.data, owners });
  ctx.current = { protocols: protocols.data, owners };
  const forUhid = useRef("");
  const uhid = form.lookup?.found ? form.lookup.patient?.uhid || form.lookup.identifier || "" : "";

  /** Put back what the AI replaced, for the fields it still holds; the doctor's own edits stay. */
  const revert = useCallback(() => {
    const m = marksRef.current;
    const back: Partial<NewCaseForm> = {};
    for (const f of Object.keys(m) as AiField[]) {
      for (const k of KEYS[f]) {
        if (k === "setting" && f === "cancer" && touched.current.has("setting")) continue;
        if (k in before.current) (back as Record<string, unknown>)[k] = before.current[k];
      }
    }
    if (Object.keys(back).length) setForm((cur) => ({ ...cur, ...back }));
    setMarks({});
  }, [setForm]);

  const apply = useCallback((r: PrefillResult) => {
    const f = formRef.current;
    const t = touched.current;
    const free = emptyFields(f);
    const { protocols: plist, owners: own } = ctx.current;
    const known = plist ? new Set((plist.protocols ?? []).map((p) => p.id)) : null;
    const patch: Partial<NewCaseForm> = {};
    const m: Partial<Record<AiField, AiMark>> = {};
    if (r.cancer && !t.has("cancer") && free.has("cancer")) {
      const change = cancerChange(r.cancer, known, f.lookup?.patient);
      if (change) { Object.assign(patch, change); m.cancer = { field: "cancer", value: r.cancer.name, quote: r.cancer.quote, source: r.cancer.report }; }
    }
    const protocolNow = "protocol" in patch ? patch.protocol : f.protocol;
    const settingFree = "cancer" in m ? !patch.setting : free.has("setting");  // the AI's own cancer pick resets the setting: still free
    if (r.setting && r.cancer && !t.has("setting") && settingFree && protocolNow === r.cancer.protocol && !isGeneric(protocolNow)) {
      patch.setting = r.setting.id;
      m.setting = { field: "setting", value: r.setting.label, quote: r.setting.quote, source: r.setting.report };
    }
    if (r.board_question?.text && !t.has("boardQuestion") && free.has("boardQuestion")) {
      patch.boardQuestion = r.board_question.text;
      m.boardQuestion = { field: "boardQuestion", value: r.board_question.text, basis: r.board_question.basis };
    }
    if (r.department && !t.has("department") && free.has("department") && own.length > 1 && own.some((o) => o.id === r.department?.id)) {
      patch.department = r.department.id;
      m.department = { field: "department", value: r.department.name, why: r.department.why };
    }
    const prev: Partial<NewCaseForm> = {};
    for (const k of Object.keys(patch) as Array<keyof NewCaseForm>) (prev as Record<string, unknown>)[k] = f[k];
    before.current = prev;
    if (Object.keys(patch).length) setForm((cur) => ({ ...cur, ...patch }));
    setMarks(m);
  }, [setForm]);

  useEffect(() => {
    if (forUhid.current && forUhid.current !== uhid) {  // another patient (or none): the previous patient's suggestions go
      revert();
      setResult(null); setError(""); setStatus("off");
    }
    forUhid.current = uhid;
    if (!enabled || !uhid) return;
    touched.current = new Set();
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setStatus("running"); setError(""); setResult(null);
    const fail = (msg?: string) => { if (alive) { setStatus("failed"); setError(msg || QUIET_ERROR); } };
    const poll = (job: string) => {
      timer = setTimeout(async () => {
        try {
          const j = await api.get<PrefillJob>(EP.hisPrefillJob(job));
          if (!alive) return;
          if (j.state === "running") { poll(job); return; }
          if (j.state === "done" && j.result) { setResult(j.result); apply(j.result); setStatus("done"); return; }
          fail(j.error);
        } catch { fail(); }
      }, POLL_MS);
    };
    const w = formRef.current.windowMonths;
    api.post<{ job?: string; state?: string }>(EP.hisPrefill, { identifier: uhid, ...(w === "all" ? { all: true } : { months: w }) })
      .then((r) => { if (!alive) return; if (r?.job) poll(r.job); else setStatus("off"); })
      .catch(() => fail());
    return () => { alive = false; if (timer) clearTimeout(timer); };
  }, [enabled, uhid]); // eslint-disable-line react-hooks/exhaustive-deps

  const touch = useCallback((patch: Partial<NewCaseForm>) => {
    const { touched: tf, changed } = touchedBy(patch);
    tf.forEach((f) => touched.current.add(f));
    if (changed.some((f) => marksRef.current[f])) {
      setMarks((cur) => { const next = { ...cur }; changed.forEach((f) => delete next[f]); return next; });
    }
  }, []);

  const clear = useCallback(() => { revert(); setStatus("cleared"); }, [revert]);

  const expected = Math.min(form.lookup?.reports ?? 0, MAX_REPORTS);
  return { status, expected, result, error, marks, urgency: status === "done" ? result?.urgency ?? null : null, clear, touch };
}
