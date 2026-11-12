// The wording of the product page's additions of 12 Nov: the five boxes under the hero ("What Vaidyx does"), the three new
// sections they open (Ask PubMed, the benchmark, runs locally) and "Customisable for your hospital". The owner's own wording stays
// in content.ts, untouched; everything new is here.
// Register: plain Indian English a doctor or an administrator reads in one glance. No accuracy or validation claim. The AI does
// not diagnose, stage, read images, predict or advise treatment. Models are named with their labels.
// Every fact was checked against the code or the docs on 12 Nov 2026 (the source is named beside each block).

/** The five boxes. `to` is the id of the section a box scrolls to: `sources` and `how` are the owner's sections. */
export const PILLARS = {
  eyebrow: "At a glance",
  title: ["What Vaidyx does,", "in simple words."],
  go: "See how",
  items: [
    { key: "proof", to: "sources", title: "Every answer shows its proof", text: "Taken from the patient's own reports, word for word." },
    { key: "pubmed", to: "pubmed", title: "Evidence from PubMed", text: "General questions are answered only from published papers, quoted line by line." },
    { key: "benchmark", to: "benchmark", title: "Models tested before use", text: "13 open models, 11 medical and 2 general-purpose, on 11 public benchmarks." },
    { key: "local", to: "local", title: "Runs inside your hospital", text: "The AI models run on your own server. Patient records stay with you." },
    { key: "assistant", to: "how", title: "One assistant, start to finish", text: "Before, during and after the Tumour Board. Doctors decide." },
  ],
} as const;

/* Ask PubMed (docs/pubmed-ask/DESIGN.md; features/pubmed). The example is a real answer of the product, cut from a proof run on
   public PubMed records (e2e/support/f2/pubmed.json, thread "home"): the quotes are the papers' own words, as the server checked
   them. The label is the product's own sentence (features/pubmed/api.ts). */
export const PUBMED = {
  eyebrow: "Published evidence",
  title: ["General questions, answered", "only from PubMed."],
  lead: "When a doctor asks a general question, Vaidyx searches PubMed at that moment and reads the abstracts it finds. Every line of the answer is quoted word for word from a paper and carries its PMID. Nothing comes from the model's own memory.",
  points: [
    { key: "live", title: "Fetched from PubMed", text: "The search runs on PubMed when the question is asked, through the NCBI E-utilities service. A paper's record is kept for at most a week before it is fetched again." },
    { key: "quote", title: "Quoted word for word", text: "Each line names its paper by PMID and shows the exact words of the abstract. A line whose quote is not found in the abstract is dropped." },
    { key: "memory", title: "Never from memory", text: "If the abstracts do not answer the question, Vaidyx says: \"No answer found in the PubMed abstracts read.\"" },
    { key: "words", title: "Only the search words leave the hospital", text: "A name, UHID, IP or OP number, ABHA, date, age or place is never sent to PubMed." },
  ],
  demo: {
    title: "Ask PubMed",
    stamp: "Example",
    asked: "Question",
    question: "What did trials from India report about low-dose metronomic chemotherapy in head and neck cancer?",
    wordsLabel: "Search words sent to PubMed",
    words: "(metronomic chemotherapy OR low-dose chemotherapy) AND (\"head and neck neoplasms\" OR \"head and neck cancer\") AND (India OR Indian)",
    counts: "56 papers found, 15 abstracts read",
    lines: [
      {
        text: "A randomised phase III study reported that adding low-dose nivolumab to triple metronomic chemotherapy improved 1-year overall survival from 16.3% to 43.4%.",
        quote: "The addition of low-dose nivolumab led to an improvement in the 1-year OS from 16.3% (95% CI, 8.0 to 27.4) to 43.4% (95% CI, 30.8 to 55.3; hazard ratio, 0.545; 95% CI, 0.362 to 0.820; P = .0036).",
        pmid: "36265101",
        paper: "J Clin Oncol 2023, randomised trial, India",
      },
      {
        text: "A randomised phase III trial in India found that triple metronomic chemotherapy improved survival outcomes over physician choice therapy in platinum-refractory head and neck cancer.",
        quote: "These results suggest that TMC significantly improves survival outcomes over physician choice therapy in platinum-refractory head and neck cancer.",
        pmid: "40209850",
        paper: "Cancer Lett 2025, randomised trial, India",
      },
    ],
    quoteLabel: "Quote",
    pmidLabel: "PMID",
    pmidHref: "https://pubmed.ncbi.nlm.nih.gov/",
    label: "From PubMed. Every line is quoted word for word from the paper's abstract. Published evidence, not advice for this patient.",
    model: "Written by Gemma-4-31B (non-medical)",
  },
} as const;

/* The benchmark (docs/research/benchmark-paper; the figures are read from research/data.ts, the same data the Research page
   shows, so the two can never differ). */
