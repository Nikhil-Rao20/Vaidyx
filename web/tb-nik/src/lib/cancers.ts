// The cancer picker of the New Case File flow: the ten commonest cancers per group and the checklist (protocol) each one
// maps to. Source of the lists: Report of National Cancer Registry Programme 2020 (ICMR-NCDIR, Bengaluru), leading sites
// by sex and the childhood cancers chapter. A cancer without a built checklist maps to protocol null: the generic rule
// applies and the doctor types the name. Cancer of Unknown Primary maps to the "cup" protocol (draft).

export type CancerGroup = "men" | "women" | "children" | "general";

export interface CancerEntry {
  id: string;
  label: string;
  /** The protocol id (GET /protocols) with a built checklist, or null for the generic rule. */
  protocol: string | null;
  /** Words a search box matches on. */
  keywords?: string[];
  /** The group lists this cancer sits in (any cancer can be picked from General). */
  groups: CancerGroup[];
  /** Why the checklist shown differs from the name (e.g. colorectal uses the rectal checklist). */
  note?: string;
}

export const SOURCE_NOTE = "Top 10 lists from the National Cancer Registry Programme report 2020 (ICMR-NCDIR).";

export const CANCERS: CancerEntry[] = [
  { id: "lung", label: "Lung", protocol: "lung_nsclc", keywords: ["nsclc", "bronchus", "chest"], groups: ["men", "women", "general"] },
  { id: "mouth", label: "Mouth", protocol: "oral_cavity", keywords: ["oral", "buccal", "gum", "cheek", "oral cavity"], groups: ["men", "women", "general"] },
  { id: "prostate", label: "Prostate", protocol: null, groups: ["men", "general"] },
  { id: "tongue", label: "Tongue", protocol: "oral_cavity", keywords: ["oral"], groups: ["men", "general"], note: "Uses the oral cavity checklist." },
  { id: "stomach", label: "Stomach", protocol: null, keywords: ["gastric"], groups: ["men", "general"] },
  { id: "oesophagus", label: "Oesophagus", protocol: null, keywords: ["esophagus", "food pipe"], groups: ["men", "women", "general"] },
  { id: "colorectal", label: "Colorectal", protocol: "colorectal_rectum", keywords: ["colon", "rectum", "rectal", "bowel"], groups: ["men", "women", "general"], note: "The built checklist is for rectal cancer; a colon cancer follows the generic rule for the rest." },
  { id: "liver", label: "Liver", protocol: null, keywords: ["hepatocellular", "hcc"], groups: ["men", "children", "general"] },
  { id: "larynx", label: "Larynx", protocol: null, keywords: ["voice box", "throat"], groups: ["men", "general"] },
  { id: "lymphoma_nhl", label: "Lymphoma (NHL)", protocol: null, keywords: ["non-hodgkin", "lymph"], groups: ["men", "general"] },
  { id: "breast", label: "Breast", protocol: "breast", groups: ["women", "general"] },
  { id: "cervix", label: "Cervix", protocol: "cervix", keywords: ["cervical"], groups: ["women", "general"] },
  { id: "ovary", label: "Ovary", protocol: null, keywords: ["ovarian"], groups: ["women", "general"] },
  { id: "corpus_uteri", label: "Corpus uteri", protocol: null, keywords: ["endometrium", "endometrial", "uterus"], groups: ["women", "general"] },
  { id: "gallbladder", label: "Gallbladder", protocol: null, keywords: ["biliary"], groups: ["women", "general"] },
  { id: "thyroid", label: "Thyroid", protocol: null, groups: ["women", "general"] },
  { id: "leukaemia", label: "Leukaemia", protocol: null, keywords: ["leukemia", "all", "aml", "blood"], groups: ["children", "general"] },
  { id: "lymphoma_child", label: "Lymphoma", protocol: null, keywords: ["hodgkin", "lymph"], groups: ["children"] },
  { id: "brain", label: "Brain", protocol: null, keywords: ["cns", "glioma", "medulloblastoma"], groups: ["children", "general"] },
  { id: "bone", label: "Bone", protocol: null, keywords: ["osteosarcoma", "ewing"], groups: ["children", "general"] },
  { id: "kidney", label: "Kidney", protocol: null, keywords: ["wilms", "renal"], groups: ["children", "general"] },
  { id: "retinoblastoma", label: "Retinoblastoma", protocol: null, keywords: ["eye"], groups: ["children"] },
  { id: "soft_tissue", label: "Soft tissue", protocol: null, keywords: ["sarcoma", "rhabdomyosarcoma"], groups: ["children", "general"] },
  { id: "germ_cell", label: "Germ cell", protocol: null, keywords: ["testis", "teratoma"], groups: ["children", "general"] },
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
  return CANCERS.filter((c) => c.label.toLowerCase().includes(needle) || (c.keywords || []).some((k) => k.includes(needle)));
}
