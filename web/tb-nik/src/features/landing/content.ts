// Every word on the public site, in one place, so the wording can be reviewed and changed without touching the layout.
// Register: plain, everyday English; short sentences; no jargon where a common word will do. British spelling.
// Constraints: no accuracy or validation claims; no model names; every patient detail is synthetic.
import type { LucideIcon } from "lucide-react";
import { Activity, Building2, CalendarDays, FileSearch, FlaskConical, FolderInput, Layers, MapPin, PenLine, Stethoscope, UserRound, Users, Workflow } from "lucide-react";

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
  email: "sulake.nikhileswararao@tanuh.ai",
};

export const HERO = {
  eyebrow: "Vaidyx Tumour Board",
  // The second line is set in the serif face.
  title: ["AI Agent for","Tumour Board meetings."],
  lead: "Vaidyx is an AI agentic workflow assisting clinicans in making their patient case ready for the Tumor Board, with inteligent pre-authorization and connectivity to all other doctors.",
  primary: "How it works",
  scroll: "Scroll",
};

export const STRIP = [
  "Follows NCG guides",
  "ICMR cancer lists",
  "Clinican-led AI framework",
  "Fullly offline and secure",
  "Clinically-Validated models",
  "UHID, IP and OP numbers, ABHA",
  "Works with the HIS, RIS, LIS and PACS",
  "Runs inside the hospital",
  "Every value shows its source",
];

export const CHALLENGE = {
  eyebrow: "The problem",
  title: ["Most of the work happens", "before the meeting."],
  lead: "A Tumour Board spends a few minutes on each patient. Getting a patient ready takes hours: reports from several departments, scans on another system, and slides that are out of date before the meeting starts.",
  points: [
    { icon: Layers, title: "Records in many places", text: "Patient records sit in the HIS, the lab system, the PACS and paper files. No one sees the whole picture in one place." },
    { icon: FileSearch, title: "Gaps found too late", text: "A missing report is noticed in the meeting, and the patient waits for the next Board." },
    { icon: Activity, title: "Decisions that get lost", text: "The decision is written in a register. The ward, the insurer and the next clinic each ask for it again." },
  ],
};

/* The problem, as the owner set it out (20 Oct): three items, the observed context, and the national figures with their source. */
export const PROBLEM = {
  items: [
    { n: "01", icon: FolderInput, title: "Manual Case File assembly", text: "Mandatory reports and results may need to be gathered from several systems before the Case File is ready for Tumour Board discussion." },
    { n: "02", icon: PenLine, title: "Subjective summary preparation", text: "A concise narrative summary may need to be written from the available reports so that key findings, clinical context, complications and points for discussion are ready for the Board." },
    { n: "03", icon: Workflow, title: "Coordination across several departments", text: "Radiology, pathology, PET / staging, laboratory, clinical and other inputs may need to be brought together in the required sequence and format, each on its own timeline." },
  ],
  observed: {
    label: "Observed workflow context",
    figure: "about a week",
    text: "Preparation may extend to around a week when required records are still being assembled.",
    note: "Observed in this team's setting, not a general Tumour Board figure.",
  },
  national: {
    label: "National context, India",
    stats: [
      { value: 88.3, text: "still rely on physical records, fully or in part" },
      { value: 53.3, text: "do not report radiologist participation in the Tumour Board" },
      { value: 48.2, text: "have no system to monitor recommended treatments" },
    ],
    source: {
      short: "Sarveswaran et al., 2026",
      text: "Sarveswaran et al., ecancermedicalscience 2026;20:2090. Cross-sectional survey of 172 hospitals registered under the National Cancer Registry Programme, India.",
      href: "https://doi.org/10.3332/ecancer.2026.2090",
    },
  },
};

export interface Phase {
  key: "before" | "during" | "after";
  label: string;
  title: string;
  steps: { title: string; text: string }[];
}