export const BENCHMARK = {
  eyebrow: "Benchmark",
  title: ["Thirteen open models, tested", "before we chose."],
  lead: "The team ran 13 open models, 11 medical and 2 general-purpose, on 11 public benchmarks on its own server, with the published full-precision weights. The models Vaidyx runs were chosen from these results and from its own checks on synthetic Case Files.",
  groups: {
    medical: "medical models",
    general: "general-purpose models (non-medical)",
    text: "text sets",
    image: "image sets",
    questions: "questions",
  },
  chart: {
    title: "Score on the 9,995 text questions",
    sub: "Share of questions answered correctly, step by step, in %. One bar per model, highest first.",
    medical: "Medical",
    general: "General-purpose (non-medical)",
    used: "runs in Vaidyx",
    label: "Overall step-by-step score of the 13 models on the 9,995 text questions",
  },
  roles: {
    "gemma-4-31b-it": "Gemma-4-31B (non-medical) writes the summaries and the answers.",
    "qwen3.5-4b": "Qwen3.5-4B (Chinese, non-medical) reads the reports.",
  },
  note: "These are scores on public examination questions, measured on one server. They are not a clinical validation of Vaidyx.",
  link: "See every table on the Research page",
  to: "/research",
} as const;

/* Runs locally (the approved fact sheet, docs/night-v3/FEATURES.md "Voice, all local", docs/pubmed-ask/DESIGN.md section 2). */
export const LOCAL = {
  eyebrow: "Runs locally",
  title: ["The AI runs inside", "your hospital."],
  lead: "All the AI models run on the hospital's own server. Patient records, images and voice stay inside the hospital. No cloud AI service is used.",
  diagram: {
    label: "The hospital boundary: the hospital's systems, the Vaidyx server with its AI models and the doctors' screens are inside; only PubMed search words go out",
    inside: "Inside the hospital",
    systemsTitle: "Hospital systems",
    systems: [
      { key: "his", title: "HIS / HIMS", sub: "Read only, HL7 FHIR R4" },
      { key: "pacs", title: "PACS", sub: "DICOMweb, scans stay here" },
    ],
    server: {
      title: "Vaidyx server",
      sub: "The hospital's own GPU server",
      modelsTitle: "AI models on this server",
      models: [
        { does: "Writes", name: "Gemma-4-31B", tag: "non-medical" },
        { does: "Reads", name: "Qwen3.5-4B", tag: "Chinese, non-medical" },
        { does: "Voice", name: "Speech models", tag: "typing by voice, read aloud" },
        { does: "Search", name: "Search model", tag: "finds the right lines" },
      ],
    },
    peopleTitle: "Doctors and the Board",
    people: [
      { key: "casefile", title: "Tumour Board Case File", sub: "On the hospital's own screens" },
      { key: "meeting", title: "Board meeting", sub: "Self-hosted video" },
    ],
    reads: "reads",
    shows: "shows",
    out: "Only search words go out",
    outsideTitle: "Outside the hospital",
    pubmed: { title: "PubMed", sub: "Public library of papers (NCBI)" },
    cloud: { title: "Cloud AI services", sub: "Not used" },
  },
  points: [
    { key: "models", title: "Models on your own server", text: "The language models, the search model and the speech models all run on the hospital's GPU server. The language models use the published full-precision weights." },
    { key: "records", title: "Records and images stay inside", text: "Vaidyx reads the hospital system and never writes to it. Scans stay in the PACS and open in a viewer inside the Case File." },
    { key: "voice", title: "Voice is not stored", text: "Speech is turned into text on the server itself. The audio is not kept." },
    { key: "words", title: "Only search words go out", text: "Ask PubMed sends search words to PubMed, never a name, a hospital number or a date." },
  ],
} as const;

/* Customisable for your hospital. Each tab is something a hospital sets for itself today:
   hospital, departments, people, hospital system and board = the guided set-up (features/admin/SetupSteps.tsx, tumour_board/org.py);
   checklists = tumour_board/protocols/*.json (24 cancers, tiers in protocol.py, the level rule in rules.py);
   agents = tumour_board/skills/<role>/SKILL.md (the hospital's edit wins; the hard rules stay in agents.py);
   meetings = the weekly series (features/meetings/planner). The checklist rows are from protocols/breast.json, the focus lines
   from skills/radiology/SKILL.md. Names of people are synthetic. */
