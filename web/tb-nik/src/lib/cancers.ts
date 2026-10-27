// The cancer picker of the New Case File flow: the ten commonest cancers per group and the checklist (protocol) each one
// maps to. Source of the lists: Report of National Cancer Registry Programme 2020 (ICMR-NCDIR, Bengaluru), leading sites
// by sex and the childhood cancers chapter. A cancer without a built checklist (protocol null here, or a checklist the server
// does not list) maps to protocol "generic": four core records are checked (histopathology, staging imaging, a clinical note with
// performance status, the question for the board; owner decision R05-Q04) and the picked or typed name is sent as cancer_name.
// A typed (not listed) cancer asks solid or blood: a blood cancer maps to "generic_haem" (night-v3 item 2.9: the marrow, flow
// cytometry or cytogenetics report instead of staging imaging). Cancer of Unknown Primary maps to the "cup" protocol (draft).
// Night-v3 item 2.10: every entry has a checklist except Thyroid (generic rule); Colorectal and Kidney ask one more question
// (variants) before the setting. The new checklists are drafts ("0.1-draft"): see isDraftChecklist.

export type CancerGroup = "men" | "women" | "children" | "general";

/** One answer of an entry's follow-up question (Colorectal: colon or rectum; Kidney: adult or child), each with its own checklist. */
export interface CancerVariant {
  id: string;
  label: string;
  protocol: string;
  note?: string;
  /** The child's option: pre-selected when the patient is under 15 (the other one otherwise), where the entry has `childDefault`. */
  child?: boolean;
}

export interface CancerEntry {
  id: string;
  label: string;
  /** The protocol id (GET /protocols) with a built checklist, or null: no checklist yet, the generic rule (see protocolFor), or
   * an entry with variants (its checklist is the picked variant's). */
  protocol: string | null;
  /** A follow-up question before the setting; the entry's own protocol stays null and a variant must be picked. */
  variants?: CancerVariant[];
  /** The follow-up question, e.g. "Where is the tumour?". */
  question?: string;
  /** Pre-select the variant by age (the child's under 15, else the other); without it nothing is pre-selected. */
  childDefault?: boolean;
  /** Words a search box matches on. */
  keywords?: string[];
  /** The group lists this cancer sits in (any cancer can be picked from General). */
  groups: CancerGroup[];
  /** Why the checklist shown differs from the name (e.g. colorectal uses the rectal checklist). */
  note?: string;
}

export const SOURCE_NOTE = "Top 10 lists from the National Cancer Registry Programme report 2020 (ICMR-NCDIR).";

/** The protocol of a cancer with no checklist yet (tumour_board/protocols/generic.json) and its one setting. */
export const GENERIC_PROTOCOL = "generic";
export const GENERIC_SETTING = "as_recorded";
/** What the generic rule checks, word for word on the review step and the Case File header. */
export const GENERIC_RULE = "No disease-specific Indian protocol: four core records are checked";
/** How lists and the Case File name a cancer with no checklist yet: "<name> (no checklist yet)". */
export const NO_CHECKLIST_WORDS = "no checklist yet";
export const GENERIC_RECORDS = [
  "Histopathology or cytology report",
  "Staging imaging report (CT, MRI or PET-CT, any one)",
  "Clinical note with performance status",
  "The question for the board (you can type it)",
];
/** The cancer's name as the server accepts it: 2 to 80 characters after trimming. */
export const CANCER_NAME_MIN = 2;
export const CANCER_NAME_MAX = 80;

/** The blood cancer variant of the generic rule (tumour_board/protocols/generic_haem.json, night-v3 item 2.9). */
export const GENERIC_HAEM_PROTOCOL = "generic_haem";
export const GENERIC_PROTOCOLS = [GENERIC_PROTOCOL, GENERIC_HAEM_PROTOCOL];
/** The blood cancer rule checks three core records (coordinator decision, 27 Oct 2026); an earlier treatment summary is optional, not core. */
export const GENERIC_HAEM_RULE = "No disease-specific Indian protocol: three core records are checked (blood cancer)";
export const GENERIC_HAEM_RECORDS = [
  "Histopathology, bone marrow, flow cytometry or cytogenetics report (any one)",
  "Clinical note with performance status",
  "The question for the board (you can type it)",
];
/** The question of the "not listed" path, and its two answers. */
export const KIND_QUESTION = "Is this a solid cancer or a blood cancer?";
export const KIND_CHOICES: Array<{ protocol: string; label: string }> = [
  { protocol: GENERIC_PROTOCOL, label: "Solid cancer (organ, tissue)" },
  { protocol: GENERIC_HAEM_PROTOCOL, label: "Blood cancer (leukaemia, lymphoma, myeloma and the like)" },
];