export const HOW = {
  eyebrow: "How it works",
  title: ["Before, during and after", "the meeting."],
  lead: "Vaidyx stays with the patient through the whole Tumour Board, from preparation to follow-up.",
  phases: [
    {
      key: "before",
      label: "Before",
      title: "Getting the patient ready",
      steps: [
        { title: "Start with the UHID", text: "Vaidyx collects the patient's reports from the HIS, the lab and radiology systems, and lists the scans on the PACS." },
        { title: "Every value with its source", text: "Each value is kept together with the line of the report it came from. A value without a source is dropped or marked for review." },
        { title: "A checklist for the cancer", text: "The checklist shows which reports the Board needs. Missing items are requested from Pathology or Radiology from inside the Case File." },
        { title: "Ready for the Board", text: "Specialty briefs are prepared for each department. The treating doctor writes the question for the Board and marks the file as ready." },
      ],
    },
    {
      key: "during",
      label: "During",
      title: "The meeting",
      steps: [
        { title: "The agenda", text: "The MDT Coordinator sets the agenda. Each Case File is ready, or shows what is still missing." },
        { title: "In the room or online", text: "Members join in person or by video. The room display shows the case summary and the scans from the PACS." },
        { title: "The decision, recorded", text: "The decision is recorded during the discussion, with who was present and what was asked." },
      ],
    },
    {
      key: "after",
      label: "After",
      title: "After the meeting",
      steps: [
        { title: "Minutes", text: "The decision record and the minutes are ready when the meeting ends." },
        { title: "Exports", text: "The Board presentation and the NCG Virtual Tumour Board template are exported with the hospital's name and logo." },
        { title: "Follow-up and audit", text: "Follow-up actions are tracked, and every action is kept in the audit log." },
      ],
    },
  ] satisfies Phase[],
};

export const SOURCES = {
  eyebrow: "Traceability",
  title: ["Every value shows", "where it came from."],
  lead: "Vaidyx shows a value only when it can point to the line of the report it came from. Ask the Case File a question, and each sentence of the answer links back to its source.",
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
  ask: {
    title: "Ask the Case File",
    placeholder: "Ask a question about this Case File",
    who: "Dr L. Rao, Breast Surgery",
    question: "What are the hormone receptor and HER2 results?",
    reading: "Finding the lines that answer this",
    answer: [
      { text: "ER is positive in 80 % of tumour cells, with strong intensity.", quote: 4 },
      { text: "PR is positive in 60 % of tumour cells, with moderate intensity.", quote: 5 },
      { text: "HER2 is equivocal (2+). FISH has been advised.", quote: 6, review: true },
    ],
    note: "Each sentence links to a line of the report. The HER2 result stays marked for review until the FISH result arrives.",
    labels: { source: "source", review: "for review" },
  },
};

export const ROLES = {
  eyebrow: "Roles",
  title: ["Made for everyone", "on the Board."],
  lead: "Each person sees their own work first. Choose a seat at the table.",
  centre: "Case File",
  cards: [
    { key: "doctor", icon: Stethoscope, title: "Treating doctor", short: "Doctor", text: "Your patients, what is still missing, and the question for the Board. Approve from your phone between patients.", points: ["A view of what needs you", "One-tap requests to Pathology and Radiology", "The decision back in the Case File"] },
    { key: "resident", icon: UserRound, title: "Resident", short: "Resident", text: "Build a Case File in minutes, not an afternoon.", points: ["Pull the records by UHID", "The checklist shows what to chase", "Propose; the consultant signs off"] },
    { key: "lab", icon: FlaskConical, title: "Pathologist and Radiologist", short: "Pathology", text: "Requests come with the clinical context. Answer from the Case File or open the order in the HIS.", points: ["An inbox of requests", "A direct link to the order", "Your report lands in the Case File"] },
    { key: "coordinator", icon: CalendarDays, title: "MDT Coordinator", short: "Coordinator", text: "Agenda, people, room and minutes in one place.", points: ["An agenda with readiness", "Video meeting and room display", "Minutes and exports"] },
    { key: "expert", icon: Users, title: "External expert", short: "Expert", text: "Join a Board with a code and see only the cases shown to you.", points: ["A code, no account", "Admitted by the coordinator", "Nothing to install"] },
    { key: "it", icon: Building2, title: "Hospital IT and department admins", short: "Admin", text: "Set up departments and people in an afternoon. Patient data stays in the hospital.", points: ["Roles by department", "An audit log of every action", "Runs on your own server"] },
  ],
};