export const CUSTOM = {
  eyebrow: "Your hospital, your way",
  title: ["Customisable", "for your hospital."],
  lead: "Every hospital runs its Tumour Board in its own way. Vaidyx is set up for each hospital: its name and level, its departments and people, its checklists, its own HIS and PACS, and its meeting day.",
  tabsLabel: "What a hospital can set",
  hint: "Choose a setting to see it.",
  mock: "A picture of the settings, with synthetic names.",
  tabs: [
    { key: "hospital", label: "Hospital", sub: "Name, logo, level, PM-JAY" },
    { key: "departments", label: "Departments and roles", sub: "Who works where" },
    { key: "checklists", label: "Cancer checklists", sub: "What each cancer needs" },
    { key: "agents", label: "Specialty AI agents", sub: "What each agent looks for" },
    { key: "systems", label: "HIS and PACS", sub: "Your own systems" },
    { key: "meetings", label: "Meetings", sub: "Day, time, room" },
  ],
  hospital: {
    title: "Hospital",
    text: "The name and the logo appear on the Board presentation and the exports. The level and the PM-JAY setting decide what the checklists and the board record ask for.",
    name: { label: "Hospital name", value: "Vaidyx Demo Hospital" },
    logo: { label: "Hospital logo", value: "Uploaded" },
    level: { label: "NCG level", options: [{ key: "essential", label: "Essential" }, { key: "optimal", label: "Optimal" }] },
    pmjay: { label: "Empanelled under PM-JAY", on: "The board record carries the Pre-Authorization checks.", off: "The PM-JAY checks are switched off." },
    window: { label: "Records fetched for a new Case File", value: "12 months" },
  },
  departments: {
    title: "Departments and roles",
    text: "The hospital switches on the departments it has, treating and supporting, and places each person in a department with a role. A department admin looks after its own people.",
    treating: { label: "Treating departments", items: ["Breast Surgery", "Medical Oncology", "Surgical Oncology", "Radiation Oncology", "Gynaecologic Oncology", "ENT / Head and Neck Surgery"] },
    supporting: { label: "Supporting departments", items: ["Radiology", "Pathology", "Biochemistry", "Nuclear Medicine"] },
    more: "and more: the list is the hospital's own",
    rolesLabel: "Roles",
    roles: ["Doctor", "Head", "Resident", "Department admin", "MDT Coordinator"],
    people: [
      { name: "Dr L. Rao (SYNTHETIC)", role: "Head, Breast Surgery" },
      { name: "Dr S. Iyer (SYNTHETIC)", role: "Doctor, Radiology" },
      { name: "Ms A. Thomas (SYNTHETIC)", role: "MDT Coordinator" },
    ],
  },
  checklists: {
    title: "Cancer checklists",
    text: "Each cancer has its own checklist: which records and values the Board needs, and which department holds each one. Checklists for 24 cancers come built in, with the NCG levels as printed. The newer ones are drafts until a clinician checks them. Each checklist is a plain file, so it can be reviewed and changed for your hospital with your doctors.",
    cancer: "Breast cancer",
    count: "1 of 24 cancers",
    levelLabel: "Hospital level",
    tiers: { a: "Essential", b: "Optimal", c: "Optional" },
    needed: "Needed",
    notNeeded: "Not asked at this level",
    rows: [
      { label: "Histopathology (core biopsy preferred) or FNAC", dept: "Pathology", tier: "a" },
      { label: "Receptor status (ER / PR / HER2)", dept: "Pathology", tier: "a" },
      { label: "Breast imaging report (mammography / ultrasound)", dept: "Radiology", tier: "a" },
      { label: "Grade (core biopsy)", dept: "Pathology", tier: "b" },
      { label: "Ki-67", dept: "Pathology", tier: "c" },
    ],
  },
  agents: {
    title: "Specialty AI agents",
    text: "Six specialty AI agents prepare briefs and stand in for an absent specialist in the meeting. What each agent looks for is a short text, a skill, that the hospital can change. The safety rules are not part of that text: they stay fixed for every hospital.",
    roles: ["Radiology", "Pathology", "Medical Oncology", "Surgical Oncology", "Radiation Oncology", "Nuclear Medicine"],
    skillOf: "Radiology support: what it looks for",
    focus: [
      "modality and date of each study",
      "lesion sizes and measurements exactly as reported",
      "comparison with prior imaging as documented",
      "imaging that is missing, pending or not final",
      "differences between reports",
    ],
    fixedLabel: "Fixed for every hospital",
    fixed: ["Every sentence needs a quote from the records", "No diagnosis, staging or treatment advice", "No reading of images"],
  },
  systems: {
    title: "HIS and PACS",
    text: "Vaidyx reads from the systems the hospital already has, through open standards. The hospital gives the address of its own HIS and PACS and tests the connection.",
    his: { label: "Hospital system (HIS / HIMS)", standard: "HL7 FHIR R4", mode: "Read only", address: "https://his.hospital.example/fhir", test: "Connection test: answered" },
    pacs: { label: "PACS", standard: "DICOMweb", mode: "Scans stay in the PACS", address: "https://pacs.hospital.example/dicom-web", test: "Opens in the viewer inside the Case File" },
    ids: { label: "Patient numbers", items: ["UHID", "IP No.", "OP No.", "ABHA"] },
  },
  meetings: {
    title: "Meetings",
    text: "The MDT Coordinator plans the Tumour Board as a weekly series: the day, the time, the room and the minutes for each case. The heads who should be at every Board are the hospital's choice.",
    series: "Every week on Friday",
    rows: [
      { label: "Day", value: "Friday" },
      { label: "Time", value: "15:00" },
      { label: "Room", value: "Seminar Room 2" },
      { label: "Minutes per case", value: "10" },
    ],
    days: ["M", "T", "W", "T", "F", "S", "S"],
    dayIndex: 4,
    headsLabel: "Heads at every Board",
    heads: ["Radiology", "Medical Oncology", "Surgical Oncology", "Pathology", "Radiation Oncology"],
    coordinator: { label: "MDT Coordinator", value: "Ms A. Thomas (SYNTHETIC)" },
  },
} as const;
