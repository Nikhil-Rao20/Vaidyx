// Every word on the landing page, in one place, so the words can be reviewed and changed without touching the layout.
// Rules: careful, plain English; no accuracy or validation claims; the scope line is exact (checks, routes, summarises, flags;
// never a diagnosis, a stage or a treatment advice). Every patient detail on the page is synthetic.
import type { LucideIcon } from "lucide-react";
import {
  Activity, BadgeCheck, Building2, CalendarDays, ClipboardList, Eye, FileSearch, FlaskConical, Hospital, Landmark, Layers,
  LockKeyhole, MapPin, MonitorPlay, Quote, ScanSearch, ShieldCheck, Stethoscope, UserRound, Users, Video,
} from "lucide-react";

export const NAV = [
  { id: "how", label: "How it works" },
  { id: "sources", label: "Sources" },
  { id: "roles", label: "For your team" },
  { id: "safety", label: "Safety" },
  { id: "team", label: "Team" },
  { id: "tanuh", label: "TANUH" },
] as const;

export const HERO = {
  eyebrow: "Vaidyx Tumour Board",
  // The accent word is set in the serif face.
  title: ["The Tumour Board,", "prepared."],
  lead: "One Case File per patient, built from the hospital's own records. Every value quoted from its source. Checked against Indian protocols before the meeting, and carried through after it.",
  primary: "See how it works",
  signIn: "Sign in",
  open: "Open Case Files",
  // Synthetic lines that float around the mark: records becoming one Case File.
  chips: [
    { text: "Histopathology", sub: "3 values, each quoted", icon: FlaskConical },
    { text: "IHC panel", sub: "requested from Pathology", icon: ClipboardList },
    { text: "Staging imaging", sub: "as recorded, on the PACS", icon: ScanSearch },
    { text: "Question for the board", sub: "written by the treating doctor", icon: Quote },
    { text: "Ready for the board", sub: "2 records left, then ready", icon: BadgeCheck },
  ],
  scroll: "Scroll",
};

export const STRIP = [
  "NCG guidelines first",
  "ICMR cancer registry lists",
  "UHID, IP and OP numbers, ABHA",
  "Reads from the HIS, RIS, LIS and PACS",
  "Laptop in the OPD, phone on the ward",
  "Runs inside the hospital",
  "Every value with its source",
];