export function isGeneric(protocol?: string | null): boolean {
  return !!protocol && GENERIC_PROTOCOLS.includes(protocol);
}

/** What the generic rule checks, by variant: the solid rule or the blood cancer rule. */
export function genericRule(protocol?: string | null): string {
  return protocol === GENERIC_HAEM_PROTOCOL ? GENERIC_HAEM_RULE : GENERIC_RULE;
}

export function genericRecords(protocol?: string | null): string[] {
  return protocol === GENERIC_HAEM_PROTOCOL ? GENERIC_HAEM_RECORDS : GENERIC_RECORDS;
}

/** A checklist built from the books but not yet checked by a clinician (owner decision D6): version "x-draft" (or a note saying so). */
export const DRAFT_CHECKLIST = "Draft checklist: needs a clinician's check";
export const BUILT_WORDS = "Checklist built";
export const BUILT_DRAFT_WORDS = "Checklist built (draft): needs a clinician's check";

export function isDraftChecklist(p?: { version?: string; note?: string } | null): boolean {
  if (!p) return false;
  return /-draft$/i.test(p.version ?? "") || /\bdraft\b/i.test(p.note ?? "");
}

/** The variant of an entry by its id. */
export function variantOf(c: CancerEntry, variantId?: string | null): CancerVariant | undefined {
  return variantId ? c.variants?.find((v) => v.id === variantId) : undefined;
}

/** The variant pre-selected for this patient: by age where the entry asks so (Kidney: Wilms tumour under 15), else none. */
export function defaultVariant(c: CancerEntry, age?: number | string | null): CancerVariant | undefined {
  if (!c.variants?.length || !c.childDefault) return undefined;
  const a = typeof age === "string" ? parseInt(age, 10) : age;
  const child = typeof a === "number" && !isNaN(a) && a < 15;
  return c.variants.find((v) => Boolean(v.child) === child);
}

/** The protocol a picked cancer is created under: its built checklist when the server lists it (or the list has not arrived yet),
 * otherwise the generic rule. An entry with variants needs one picked: null until then. */
export function protocolFor(c: CancerEntry, built?: { has(id: string): boolean } | null, variantId?: string | null): string | null {
  const own = c.variants?.length ? variantOf(c, variantId)?.protocol : c.protocol;
  if (c.variants?.length && !own) return null;
  if (own && !isGeneric(own) && (!built || built.has(own))) return own;
  return GENERIC_PROTOCOL;
}

/** The checklists an entry can lead to (its own, or each variant's), for the picker card. */
export function protocolsOf(c: CancerEntry): string[] {
  return c.variants?.length ? c.variants.map((v) => v.protocol) : c.protocol ? [c.protocol] : [];
}

/** The cancer's name cleaned as the server cleans it (trimmed, inner spaces collapsed). */
export function cleanCancerName(name: string): string {
  return name.replace(/\s+/g, " ").trim();
}