export const SAFETY = {
  eyebrow: "Safety",
  title: ["Safe", "by design."],
  lead: "Vaidyx helps the Board prepare and keep records. Doctors make the decisions.",
  principles: [
    { key: "people", title: "People decide", text: "A summary is a draft until a doctor has reviewed it." },
    { key: "sources", title: "Sources first", text: "Every value and every statement comes with a quote from the record." },
    { key: "scans", title: "Scans are for doctors", text: "PACS images are shown to doctors. No model reads them." },
    { key: "onsite", title: "Inside the hospital", text: "Runs on the hospital's own server. Patient records stay on site." },
    { key: "india", title: "India first", text: "NCG, ICMR and PM-JAY come before international sources. Indian IDs, names, units and dates." },
    { key: "audit", title: "Everything is logged", text: "Every AI step and every user action is recorded, with who and when." },
  ],
};

export const CTA = {
  title: ["Bring Vaidyx to", "your Tumour Board."],
  text: "Vaidyx is being built with hospitals in India. If your Board would like to try it, send us an enquiry.",
  signIn: "Sign in",
  contact: "Send an enquiry",
  contactTo: "/contact",
};

export const FOOTER = {
  note: "All patient names, identifiers and values shown on this site are synthetic.",
  scope: "Vaidyx checks, routes, summarises and flags. Doctors make the decisions.",
  copyright: `© ${new Date().getFullYear()} TANUH, The AI Centre of Excellence in Healthcare.`,
  columns: [
    { title: "Product", links: [{ label: "How it works", to: "/#how" }, { label: "Traceability", to: "/#sources" }, { label: "Roles", to: "/#roles" }, { label: "Safety", to: "/#safety" }] },
    { title: "About", links: [{ label: "Our team", to: "/about" }, { label: "TANUH", to: "/about#tanuh" }, { label: "Contact", to: "/contact" }] },
    { title: "Resources", links: [{ label: "Documentation", to: "/docs" }, { label: "Visit TANUH", to: "https://tanuh.ai" }] },
    { title: "Account", links: [{ label: "Sign in", to: "/sign-in" }] },
  ],
};

/* About */
export const ABOUT = {
  eyebrow: "About",
  title: ["Meet", "our team."],
  lead: "Vaidyx is built at TANUH, the AI Centre of Excellence in Healthcare at IISc Bengaluru, together with the doctors who will use it.",
};

export interface Member { name: string; photo: string | null }
export const TEAM = {
  // Names and photographs to be supplied by the owner. Photographs: public/brand/team/<file>.
  members: [
    { name: "Team member", photo: null },
    { name: "Team member", photo: null },
    { name: "Team member", photo: null },
    { name: "Team member", photo: null },
    { name: "Team member", photo: null },
    { name: "Team member", photo: null },
  ] satisfies Member[],
};

export const TANUH = {
  eyebrow: "TANUH",
  title: ["The AI Centre of Excellence", "in Healthcare."],
  text: "TANUH, Translational AI for Networked Universal Healthcare, is the AI Centre of Excellence in Healthcare at the Indian Institute of Science, Bengaluru, funded by the Ministry of Education, Government of India. Vaidyx is built at the Centre with the doctors who will use it.",
  visit: "Visit TANUH",
  href: "https://tanuh.ai",
  place: { icon: MapPin, text: "Indian Institute of Science, Bengaluru" },
};

/* Placeholder pages */
export const DOCS = {
  eyebrow: "Documentation",
  title: ["Documentation", "coming soon."],
  text: "Installation, hospital system integration, roles and the audit log will be documented here.",
};

export const CONTACT = {
  eyebrow: "Contact",
  title: ["Send us", "an enquiry."],
  lead: "Tell us about your hospital and your Tumour Board. We reply by email.",
  form: {
    name: "Your name",
    email: "Your email",
    hospital: "Hospital or institution",
    message: "Message",
    submit: "Send enquiry",
    sending: "Sending",
    sent: "Thank you. Your enquiry has been sent.",
    received: "Thank you. Your enquiry has been received.",
    failed: "The enquiry could not be sent. Please write to us directly.",
    invalid: "Please fill in your name, a valid email address and a message.",
    notice: "Email sending from this form is not built yet. To be sure we see your message, write to us directly at",
  },
  direct: "To reach us directly, write to",
  subject: "[Vaidyx] Website enquiry",
};