export const PROBLEM = {
  eyebrow: "Why",
  title: ["Ten minutes in the room.", "Hours before it."],
  lead: "A Tumour Board decides a patient's treatment in minutes. Getting a patient there takes a resident most of a day: reports from four departments, a scan on another system, and a slide deck that is out of date before the meeting starts.",
  points: [
    { icon: Layers, title: "Scattered", text: "The records sit in the HIS, the lab system, the PACS and a folder of scans. Nobody sees the whole story in one place." },
    { icon: FileSearch, title: "Found too late", text: "What is missing is discovered in the meeting, not before it. The patient waits for the next board." },
    { icon: Activity, title: "Lost after the room", text: "The decision becomes a line in a register. The ward, the insurer and the next clinic each ask for it again." },
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
  title: ["Before, during and after", "the board."],
  lead: "Vaidyx follows the patient through the whole board, not just the meeting.",
  phases: [
    {
      key: "before",
      label: "Before",
      title: "A Case File that builds itself",
      steps: [
        { title: "Start from the UHID", text: "Vaidyx pulls the patient's reports from the HIS, the lab and radiology systems, and lists the imaging on the PACS." },
        { title: "Every report is read", text: "Each value is kept only with the line of the report it came from. A value with no line is dropped or marked for review." },
        { title: "The checklist shows what is missing", text: "The protocol for that cancer lists the records a board needs. A request goes to Pathology or Radiology in one click and comes back into the file." },
        { title: "Ready for the board", text: "Specialty helpers prepare a brief for each department. The treating doctor writes the question for the board and marks the file ready." },
      ],
    },
    {
      key: "during",
      label: "During",
      title: "A meeting about the patient, not the paperwork",
      steps: [
        { title: "An agenda that is honest", text: "The MDT Coordinator lists the Case Files. Each one is ready, or says what is left." },
        { title: "In the room or from anywhere", text: "Join with video from the ward, the OPD or home. The room screen shows the images from the PACS." },
        { title: "The decision, as it is made", text: "Recorded live, with who was present and what was asked. Questions from the team stay with the file." },
      ],
    },
    {
      key: "after",
      label: "After",
      title: "The decision travels",
      steps: [
        { title: "Minutes when the meeting ends", text: "The decision record and the minutes are ready as the last patient is discussed." },
        { title: "Exports in the hospital's name", text: "The board deck and the NCG Virtual Tumour Board template, with the hospital's own logo." },
        { title: "Nothing is forgotten", text: "Follow-ups are tracked and every action stays in the audit log." },
      ],
    },
  ] satisfies Phase[],
};

export const SOURCES = {
  eyebrow: "Trust",
  title: ["Every fact has", "its source."],
  lead: "Vaidyx never shows a value it cannot point to. Each number, date and finding carries the exact line of the report it came from, and one click opens it. A value whose line cannot be found is dropped or marked for review. A clinician's confirmation always beats what the model read.",
  // A synthetic report and the values read from it. The quote index points at the line in `report`.
  report: {
    title: "Histopathology report",
    stamp: "SYNTHETIC",
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
  fields: [
    { label: "Tumour size", value: "2.8 cm", quote: 2, state: "quoted" as const },
    { label: "Grade", value: "2", quote: 3, state: "quoted" as const },
    { label: "ER", value: "Positive, 80 %", quote: 4, state: "quoted" as const },
    { label: "HER2", value: "Equivocal (2+)", quote: 6, state: "review" as const, note: "FISH advised: for the pathologist to confirm" },
  ],
  rules: [
    { icon: Quote, title: "No quote, no value", text: "A value is shown only with the line it came from." },
    { icon: UserRound, title: "The clinician's word wins", text: "A confirmation by a doctor stays, even when the records are read again." },
    { icon: Eye, title: "Points for review", text: "Anything uncertain is marked, never hidden." },
  ],
};

export const ROLES = {
  eyebrow: "For your team",
  title: ["Built for everyone", "at the table."],
  lead: "Each role sees its own work first. Nobody has to learn the whole system to do their part.",
  cards: [
    { icon: Stethoscope, title: "Treating doctor", text: "Your patients, what is left on each, and the question for the board. Sign off from the phone between cases.", points: ["A Needs-me view", "One-tap requests to Pathology and Radiology", "The decision back in the file"] },
    { icon: UserRound, title: "Resident", text: "Build the Case File in minutes, not an afternoon.", points: ["Pull the records by UHID", "The checklist tells you what to chase", "Propose; the consultant signs off"] },
    { icon: FlaskConical, title: "Pathologist and Radiologist", text: "Requests arrive with their context. Answer from the file or open the order in the HIS.", points: ["An inbox of requests", "A direct link to the order", "Your report lands in the file"] },
    { icon: CalendarDays, title: "MDT Coordinator", text: "Agenda, people, room and minutes, in one place.", points: ["An agenda with readiness", "Video meeting and the room screen", "Minutes and exports"] },
    { icon: Users, title: "Outside expert", text: "Join a board with a code and see only what you are shown.", points: ["A code, not an account", "Admitted by the coordinator", "Nothing to install"] },
    { icon: Building2, title: "Department admin and hospital IT", text: "Set up departments and people in an afternoon. Nothing leaves the hospital.", points: ["Roles per department", "An audit log of every action", "Self-hosted on your server"] },
  ],
};

export const SAFETY = {
  eyebrow: "Safety and scope",
  title: ["What Vaidyx will", "never do."],
  statement: "Vaidyx checks, routes, summarises and flags. It never diagnoses, never computes a stage and never advises a treatment. It does not read images. The clinician's confirmation always wins, and every action is in the audit log.",
  principles: [
    { icon: ShieldCheck, title: "Human oversight", text: "Expert-in-the-loop by design. A summary is a draft until a clinician reviews it." },
    { icon: Quote, title: "Source or nothing", text: "Every value and every sentence shown as fact carries a verified quote." },
    { icon: MonitorPlay, title: "Images are for people", text: "PACS images are shown to clinicians. No model reads them." },
    { icon: LockKeyhole, title: "Inside the hospital", text: "Designed to run on the hospital's own server. Records stay where they are." },
    { icon: Landmark, title: "India first", text: "NCG, ICMR and PM-JAY sources before international ones. Indian identifiers, names, units and dates." },
    { icon: Hospital, title: "Audited", text: "Every AI call and every user action is logged, with who and when." },
  ],
};

export interface Member { name: string; role: string; photo: string | null; }
export const TEAM = {
  eyebrow: "Team",
  title: ["The people behind", "Vaidyx."],
  lead: "A small team at TANUH, building Vaidyx with the clinicians who will use it.",
  // Names, roles and photos to be filled in (the owner shares them later). Photos: public/brand/team/<file>.
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
  eyebrow: "A product of TANUH",
  title: ["Built at the AI Centre of", "Excellence in Healthcare."],
  text: "TANUH, Translational AI for Networked Universal Healthcare, is the AI Centre of Excellence in Healthcare at the Indian Institute of Science, Bengaluru, funded by the Ministry of Education, Government of India. Vaidyx is built there, with the clinicians who will use it.",
  links: [
    { label: "tanuh.ai", href: "https://tanuh.ai", text: "The centre, its mission and its work" },
    { label: "dpi.tanuh.ai", href: "https://dpi.tanuh.ai", text: "Open digital public infrastructure for healthcare AI" },
  ],
  place: { icon: MapPin, text: "Indian Institute of Science, Bengaluru" },
};

export const CTA = {
  title: ["Bring Vaidyx to", "your Tumour Board."],
  text: "Vaidyx is being built with hospitals in India. If your Tumour Board would like to try it, write to TANUH.",
  signIn: "Sign in",
  write: "Write to TANUH",
  writeHref: "https://tanuh.ai",
};

export const FOOTER = {
  note: "Every patient name, identifier and value shown on this page is synthetic.",
  scope: "Vaidyx checks, routes, summarises and flags. Never a diagnosis, a stage or a treatment advice.",
  copyright: `© ${new Date().getFullYear()} TANUH, The AI Centre of Excellence in Healthcare.`,
  columns: [
    { title: "Product", links: [{ label: "How it works", to: "#how" }, { label: "Sources", to: "#sources" }, { label: "Safety", to: "#safety" }] },
    { title: "People", links: [{ label: "For your team", to: "#roles" }, { label: "Team", to: "#team" }] },
    { title: "TANUH", links: [{ label: "tanuh.ai", to: "https://tanuh.ai" }, { label: "TANUH DPI", to: "https://dpi.tanuh.ai" }] },
    { title: "Account", links: [{ label: "Sign in", to: "/sign-in" }] },
  ],
};

export type Icon = LucideIcon;
export const ICONS = { Video, Hospital };