export const CANCERS: CancerEntry[] = [
  { id: "lung", label: "Lung", protocol: "lung_nsclc", keywords: ["nsclc", "bronchus", "chest"], groups: ["men", "women", "general"] },
  { id: "mouth", label: "Mouth", protocol: "oral_cavity", keywords: ["oral", "buccal", "gum", "cheek", "oral cavity"], groups: ["men", "women", "general"] },
  { id: "prostate", label: "Prostate", protocol: "prostate", groups: ["men", "general"] },
  { id: "tongue", label: "Tongue", protocol: "oral_cavity", keywords: ["oral"], groups: ["men", "general"], note: "Uses the oral cavity checklist." },
  { id: "stomach", label: "Stomach", protocol: "stomach", keywords: ["gastric"], groups: ["men", "general"] },
  { id: "oesophagus", label: "Oesophagus", protocol: "oesophagus", keywords: ["esophagus", "food pipe"], groups: ["men", "women", "general"] },
  {
    id: "colorectal", label: "Colorectal", protocol: null, keywords: ["colon", "rectum", "rectal", "bowel", "caecum", "sigmoid"], groups: ["men", "women", "general"],
    question: "Where is the tumour?",
    variants: [{ id: "colon", label: "Colon", protocol: "colorectal_colon" }, { id: "rectum", label: "Rectum", protocol: "colorectal_rectum" }],
  },
  { id: "liver", label: "Liver", protocol: "liver_hcc", keywords: ["hepatocellular", "hcc", "hepatoblastoma"], groups: ["men", "children", "general"], note: "Uses the liver cancer (HCC) checklist." },
  { id: "larynx", label: "Larynx", protocol: "larynx", keywords: ["voice box", "throat"], groups: ["men", "general"] },
  { id: "lymphoma_nhl", label: "Lymphoma (NHL)", protocol: "lymphoma", keywords: ["non-hodgkin", "lymph"], groups: ["men", "general"] },
  { id: "breast", label: "Breast", protocol: "breast", groups: ["women", "general"] },
  { id: "cervix", label: "Cervix", protocol: "cervix", keywords: ["cervical"], groups: ["women", "general"] },
  { id: "ovary", label: "Ovary", protocol: "ovary", keywords: ["ovarian"], groups: ["women", "general"] },
  { id: "corpus_uteri", label: "Corpus uteri", protocol: "corpus_uteri", keywords: ["endometrium", "endometrial", "uterus"], groups: ["women", "general"] },
  { id: "gallbladder", label: "Gallbladder", protocol: "gallbladder", keywords: ["biliary", "gall bladder"], groups: ["women", "general"] },
  { id: "thyroid", label: "Thyroid", protocol: null, groups: ["women", "general"] },
  { id: "leukaemia", label: "Leukaemia", protocol: "leukaemia", keywords: ["leukemia", "all", "aml", "blood"], groups: ["children", "general"] },
  { id: "lymphoma_child", label: "Lymphoma", protocol: "lymphoma", keywords: ["hodgkin", "lymph"], groups: ["children"] },
  { id: "brain", label: "Brain", protocol: "brain_cns", keywords: ["cns", "glioma", "medulloblastoma"], groups: ["children", "general"] },
  { id: "bone", label: "Bone", protocol: "bone_sarcoma", keywords: ["osteosarcoma", "ewing", "chondrosarcoma", "sarcoma"], groups: ["children", "general"] },
  {
    id: "kidney", label: "Kidney", protocol: null, keywords: ["wilms", "renal", "rcc", "nephroblastoma"], groups: ["children", "general"],
    question: "Which kidney cancer?", childDefault: true,
    variants: [
      { id: "rcc", label: "Renal cell carcinoma (adult)", protocol: "kidney" },
      { id: "wilms", label: "Wilms tumour (child)", protocol: "wilms", child: true },
    ],
  },
  { id: "retinoblastoma", label: "Retinoblastoma", protocol: "retinoblastoma", keywords: ["eye"], groups: ["children"] },
  { id: "soft_tissue", label: "Soft tissue", protocol: "soft_tissue_sarcoma", keywords: ["sarcoma", "rhabdomyosarcoma"], groups: ["children", "general"] },
  { id: "germ_cell", label: "Germ cell", protocol: "germ_cell", keywords: ["testis", "testicular", "teratoma", "seminoma"], groups: ["children", "general"] },
  { id: "other_child", label: "Others", protocol: null, groups: ["children"] },
  { id: "cup", label: "Cancer of Unknown Primary", protocol: "cup", keywords: ["cup", "unknown primary", "muo"], groups: ["general"] },
];

/** The ten in NCRP order per group; General lists everything. */
export const TOP10: Record<CancerGroup, string[]> = {
  men: ["lung", "mouth", "prostate", "tongue", "stomach", "oesophagus", "colorectal", "liver", "larynx", "lymphoma_nhl"],
  women: ["breast", "cervix", "ovary", "corpus_uteri", "lung", "mouth", "colorectal", "gallbladder", "thyroid", "oesophagus"],
  children: ["leukaemia", "lymphoma_child", "brain", "bone", "kidney", "retinoblastoma", "soft_tissue", "germ_cell", "liver", "other_child"],
  general: CANCERS.map((c) => c.id),
};

export const GROUP_LABELS: Record<CancerGroup, string> = { men: "Men", women: "Women", children: "Children", general: "All" };

export function cancerById(id: string): CancerEntry | undefined {
  return CANCERS.find((c) => c.id === id);
}

export function cancersFor(group: CancerGroup): CancerEntry[] {
  return TOP10[group].map((id) => cancerById(id)).filter((c): c is CancerEntry => Boolean(c));
}

/** The group the record suggests: children under 15, else by sex; unknown sex shows all. */
export function groupFor(sex?: string | null, age?: number | string | null): CancerGroup {
  const a = typeof age === "string" ? parseInt(age, 10) : age;
  if (typeof a === "number" && !isNaN(a) && a < 15) return "children";
  if (/^f/i.test(sex || "")) return "women";
  if (/^m/i.test(sex || "")) return "men";
  return "general";
}

export function searchCancers(text: string): CancerEntry[] {
  const needle = text.trim().toLowerCase();
  if (!needle) return [];
  return CANCERS.filter((c) => c.label.toLowerCase().includes(needle) || (c.keywords || []).some((k) => k.includes(needle))
    || (c.variants || []).some((v) => v.label.toLowerCase().includes(needle)));
}
