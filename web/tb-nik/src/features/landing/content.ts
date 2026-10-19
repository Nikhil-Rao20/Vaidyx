// Every word on the public site, in one place, so the wording can be reviewed and changed without touching the layout.
// Register: formal British English for clinicians and academic readers; no contractions; short declarative sentences.
// Constraints: no accuracy or validation claims; no model names; every patient detail is synthetic.
import type { LucideIcon } from "lucide-react";
import {
  Activity, Building2, CalendarDays, Eye, FileSearch, FlaskConical, Hospital, Landmark, Layers, LockKeyhole, MapPin, MonitorPlay,
  Quote, ShieldCheck, Stethoscope, UserRound, Users,
} from "lucide-react";

export type Icon = LucideIcon;

/** The pages of the top bar. Product is the landing page and the default. */
export const PAGES = [
  { to: "/", label: "Product" },
  { to: "/docs", label: "Docs" },
  { to: "/about", label: "About" },
  { to: "/contact", label: "Contact" },
] as const;

export const SITE = {
  name: "Vaidyx Tumour Board",
  product: "Tumour Board",
  by: "TANUH, The AI Centre of Excellence in Healthcare",
  signIn: "Sign in",
  open: "Open Case Files",
  skip: "Click to skip",
};

export const HERO = {
  eyebrow: "Vaidyx Tumour Board",
  // The second line is set in the serif face.
  title: ["Tumour Board preparation,", "complete and traceable."],
  lead: "Vaidyx assembles each patient's records into a single Case File, verifies every extracted value against its source document, checks completeness against Indian protocols, and records the Board's decision for the care that follows.",
  primary: "How it works",
  scroll: "Scroll",
};

export const STRIP = [
  "Aligned with NCG guidelines",
  "ICMR cancer registry lists",
  "UHID, IP and OP numbers, ABHA",
  "Integrates with HIS, RIS, LIS and PACS",
  "Desktop and mobile",
  "Deployed within the hospital",
  "Every value traceable to its source",
];

export const CHALLENGE = {
  eyebrow: "The challenge",
  title: ["Preparation determines", "the quality of the decision."],
  lead: "A Tumour Board allots a few minutes to each patient. Preparing a patient for discussion takes hours: reports from several departments, imaging on a separate system, and a presentation that is out of date before the meeting begins.",
  points: [
    { icon: Layers, title: "Fragmented records", text: "Patient records are distributed across the HIS, the laboratory and radiology systems and the PACS. No single view presents the complete clinical picture." },
    { icon: FileSearch, title: "Gaps identified late", text: "Missing reports and pending investigations are discovered during the meeting, and the patient is deferred to a later Board." },
    { icon: Activity, title: "Decisions not carried forward", text: "The Board's decision is entered in a register. The ward, the insurer and the follow-up clinic each request it separately." },
  ],
};

export interface Phase {
  key: "before" | "during" | "after";
  label: string;
  title: string;
  steps: { title: string; text: string }[];
}

export const HOW = {
  eyebrow: "How it works",
  title: ["Before, during and after", "the Tumour Board."],
  lead: "Vaidyx supports the complete cycle of the Tumour Board, from case preparation to the follow-up of its decision.",
  phases: [
    {
      key: "before",
      label: "Before",
      title: "Case preparation",
      steps: [
        { title: "Retrieval by UHID", text: "Vaidyx retrieves the patient's reports from the HIS and the laboratory and radiology systems, and lists the imaging studies available on the PACS." },
        { title: "Verified extraction", text: "Each value is extracted together with the line of the report from which it was taken. A value that cannot be traced to its source is discarded or marked for review." },
        { title: "Protocol checklist", text: "The checklist for the cancer type lists the records a Tumour Board requires. Pending items are requested from Pathology or Radiology directly from the Case File." },
        { title: "Readiness", text: "Specialty briefs are prepared for each department. The treating clinician records the question for the Board and marks the Case File as ready." },
      ],
    },
    {
      key: "during",
      label: "During",
      title: "The meeting",
      steps: [
        { title: "Agenda", text: "The MDT Coordinator sets the agenda. Each Case File is either ready or shows its pending items." },
        { title: "Participation", text: "Members join in person or by video. The room display presents the case summary and the imaging from the PACS." },
        { title: "Decision record", text: "The decision is recorded during the discussion, with the members present and the questions raised." },
      ],
    },
    {
      key: "after",
      label: "After",
      title: "Follow-through",
      steps: [
        { title: "Minutes", text: "The decision record and the minutes are available when the meeting closes." },
        { title: "Exports", text: "The Board presentation and the NCG Virtual Tumour Board template are generated under the hospital's identity." },
        { title: "Follow-up and audit", text: "Follow-up actions are tracked, and every action is entered in the audit log." },
      ],
    },
  ] satisfies Phase[],
};

