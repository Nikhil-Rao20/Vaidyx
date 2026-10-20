// Every word on the public site, in one place, so the wording can be reviewed and changed without touching the layout.
// Register: plain, everyday English; short sentences; no jargon where a common word will do. British spelling.
// Constraints: no accuracy or validation claims; no model names; every patient detail is synthetic.
import type { LucideIcon } from "lucide-react";
import { Activity, FileSearch, FileStack, Layers, MapPin, Network, NotebookPen } from "lucide-react";

export type Icon = LucideIcon;

/** The pages of the top bar. Product is the landing page and the default. */
export const PAGES = [
  { to: "/", label: "Product" },
  { to: "/research", label: "Research" },
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
    { n: "01", icon: FileStack, title: "Manual Case File assembly", text: "Mandatory reports and results may need to be gathered from several systems before the Case File is ready for Tumour Board discussion." },
    { n: "02", icon: NotebookPen, title: "Subjective summary preparation", text: "A concise narrative summary may need to be written from the available reports so that key findings, clinical context, complications and points for discussion are ready for the Board." },
    { n: "03", icon: Network, title: "Coordination across several departments", text: "Radiology, pathology, PET / staging, laboratory, clinical and other inputs may need to be brought together in the required sequence and format, each on its own timeline." },
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
      { value: 53.3, text: "have no radiologist taking part in the Board" },
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
        { title: "Reports and scans, in the meeting", text: "Any report or scan in the Case File opens inside the meeting, beside the slide on the room display, without leaving the room." },
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

/* The journey of one patient, step by step (the interactive flow that replaced the roles section, 20 Oct). Each step lights
   nodes and lines of the diagram (ids in sections/flow/diagram.tsx), names who acts, and may show a small preview. */
export interface FlowStep {
  id: string;
  title: string;
  body: string;
  who: string;
  chip?: string;
  nodes: string[];
  paths: string[];
  preview?: "casefile" | "request" | "brief" | "slide" | "room" | "after";
}

export const FLOW = {
  eyebrow: "Workflow",
  title: ["The Tumour Board workflow,", "from records to follow-up."],
  lead: "Who does what, and when: a Case File moves from the hospital's records to the Board's decision and the care that follows, and loops back when the Board needs more.",
  frame: "Inside the hospital · nothing leaves",
  lanes: { systems: "Hospital systems", dept: "Treating department", vaidyx: "Vaidyx", support: "Pathology · Radiology", board: "Coordinator · Board" },
  phases: { before: "Before the Board", meeting: "The meeting", after: "After" },
  labels: { step: "Step", of: "of", who: "Who acts", next: "Next step", restart: "Start over", auto: "Playing · click to take over" },
  steps: [
    { id: "uhid", title: "A Case File is opened by UHID", body: "The records arrive from the HIS, the lab and radiology systems and the PACS, each value stored with its source line.", who: "Resident · Vaidyx", chip: "Every value quoted", nodes: ["systems", "opened", "records"], paths: ["opened-records", "systems-records"], preview: "casefile" },
    { id: "quote", title: "Pre-Authorization against the protocol", body: "The Pre-Authorization check for this cancer, built on NCG guidance, lists what the Board needs and which department holds it.", who: "Vaidyx", nodes: ["records", "checklist"], paths: ["records-checklist"], preview: "casefile" },
    { id: "request", title: "Missing reports requested and returned", body: "A request reaches the Pathology or Radiology desk in the HIS; the filed report returns into the Case File and the item closes.", who: "Pathologist · Radiologist", chip: "The loop closes in the file", nodes: ["checklist", "request", "report", "records"], paths: ["checklist-request", "request-report", "report-records"], preview: "request" },
    { id: "briefs", title: "Specialty briefs prepared", body: "Six specialty helpers prepare briefs from the records, every sentence with its quote.", who: "Vaidyx", nodes: ["request", "briefs"], paths: ["request-briefs"], preview: "brief" },
    { id: "question", title: "The question for the Board", body: "The treating doctor reads the briefs, writes the question and marks the Case File ready.", who: "Treating doctor", chip: "Doctors decide", nodes: ["briefs", "question"], paths: ["briefs-question"] },
    { id: "meeting", title: "The agenda and the meeting", body: "The MDT Coordinator lists the ready Case Files; in the room the display shows the slide, and any report or scan opens beside it.", who: "MDT Coordinator · the Board", nodes: ["question", "agenda", "meeting"], paths: ["question-agenda", "agenda-meeting"], preview: "room" },
    { id: "decision", title: "The decision, or a deferral", body: "The Board's decision is recorded during the discussion; when more information is needed, the Case File goes back to the treating doctor.", who: "The Board", chip: "Doctors decide", nodes: ["meeting", "decision", "question"], paths: ["meeting-decision", "decision-question"], preview: "slide" },
    { id: "after", title: "Minutes, deck and forms from one record", body: "Minutes, the board deck, the NCG form and the PM-JAY pre-authorization papers come from the same record, and every action is logged.", who: "MDT Coordinator", chip: "Nothing leaves the hospital", nodes: ["decision", "outputs"], paths: ["decision-outputs"], preview: "after" },
    { id: "followup", title: "Follow-up, and back to the Board when needed", body: "The treating department tracks the follow-up; at progression the same Case File is re-discussed.", who: "Treating department", nodes: ["outputs", "followup", "opened"], paths: ["outputs-followup", "followup-opened"] },
  ] satisfies FlowStep[],
};

export const SAFETY = {
  eyebrow: "Design principles",
  title: ["Designed for clinical safety", "and hospital control."],
  lead: "Vaidyx supports the Tumour Board without taking decisions away from doctors. Six principles guide how it is built and how it runs in the hospital.",
  principles: [
    { key: "people", title: "People decide", text: "A summary is a draft until a doctor has reviewed it." },
    { key: "sources", title: "Sources first", text: "Every value and every statement comes with a quote from the record." },
    { key: "scans", title: "One screen in the meeting", text: "The slide, the report and the scan are presented from the Case File on the room display, so the whole Board looks at the same material. Doctors read the images; no model does." },
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
    { title: "Product", links: [{ label: "How it works", to: "/#how" }, { label: "Traceability", to: "/#sources" }, { label: "Workflow", to: "/#journey" }, { label: "Design principles", to: "/#safety" }] },
    { title: "About", links: [{ label: "Our team", to: "/about" }, { label: "TANUH", to: "/about#tanuh" }, { label: "Contact", to: "/contact" }] },
    { title: "Resources", links: [{ label: "Research", to: "/research" }, { label: "Documentation", to: "/docs" }, { label: "Visit TANUH", to: "https://tanuh.ai" }] },
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
  // The six, in alphabetical order of the name as shown (the owner, 20 Oct). Photographs in public/brand/team (originals in
  // web/tb-nik/brand-src/team).
  members: [
    { name: "Bharath Tangella", photo: "/static/tb-nik/brand/team/bharath-tangella.jpg" },
    { name: "Minmini Selvam", photo: "/static/tb-nik/brand/team/minmini-selvam.jpg" },
    { name: "Nikhileswara Rao Sulake", photo: "/static/tb-nik/brand/team/nikhileswara-rao-sulake.jpg" },
    { name: "Phaneendra K Yalavarthy", photo: "/static/tb-nik/brand/team/phaneendra-k-yalavarthy.jpg" },
    { name: "Sai Manikanta Eswar Machara", photo: "/static/tb-nik/brand/team/sai-manikanta-eswar-machara.jpg" },
    { name: "Usha Adiga", photo: "/static/tb-nik/brand/team/usha-adiga.jpg" },
  ] satisfies Member[],
};

export const TANUH = {
  eyebrow: "TANUH",
  title: "The AI Centre of Excellence in Healthcare",
  // The centre's own words (tanuh.ai), as the owner pasted them.
  summary: [
    "TANUH (Translational AI for Networked Universal Healthcare) is an AI Centre of Excellence under the Ministry of Education, Government of India, hosted at the Indian Institute of Science, Bengaluru.",
    "We develop and deploy AI-driven diagnostics and decision-support tools for early detection and management of high-burden non-communicable diseases (NCDs) across India.",
    "TANUH is a non-profit organization registered under Section 8 of the Companies Act, 2013, and holds valid registrations under Sections 12A and 80G of the Income-tax Act, 1961, as well as CSR registration with the Ministry of Corporate Affairs.",
  ],
  sections: [
    { title: "Our Mission", text: "To advance the early detection, prevention, and management of non-communicable diseases through scalable, AI-driven innovation. The centre is committed to empowering healthcare providers and systems with data-centric decision support that strengthens universal healthcare delivery, reduces disparities, and ensures equitable, accessible, and high-quality care for all populations." },
    { title: "Our Vision", text: "To build a reliable and trustworthy digital health ecosystem powered by scalable and culturally attuned AI solutions. The centre goal is to transform clinical and frontline care to make healthcare timely, accessible, and effective for every citizen of India." },
  ],
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

export const RESEARCH = {
  eyebrow: "Research",
  title: ["Thirteen open models,", "measured like for like."],
  lead: "A full-precision benchmark of open medical and general language models on 111,222 public examination questions, and the grounded evaluations that decide what Vaidyx-TB ships. Every number below is in the paper; the PDF is the citable version.",
  paper: {
    title: "Full-Precision Benchmarking of Open Medical and General Language Models for a Tumour Board Assistant in India",
    kind: "Technical report",
    date: "October 2026",
    authors: ["Bharath Tangella", "Minmini Selvam", "Nikhileswara Rao Sulake", "Phaneendra K Yalavarthy", "Sai Manikanta Eswar Machara", "Usha Adiga"],
    corresponding: "Phaneendra K Yalavarthy",
    affiliation: "TANUH, the AI Centre of Excellence in Healthcare, Indian Institute of Science, Bengaluru",
    download: "Download the paper (PDF)",
    file: "/static/tb-nik/research/vaidyx-benchmark-2026.pdf",
    facts: [["13", "models"], ["11", "benchmarks"], ["111,222", "questions"], ["1.0 million", "graded answers"]],
  },
  contents: "On this page",
  swipe: "Swipe the table sideways to see every column.",
  abstract: {
    title: "Abstract",
    text: [
      "Vaidyx-TB is an assistant for hospital Tumour Boards in India. It checks, routes and summarises the records of a Case File and keeps every fact it shows tied to a verbatim quote from a source document; it does not interpret images, stage disease or advise treatment. Choosing the open-weight models behind it needs scores that are comparable with the published model cards and that reflect the exact weights the system runs.",
      "We benchmarked 13 open models (11 medical fine-tunes and 2 general models, 4B to 32B parameters, from developers in the USA, China and the UAE) on 11 public benchmarks, 5 text (9,995 questions) and 6 image (101,227 questions), with the published bf16 weights on one NVIDIA H200, greedy decoding, full test splits and no quantisation, under two protocols: about one million graded answers. The harness reproduces published scores: MedGemma-27B-it lands within 2.5 points of its model card on all five text sets, and Lingshu-32B scores 82.4 % against a published 83.4 % on OmniMedVQA. Gemma-4-31B-it, a general model, is the strongest text model at 76.6 % overall and 55.1 % on MedXpertQA, where every medical model stays below 41 %. HuatuoGPT-3-27B is the best medical model (71.2 %) and leads OmniMedVQA (82.9 %). Qwen3.5-4B matches MedGemma-27B-it on text at a seventh of the size, and Lingshu-32B leads radiology and pathology VQA. Full precision removes most of the gap seen in an earlier 4-bit run.",
      "We then report the grounded evaluations that decide what Vaidyx-TB ships: a reader and extractor bake-off on synthetic Case Files, 33 answerability probes with no fabrication from any of three candidate reasoners, 166 values extracted from 30 real TCGA pathology reports with none ungrounded, report-status detection measured on 9,523 real reports, a summary omission check, and an independent OCR number check. Every answer is saved per question, so every number here can be re-scored.",
    ],
  },
  why: {
    title: "Why this benchmark",
    text: [
      "A Tumour Board decides the treatment plan of a cancer patient from the records of several departments. In India most of that preparation is manual: a 2026 survey of Indian cancer centres reports that 88.3 % keep Board records on paper or in mixed form, that 53.3 % have no radiologist taking part in the Board, and that 48.2 % have no system to monitor whether the recommended treatment was given.",
      "The system runs open-weight models on a hospital's own server. Two questions decide which models: how much medical knowledge a model has, measured on public examinations, and how reliably it stays grounded in the documents it is given, which no public benchmark measures. The benchmark answers the first question; Vaidyx's own evaluations answer the second.",
      "The benchmark differs from the usual model-card table in four ways. Every model runs with its exact published bf16 weights, because the deployed system also runs bf16. Every dataset runs in full. Every model runs under the same two protocols, step-by-step (how model cards report) and direct answer (knowledge without reasoning, and format discipline). And every answer is saved per question, so every score can be re-checked from the saved replies.",
    ],
  },
  models: {
    title: "The models",
    text: [
      "Each model carries two labels that appear in every table here and in the Vaidyx-TB interface: the developer's country, and whether the model is a medical fine-tune or a general model that is not medically validated. Seven models read images; six are text only. All weights are the published bf16 checkpoints from Hugging Face. HuatuoGPT-3, Baichuan-M2 and Qwen3.5 have a thinking mode; it was switched off so that every model sees the same visible step-by-step prompt and the same token budget.",
    ],
    caption: "The 13 models. Medical = fine-tuned for medicine; Non-medical = a general model, not medically validated. Earlier report = part of the 4-bit run of September 2026.",
  },
  data: {
    title: "The benchmarks",
    text: [
      "Five text sets (9,995 questions) and six image sets (101,227 questions), all on their full test split. MedQA, MedMCQA, PubMedQA and MMLU-Med are the four sets used on the MedGemma, Med42 and OpenBioLLM model cards. MedMCQA, drawn from the Indian postgraduate entrance examinations, is the most India-relevant set and the largest, so it carries the most weight in the overall text score, which is the accuracy over all 9,995 questions together.",
    ],
    caption: "Data cards of the 11 benchmarks: five text sets (9,995 questions), then six image sets (101,227 questions). Chance = the score of random guessing.",
    textLabel: "Text",
    imageLabel: "Image",
    fields: { tests: "What it tests", n: "Questions", fmt: "Format", chance: "Chance", scoring: "Scoring" },
  },
  protocol: {
    title: "Protocol",
    items: [
      ["Hardware and engine", "One NVIDIA H200 NVL (141 GB), vLLM 0.30, PyTorch 2.13, CUDA 13. One model on the GPU at a time, prefix caching on. The GPU ran power-capped at 300 W; the cap slows runs but changes no answer."],
      ["Weights and decoding", "Exact published bf16 weights; no quantisation anywhere. Greedy decoding (temperature 0), seed 0. Each model's own chat template; thinking mode off where a switch exists."],
      ["Step-by-step (CoT)", "The model is asked to think through the question step by step and finish with a final line \"Answer: X\"; up to 2,048 new tokens. This is how model cards report their results, so these are the scores to compare with published numbers."],
      ["Direct", "The model must respond with only the letter of the correct option (yes/no, or a short phrase for open image questions); at most 32 new tokens. It measures knowledge without reasoning and whether the model follows a strict output format."],
      ["Strict and first-token scores", "The strict score counts an answer only if a valid option can be read from the reply. The first-token score is format-free: the option letter with the highest probability among the first generated token's top-20 candidates. Parsed % is the share of replies from which an answer could be read; below about 95 % a score is partly a formatting result."],
      ["Open answers and errors", "For VQA-RAD, SLAKE and PathVQA the score is split into yes/no and open short answers; open answers are scored by exact match after normalising, which is strict for every model equally. Errors are questions the serving engine refused (an image too large for the context window, or more than four images); they count as wrong."],
      ["Published numbers", "Opened directly from the official model cards and papers on 9 October 2026. Where a card uses a different scoring rule, the rule is stated next to the number."],
    ],
  },
  text: {
    title: "Text results",
    cot: {
      title: "Step-by-step accuracy",
      text: "Gemma-4-31B-it, a general model, leads every column except PubMedQA: MedQA 93.2, MedMCQA 78.5, MMLU-Med 94.6, and 55.1 on MedXpertQA, where every medical model stays below 41. HuatuoGPT-3-27B is the best medical model at 71.2 % overall and has the highest PubMedQA score. Qwen3.5-4B, a 4B general model, reaches 62.4 %, ahead of MedGemma-27B-it (61.7 %). MedMCQA is the hardest of the four standard sets: the seven strongest models score 9 to 16 points lower on it than on MedQA.",
      caption: "Step-by-step (CoT) accuracy in %, ranked by overall accuracy over all 9,995 text questions. Bold = best in column. Min parsed = the lowest parse rate across the five sets.",
    },
    direct: {
      title: "Direct answers and the gain from reasoning",
      text: "HuatuoGPT-3-27B is the best direct-answer model (66.0 %), which matters for a system that asks short, structured questions. Reasoning helps the general models most: Gemma-4-31B-it gains 17.4 points overall and 44.1 points on MedXpertQA. Two Google models cannot follow the letter-only instruction: MedGemma-27B-text-it scores 8.0 on MedQA under the direct protocol with 25 % of replies parseable, against 80.2 with reasoning; the first-token column shows what they knew. Baichuan-M2's direct replies all began with a stray thinking tag; the saved replies were re-scored with the tag removed, nothing was regenerated.",
      caption: "Direct-answer accuracy in % (at most 32 new tokens), ranked by overall. First-token = the format-free score. Parsed = the lowest parse rate across the five sets. CoT gain = overall step-by-step minus overall direct, in points. † re-scored from the saved replies.",
    },
    published: {
      title: "Comparison with published scores",
      text: "MedGemma-27B-it lands within 2.5 points of its card on all five sets, MedGemma-4B-it slightly above its card, and Lingshu-32B within 3.4 points on every set: the harness is like for like with a generated-answer protocol. MedGemma-1.5-4B is 10 points below its card, mainly because 29 % of its MedQA replies never reach a final answer line within 2,048 tokens. Med42, JSL-MedLlama and OpenBioLLM are scored on their cards by answer likelihood, not by generated answers, which usually gives a few points more. No published scores on these sets exist for Gemma-4-31B, Qwen3.5-4B, HuatuoGPT-3-27B, Baichuan-M2-32B or MedLlama2-7B.",
      caption: "This run (bf16, step-by-step) against the published scores, in %. Difference = this run minus published, in points; the mean is over the sets the source reports.",
      note: "The Med42, JSL and Saama cards score by answer likelihood (lm-evaluation-harness), not by generated answers. MMLU on the Med42 card covers the clinical topics; on the JSL and Saama cards it is the mean of the six medical subjects.",
      rows: ["This run (bf16, CoT)", "Published", "Difference"],
    },
    q4: {
      title: "Full precision against the earlier 4-bit run",
      text: "Seven of these models were run in September 2026 as Q4_K_M 4-bit weights on a GB10 workstation under a direct letter prompt. With the same weights at full precision and allowed to reason, MedGemma-27B-it rises from 69.8 to 83.1 on MedQA, and the older 7B to 8B fine-tunes gain between 10.6 and 30.1 points on average over the five sets. Under the direct protocol the gains are smaller, so most of the earlier gap was the combination of 4-bit compression and a short-answer format, not the models themselves.",
      caption: "The earlier 4-bit run against this run, in %. Mean gain = the average of the five scores minus the Q4 average, in points.",
      rows: ["Q4_K_M, GB10 (Sept. 2026)", "bf16, H200, direct", "bf16, H200, CoT"],
    },
  },
  image: {
    title: "Image results",
    all: {
      title: "All datasets",
      text: "Lingshu-32B is clearly the best model on the radiology and pathology sets: SLAKE 84.9, VQA-RAD 67.4 and PathVQA 59.9, where the next best SLAKE score is 60.3. HuatuoGPT-3-27B leads OmniMedVQA (82.9). Gemma-4-31B-it leads the two expert multiple-choice sets once it is allowed to reason: PMC-VQA 66.2 and MedXpertQA-MM 55.5. Two OmniMedVQA strict scores are formatting failures, not knowledge failures: MedGemma-1.5-4B (19.1) and Qwen3.5-4B (27.6) describe the image before answering and are cut at 32 tokens; their first-token scores are 68.2 and 74.2.",
      caption: "Image question accuracy in %. The first five score columns use the direct protocol; the two CoT columns use the step-by-step protocol on the two multiple-choice sets. Sorted by OmniMedVQA first-token score.",
    },
    split: {
      title: "Closed and open answers",
      text: "On yes/no questions most models sit between 70 and 90 %; on open answers, scored by exact match, scores fall to between 1 and 46 %, and on PathVQA, whose open answers are long medical phrases, to single digits for all but Lingshu. Lingshu-32B was trained on the training splits of these three datasets, which helps its open-answer wording. A correct but differently worded answer scores zero under exact match, so open scores understate every model's ability equally.",
      caption: "Radiology and pathology VQA split into yes/no and open short-answer questions, in % (direct protocol, exact match for open answers).",
    },
    omni: {
      title: "OmniMedVQA in detail",
      text: "Modality recognition is nearly solved by every model (82 to 99 %); anatomy identification separates the models most (48 to 84 %); lesion grading is the hardest type for most. The errors column counts the questions the engine refused: very large dermoscopy and chest X-ray images exceed the 12,288-token context of the Qwen-family image encoder used by HuatuoGPT-3, Lingshu and Qwen3.5. Excluding them would add about one point to those three models; they are kept as wrong for fairness.",
      caption: "OmniMedVQA (88,996 questions) in detail, in %. Question-type columns use the first-token score. Errors = questions the engine refused, counted as wrong.",
    },
    published: {
      title: "Comparison with published image scores",
      text: "Where the comparison is like for like, the harness agrees: Lingshu-32B scores 82.4 against a published 83.4 on OmniMedVQA and 31.5 against 30.9 on MedXpertQA-MM; MedGemma-4B-it 70.4 against 69.8 on OmniMedVQA. Where the published number uses a different rule the gap is not a quality gap: Lingshu's paper has GPT-4.1 judge the open answers, and the Gemma 4 and Qwen cards use their thinking mode, which we switched off. No published image scores exist for HuatuoGPT-3-27B.",
      caption: "This run against the published image scores, in %. Diff. = this run minus published, in points. Rows marked No are listed for completeness: the published number uses a different scoring rule.",
    },
  },
  throughput: {
    title: "Throughput",
    text: "Under the direct protocol every model finishes the 9,995 text questions in 2 to 11 minutes on the power-capped H200 with vLLM batching. The step-by-step protocol costs 5 to 25 times more, in proportion to how much each model writes: MedGemma-27B-text-it writes 1,342 tokens per question on average and takes 2.6 hours; Lingshu-32B writes 271 and takes 31 minutes. These are batched evaluation timings, not the interactive latency of the deployed system.",
    caption: "Load and run time over the five text sets (9,995 questions) and mean generated tokens per question, on one H200 at 300 W.",
  },
  grounded: {
    title: "Grounded evaluations for the Tumour Board",
    intro: "Examinations measure knowledge. Vaidyx-TB needs something else: a reader that transcribes a scanned page without inventing a number, an extractor that fills the Board's fields only with values it can quote, a reasoner that answers a question from the Case File or says that the file does not contain the answer, and a pipeline that tells a draft report from a final one. These are measured on a synthetic corpus of Case Files with an answer key (no real patient data) and, where real text is needed, on public de-identified pathology reports from The Cancer Genome Atlas (TCGA). All of them run through the same grounding layer as the product: a value or sentence is kept only when its verbatim quote is found in the source document.",
    bakeoff: {
      title: "Reader and extractor bake-off",
      text: "The corpus has three Case Files and 31 documents (PDF text layers, five scanned pages and one text file) with an answer key. The reader transcribes the five scans and is scored by word recall and invented numbers; the extractor classifies the document type and fills 49 fields and is scored on types, fields and fabrications (values with no quote). Qwen3.5-4B is the most accurate and by far the fastest, at 9 GB of weights. It is Vaidyx-TB's reader and extractor, labelled Chinese and non-medical throughout the product.",
      caption: "Reader and extractor bake-off on the synthetic corpus (3 Case Files, 31 documents, 5 scans). Fabricated = extracted values with no verbatim quote. Times on the H200 at 300 W.",
    },
    answerability: {
      title: "Answerability of questions to the Case File",
      text: "Thirty-three probes cover answerable questions, absent values (fabrication traps, where the right answer is that the file does not say) and out-of-scope requests (a treatment recommendation, which must be declined). Gemma-4-31B-it passes all 33 and is the fastest, so it is the reasoner, labelled non-medical everywhere in the product. All three produced zero fabrications, which is the grounding layer's doing rather than the models'. The same probes are re-run at every release.",
      caption: "Ask-the-Case-File answerability, 33 probes. Latency is the mean per answer on the H200 at 300 W; Gemma's figure is after the parallel scope check.",
    },
    tcga: {
      title: "Real pathology reports",
      text: "Thirty pathology reports from TCGA (OCR text of the public de-identified PDFs) were processed with the shipped reader and extractor and compared with the TCGA clinical ground truth. Every disagreement is a metric artefact rather than a wrong reading: the report says \"95 % nuclear staining with moderate intensity\" where the ground truth says ER positive, or states a stage group where the ground truth gives a pT.",
      caption: "Thirty real TCGA pathology reports through the shipped pipeline: extracted values, grounding and agreement with the clinical ground truth.",
      labels: { reports: "Reports", claims: "Extracted values", ungrounded: "Ungrounded", seconds: "Run time" },
    },
    status: {
      title: "Report status on 9,523 real reports",
      text: "Whether a report is final decides whether a pre-authorisation requirement is met. The first status detector was tuned on the synthetic corpus, whose reports carry a \"Report status:\" line. Measured on 9,523 real TCGA pathology reports, 61 % carry no explicit status or signature evidence at all, because de-identification removes signatures; a hard rule would have stalled most real Case Files. The shipped policy follows the FHIR DiagnosticReport status vocabulary: an explicit negative never counts; an explicit positive counts as final; no marker at all turns the requirement into \"confirm final version\", neither blocked nor passed, which a clinician can attest with one audited click.",
      caption: "Status evidence found in 9,523 real TCGA pathology reports (a report can carry more than one marker).",
    },
    summary: {
      title: "Summary omission",
      text: "After full processing of a synthetic Case File, the Board summary and the verified primary-fields table are checked against the answer key: 47 of 48 answer-key fields appear in the verified fields or in a cited summary sentence. The one miss is a negative finding in a discharge summary (\"IV antibiotics were not required\") that the Board summary did not restate. The check is repeated at every release.",
    },
    ocr: {
      title: "Scanned pages: two reads and an independent OCR engine",
      text: [
        "Generative readers silently \"correct\" digits. Vaidyx-TB therefore reads every scanned page twice (at full resolution and at a 70 % downscale), aligns the two reads line by line and marks any number the reads disagree on; a value quoted from such a line needs review. Both reads come from the same model, so a digit it corrects the same way twice would pass. An independent classical OCR engine was added as a third read of the numbers only. Tesseract 5.5.3 was integrated: it runs with no Python package in the application, one thread per page, in parallel with the two model reads, and it never changes the transcription.",
        "The check was tuned to be quiet. The two-read rule applied as is raises 54 false alarms on these pages (lost decimal points, cut leading digits, list markers, letters read as digits). Comparing digits only, requiring the engine to read another number with the same count of digits, and keeping a flag only when a second engine read at 1.5x scale doubts the same number brings the false alarms to zero while still catching 834 of 839 substituted digits. The corpus is synthetic; real scans with faint stamps and handwriting will give the engine more misses, and a missed number never raises a flag, so the check gets quieter, not noisier.",
      ],
      captionEngines: "Independent OCR engines on 111 synthetic scanned pages with an exact reference text, CPU only. Recall = reference numbers found on the aligned engine line; precision = engine numbers found on the aligned reference line.",
      captionCheck: "The OCR number check with Tesseract: false alarms with the reference text as the transcription (111 pages) and planted one-digit errors caught (839 substitutions, 839 insertions, 735 deletions).",
    },
    speed: {
      title: "Interactive speed",
      text: "On the power-capped H200, Gemma-4-31B-it decodes at about 30 tokens a second. Prompt-lookup speculative decoding on the reasoner gives byte-identical greedy output, which was verified, and about three times faster generation: a specialty brief falls from 37.6 s to 12.4 s and a Case File summary from 63.8 s to 20.8 s. Ingestion of 27 documents including five scans takes about 6 s; the instant value search about 2 ms and a guideline query about 120 ms over a library of 97 files and 5,759 passages, India first (NCG, ICMR, PM-JAY, ICRI/IRIA), then ESMO, CAP/ASCO-CAP, ACR, RECIST, NCI PDQ, RCPath, RCR and NICE.",
    },
  },
  findings: {
    title: "Key findings",
    items: [
      ["The harness is like for like.", "Where the published protocol matches ours, our scores agree with the cards within a few points in both directions. The disagreements are explained by protocol: answer likelihood against generated answers, a language-model judge against exact match, thinking mode against a visible chain of thought."],
      ["Model generation matters more than size or medical fine-tuning.", "Qwen3.5-4B, a 4B general model, matches a 27B medical model on text and beats every 7B to 8B medical fine-tune of the previous generation by 10 to 28 points. The older fine-tunes are superseded."],
      ["The hard sets separate the models.", "On MedQA and MMLU-Med the top models are close to the ceiling. MedXpertQA and MedMCQA spread them out: 55.1 against at most 40.4 on MedXpertQA. An India-specific test is the obvious next addition."],
      ["Format discipline is a separate property.", "Several strong models cannot reply with a letter when asked to. The first-token and parse-rate columns separate this from knowledge; for a system that asks structured questions, the direct-answer columns favour HuatuoGPT-3-27B and Lingshu-32B."],
      ["Benchmarks do not measure grounding.", "All three candidate reasoners produced zero fabrications on the 33 probes, and the 166 values from real pathology reports were all grounded, because the grounding layer, not the model, decides what is shown. The benchmark picks the model with the most knowledge; the grounded evaluations decide whether the product may show its output."],
    ],
  },
  caveats: {
    title: "Caveats",
    items: [
      ["Thinking mode was off.", "HuatuoGPT-3, Baichuan-M2 and Qwen3.5 publish results with thinking mode on and long budgets; here every model got the same visible step-by-step prompt and 2,048 tokens, so these three may score higher in their own settings."],
      ["Open image answers use exact match.", "Correct but differently worded short answers score zero. Papers often use a language-model judge, which gives much higher open-answer numbers."],
      ["Engine errors count as wrong.", "HuatuoGPT-3 (922), Lingshu (1,043) and Qwen3.5 (922) had OmniMedVQA questions refused because large images exceed the context window. Excluding them adds about one point."],
      ["Baichuan-M2's direct scores were re-scored", "from the saved replies after a stray thinking tag broke the parser; no answer was regenerated."],
      ["Possible training overlap.", "Lingshu was trained on the training splits of VQA-RAD, SLAKE and PathVQA, and newer models may have seen public test items. Benchmarks measure examination knowledge, not safety on real patient documents."],
      ["The grounded evaluations are small and mostly synthetic.", "Three Case Files, 31 documents, 33 probes, 111 synthetic scanned pages and 30 real reports. They are release gates for one product, not a clinical validation, and no clinical claim is made from them."],
    ],
  },
  uses: {
    title: "What Vaidyx-TB uses",
    text: [
      "Gemma-4-31B-it (non-medical) is the reasoner: the strongest text model, with the verbatim-quote grounding because it is not medically validated. Qwen3.5-4B (Chinese, non-medical) is the reader and extractor: 62.4 % overall at 4B, ahead of every 7B to 8B medical model, and the winner of the bake-off; MedGemma-4B-it is the best small option from outside China. HuatuoGPT-3-27B (Chinese, medical) is worth a Vaidyx-specific evaluation as a second opinion where a Chinese-origin model is acceptable for the deployment. Lingshu-32B (Chinese, medical) leads radiology and pathology VQA; neither it nor any other model reads a scan inside Vaidyx-TB, which only reads report documents and leaves images to the clinicians.",
      "The next benchmark round will strip thinking tags in the parser, re-run the direct image tests with 128 tokens so that explaining models are scored fairly, add an Indian-language and Indian-guideline test set, and score open image answers with a language-model judge alongside exact match.",
    ],
  },
  sources: {
    title: "Sources for the published numbers",
    note: "Pages opened on 9 October 2026.",
    items: [
      { label: "MedGemma model card (27B, 27B-text, 4B)", href: "https://huggingface.co/google/medgemma-27b-it" },
      { label: "MedGemma 1.5 4B model card", href: "https://huggingface.co/google/medgemma-1.5-4b-it" },
      { label: "Lingshu-32B model card", href: "https://huggingface.co/lingshu-medical-mllm/Lingshu-32B" },
      { label: "Lingshu technical report", href: "https://arxiv.org/abs/2506.07044" },
      { label: "Gemma 4 31B model card", href: "https://huggingface.co/google/gemma-4-31B-it" },
      { label: "Gemma 4 technical report", href: "https://arxiv.org/html/2607.02770" },
      { label: "Qwen3.5-4B model card", href: "https://huggingface.co/Qwen/Qwen3.5-4B" },
      { label: "Llama3-Med42-8B model card", href: "https://huggingface.co/m42-health/Llama3-Med42-8B" },
      { label: "Llama3-OpenBioLLM-8B model card", href: "https://huggingface.co/aaditya/Llama3-OpenBioLLM-8B" },
      { label: "JSL-MedLlama-3-8B-v2.0 model card", href: "https://huggingface.co/johnsnowlabs/JSL-MedLlama-3-8B-v2.0" },
      { label: "HuatuoGPT-3 repository", href: "https://github.com/FreedomIntelligence/HuatuoGPT-3" },
      { label: "Baichuan-M2-32B model card", href: "https://huggingface.co/baichuan-inc/Baichuan-M2-32B" },
      { label: "Sarveswaran et al., ecancermedicalscience 2026 (the Indian survey)", href: "https://doi.org/10.3332/ecancer.2026.2090" },
    ],
  },
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
