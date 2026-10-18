// The New Case File form: one object carried through the three steps, with the recommended defaults pre-filled
// (owner's UX note 1: a common value is already there and easy to change). Urgency has no default on purpose.
import type { HisLookup } from "@/lib/types";
import { GENERIC_SETTING, cleanCancerName, isGeneric } from "@/lib/cancers";

export interface NewCaseForm {
  identifier: string;
  lookup: HisLookup | null;
  /** A CancerEntry id from lib/cancers, "custom" for a typed name, or null. */
  cancerId: string | null;
  /** The cancer's name (the picked label, or the typed name when it is not listed); sent as cancer_name. */
  cancerName: string;
  /** The built checklist, or "generic" (lib/cancers GENERIC_PROTOCOL) for a cancer with no checklist yet; null before a pick. */
  protocol: string | null;
  /** The NCG setting id "as recorded"; NOT_RECORDED (StepCancer) when the records do not say yet; "as_recorded" under the generic rule. */
  setting: string;
  windowMonths: number | "all";
  boardQuestion: string;
  urgency: number | null;
  /** YYYY-MM-DD from the date input, or "". */
  boardDate: string;
  joinCode: boolean;
  outsideConsent: boolean;
  /** The owning treating department when the doctor has several (or is a coordinator). */
  department: string;
}

export const DEFAULT_FORM: NewCaseForm = {
  identifier: "",
  lookup: null,
  cancerId: null,
  cancerName: "",
  protocol: null,
  setting: "",
  windowMonths: 12,
  boardQuestion: "",
  urgency: null,
  boardDate: "",
  joinCode: true,
  outsideConsent: false,
  department: "",
};

export const WINDOW_CHOICES: Array<{ value: number | "all"; label: string }> = [
  { value: 6, label: "Last 6 months" },
  { value: 12, label: "Last 12 months (usual)" },
  { value: 24, label: "Last 24 months" },
  { value: "all", label: "Everything on record" },
];

export function windowWords(w: number | "all"): string {
  return w === "all" ? "everything on record" : `the last ${w} months`;
}

/** The body of POST /cases/from-his. A cancer with no checklist yet goes as protocol "generic" with its one setting and its name
 * (required there); a built checklist sends the picked name too, for the record. */
export function createBody(form: NewCaseForm, notRecorded: string) {
  const p = form.lookup?.patient;
  const generic = isGeneric(form.protocol);
  return {
    identifier: p?.uhid || form.identifier,
    protocol: form.protocol || "",
    setting: generic ? GENERIC_SETTING : form.setting && form.setting !== notRecorded ? form.setting : "",
    board_date: form.boardDate || "",
    window: form.windowMonths === "all" ? { all: true } : { months: form.windowMonths },
    department: form.department || undefined,
    cancer_name: cleanCancerName(form.cancerName) || undefined,
  };
}