export const SOURCES = {
  eyebrow: "Traceability",
  title: ["Every value,", "traceable to its source."],
  lead: "Vaidyx presents a value only when it can point to the line of the report from which it was taken. Each value opens its source on request. A value that cannot be verified is discarded or marked for review, and a clinician's confirmation takes precedence over any extracted value.",
  // A synthetic report. `quote` below is the index of the supporting line.
  report: {
    title: "Histopathology report",
    stamp: "Synthetic",
    lines: [
      "Specimen: core needle biopsy, left breast, 2 o'clock.",
      "Microscopy: invasive carcinoma of no special type.",
      "Tumour size on core: 2.8 cm in the largest dimension.",
      "Nottingham grade: 2 (tubules 3, pleomorphism 2, mitoses 1).",
      "ER: positive, 80 % of tumour cells, strong intensity.",
      "PR: positive, 60 % of tumour cells, moderate intensity.",
      "HER2: equivocal (2+). FISH advised.",
      "Ki-67: 22 %.",
    ],
  },
  valuesTitle: "Extracted values",
  fields: [
    { label: "Tumour size", value: "2.8 cm", quote: 2, state: "verified" as const },
    { label: "Grade", value: "2", quote: 3, state: "verified" as const },
    { label: "ER", value: "Positive, 80 %", quote: 4, state: "verified" as const },
    { label: "HER2", value: "Equivocal (2+)", quote: 6, state: "review" as const, note: "FISH advised; for confirmation by the pathologist" },
  ],
  ask: {
    title: "Ask the Case File",
    who: "Dr L. Rao, Breast Surgery",
    question: "What are the hormone receptor and HER2 results?",
    answer: [
      { text: "ER is positive in 80 % of tumour cells, with strong intensity.", quote: 4 },
      { text: "PR is positive in 60 % of tumour cells, with moderate intensity.", quote: 5 },
      { text: "HER2 is equivocal (2+); FISH has been advised.", quote: 6, review: true },
    ],
    note: "Each sentence carries a verified quotation from the report. The HER2 result is marked for review pending FISH.",
    labels: { verified: "verified", review: "for review", source: "source" },
  },
  rules: [
    { icon: Quote, title: "Verification before display", text: "A value is shown only with the report line that supports it." },
    { icon: UserRound, title: "Clinical precedence", text: "A clinician's confirmation is retained, including when the records are processed again." },
    { icon: Eye, title: "Points for review", text: "Uncertain items are marked for review rather than omitted." },
  ],
};

export const ROLES = {
  eyebrow: "Roles",
  title: ["Designed for every member", "of the Tumour Board."],
  lead: "Each role sees its own responsibilities first.",
  cards: [
    { icon: Stethoscope, title: "Treating clinician", text: "Your patients, their pending items and the question for the Board. Approvals from a phone between consultations.", points: ["Needs-attention view", "Direct requests to Pathology and Radiology", "The decision returned to the Case File"] },
    { icon: UserRound, title: "Resident", text: "Case Files prepared in minutes rather than an afternoon.", points: ["Retrieval of records by UHID", "Checklist of pending items", "Proposals submitted for the consultant's approval"] },
    { icon: FlaskConical, title: "Pathologist and Radiologist", text: "Requests arrive with their clinical context. Respond from the Case File or open the order in the HIS.", points: ["Request inbox", "Direct link to the order", "Reports filed to the Case File"] },
    { icon: CalendarDays, title: "MDT Coordinator", text: "Agenda, participants, room and minutes in one place.", points: ["Agenda with readiness status", "Video meeting and room display", "Minutes and exports"] },
    { icon: Users, title: "External expert", text: "Join a Board with an access code and view only the cases presented.", points: ["Access by code, no account required", "Admission by the coordinator", "No installation"] },
    { icon: Building2, title: "Department administrator and hospital IT", text: "Departments and users configured in an afternoon. Patient data remains within the hospital.", points: ["Role assignment by department", "Audit log of every action", "Self-hosted deployment"] },
  ],
};

export const SAFETY = {
  eyebrow: "Clinical safety",
  title: ["Clinical safety", "by design."],
  lead: "Vaidyx supports the work of the Tumour Board without replacing clinical judgement.",
  principles: [
    { icon: ShieldCheck, title: "Human oversight", text: "Expert-in-the-loop by design. Every summary is a draft until a clinician has reviewed it." },
    { icon: Quote, title: "Verified sources", text: "Every value and every statement presented as fact carries a verified quotation from the record." },
    { icon: MonitorPlay, title: "Imaging for clinicians", text: "PACS images are presented to clinicians for their own review and interpretation." },
    { icon: LockKeyhole, title: "Deployed within the hospital", text: "Designed to run on the hospital's own infrastructure. Patient records remain on site." },
    { icon: Landmark, title: "India first", text: "NCG, ICMR and PM-JAY references take precedence over international sources. Indian identifiers, names, units and date formats." },
    { icon: Hospital, title: "Complete audit trail", text: "Every AI operation and every user action is logged with the user and the time." },
  ],
};

export const CTA = {
  title: ["Vaidyx for", "your Tumour Board."],
  text: "Vaidyx is being developed with hospitals in India. Hospitals interested in a pilot are invited to contact TANUH.",
  signIn: "Sign in",
  contact: "Contact TANUH",
  contactTo: "/contact",
};

export const FOOTER = {
  note: "All patient names, identifiers and values shown on this site are synthetic.",
  scope: "Vaidyx checks, routes, summarises and flags. Clinical decisions remain with the clinician.",
  copyright: `© ${new Date().getFullYear()} TANUH, The AI Centre of Excellence in Healthcare.`,
  columns: [
    { title: "Product", links: [{ label: "How it works", to: "/#how" }, { label: "Traceability", to: "/#sources" }, { label: "Roles", to: "/#roles" }, { label: "Clinical safety", to: "/#safety" }] },
    { title: "Organisation", links: [{ label: "About", to: "/about" }, { label: "Team", to: "/about#team" }, { label: "TANUH", to: "/about#tanuh" }, { label: "Contact", to: "/contact" }] },
    { title: "Resources", links: [{ label: "Documentation", to: "/docs" }, { label: "tanuh.ai", to: "https://tanuh.ai" }, { label: "TANUH DPI", to: "https://dpi.tanuh.ai" }] },
    { title: "Account", links: [{ label: "Sign in", to: "/sign-in" }] },
  ],
};

/* About */
export const ABOUT = {
  eyebrow: "About",
  title: ["Developed with the clinicians", "who will use it."],
  lead: "Vaidyx is developed at TANUH, The AI Centre of Excellence in Healthcare at the Indian Institute of Science, Bengaluru, together with Tumour Boards at hospitals in India.",
  mission: [
    { title: "Purpose", text: "To give every patient discussed at a Tumour Board a complete, verified Case File, and to carry the Board's decision through to the care that follows." },
    { title: "Approach", text: "Vaidyx assists with preparation, verification and record-keeping. Clinical judgement remains with the clinician at every step." },
    { title: "Setting", text: "Designed for Indian hospitals: NCG and ICMR references, Indian identifiers and formats, and deployment within the hospital." },
  ],
};

export interface Member { name: string; role: string; photo: string | null }
export const TEAM = {
  eyebrow: "Team",
  title: ["The people behind", "Vaidyx."],
  lead: "A multidisciplinary team at TANUH.",
  // Names, roles and photographs to be supplied. Photographs: public/brand/team/<file>.
  members: [
    { name: "Team member", role: "Role", photo: null },
    { name: "Team member", role: "Role", photo: null },
    { name: "Team member", role: "Role", photo: null },
    { name: "Team member", role: "Role", photo: null },
    { name: "Team member", role: "Role", photo: null },
    { name: "Team member", role: "Role", photo: null },
  ] satisfies Member[],
};

export const TANUH = {
  eyebrow: "TANUH",
  title: ["The AI Centre of Excellence", "in Healthcare."],
  text: "TANUH, Translational AI for Networked Universal Healthcare, is the AI Centre of Excellence in Healthcare at the Indian Institute of Science, Bengaluru, funded by the Ministry of Education, Government of India. Vaidyx is developed at the Centre with the clinicians who will use it.",
  links: [
    { label: "tanuh.ai", href: "https://tanuh.ai", text: "The Centre, its mission and its programmes" },
    { label: "dpi.tanuh.ai", href: "https://dpi.tanuh.ai", text: "Open digital public infrastructure for healthcare AI" },
  ],
  place: { icon: MapPin, text: "Indian Institute of Science, Bengaluru" },
};

/* Placeholder pages */
export const DOCS = {
  eyebrow: "Documentation",
  title: ["Documentation", "in preparation."],
  text: "The documentation will cover installation, integration with hospital information systems, roles and permissions, and the audit model. It will be published on this page.",
};

export const CONTACT = {
  eyebrow: "Contact",
  title: ["Write to", "the Vaidyx team."],
  lead: "Hospitals interested in Vaidyx, and clinicians who would like to take part in its development, are invited to write to us.",
  email: "sulake.nikhileswararao@tanuh.ai",
  // Fixed, so that enquiries from the site can be filtered in the mailbox.
  subject: "[Vaidyx] Website enquiry",
  emailTitle: "Email",
  write: "Write an email",
  copy: "Copy address",
  copied: "Copied",
  form: {
    title: "Enquiry",
    name: "Name",
    hospital: "Hospital or institution",
    role: "Role",
    message: "Message",
    submit: "Compose email",
    note: "The enquiry opens in your email application, addressed to the Vaidyx team with a fixed subject line. Nothing is sent from this page.",
  },
  place: { icon: MapPin, text: "TANUH, Indian Institute of Science, Bengaluru" },
};
