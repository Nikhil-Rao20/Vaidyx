/* Vaidyx-TB workflow atlas: content. Facts come from the code on branch the-ui (16 Oct 2026), the team's plans
   (docs_Eswar/changes_v1.md, changes_v2.md, 01_how_vaidyx_tb_works.md), Eswar's prompts (10 and 13 Oct 2026),
   DESIGN.md, UI_PLAN_OCT15.md and outside research (sources in ATLAS.research.sources). No em dashes anywhere. */
window.ATLAS = {
  meta: {
    built: "16 Oct 2026",
    branch: "the-ui (from main, commit 78bcd4b)",
    scope: "The AI checks, routes, summarises and flags. It never diagnoses, interprets images, computes a stage or recommends treatment. Every value shown as a fact carries a verified quote. Human oversight (expert-in-the-loop) throughout."
  },

  engines: {
    rules:  { label: "Plain rules", note: "Fixed code, no AI, milliseconds" },
    qwen:   { label: "Qwen reader", note: "Qwen3.5-4B, Chinese (Alibaba Qwen), non-medical: reads, transcribes, classifies, extracts" },
    gemma:  { label: "Gemma reasoner", note: "Gemma-4-31B-it, non-medical: writes cited drafts (answers, briefs, summary, adjudication lists)" },
    search: { label: "Search", note: "BM25 + embeddings on CPU: finds text, writes nothing" },
    ocr:    { label: "Tesseract", note: "Second OCR engine on CPU: flags numbers it reads differently" },
    his:    { label: "Hospital system", note: "Mock Indian HIS (FHIR R4, port 7130), RIS / LIS desk, Orthanc PACS + OHIF (8042)" },
    people: { label: "People", note: "A person does it; the system records it" }
  },

  stages: [
    { id: "setup",  label: "Set-up", tone: "setup",  line: "Once per hospital, then when people join or leave." },
    { id: "before", label: "Before the board", tone: "before", line: "From the patient's UHID to a complete, summarised Case File on the agenda." },
    { id: "during", label: "During the board", tone: "during", line: "The meeting: attendance, presentation, AI support for absent heads, the decision." },
    { id: "after",  label: "After the board", tone: "after",  line: "Built in V1 and left open for Eswar's discussion: checks on the record, follow-up, exports." }
  ],

  /* swimlane lanes: built roles first, then the roles research says are missing (shown dashed) */
  lanes: [
    { id: "treating",    label: "Treating doctor" },
    { id: "supporting",  label: "Supporting doctor" },
    { id: "coordinator", label: "MDT Coordinator" },
    { id: "boardheads",  label: "Board in the room" },
    { id: "ai",          label: "AI support" },
    { id: "system",      label: "System / HIS" },
    { id: "admins",      label: "Admins" },
    { id: "resident",    label: "Resident / PG", missing: true },
    { id: "chair",       label: "Chair", missing: true },
    { id: "nurse",       label: "Nurse navigator", missing: true },
    { id: "pmjay",       label: "PM-JAY desk", missing: true },
    { id: "patient",     label: "Patient / family", missing: true }
  ],

  /* ---------------------------------------------------------------- roles */
  roles: [
    {
      id: "treating", name: "Treating doctor", group: "Clinical team", status: "built", lane: "treating",
      who: "A consultant of a treating department (22 in the code: Surgical, Medical and Radiation Oncology, Breast Surgery, Gynaecologic Oncology, ENT / Head and Neck, Colorectal Surgery, Pulmonology and others). The department owns the patient's cancer episode.",
      eswar: "Around 5 doctors per department are the top position; their PG students do the report work using the lead doctor's login. We don't need to take care of that (Eswar, 13 Oct).",
      assigned: "Department admin (or root admin) places the login as Doctor (member) or Head of a treating department. Stored in org.json users[u].departments.",
      home: "My Case Files (owned first, ready mark, referral waiting, suggested requests not sent), + Create from UHID, requests to its department (counts only), referrals to answer, notifications.",
      stages: {
        before: [
          "Creates the Case File from the patient's UHID, IP No. or OP No.: picks the cancer protocol, the NCG setting as recorded, hospital level, fetch window (12 months default) and board date.",
          "Links possible duplicate or temporary registrations (never merged automatically).",
          "Reads the Pre-Authorization check: Level 1 (record present, final, signed, right patient) and Level 2 (required values present with a verified quote).",
          "Does what only a person can: attest final, confirm dates, type, patient or a critical value read from a scan, dismiss a failed document (reason), waive a record (reason), note a discordance.",
          "Sends the suggested requests: edits the draft, sends in-app, or opens it in their own mail; writes free requests (Anaesthesiology, Clinical Pharmacology).",
          "Presses Re-fetch after a department says Done; requests close themselves when the record arrives final and signed.",
          "Uploads outside reports (other hospital, private lab); confirms the patient when matched by name only.",
          "Refers the Case File to another treating department when the diagnosis changes; links a second primary.",
          "Adds participating departments.",
          "Compiles the Case File summary once the check is met; reviews it; exports the NCG Virtual Tumour Board template.",
          "Marks the Case File ready for the board (the coordinator is told)."
        ],
        during: [
          "Present at the board (real world: often the resident presents). In Vaidyx: opens the Board room if it may read a Case File on the agenda, opens records and images, asks the Case File or an agent.",
          "Cannot record the decision: only the MDT Coordinator can (code)."
        ],
        after: [
          "Receives board actions only when its department is named in an action.",
          "Is not notified when the decision is recorded (gap).",
          "Real world: agrees the plan with the patient; in the code the 'inform the patient' task goes to the coordinator."
        ]
      },
      cannot: ["Record the board decision or resolve adjudication flags (coordinator only)", "Act on another department's Case File unless participating (read only)", "Delete a Case File (coordinator only)"],
      needs: [
        "A complete Case File without chasing departments by phone (research: missing information is the top cause of deferral).",
        "One place that says what is missing, who is asked, and what to do next.",
        "Notifications on the phone; work on the OPD desktop.",
        "An editable summary that keeps its sources (Hartmann 2026: case preparation took 13 min, about 25 program switches, the summary rewritten 3.5 times).",
        "The board's decision back within one working day (Greater Manchester, Victoria)."
      ],
      devices: ["Desktop / laptop in OPD", "Phone", "Meeting-room screen"],
      notifications: ["request_acknowledged", "request_done", "owner_reminder", "referral_answered", "case_shared", "board_action (if named)", "re-fetch result"],
      screens: ["Home (treating)", "Case File: all 7 tabs", "New Case File from HIS", "Notify dialog", "Refer dialog", "Department inbox (as receiver)", "Board room (read)"],
      gaps: ["G01", "G03", "G04", "G08", "G11", "G14", "G21", "U01", "U02", "U16"],
      ideas: ["I16", "I10", "I15", "I03"]
    },
    {
      id: "supporting", name: "Supporting doctor", group: "Clinical team", status: "built", lane: "supporting",
      who: "Radiologist, pathologist, nuclear medicine physician, biochemist, microbiologist, clinical pharmacologist, dental surgeon, anaesthesiologist (8 supporting departments).",
      eswar: "A radiologist won't upload anything to our platform: they work in the PACS, sign with their digital signature, and the report reaches the HIS automatically. Our platform is a notification carrier for missing records or values (Eswar, 13 Oct).",
      assigned: "Department admin places the login as Doctor or Head of a supporting department.",
      home: "Per supporting department: open, overdue, taken up, done awaiting re-fetch, with Acknowledge and Done on each request.",
      stages: {
        before: [
          "Gets a request (bell + department inbox) with UHID, IP / OP No., accession No., who sent it, due date.",
          "Acknowledges it.",
          "Finds the patient in its own PACS / RIS / LIS (demo: the mock reporting desk, a separate site with no link from Vaidyx), completes and signs the report there.",
          "Sends Done with an optional note. The request closes only when the treating side re-fetches and the signed report arrives.",
          "Sees a limited view of the Case File: only its requests and the records it produced or was asked about (no gate, no values, no summary)."
        ],
        during: [
          "Radiology and Pathology are board heads: present in the room, or their AI agent stands in.",
          "A department on the attendance sheet can open the Board room; Case Files it may not read show as restricted."
        ],
        after: [
          "Receives board actions for its department (example: MRI breast for Radiology) and closes them; may see 'May be complete' when a matching report arrives."
        ]
      },
      cannot: ["Upload records (V2 removed the department upload screen)", "Waive, confirm or create Case Files", "See the gate, values or summary of a Case File it was only asked about"],
      needs: [
        "Few clicks, on the phone, between reporting work.",
        "Exactly what to find: patient IDs, accession, what is missing, due date.",
        "No second system to log into for something already signed in the RIS / LIS.",
        "Research: radiologists spend about an hour preparing a board list (Bart's); attendance in India is low (radiologist 46.7%, pathologist 28.5%), so asynchronous confirmation helps."
      ],
      devices: ["Reporting workstation (PACS / RIS / LIS)", "Phone"],
      notifications: ["request", "request_reminder", "request_closed", "board_action", "board_action_suggestion"],
      screens: ["Home (supporting)", "Department inbox", "Limited Case File view", "Mock reporting desk (/desk, outside Vaidyx)"],
      gaps: ["G20", "G10", "G13", "U03", "U11", "U02"],
      ideas: ["I14", "I12", "I08"]
    },
    {
      id: "coordinator", name: "MDT Coordinator", group: "Board", status: "built", lane: "coordinator",
      who: "The Tumour Board secretariat: organises sessions, collects the data, chases departments. India: 52.5% of boards have a designated secretariat (ICMR-NCDIR survey).",
      eswar: "There will be a coordinator who organises the Tumour Board sessions and mostly collects data; give the coordinator a login and define the role (Eswar, 13 Oct).",
      assigned: "Root admin sets the coordinator flag on a login (a role, not a department).",
      home: "Next board date with its readiness and chase list (Remind from the home), open and closed sessions, ready marks.",
      stages: {
        before: [
          "Watches readiness for a board date: ready, on track, at risk, blocked, not listed (rules, from the check and request due dates).",
          "Chases on the owner's behalf: Remind a department about a sent request; Remind owner about unsent suggestions, overdue requests, missing summary, not marked ready.",
          "Lists or changes the listing of a Case File (protocol, setting, board date, level).",
          "Works the Needs matching queue (records that could not be matched to a patient).",
          "Creates the board session from the Case Files their owners marked ready."
        ],
        during: [
          "Records attendance: the four heads first, then Radiation Oncology and Nuclear Medicine, the hospital's list and the owners; members present by name.",
          "Starts the session: the agent of every head not recorded present prepares its brief.",
          "Moves through the agenda (Make current), opens records and images.",
          "Records the decision as dictated, with actions (department, due date); adjudication runs.",
          "Marks each agent point Discussed / Accepted / Not relevant."
        ],
        after: [
          "Resolves adjudication flags: Corrected (new version), Intentional deviation (reason), False alarm.",
          "Records patient communication fields; owns the 'inform the patient' task (due in 7 days).",
          "Tracks follow-up; exports minutes and the agent log; reads the quality dashboard.",
          "Hears when a later amended report changes a value the decision cited."
        ]
      },
      cannot: ["Confirm, waive or edit records", "Upload, re-fetch or re-process on an owned Case File"],
      needs: [
        "A clear agenda list with what is missing per Case File, and who to chase.",
        "A cut-off for the agenda and a way to handle late additions (Victoria: agenda out 48 h before).",
        "Fast data entry in the room while people talk (scribe role); Victoria: the scribe may ask the chair to slow down.",
        "Outcomes sent within one working day; actions with named owners."
      ],
      devices: ["Desktop", "Meeting-room screen"],
      notifications: ["case_ready", "board_ready", "decision_value_changed", "board_action (inform the patient)", "request (rows addressed to the coordinator)"],
      screens: ["Home (coordinator)", "Board sessions", "Board room", "Quality dashboard", "Needs matching", "Case File: Board and follow-up tab"],
      gaps: ["G03", "G02", "G15", "G22", "G23", "U17", "U14"],
      ideas: ["I01", "I05", "I06", "I09", "I13"]
    },
    {
      id: "boardheads", name: "Board heads and members", group: "Board", status: "partial", lane: "boardheads",
      who: "The board's core specialties: Radiology, Medical Oncology, Surgical Oncology, Pathology (Eswar: 'kind of judges / jury'). Plus Radiation Oncology and Nuclear Medicine on demand, and the Case File's own surgeon.",
      eswar: "In the tumour board these people are the heads: Radiology, Medical Oncology, Medical Surgery and Pathology; agent support stands in (Eswar, 13 Oct). 'Medical Surgery' was read as the Surgical Oncology seat.",
      assigned: "Hospital settings (board_heads, board_attendance) under Organisation. Heads are departments, not named people.",
      home: "No home of their own: they are treating or supporting doctors.",
      stages: {
        during: [
          "Marked present or absent on the attendance sheet. A head not recorded present gets its AI agent for every Case File on the agenda.",
          "Surgical seat: Surgical Oncology, or a present surgeon of the Case File's own surgical department; otherwise the Surgical Oncology agent stands in for that Case File.",
          "PM-JAY composition (empanelled hospitals only): surgical, radiation and medical oncologist present; a review flag, never a block; an agent never counts.",
          "Discuss and decide. The decision is the board's; Vaidyx only records it."
        ]
      },
      cannot: ["Record the decision themselves (coordinator only)"],
      needs: [
        "The case on one screen: question for the board, key findings with sources, images one click away.",
        "About 3 to 6 minutes per case (CRUK: more than half of cases get 2 minutes or less)."
      ],
      devices: ["Meeting-room screen", "Laptop (online members)"],
      notifications: [],
      screens: ["Board room"],
      gaps: ["G02", "G13", "G25"],
      ideas: ["I01", "I02"]
    },
    {
      id: "ai", name: "AI support (role-specific)", group: "Board", status: "built", lane: "ai",
      who: "Six specialty agents (Radiology, Pathology, Medical, Surgical, Radiation Oncology, Nuclear Medicine). Not people and never members of the board.",
      eswar: "If the radiologist didn't attend, our Radiology agent gets active and gives its view; the board re-thinks and decides; we store what it said and what happened (Eswar, 10 Oct).",
      assigned: "Each agent's focus comes from an editable SKILL.md (root admin edits; hard rules stay in code).",
      home: "None.",
      stages: {
        during: [
          "Prepares a brief from the Case File records and its India-first guideline pack: sections, Points for review (questions about the records, not treatment), 'not documented' items. Gemma, 13 to 17 s per brief.",
          "Answers live questions from the room (1.6 to 5.9 s); out-of-scope questions are refused.",
          "Every item needs a verified quote; removed items are kept for reviewers.",
          "No documents for its specialty: says so without a model call."
        ],
        before: ["Specialty support tab: a brief can be prepared on any Case File."],
        after: ["What each agent said stays in the agent log beside the board's decision."]
      },
      cannot: ["Read images", "Diagnose, stage, recommend treatment or estimate prognosis"],
      needs: ["Clinicians need to see quickly which statements are verified and which were removed."],
      devices: [],
      notifications: [],
      screens: ["Specialty support tab", "Board room: AI support card", "Agent skills"],
      gaps: ["G09", "K01", "K02"],
      ideas: []
    },
    {
      id: "participant", name: "Participating department", group: "Clinical team", status: "partial", lane: "treating",
      who: "Another department sharing a Case File (for example the referring department after a referral).",
      eswar: "",
      assigned: "The owner's doctors add it on the Ownership card; the referring department is added on acceptance.",
      home: "Shown among 'other' Case Files on the treating home.",
      stages: { before: ["Reads the whole Case File, cannot act on it."], during: ["Can open the Board room for that Case File."], after: [] },
      cannot: ["Any clinical action", "Comment (promised as 'read and comment', not built)"],
      needs: ["A way to comment or ask the owner."],
      devices: ["Desktop"],
      notifications: ["case_shared", "case_unshared"],
      screens: ["Case File (read)"],
      gaps: ["G08"],
      ideas: []
    },
    {
      id: "root", name: "Root admin", group: "Administration", status: "built", lane: "admins",
      who: "The Tumour Board super-admin of the hospital. A plain Vaidyx account named by the Vaidyx admin; never a Vaidyx admin (those have a server shell tool).",
      eswar: "The overall admin is at the root node; admins per department are internal nodes; doctors are leaf nodes (Eswar, 13 Oct).",
      assigned: "Vaidyx admin or another root admin (org.json admins[]).",
      home: "First set-up card until answered (hospital name, NCG level, PM-JAY empanelled), then the organisation in tiles.",
      stages: {
        setup: [
          "Answers the first set-up once.",
          "Organisation: hospital settings (name, NCG level, type, PM-JAY, fetch window, board lists), departments with group and email, the routing table, accounts and roles (New login), HIS connection.",
          "Creates department admins and the MDT Coordinator login.",
          "Edits agent skills (SKILL.md)."
        ]
      },
      cannot: ["Open Case Files or receive notifications", "Clinical actions (by convention: the code lets a root admin give itself a clinical role)"],
      needs: ["Set up once, then rarely touched; changes audited."],
      devices: ["Desktop"],
      notifications: [],
      screens: ["Home (root)", "Organisation", "Agent skills"],
      gaps: ["G05", "G06", "G18", "K07"],
      ideas: []
    },
    {
      id: "deptadmin", name: "Department admin", group: "Administration", status: "built", lane: "admins",
      who: "One or more per department; creates and disables the doctor logins of its own department. May also be a doctor.",
      eswar: "First we create admins for each department; those admins create the doctors' logins and hand the credentials over (Eswar, 13 Oct).",
      assigned: "Root admin (users[u].admin_of).",
      home: "Per department: doctors, heads, disabled, without login; Manage doctors.",
      stages: { setup: ["Creates doctor logins (Doctor or Head), disables leavers, removes placements. Password resets go to the Vaidyx admin."] },
      cannot: ["Open Case Files (no clinical access as admin)", "Reset a password"],
      needs: ["A simple people list; password reset without calling IT."],
      devices: ["Desktop"],
      notifications: [],
      screens: ["Home (department admin)", "My department"],
      gaps: ["G05", "G17"],
      ideas: []
    },
    {
      id: "vaidyxadmin", name: "Vaidyx admin", group: "Administration", status: "built", lane: "admins",
      who: "Server-level admin of the main Vaidyx app (has a server shell tool). Sees and may do everything; never created by any Tumour Board action.",
      eswar: "",
      assigned: "Outside the Tumour Board (main app).",
      home: "Treating, coordinator and root sections together.",
      stages: { setup: ["Names root admins; manages connectors (only role the UI shows Connectors to); resets passwords."] },
      cannot: [],
      needs: ["Should be rarely used in daily work: it holds the shell tool."],
      devices: ["Desktop"],
      notifications: ["Every department's notifications"],
      screens: ["Every screen", "Connectors"],
      gaps: ["G18"],
      ideas: []
    },
    /* -------- roles research says exist in real boards but the code does not have */
    {
      id: "chair", name: "Board chair / convenor", group: "Missing roles", status: "missing", lane: "chair",
      who: "Runs the meeting: checks quorum, paces discussion, mediates, makes sure trials are considered, confirms the final recommendation (Victoria framework, NHS).",
      eswar: "",
      assigned: "Not in the code.",
      home: "",
      stages: {
        before: ["Approves late additions to the agenda (Victoria: needs chair, pathologist and radiologist agreement)."],
        during: ["Decides if each case has enough specialists; keeps time; confirms the decision as recorded."],
        after: ["Signs off the record (today nobody signs off; the coordinator's record is final once flags are resolved)."]
      },
      cannot: [], needs: ["A chair panel: quorum, time per case, what is left on the agenda."],
      devices: ["Meeting-room screen"], notifications: [], screens: [], gaps: ["G02"], ideas: ["I02", "I01"]
    },
    {
      id: "resident", name: "Resident / PG / fellow", group: "Missing roles", status: "missing", lane: "resident",
      who: "Junior doctors under a consultant. In India they usually collect reports, prepare the case summary and slides, and present (widely assumed; not found in published sources). US data: residents carried 39% to 72% of preparation hours.",
      eswar: "PG students use their lead doctor's credentials; we don't need to take care of that (Eswar, 13 Oct).",
      assigned: "Not in the code: they share the consultant's login, so the audit shows the consultant.",
      home: "",
      stages: {
        before: ["Creates the Case File, chases reports, prepares and edits the summary (under the consultant's login today)."],
        during: ["Presents the case on the big screen."],
        after: ["Updates notes, books tests."]
      },
      cannot: [], needs: ["Phone and ward desktop; an editable summary with sources instead of copy-paste; the consultant approves."],
      devices: ["Ward desktop", "Phone"], notifications: [], screens: [], gaps: ["G14"], ideas: ["I03"]
    },
    {
      id: "nurse", name: "Nurse navigator / key worker", group: "Missing roles", status: "missing", lane: "nurse",
      who: "Clinical nurse specialist or patient navigator: the patient's contact, collects comorbidities and social needs, tells the patient the outcome, books next steps (NICE key worker).",
      eswar: "",
      assigned: "Not in the code; the board record has a free-text 'key worker' field and the 'inform the patient' task goes to the coordinator.",
      home: "",
      stages: {
        before: ["Collects patient preferences and consent (only 4.2% of MDT discussions mention preferences, Wihl)."],
        during: ["Brings the patient's voice into the room."],
        after: ["Informs the patient (Greater Manchester: within 2 working days), records who was told, books appointments."]
      },
      cannot: [], needs: ["A task list of patients to inform, in the patient's language."],
      devices: ["Phone", "Desktop"], notifications: [], screens: [], gaps: ["G15"], ideas: ["I04", "I09"]
    },
    {
      id: "pmjay", name: "PM-JAY desk (Arogya Mitra, MEDCO)", group: "Missing roles", status: "missing", lane: "pmjay",
      who: "Pradhan Mantri Arogya Mitra at the hospital's PM-JAY desk and the MEDCO (medical coordinator): verify the beneficiary, upload the treatment plan and documents for pre-authorisation, answer insurer queries.",
      eswar: "",
      assigned: "Not in the code. The Annexure 1 export (V1 7.5) waits for the form.",
      home: "",
      stages: {
        after: ["Needs the board's signed treatment plan (Annexure 1) and the package's mandatory documents; pre-authorisation must be decided within 6 hours (NHA process flow). Gujarat 2024: a tumour board certificate signed by a medical, surgical and radiation oncologist."]
      },
      cannot: [], needs: ["A non-clinical checklist and status per patient: what is uploaded, what is missing."],
      devices: ["Desktop", "Phone"], notifications: [], screens: [], gaps: ["G16"], ideas: ["I11"]
    },
    {
      id: "records", name: "Medical records / HIS staff", group: "Missing roles", status: "missing", lane: "system",
      who: "Retrieve files, scan paper records (63.5% of Indian boards keep paper records), file the decision in the medical record.",
      eswar: "",
      assigned: "Not in the code; V2 fetches from the HIS instead.",
      home: "",
      stages: { before: ["Scan and attach paper or outside reports."], after: ["File the decision in the medical record."] },
      cannot: [], needs: ["A printable one-page decision for the paper file."],
      devices: ["Scanner", "Desktop"], notifications: [], screens: [], gaps: [], ideas: ["I10"]
    },
    {
      id: "quality", name: "Hospital quality team", group: "Missing roles", status: "missing", lane: "admins",
      who: "Audits completeness, quorum, follow-up, NABH and PM-JAY evidence (48.2% of Indian boards have no follow-up system).",
      eswar: "",
      assigned: "Not in the code; the quality dashboard needs the coordinator role.",
      home: "",
      stages: { after: ["Monthly: readiness at cut-off, deferrals by reason, quorum, time to inform the patient, plan versus treatment received."] },
      cannot: [], needs: ["Read-only dashboard access without clinical rights."],
      devices: ["Desktop"], notifications: [], screens: [], gaps: [], ideas: ["I19"]
    },
    {
      id: "patient", name: "Patient and family", group: "Missing roles", status: "missing", lane: "patient",
      who: "Not a user of Vaidyx. Consents to discussion, has preferences, hears the outcome. Indian families often steer disclosure; patients visit 2 to 3 hospitals per episode.",
      eswar: "",
      assigned: "Not a user; patient-communication fields on the board record (12 Oct features).",
      home: "",
      stages: { before: ["Consent and preferences (not captured before the meeting today)."], after: ["Told the outcome in their language; who was told is recorded."] },
      cannot: [], needs: ["Plain-language outcome; scheme status."],
      devices: ["Phone"], notifications: [], screens: [], gaps: ["G29"], ideas: ["I04", "I07"]
    },
    {
      id: "vtb", name: "NCG Virtual Tumour Board centre", group: "Missing roles", status: "missing", lane: "boardheads",
      who: "A spoke hospital presenting to an NCG hub (or the hub's experts). Template: de-identified clinical details, pathology, radiology, specific questions; recommendations emailed back. Median 4 cases per session, 19 centres.",
      eswar: "",
      assigned: "Not a role; the NCG VTB .pptx export exists (V1 4.6).",
      home: "",
      stages: { before: ["Fills the NCG case template."], after: ["Receives the emailed recommendation."] },
      cannot: [], needs: ["One-click de-identified template."],
      devices: ["Video call", "Email"], notifications: [], screens: ["Summary tab: Export .pptx"], gaps: [], ideas: ["I18"]
    }
  ],

  /* ---------------------------------------------------------------- specialties: who brings what */
  specialties: [
    { name: "Radiology", group: "Supporting", head: true, agent: "Radiology", produces: "CT, MRI, X-ray, ultrasound, mammogram reports", asked: "Imaging records (CECT, MRI, mammogram, USG axilla, chest X-ray)", real: "Re-reviews imaging, shows images in the room. Attends 46.7% of Indian boards.", skill: "Study and report dates, final and signed, technique, measurement mismatches; copies BI-RADS / Lung-RADS, never assigns." },
    { name: "Pathology", group: "Supporting", head: true, agent: "Pathology", produces: "Histopathology, cytology, IHC, molecular, CBC", asked: "Biopsy, receptor status, EGFR / ALK / ROS1, PD-L1, MMR, CBC", real: "Reviews slides and markers, confirms histology. Attends 28.5% of Indian boards.", skill: "Specimen and dates, biomarkers with method, clone and cut-off, awaited results, preliminary vs final." },
    { name: "Medical Oncology", group: "Treating", head: true, agent: "Medical Oncology", produces: "Clinical notes, treatment summaries", asked: "Clinical history and performance status (lung default)", real: "Systemic therapy view. Attends 78.8%.", skill: "ECOG / KPS, comorbidities, regimen and cycles, baseline labs, the board question." },
    { name: "Surgical Oncology", group: "Treating", head: true, agent: "Surgical Oncology", produces: "Clinical notes, operative notes", asked: "Clinical evaluation (oral cavity default)", real: "Operability. The surgical seat; the Case File's own surgeon can fill it. Attends 83.2%.", skill: "Site, size and extent wording, prior procedures, fitness, earlier board actions done." },
    { name: "Radiation Oncology", group: "Treating", head: false, agent: "Radiation Oncology (on demand)", produces: "Treatment summaries", asked: "None by default", real: "Radiotherapy view. Attends 92.7% (highest). Needed for PM-JAY composition, yet not a board head in the code.", skill: "Dose, fractions, dates, concurrent agent, restaging timing." },
    { name: "Nuclear Medicine", group: "Supporting", head: false, agent: "Nuclear Medicine (on demand)", produces: "PET-CT, bone scan", asked: "PET-CT staging, bone scan", real: "PET-CT review and presentation.", skill: "Tracer, uptake time, SUVmax as written, stage only as the report states it." },
    { name: "Biochemistry", group: "Supporting", head: false, agent: "None", produces: "LFT, RFT, CEA", asked: "Liver and renal function tests, CEA", real: "Lab values; not in the room.", skill: "" },
    { name: "Microbiology", group: "Supporting", head: false, agent: "None", produces: "Viral markers", asked: "HIV status (cervix)", real: "Lab values; not in the room.", skill: "" },
    { name: "Clinical Pharmacology", group: "Supporting", head: false, agent: "None", produces: "Medication reviews", asked: "Free request only (no protocol record)", real: "Drug interactions, dosing.", skill: "" },
    { name: "Dental Surgery / OMFS", group: "Supporting", head: false, agent: "None", produces: "Dental evaluation", asked: "Dental evaluation (oral cavity)", real: "Pre-radiotherapy dental check.", skill: "" },
    { name: "Anaesthesiology", group: "Supporting", head: false, agent: "None", produces: "Pre-anaesthetic check", asked: "Free request only", real: "Fitness for surgery.", skill: "" },
    { name: "Organ-site surgery (Breast, Gynaecologic Oncology, ENT / Head and Neck, Colorectal, Thoracic, Urology, GI, HPB and others)", group: "Treating", head: false, agent: "Surgical Oncology agent stands in", produces: "Clinical notes, operative notes", asked: "Clinical history (route: owner)", real: "Own most Case Files; their surgeon fills the surgical seat for their Case Files.", skill: "" },
    { name: "Pulmonology, Medical Gastroenterology", group: "Treating", head: false, agent: "None", produces: "Bronchoscopy, EBUS, PFT; endoscopy", asked: "Bronchoscopy, mediastinal staging; endoscopy (rectal)", real: "Treating departments that also receive procedure requests; their home shows only counts for them (gap G11).", skill: "" },
    { name: "Palliative Medicine", group: "Treating", head: false, agent: "None", produces: "Clinical notes", asked: "None", real: "Attends 48.9% of Indian boards; no special role in the code.", skill: "" }
  ],

  /* ---------------------------------------------------------------- the workflow, step by step */
  steps: [
    /* set-up */
    { id: "S1", stage: "setup", title: "Name the root admin", actors: ["admins"], engine: ["people"], what: "The Vaidyx admin (server level) names one or more root admins for the Tumour Board. Root admins are plain accounts, never Vaidyx admins.", screen: "Organisation (as Vaidyx admin)", checkpoint: "", gaps: ["G06"] },
    { id: "S2", stage: "setup", title: "First set-up", actors: ["admins"], engine: ["people"], what: "Root admin answers once: hospital name, NCG level (Essential / Optimal: decides which records are required), PM-JAY empanelled (turns on the board-composition check). Refused after the first answer; changed later on Organisation.", screen: "Home (root): First set-up card", checkpoint: "", gaps: ["K07"] },
    { id: "S3", stage: "setup", title: "Departments, emails, routes, board lists", actors: ["admins"], engine: ["people"], what: "22 treating and 8 supporting departments with group and email (placeholders <id>@hospital.example), the routing table (which department produces each required record), board heads and attendance list, surgical departments, PM-JAY surgical list, HIS connection and fetch window.", screen: "Organisation", checkpoint: "Every save audited", gaps: ["G18"] },
    { id: "S4", stage: "setup", title: "Department admins and coordinator logins", actors: ["admins"], engine: ["people"], what: "Root admin creates logins (New login) and gives roles: department admin of X, MDT Coordinator, root admin.", screen: "Organisation: New login", checkpoint: "", gaps: [] },
    { id: "S5", stage: "setup", title: "Doctor logins", actors: ["admins"], involved: ["resident"], engine: ["people"], what: "Each department admin creates its doctors (Doctor or Head), disables leavers. PG residents use their lead doctor's login (Eswar), so every action is audited under the doctor.", screen: "My department", checkpoint: "", gaps: ["G14", "G17"] },
    { id: "S6", stage: "setup", title: "Agent skills (optional)", actors: ["admins"], engine: ["people"], what: "Root admin edits what each specialty agent looks for (SKILL.md). Hard rules stay in code; a skill cannot add a tool or model.", screen: "Agent skills", checkpoint: "Edits audited, backups kept", gaps: [] },

    /* before the board */
    { id: "B1", stage: "before", title: "Patient worked up in the hospital", actors: ["system"], involved: ["treating", "supporting", "patient"], engine: ["his"], what: "Outside Vaidyx: registration (UHID), OPD visits (OP No.), admission (IP No.), orders to RIS / LIS / pathology, reports preliminary then final and digitally signed in the HIS.", screen: "Hospital systems (mock: /his, /desk)", checkpoint: "", gaps: [] },
    { id: "B2", stage: "before", title: "Create the Case File from the UHID", actors: ["treating"], involved: ["resident", "system"], engine: ["his", "rules"], what: "Treating doctor enters UHID, IP No. or OP No., looks the patient up, picks the cancer protocol, NCG setting as recorded, hospital level, fetch window (6 / 12 / 24 months, all, or from a date) and board date. Ownership: the doctor's treating department.", screen: "+ Create from UHID (home) or + New (side panel)", checkpoint: "Possible duplicate or temporary registrations listed for a person to link; never merged", gaps: ["G14"] },
    { id: "B3", stage: "before", title: "Records fetched and read", actors: ["system"], involved: ["ai"], engine: ["his", "qwen", "ocr", "rules"], what: "Every report version of every OP visit and IP admission in the window is downloaded and read: text layer, or scans transcribed twice by the reader plus Tesseract; type (reader + title keywords + HIS order code), status and signature (HIS and text rules, the stricter wins), dates and identity (rules), required fields with a verified verbatim quote.", screen: "Progress inside the upload card; Documents tab grouped by OP / IP", checkpoint: "Unverified values never shown as fact", time: "Seconds; scans about 1.2 s per page", gaps: ["U08"] },
    { id: "B4", stage: "before", title: "Pre-Authorization check", actors: ["system"], involved: ["treating"], engine: ["rules"], what: "Required records from the NCG Essential / Optimal / Optional tiers for this cancer, setting and hospital level. Level 1: present, final, signed, right patient. Level 2: required values present, verified, not pending. Statuses: satisfied, missing record, not final, needs confirmation, missing field, needs review, waived. Failed documents block it.", screen: "Pre-Authorization tab", checkpoint: "", time: "Milliseconds", gaps: ["U16", "U19"] },
    { id: "B5", stage: "before", title: "Doctor settles what only a person can", actors: ["treating"], involved: ["resident"], engine: ["people"], what: "Attest final, confirm dates, document type, patient match, a critical value read from a scan (against the page image), dismiss a failed document (reason), waive a record (reason), link registrations, note a discordance between reports.", screen: "One confirm dialog from the gate rows and Documents tab", checkpoint: "Every confirmation audited and undoable; it beats model output and survives re-process", gaps: ["U07", "U11"] },
    { id: "B6", stage: "before", title: "Send the suggested requests", actors: ["treating"], involved: ["supporting"], engine: ["rules", "people"], what: "Each gap shows 'Notify <department>' with a draft: patient, UHID, IP / OP No., treating department, record, what is missing, accession and stage in the HIS, due date. The doctor edits and sends in-app, or Open in mail / Copy draft. 'Notify a department' writes a free request. Nothing is sent automatically.", screen: "Requests to departments card; Notify dialog", checkpoint: "Every send audited", gaps: ["G12", "G31", "U01"] },
    { id: "B7", stage: "before", title: "Department answers the request", actors: ["supporting"], engine: ["people"], what: "Bell and inbox; Acknowledge; the report is completed and signed in the department's own RIS / LIS / PACS (demo: the mock desk 'Complete and sign'); Done with an optional note. The owner hears both.", screen: "Department inbox, supporting home; mock /desk outside Vaidyx", checkpoint: "", gaps: ["G20", "G10", "U03"] },
    { id: "B8", stage: "before", title: "Re-fetch", actors: ["treating"], involved: ["system"], engine: ["his", "rules"], what: "Pulls only versions changed since the last fetch, files them, keeps the superseded version as history, re-runs the check; requests whose record now arrives final and signed close themselves; the owning department is told. No background polling.", screen: "Re-fetch (appears twice on the Pre-Authorization tab)", checkpoint: "", gaps: ["G21", "U03"] },
    { id: "B9", stage: "before", title: "Outside reports", actors: ["treating"], involved: ["records"], engine: ["qwen", "ocr", "rules"], what: "Reports from other hospitals or private labs are uploaded by the treating doctor, labelled 'outside report', read through the V1 pipeline (OCR, Aadhaar masking, patient matching).", screen: "Outside reports / Add documents card", checkpoint: "A name-only match counts only after the doctor confirms the patient", gaps: [] },
    { id: "B10", stage: "before", title: "Referral when the diagnosis changes", actors: ["treating"], engine: ["people", "rules"], what: "Owner refers to another treating department with a reason (the HIS's own referral is shown as a suggestion). Receiver accepts (choosing the new protocol) or declines. On accept ownership moves, the earlier check is kept read-only, the referring department stays a participant, the new check runs on the same records.", screen: "Ownership and referral card; inbox Referrals; Accept dialog", checkpoint: "Every step audited", gaps: ["U03"] },
    { id: "B11", stage: "before", title: "Two primaries", actors: ["treating"], engine: ["rules"], what: "A second cancer of the same UHID gets its own Case File, linked both ways; the site words of each protocol prefer the right biopsy for each Case File.", screen: "Case File header: Linked Case File", checkpoint: "", gaps: [] },
    { id: "B12", stage: "before", title: "Participating departments", actors: ["treating"], engine: ["people"], what: "The owner adds departments that read the Case File (and are promised to comment).", screen: "Ownership and referral card", checkpoint: "", gaps: ["G08"] },
    { id: "B13", stage: "before", title: "Case File summary", actors: ["treating"], involved: ["ai", "resident"], engine: ["gemma", "rules"], what: "Once every check is met: 10 to 18 cited sentences in the six NCG Virtual Tumour Board sections, stage only as recorded, Points for review. Stale banner when the Case File changes. Export the NCG VTB template (.pptx).", screen: "Case File summary tab", checkpoint: "AI draft until a person marks it reviewed or flags it", time: "24 to 34 s", gaps: ["G09", "K02"] },
    { id: "B14", stage: "before", title: "Mark ready for the board", actors: ["treating"], involved: ["coordinator"], engine: ["people"], what: "The owning department marks the Case File ready (optional note); the coordinator is told.", screen: "Case File header", checkpoint: "Audited", gaps: [] },
    { id: "B15", stage: "before", title: "Readiness and chasing", actors: ["coordinator"], involved: ["treating", "supporting"], engine: ["rules"], what: "Per board date: ready, on track, at risk, blocked, not listed, with the chase list per department. Remind a department (on behalf of the owner) or Remind owner (everything still open).", screen: "Coordinator home; Board sessions", checkpoint: "", gaps: ["G23", "U17"] },
    { id: "B16", stage: "before", title: "Build the session agenda", actors: ["coordinator"], involved: ["chair"], engine: ["people"], what: "New board session: date, title, the candidate Case Files (owner, ready mark, check result, summary state). A Case File added unmarked is minuted as 'not marked ready by the owner'.", screen: "Board sessions: New board session", checkpoint: "", gaps: ["G22", "G23", "G24"] },

    /* during */
    { id: "D1", stage: "during", title: "Attendance", actors: ["coordinator"], involved: ["boardheads"], engine: ["people"], what: "The four heads first (Radiology, Medical Oncology, Surgical Oncology, Pathology), then Radiation Oncology and Nuclear Medicine, the hospital's list and the owners. Present / absent / not marked; members by name.", screen: "Board room: Attendance", checkpoint: "An agent is never counted as a member", gaps: ["G13"] },
    { id: "D2", stage: "during", title: "Start: agents for absent heads", actors: ["coordinator"], involved: ["ai"], engine: ["gemma"], what: "Every head not recorded present gets its agent for every Case File on the agenda, in parallel; a current brief is reused. Surgical seat: Surgical Oncology or the Case File's own surgeon, else the agent.", screen: "Board room: AI support", checkpoint: "", time: "13 to 17 s per brief", gaps: ["K02"] },
    { id: "D3", stage: "during", title: "Present the case", actors: ["boardheads"], involved: ["resident", "treating", "coordinator"], engine: ["people", "his"], what: "The current Case File: summary, records with HIS status and signature (PDF fetched live if missing), Open images (OHIF through the app, 12 h grant, audited; people view, no model reads images), AI support briefs with Points for review.", screen: "Board room (collapses to one column below 1100 px)", checkpoint: "", gaps: ["G25", "K03", "U02"] },
    { id: "D4", stage: "during", title: "Questions to the Case File and agents", actors: ["boardheads"], involved: ["ai"], engine: ["gemma", "search"], what: "Ask the Case File (cited answers, 'not documented', refusals out of scope) and Ask an agent (live, 1.6 to 5.9 s). Value search finds a number on any page in about a millisecond.", screen: "Board room question box; Ask the Case File tab", checkpoint: "Every statement verified; refusals worded per scope", gaps: ["K01"] },
    { id: "D5", stage: "during", title: "Discuss and decide", actors: ["boardheads"], involved: ["chair", "nurse"], engine: ["people"], what: "The board discusses and decides. Vaidyx does not suggest a decision.", screen: "", checkpoint: "", gaps: ["G02"] },
    { id: "D6", stage: "during", title: "Record the decision", actors: ["coordinator"], involved: ["chair"], engine: ["people", "rules"], what: "The coordinator records the decision as dictated, with actions (department, due date); participants come from the attendance. PM-JAY composition check (empanelled hospitals). Adjudication runs at once.", screen: "Board room: Board decision (fewer fields than the Board tab form)", checkpoint: "", gaps: ["G03", "U03"] },
    { id: "D7", stage: "during", title: "Mark the agent's points", actors: ["coordinator"], engine: ["people"], what: "Each brief item, point for review, not-documented item and live answer: Discussed / Accepted / Not relevant. Reporting only; it does not measure accuracy.", screen: "Board room: Agent log", checkpoint: "", gaps: [] },
    { id: "D8", stage: "during", title: "Next case, close, minutes", actors: ["coordinator"], engine: ["rules"], what: "Time per case is kept. Close the session; Minutes (attendance with who stood in for whom, per Case File the decision, actions, surgical seat, PM-JAY result) and the agent log export.", screen: "Board room header", checkpoint: "", gaps: [] },

    /* after */
    { id: "A1", stage: "after", title: "Checks on the record (adjudication)", actors: ["system"], involved: ["ai"], engine: ["gemma", "rules"], what: "Required record fields, a correction mentioned but not logged, actions without department or due date, decision while checks open, values in the decision vs the sources (numbers and polarity), doses and radiotherapy schedules vs guideline references (India first), stage as written vs the signed report, PM-JAY composition, patient communication.", screen: "Board and follow-up tab", checkpoint: "Flags go to review; the AI checks the record, never the decision", gaps: [] },
    { id: "A2", stage: "after", title: "Resolve the flags", actors: ["coordinator"], involved: ["chair", "treating"], engine: ["people"], what: "Each review flag: Corrected (the decision is amended as a new version), Intentional deviation (reason), False alarm. The record counts as final when every flag is resolved.", screen: "Board and follow-up tab", checkpoint: "Audited, undoable", gaps: ["G03"] },
    { id: "A3", stage: "after", title: "Board actions to departments", actors: ["system"], involved: ["supporting", "treating"], engine: ["rules"], what: "Actions become requests in the Responsible Department's inbox (due date typed, or 14 days); a later report of the right type suggests closing it ('May be complete'); a person closes it.", screen: "Department inbox; Follow-up tracker", checkpoint: "", gaps: ["G04", "G28"] },
    { id: "A4", stage: "after", title: "Inform the patient", actors: ["coordinator"], involved: ["nurse", "patient", "treating"], engine: ["people"], what: "A follow-up 'inform the patient' task to the MDT Coordinator, due in 7 days; communication fields: informed date, key worker, intent, trial considered, consent.", screen: "Board and follow-up: Patient and communication", checkpoint: "", gaps: ["G15", "G29"] },
    { id: "A5", stage: "after", title: "Decision watch", actors: ["system"], involved: ["coordinator"], engine: ["rules"], what: "When a later amended report changes a value the decision cited, the coordinator is told once.", screen: "Notifications", checkpoint: "", gaps: [] },
    { id: "A6", stage: "after", title: "Follow-up, timeline, values over time", actors: ["coordinator"], involved: ["treating"], engine: ["rules"], what: "Pending / overdue / completed actions, longitudinal timeline, every verified numeric value with its report and quote in date order.", screen: "Board and follow-up tab", checkpoint: "", gaps: ["K09"] },
    { id: "A7", stage: "after", title: "Exports and registry", actors: ["coordinator"], involved: ["treating", "records"], engine: ["rules"], what: "FHIR R4 document bundle, HBCR registry abstract (cited), Case File JSON export, minutes.", screen: "Scattered: Pre-Authorization tab, Summary tab, Board room, dashboard", checkpoint: "", gaps: ["U03"] },
    { id: "A8", stage: "after", title: "Quality dashboard", actors: ["coordinator"], involved: ["admins"], engine: ["rules"], what: "Readiness, requests, attendance, decisions and follow-up against published standards; date range; CSV.", screen: "Quality dashboard", checkpoint: "Counts only, no clinical judgement", gaps: [] },
    { id: "A9", stage: "after", title: "PM-JAY treatment plan (on hold)", actors: [], involved: ["pmjay", "treating"], engine: ["people"], what: "Annexure 1 export waits for the form (V1 7.5). PM-JAY needs a tumour board decision for every cancer package.", screen: "Not built", checkpoint: "", gaps: ["G16"] }
  ],

  /* ---------------------------------------------------------------- click paths in today's UI */
  journeys: [
    { id: "J1", role: "treating", title: "Create a Case File from a UHID and get it ready", steps: [
      "Home: + Create from UHID (or side panel + New)", "Type the UHID, Look up, tick the patient (duplicate warning if any)", "Pick protocol, setting, level, window, department, board date; Create",
      "Pre-Authorization tab opens; fetch progress shows inside the upload card in the right column", "Requests to departments: Notify Radiology, edit the draft, Send in-app",
      "Later: the bell shows Acknowledged, then Done with a re-fetch hint", "Press Re-fetch; the request closes itself", "Case File summary tab: Compile (24 to 34 s)", "Header: Mark ready for the board"],
      friction: ["Progress shows far from where the user is looking", "Two Re-fetch buttons", "Must remember to re-fetch after Done", "Three long paragraphs before the first button"] },
    { id: "J2", role: "supporting", title: "Answer a request", steps: [
      "Home (supporting), bell or Department inbox: Acknowledge", "Leave Vaidyx (no link) and open the RIS / LIS (demo: 127.0.0.1:7130/desk/RAD)",
      "Find the accession, Complete and sign, pick the consultant", "Back in the inbox: Done (a browser prompt asks for a note)", "Closes only when the treating side re-fetches"],
      friction: ["Native prompt() for the note", "Two systems, no deep link", "The request looks open until someone else acts"] },
    { id: "J3", role: "coordinator", title: "Build a session and run the Board room", steps: [
      "Home readiness or Board sessions: chase list, Remind / Remind owner", "New board session: date, title, tick candidates, Create (if nobody marked ready, every listed Case File is ticked)",
      "Attendance: one select per department, add members (each change re-renders)", "Start session; briefs poll every 3 s", "Pick the current Case File; read summary and records; Open images; ask an agent",
      "Board decision: Record decision and run adjudication", "Mark agent points", "Next case; Close session (native confirm); Minutes and Export"],
      friction: ["No presenter view for the big screen", "Decision form in the room lacks members, consent and key worker", "Scroll and open sections lost on each re-render"] },
    { id: "J4", role: "root", title: "First set-up of the hospital", steps: [
      "Home: First set-up card (name, NCG level, PM-JAY), Save", "Open the organisation; save each card separately: Hospital settings and board lists, HIS connection, Departments and emails, Routes",
      "New login: login, password, name, department admin of, doctor or head of, coordinator / root checkboxes; Create login", "Edit an account; Save accounts and roles"],
      friction: ["One long page of separate save buttons", "Live org.json: hospital name empty, first set-up never answered"] },
    { id: "J5", role: "deptadmin", title: "Add a doctor", steps: ["Home: Manage doctors (or top bar My department)", "New doctor login: login, password, name, role; Create and place", "Role select and Disable apply at once (no confirmation)"], friction: ["No undo, no confirmation on Disable", "Password reset needs the Vaidyx admin"] },
    { id: "J6", role: "treating", title: "Refer a Case File", steps: [
      "Owner: Pre-Authorization tab, Ownership card, Refer to another department (or the HIS suggestion Refer), department and reason, Send",
      "Receiver: bell, inbox Referrals or treating home: Accept, choose protocol, Accept and list", "Gate re-runs as a job; the earlier check stays read-only"],
      friction: ["Referral controls in three places", "Decline sends the user back to the welcome page"] },
    { id: "J7", role: "coordinator", title: "Record the decision and resolve flags", steps: [
      "Board and follow-up tab: fill the record form (17 fields), Save record and run adjudication", "Each flag: Corrected (value) / Intentional deviation (reason) / False alarm, Record resolution",
      "Record communication with the patient", "Follow-up tracker: Mark completed (native prompt)"],
      friction: ["Only the coordinator can do clinical corrections", "17 fields with free-text 'Recorded by' though the user is logged in"] }
  ],

  /* ---------------------------------------------------------------- permission matrix (code, 16 Oct) */
  matrixCols: [
    { id: "vx", label: "Vaidyx admin" }, { id: "root", label: "Root admin" }, { id: "da", label: "Dept admin" }, { id: "co", label: "MDT Coordinator" },
    { id: "to", label: "Treating, owner dept" }, { id: "tx", label: "Treating, other dept" }, { id: "sa", label: "Supporting, asked" },
    { id: "sx", label: "Supporting, not asked" }, { id: "pa", label: "Participant dept" }, { id: "un", label: "Unplaced login" }
  ],
  matrixCodes: {
    Y: "Yes, on any Case File", O: "Only the owning department's doctors", D: "Own department only", L: "Limited: only the items it was asked about",
    U: "Only on Case Files with no owner (V1 demo files, intake new cases)", R: "Opens it; Case Files it may not read show as restricted", N: "No", "-": "Not applicable"
  },
  matrix: [
    { stage: "setup", action: "Organisation, accounts, HIS, skills, connectors", key: "manage_org", cells: "Y Y N N N N N N N N", note: "The Connectors button shows only for a Vaidyx admin, though the root admin holds the right." },
    { stage: "setup", action: "Doctor logins of a department", key: "manage_department", cells: "Y Y D N N N N N N N", note: "" },
    { stage: "before", action: "Open a Case File", key: "read_case", cells: "Y N N Y Y U L U Y N", note: "Root and department admins cannot open any Case File. Owner-less Case Files open fully to every placed account." },
    { stage: "before", action: "Create a Case File, HIS lookup, set owner", key: "create_case", cells: "Y N N Y D D N N - N", note: "" },
    { stage: "before", action: "List for a board date", key: "list_case", cells: "Y N N Y O N N N N N", note: "" },
    { stage: "before", action: "Upload, re-fetch, link registrations, fetch older, re-process", key: "upload_to_case", cells: "Y N N U O U N N N N", note: "" },
    { stage: "before", action: "Confirm (attest, dates, type, value), dismiss failed", key: "confirm", cells: "Y N N N O U N N N N", note: "Rule also lets the uploading department confirm its own upload, but supporting departments no longer upload and the limited view cannot reach it." },
    { stage: "before", action: "Waive a required record", key: "waive", cells: "Y N N N O U N N N N", note: "Reason required." },
    { stage: "before", action: "Send, write or close requests", key: "send_request", cells: "Y N N N O U N N N N", note: "" },
    { stage: "before", action: "Acknowledge / Done a request", key: "answer_request", cells: "Y N N D N D D N N N", note: "Coordinator only for rows addressed to the coordinator. A record routed to 'owner' asks the owner itself." },
    { stage: "before", action: "Remind", key: "remind", cells: "Y N N Y O N N N N N", note: "" },
    { stage: "before", action: "Refer, withdraw, dismiss HIS suggestion", key: "refer", cells: "Y N N N O N N N N N", note: "" },
    { stage: "before", action: "Accept / decline a referral", key: "answer_referral", cells: "Y N N N N D N N N N", note: "Doctors of the receiving department." },
    { stage: "before", action: "Add participants", key: "manage_participants", cells: "Y N N N O N N N N N", note: "" },
    { stage: "before", action: "Mark ready for the board", key: "mark_ready", cells: "Y N N N O N N N N N", note: "" },
    { stage: "before", action: "Compile the summary", key: "summary", cells: "Y N N Y O N N N N N", note: "" },
    { stage: "before", action: "Mark AI drafts reviewed / flag for correction", key: "review", cells: "Y N N Y Y U N U Y N", note: "Not tied to the specialty: any placed reader with full scope." },
    { stage: "before", action: "Needs matching queue", key: "match", cells: "Y N N Y N N N N N N", note: "" },
    { stage: "before", action: "Delete a Case File", key: "delete_case", cells: "Y N N Y N N N N N N", note: "The owner cannot delete its own Case File." },
    { stage: "before", action: "Remove a document", key: "delete_document", cells: "Y N N U O U N N N N", note: "Also the head of the uploading department for its own upload." },
    { stage: "during", action: "Create and run a session (attendance, start, close)", key: "session", cells: "Y N N Y N N N N N N", note: "" },
    { stage: "during", action: "Open the Board room", key: "may_open", cells: "Y N N Y R R R R R N", note: "Opens for departments on the attendance sheet (six by default) and readers of an agenda Case File." },
    { stage: "during", action: "Ask an agent in the session", key: "ask", cells: "Y N N Y Y U N U Y N", note: "" },
    { stage: "during", action: "Record decision, mark points, resolve flags, communication", key: "board_record", cells: "Y N N Y N N N N N N", note: "Coordinator only: the plan's role table gave board actions to the treating doctor." },
    { stage: "after", action: "Close or complete board actions", key: "update_action", cells: "Y N N Y D D D D N N", note: "No owner scoping: a receiving department can also mark a Pre-Authorization request completed." },
    { stage: "after", action: "Exports (JSON, NCG VTB, FHIR, registry)", key: "export", cells: "Y N N Y Y U N U Y N", note: "" },
    { stage: "after", action: "Quality dashboard", key: "dashboard", cells: "Y N N Y N N N N N N", note: "No read-only quality role." },
    { stage: "after", action: "Receive notifications", key: "notify", cells: "Y N N Y D D D D D N", note: "Department and root admins never receive any." }
  ],

  /* ---------------------------------------------------------------- notifications */
  notifications: [
    { kind: "request", to: "The department asked (or the coordinator)", when: "The owner sends a request or a free request" },
    { kind: "request_reminder", to: "The department holding a sent request", when: "Remind" },
    { kind: "owner_reminder", to: "Owning department", when: "Reminder about an unsent suggestion, or Remind owner" },
    { kind: "request_acknowledged / request_done", to: "Owning department (or the sender)", when: "The department acknowledges / sends Done" },
    { kind: "request_closed", to: "The department that received it", when: "Check met, waived, not needed, moved or returned, referral, owner closed a free request. Also reused for the owner's re-fetch result" },
    { kind: "case_ready", to: "Coordinator", when: "The check passes for the first time" },
    { kind: "board_ready", to: "Coordinator", when: "The owner marks ready" },
    { kind: "board_action", to: "Action's department, or the coordinator", when: "A decision with actions; the inform-the-patient task" },
    { kind: "board_action_suggestion", to: "Action's department", when: "A new document may close an action" },
    { kind: "decision_value_changed", to: "Coordinator", when: "A later report changed a value the decision cited" },
    { kind: "case_shared / case_unshared", to: "That department", when: "Participant added or removed" },
    { kind: "referral", to: "Receiving department", when: "Referral requested" },
    { kind: "referral_answered", to: "Receiving (withdraw) or referring department (decline, accept)", when: "Referral answered" }
  ],

  /* ---------------------------------------------------------------- AI and human checkpoints */
  ai: [
    { stage: "before", what: "Reading scans", engine: "qwen", out: "Two transcriptions + Tesseract; disagreeing numbers become uncertain spans", user: "'from scan (OCR)' chip; boxes on the page image" },
    { stage: "before", what: "Classify document", engine: "qwen", out: "Type (21), title, department, region, signer", user: "Type chip; keyword or HIS code disagreement asks Confirm type" },
    { stage: "before", what: "Status, signature, dates, identity", engine: "rules", out: "FINAL / PRELIMINARY / ..., signed, report and event dates, match", user: "Status chips; Confirm date / patient" },
    { stage: "before", what: "Extract required fields", engine: "qwen", out: "value + verbatim quote per field", user: "Verified fields with quote and page; needs review in violet" },
    { stage: "before", what: "Pre-Authorization check, requests, discordances, readiness", engine: "rules", out: "Statuses per record; suggested requests; disagreeing reports", user: "Gate rows, Notify buttons, Reports that disagree" },
    { stage: "before", what: "Case File summary", engine: "gemma", out: "6 NCG sections of cited sentences, Points for review, stage as recorded", user: "Summary tab, stale banner, review bar" },
    { stage: "during", what: "Specialty briefs", engine: "gemma", out: "Sections, Points for review with Indian references, not documented", user: "Board room AI support card; Specialty support tab" },
    { stage: "during", what: "Ask the Case File / ask an agent", engine: "gemma", out: "Cited statements or 'not documented' or a scope refusal", user: "Answer box with citations; removed items for reviewers" },
    { stage: "during", what: "Value search, guideline references", engine: "search", out: "Lines with values; guideline passages, India first", user: "Instant results; reference chips" },
    { stage: "after", what: "Adjudication value list, dose / RT / stage check", engine: "gemma", out: "Claims with spans; code compares numbers with sources and references", user: "Flags to resolve on the Board tab" }
  ],
  checkpoints: [
    { name: "Attest final", who: "Owner's treating doctors", when: "No status or signature line", reason: false },
    { name: "Waive", who: "Owner's treating doctors", when: "Any unmet record", reason: true },
    { name: "Confirm dates / type", who: "Owner's treating doctors", when: "Date decides a check; type disagreement", reason: false },
    { name: "Confirm patient match", who: "Coordinator (queue) or treating doctor (outside report)", when: "Name-only match", reason: false },
    { name: "Dismiss failed document", who: "Owner's treating doctors", when: "A document failed to read and blocks the check", reason: true },
    { name: "Confirm a critical value from a scan", who: "Owner's treating doctors", when: "PD-L1, EGFR, ALK, ROS1, ER, PR, HER2, Ki-67, MMR, RAS / BRAF, stage, FIGO", reason: false },
    { name: "Note a discordance", who: "Owner's treating doctors", when: "Two reports disagree", reason: false },
    { name: "Review AI draft (reviewed / flag)", who: "Any placed reader", when: "Summary, briefs", reason: false },
    { name: "Mark agent points", who: "Coordinator", when: "After the decision", reason: false },
    { name: "Resolve adjudication flag", who: "Coordinator", when: "Review or expert-review flags", reason: true }
  ],

  /* ---------------------------------------------------------------- screens today */
  screens: [
    { name: "Home (per role)", who: "Everyone placed", what: "One section per role: treating, supporting, coordinator, department admin, root admin; 3 steps to start; notifications" },
    { name: "Case File: Pre-Authorization", who: "Owner, participants, coordinator", what: "HIS card, ownership and referral, the check (Level 1, Level 2, met, shown), requests, outside reports, discordances, confirmations" },
    { name: "Case File: Documents", who: "Same", what: "Records grouped by OP visit / IP admission, chips, Open images, primary fields across the Case File" },
    { name: "Case File: Ask the Case File", who: "Same", what: "Question box, cited answers, instant value search, guideline search" },
    { name: "Case File: Specialty support", who: "Same", what: "Six agents, Prepare brief, review bar" },
    { name: "Case File: Case File summary", who: "Same", what: "Compile, stale banner, Print, Export .pptx, guideline references" },
    { name: "Case File: Board and follow-up", who: "Same (form: coordinator)", what: "Record form with 17 fields, flags, communication, follow-up, values over time, timeline" },
    { name: "Case File: Audit", who: "Same", what: "Hash-chain chip, up to 400 events with raw JSON" },
    { name: "Board sessions", who: "Coordinator; doctors see what they may read", what: "New session form, agenda readiness and chase list, sessions table" },
    { name: "Board room", who: "Coordinator, departments on the sheet", what: "Agenda, attendance, patient card, summary, records, AI support, decision, follow-up, agent log" },
    { name: "Department inbox", who: "Department doctors", what: "Referrals, requests per department with Acknowledge / Done" },
    { name: "Needs matching", who: "Coordinator (button shows to others too)", what: "Unmatched records: file, new Case File, not this patient, discard" },
    { name: "Quality dashboard", who: "Coordinator, Vaidyx admin", what: "Before / during / after tiles and bars vs published standards; CSV" },
    { name: "Organisation", who: "Root admin", what: "Hospital settings, HIS, departments, routes, accounts and roles, audit" },
    { name: "My department", who: "Department admin", what: "Doctors: role, disable, remove, new login" },
    { name: "Agent skills / Connectors / Model and data cards / Features / Glossary", who: "All (Connectors: Vaidyx admin)", what: "Modals" },
    { name: "Mock hospital: /his and /desk", who: "Demo only, no login", what: "Registration search, OP / IP timeline, referral; reporting desk: Complete and sign" }
  ],

  /* ---------------------------------------------------------------- gaps */
  gapCats: ["Access and roles", "Workflow", "Interface", "Backend that affects users"],
  gaps: [
    { id: "G01", cat: "Access and roles", sev: "high", title: "Case Files with no owner are open to everyone placed", detail: "Every placed account, supporting doctors included, gets full access, and any treating doctor may waive, confirm and send requests. The protected real-patient Case File on the internal app has no owner and shows in the side list of demo logins (tb-breast-doc, tb-mdt).", where: "access.py:131-132, 202-203", roles: ["treating", "supporting", "coordinator"] },
    { id: "G02", cat: "Access and roles", sev: "high", title: "No chair; nobody signs off the decision", detail: "Real boards have a chair who checks quorum, paces and confirms the recommendation. The code has no such role; the coordinator's record becomes final once flags are resolved.", where: "org.py ACTIONS", roles: ["chair", "coordinator", "boardheads"] },
    { id: "G03", cat: "Access and roles", sev: "high", title: "Coordinator holds every post-board clinical call", detail: "Only the coordinator records the decision, marks agent points and resolves dose or transcription flags as 'Corrected'. The plan said the coordinator does no clinical action and gave board actions to the treating doctor.", where: "org.py:151 board_record", roles: ["coordinator", "treating"] },
    { id: "G04", cat: "Access and roles", sev: "medium", title: "Owner is not told when the decision is recorded", detail: "Notifications go only to departments named in actions and to the coordinator.", where: "followup.py", roles: ["treating"] },
    { id: "G05", cat: "Access and roles", sev: "low", title: "Admins are blind", detail: "Root and department admins cannot open any Case File and receive no notifications (by design: no clinical access).", where: "org.py:715 known", roles: ["root", "deptadmin"] },
    { id: "G06", cat: "Access and roles", sev: "medium", title: "Root admin can give itself clinical roles", detail: "PUT /org accepts the caller's own entry; 'no clinical action' is a convention (audited).", where: "routes:472-490", roles: ["root"] },
    { id: "G07", cat: "Access and roles", sev: "low", title: "'Head' means two things", detail: "A department Head only adds deleting its own uploads; 'board heads' are departments at the board. Same word, different meanings.", where: "org.py:152", roles: ["treating", "supporting", "boardheads"] },
    { id: "G08", cat: "Access and roles", sev: "medium", title: "Participants cannot comment", detail: "Promised as 'read and comment'; no comment feature exists.", where: "access.py", roles: ["participant"] },
    { id: "G09", cat: "Access and roles", sev: "medium", title: "Anyone can mark an AI draft reviewed", detail: "Expert review of summary and briefs is open to any placed reader, not tied to the matching specialty.", where: "org.py:164 review", roles: ["treating", "coordinator", "ai"] },
    { id: "G10", cat: "Access and roles", sev: "medium", title: "Receiving department can mark a request completed", detail: "update_action has no owner scoping; this bypasses 'closes itself when the record arrives'.", where: "routes:1351-1373", roles: ["supporting"] },
    { id: "G11", cat: "Access and roles", sev: "medium", title: "Treating departments that are asked see only counts", detail: "Pulmonology (bronchoscopy) or Medical Gastroenterology (endoscopy) get request rows only on the supporting home, which they do not have.", where: "home.py", roles: ["treating"] },
    { id: "G12", cat: "Access and roles", sev: "low", title: "Some requests go to the owner itself", detail: "Records with route 'owner' (clinical history) make the owner send and answer its own request.", where: "protocols/*.json route owner", roles: ["treating"] },
    { id: "G13", cat: "Access and roles", sev: "low", title: "Every session opens to six departments", detail: "Heads and on-demand specialties are always on the sheet, so their doctors open every room (restricted rows for the rest).", where: "board.py:481-498", roles: ["supporting", "boardheads"] },
    { id: "G14", cat: "Access and roles", sev: "medium", title: "Residents share the consultant's login", detail: "Per Eswar this is outside our control, but the audit cannot tell who did what and there is no draft-only role.", where: "changes_v2 §4", roles: ["resident", "treating"] },
    { id: "G15", cat: "Access and roles", sev: "medium", title: "No nurse navigator / key worker", detail: "The inform-the-patient task goes to the coordinator; 'key worker' is free text.", where: "followup.py:152", roles: ["nurse", "coordinator"] },
    { id: "G16", cat: "Access and roles", sev: "medium", title: "No PM-JAY desk role; Annexure 1 on hold", detail: "PM-JAY needs the board's plan for pre-authorisation; the form was never obtained.", where: "V1 7.5", roles: ["pmjay"] },
    { id: "G17", cat: "Access and roles", sev: "low", title: "Disabling is global", detail: "A disabled flag blocks all Tumour Board access, not per department.", where: "org.py", roles: ["deptadmin"] },
    { id: "G18", cat: "Access and roles", sev: "low", title: "Connectors button only for Vaidyx admin", detail: "The root admin holds the right but the UI hides the button.", where: "tb.js:1628", roles: ["root", "vaidyxadmin"] },

    { id: "G20", cat: "Workflow", sev: "high", title: "Supporting departments work in two systems", detail: "Acknowledge in Vaidyx, sign in the RIS / LIS (no link), Done in Vaidyx; the request closes only after the treating side re-fetches.", where: "dept_requests.py, his_mock/desk.py", roles: ["supporting", "treating"] },
    { id: "G21", cat: "Workflow", sev: "medium", title: "Re-fetch is manual only", detail: "No background polling: the owner must remember to press Re-fetch after a Done.", where: "his_case.py", roles: ["treating"] },
    { id: "G22", cat: "Workflow", sev: "medium", title: "Unready Case Files get ticked for the session", detail: "When no owner marked any Case File ready, every listed one is ticked automatically.", where: "board.py candidates", roles: ["coordinator"] },
    { id: "G23", cat: "Workflow", sev: "medium", title: "No agenda cut-off or late-addition rule", detail: "Research: agenda out 48 h before (Victoria); late additions approved by chair, pathologist, radiologist.", where: "", roles: ["coordinator", "chair"] },
    { id: "G24", cat: "Workflow", sev: "medium", title: "No triage of cases", detail: "NHS 2020: 'for discussion' vs 'standard of care, not for discussion'; Greater Manchester adds 'not ready'. Clinicians decide; the AI only shows completeness.", where: "", roles: ["coordinator", "chair"] },
    { id: "G25", cat: "Workflow", sev: "high", title: "No presenter view for the room screen", detail: "The Board room is a dense working page; below 1100 px it becomes one long column.", where: "tb.js renderRoom", roles: ["boardheads", "coordinator", "resident"] },
    { id: "G27", cat: "Workflow", sev: "medium", title: "Two different decision forms", detail: "The Board tab form has members, key worker and consent; the Board room form does not.", where: "tb.js decisionHTML, renderBoard", roles: ["coordinator"] },
    { id: "G28", cat: "Workflow", sev: "medium", title: "No 'send the outcome' step", detail: "Research: outcome to the treating team within 1 working day, GP / referrer within a week.", where: "", roles: ["treating", "coordinator"] },
    { id: "G29", cat: "Workflow", sev: "medium", title: "Patient preference and consent only after the board", detail: "NHS: a preference against the standard means the case must be discussed; it should be known before.", where: "postboard.py communication", roles: ["patient", "nurse"] },
    { id: "G31", cat: "Workflow", sev: "low", title: "Request draft names the latest OP visit", detail: "Not the visit the record was ordered under (Parking lot, Phase 8 review).", where: "changes_v2 §15", roles: ["treating", "supporting"] },

    { id: "U01", cat: "Interface", sev: "high", title: "Text-heavy screens", detail: "Long paragraphs in cards, then a help line with Learn more, then long tooltips: the same thing explained three times.", where: "tb.js L227, L2098, L2359", roles: ["treating", "supporting", "coordinator"] },
    { id: "U02", cat: "Interface", sev: "high", title: "Phone pages are very long", detail: "Case File page about 9,500 px tall at 390 px width; supporting home about 7,000 px; side list hidden behind a button.", where: "screenshots 16 Oct", roles: ["treating", "supporting"] },
    { id: "U03", cat: "Interface", sev: "medium", title: "Duplicated controls", detail: "Re-fetch twice on one tab; Acknowledge / Done in three places; referral answers in three; two Request message dialogs; exports on four screens; 'Open the department inbox' four times.", where: "", roles: ["treating", "supporting", "coordinator"] },
    { id: "U04", cat: "Interface", sev: "low", title: "Help text points to the wrong place", detail: "Features and help say exports are on the Documents tab (they are on Summary and Pre-Authorization); glossary Level 1 / 2 contradicts the code.", where: "tb.js L2825, L2840, L2882", roles: [] },
    { id: "U05", cat: "Interface", sev: "medium", title: "Inconsistent names for the same thing", detail: "Ready / Ready for the board / Readiness criteria met / Pre-Authorization met; Mark completed / Done / Close; Re-check / Re-process / Re-fetch / Read again; Dismiss means three things; member vs doctor.", where: "", roles: [] },
    { id: "U06", cat: "Interface", sev: "medium", title: "Three date formats; 'today' in UTC", detail: "16 Oct 2026, 16/10/2026 and 2026-10-16 14:30 mixed; date pickers follow the browser locale (MM/DD/YYYY seen); 'today' wrong between midnight and 05:30 IST.", where: "tb.js fmtDate, dmy, L1367, L2357", roles: [] },
    { id: "U07", cat: "Interface", sev: "medium", title: "Destructive actions without confirmation", detail: "Remove waiver, remove member, Disable, role change, Undo, department or connector delete act at once; Remove document uses a bare confirm() with no reason.", where: "", roles: [] },
    { id: "U08", cat: "Interface", sev: "medium", title: "Errors and loading", detail: "Many handlers have no error handling (a spinner can stay forever); toast only, no aria-live; double submit possible on Save record, Create, Re-check.", where: "", roles: [] },
    { id: "U09", cat: "Interface", sev: "medium", title: "Every action reloads the whole Case File", detail: "Scroll position and opened sections are lost after each click.", where: "openCase", roles: [] },
    { id: "U10", cat: "Interface", sev: "medium", title: "Accessibility", detail: "Modals have no dialog role or focus trap; clickable rows not reachable by keyboard; tabs not a tablist; chips by colour only; inputs without labels.", where: "", roles: [] },
    { id: "U11", cat: "Interface", sev: "low", title: "Browser confirm() and prompt() dialogs", detail: "11 confirm() and 3 prompt() calls (Done note, Mark completed, discordance note).", where: "", roles: ["supporting", "coordinator"] },
    { id: "U12", cat: "Interface", sev: "low", title: "Polling", detail: "The whole inbox is fetched every 30 s just for a count; job polling never times out; nothing pauses in a hidden tab.", where: "tb.js L2945", roles: [] },
    { id: "U13", cat: "Interface", sev: "low", title: "Hard-coded content", detail: "Ask examples (PD-L1, CEA) for every cancer; a fixed department list for members and actions; inline colours.", where: "tb.js L1119, L1308", roles: [] },
    { id: "U14", cat: "Interface", sev: "low", title: "Audit tab shows raw JSON", detail: "Internal event names such as llm_call.", where: "renderAudit", roles: ["coordinator"] },
    { id: "U16", cat: "Interface", sev: "medium", title: "Seven tabs and jargon on every row", detail: "Level 1 / 2, NCG tier chips, accession chips, without plain words for a first-time doctor.", where: "", roles: ["treating"] },
    { id: "U17", cat: "Interface", sev: "medium", title: "Notification flood", detail: "The coordinator had 536 unread notifications; no grouping, filter or digest.", where: "screenshot 16 Oct", roles: ["coordinator"] },
    { id: "U18", cat: "Interface", sev: "medium", title: "Case File list has no search", detail: "Names written two ways ('SYNTHETIC, Lakshmi Iyer' vs 'Priya Venkatesan (SYNTHETIC)'); demo and real files mixed; 'Needs matching' shown to users who cannot match.", where: "loadCases", roles: ["treating", "coordinator"] },
    { id: "U19", cat: "Interface", sev: "low", title: "Status shown three times", detail: "'FINAL · signed' + 'Final' + 'Digitally signed' on one row.", where: "docChips, hisStatusChips", roles: [] },
    { id: "U21", cat: "Interface", sev: "medium", title: "One 376 KB script; tests tied to ids and labels", detail: "Any redesign must update tumour_board/eval/ui_test.py together with the UI.", where: "static/tb/tb.js", roles: [] },

    { id: "K01", cat: "Backend that affects users", sev: "medium", title: "Scope classifier fails open", detail: "If the reasoner is unavailable, the input classifier lets the question through (the regex layer still applies).", where: "guardrails.py:63-64", roles: ["ai"] },
    { id: "K02", cat: "Backend that affects users", sev: "medium", title: "Slow AI steps need progress feedback", detail: "Summary 24 to 34 s, brief 13 to 17 s, question median 6 s (7.9 s under load); the GPU is power-capped at 300 W.", where: "DESIGN.md", roles: ["treating", "coordinator"] },
    { id: "K03", cat: "Backend that affects users", sev: "low", title: "Image grants lost on restart", detail: "Kept in memory; OHIF's study list is refused, so another study needs another Open images.", where: "pacs.py", roles: ["boardheads"] },
    { id: "K04", cat: "Backend that affects users", sev: "low", title: "Interrupted jobs", detail: "A restart leaves jobs 'interrupted'; jobs older than 24 h are dropped.", where: "service.py", roles: [] },
    { id: "K06", cat: "Backend that affects users", sev: "high", title: "Passwords exposed", detail: "Run logs (docs_Eswar/runs/v2_round_27) hold the Vaidyx admin, tb-root and tb-mdt passwords; demo passwords also appeared in tool output on 16 Oct. Rotate them.", where: "", roles: ["vaidyxadmin"] },
    { id: "K07", cat: "Backend that affects users", sev: "low", title: "Live app not set up", detail: "Hospital name empty, first set-up never answered, demo leftovers (TB-DEMO-*, sessions) on the app.", where: "data/tumour_board/org.json", roles: ["root"] },
    { id: "K08", cat: "Backend that affects users", sev: "low", title: "Re-fetch result reuses 'request_closed'", detail: "Different events share one notification kind.", where: "his_case.py:666", roles: [] },
    { id: "K09", cat: "Backend that affects users", sev: "medium", title: "Overdue never notifies", detail: "Overdue is worked out only when a page is shown.", where: "notify.py", roles: ["coordinator", "supporting"] }
  ],

  /* ---------------------------------------------------------------- ideas (to discuss, nothing decided) */
  ideas: [
    { id: "I01", stage: "during", title: "Presenter mode for the room screen", detail: "One case per screen, large type, the board question, key values with sources one click away, gap badges, a case timer (3 to 6 min), a chair panel with quorum.", from: "Research: NAVIFY, Epic, CRUK timings" },
    { id: "I02", stage: "during", title: "A chair role", detail: "Confirms the decision as recorded, approves late additions, sees quorum.", from: "Victoria framework, NHS" },
    { id: "I03", stage: "before", title: "A resident / PG role", detail: "Prepares the Case File and summary as drafts; the consultant approves; the audit shows both names.", from: "Hartmann 2026; Eswar: PGs use the lead's login" },
    { id: "I04", stage: "after", title: "A nurse navigator / key worker role", detail: "Owns 'inform the patient' tasks, consent and preference, in the patient's language.", from: "NICE key worker; Greater Manchester 2 working days" },
    { id: "I05", stage: "before", title: "Triage lists before the board", detail: "For discussion / not ready / for noting, assigned by clinicians; the AI only shows completeness, never says 'standard of care'.", from: "NHS Streamlining MDTs 2020" },
    { id: "I06", stage: "before", title: "Agenda cut-off and late additions", detail: "Lock the agenda about 48 h before; a late addition needs a recorded approval.", from: "Victoria framework" },
    { id: "I07", stage: "before", title: "Board question and patient preference before listing", detail: "A short required block: the question for the board, patient preference, consent to discussion.", from: "Greater Manchester pro-forma; Wihl 4.2%" },
    { id: "I08", stage: "before", title: "Specialist confirmation before the meeting", detail: "Radiologist / pathologist confirm 'report signed' or 'addendum pending' asynchronously, given low attendance (46.7% / 28.5%).", from: "ICMR-NCDIR survey" },
    { id: "I09", stage: "after", title: "Send the outcome", detail: "Outcome to the treating team within 1 working day; named person informs the patient within 2 working days.", from: "Greater Manchester, Victoria" },
    { id: "I10", stage: "after", title: "Tell the owner; one-page decision", detail: "Notify the owning department when the decision is recorded; a printable one-page record for the paper file.", from: "Gap G04; 63.5% paper records" },
    { id: "I11", stage: "after", title: "PM-JAY pack and desk view", detail: "Signed decision plus the package's document checklist; a non-clinical status view for the Arogya Mitra / MEDCO.", from: "NHA process flow; Gujarat SOP 2024" },
    { id: "I12", stage: "before", title: "Phone-first views for supporting doctors", detail: "Inbox, request detail and Done in a few taps.", from: "Gap U02" },
    { id: "I13", stage: "before", title: "Grouped notifications and overdue reminders", detail: "Group by Case File and kind, filters, a daily digest; notify when a request becomes overdue.", from: "Gaps U17, K09" },
    { id: "I14", stage: "before", title: "Deep link to the department's own system", detail: "From the request straight to the order in the RIS / LIS (where the hospital allows).", from: "Gap G20" },
    { id: "I15", stage: "before", title: "One-click re-fetch on Done", detail: "When a department sends Done, the owner gets 'Re-fetch now' in the notification itself.", from: "Gap G21" },
    { id: "I16", stage: "before", title: "A 'next step' card per Case File", detail: "Tells the user, in one line, what to do now (send 2 requests, re-fetch, compile summary, mark ready).", from: "Hartmann 2026: 55% of time on system interaction" },
    { id: "I17", stage: "throughout", title: "Plain names, one date format", detail: "One word per state, consistent verbs, DD/MM/YYYY everywhere, IST for 'today'.", from: "Gaps U05, U06" },
    { id: "I18", stage: "after", title: "De-identified NCG VTB export", detail: "The existing .pptx with a de-identified option for spoke centres.", from: "NCG VTB audit" },
    { id: "I19", stage: "after", title: "Plan versus treatment received", detail: "A yearly concordance check from the follow-up tracker.", from: "Greater Manchester; 6.9% to 19.5% of decisions not implemented" },
    { id: "I20", stage: "throughout", title: "Split the UI into modules per screen", detail: "Smaller files per screen, with the UI tests updated as screens change.", from: "Gap U21" }
  ],

  /* ---------------------------------------------------------------- research */
  research: {
    india: [
      { k: "79.7%", t: "of 172 NCRP hospitals have a functional tumour board (private 86.6%, public 72.5%)", src: 1 },
      { k: "73.7%", t: "meet in person; 24.8% hybrid; 1.5% fully virtual. 47.4% weekly", src: 1 },
      { k: "63.5%", t: "keep paper records only; 11.7% electronic only", src: 1 },
      { k: "48.2%", t: "have no system to follow up decisions", src: 1 },
      { k: "28.5%", t: "of boards have a pathologist attending; radiologist 46.7%; radiation oncologist 92.7%", src: 1 },
      { k: "52.5%", t: "have a designated secretariat (coordinator)", src: 1 },
      { k: "38.0%", t: "send a written summary to the treating doctor; 35.0% tell them verbally", src: 1 },
      { k: "4", t: "median cases per NCG Virtual Tumour Board session (19 centres); 74.5% of questions had no existing guideline", src: 2 },
      { k: "6 h", t: "for the insurer to decide a PM-JAY pre-authorisation; Annexure 1 treatment plan must be filled, signed and uploaded", src: 3 }
    ],
    intl: [
      { t: "NHS England 2020: every case either 'standard of care, not for discussion' or 'for discussion'; a minimum dataset; responsibility for accurate information lies with the referring clinician; quorate on 95% of meetings.", src: 4 },
      { t: "Greater Manchester 2023: a mandatory pro-forma (performance status, frailty, clinical question, specimen numbers and dates); actions with named owners; patient told within 2 working days.", src: 5 },
      { t: "Victoria: agenda 48 h before; chair decides representation and paces; a scribe records in real time; divergent views recorded with names; recommendations within 24 h.", src: 6 },
      { t: "CRUK 2017: more than half of patients discussed for 2 minutes or less.", src: 7 }
    ],
    products: [
      { name: "Roche NAVIFY Tumor Board", t: "One dashboard from EMR, PACS, pathology; meeting calendar; interactive presentation; preparation time cut 30%." },
      { name: "Philips IntelliSpace Precision Medicine Oncology", t: "Scheduling, case preparation, session management, patient timeline." },
      { name: "Epic", t: "Real-time capture during presentation; coordinator can stage the record." },
      { name: "Microsoft Healthcare Agent Orchestrator", t: "Agents for history, radiology, status, guidelines, trials; runs in Teams; research use only." },
      { name: "OncoLens", t: "Site-specific submission templates, phone app, automatic agenda, routing to radiology and pathology." },
      { name: "Navya (TMC / NCG)", t: "Online expert opinion matched to the right disease group." }
    ],
    ux: [
      { t: "Hartmann 2026 (think-aloud): 13 min per case, about 25 program switches, 55% of time on the system, summary rewritten 3.5 times.", src: 8 },
      { t: "Lajmi 2026: an editable LLM summary took 6:55 vs 8:47 min manual; 92% found it useful.", src: 9 },
      { t: "Prades 2022: hospital systems are built 'to store and classify information rather than to work with it'.", src: 10 }
    ],
    failures: [
      { t: "UK lung MDTs: quorate in 21% of meetings; 24% of cases deferred, mostly awaiting results; performance status available in 60%.", src: 11 },
      { t: "Decisions not implemented: 6.9% (breast) to 19.5%; main reasons comorbidity, new information, patient choice.", src: 12 },
      { t: "Patient preferences came up in 4.2% of discussions (Wihl).", src: 13 }
    ],
    sources: [
      { n: 1, t: "ICMR-NCDIR national tumour board survey, ecancer 2026", u: "https://pmc.ncbi.nlm.nih.gov/articles/PMC13161587" },
      { n: 2, t: "NCG Virtual Tumour Board head and neck audit, JCO Global Oncology 2023", u: "https://pmc.ncbi.nlm.nih.gov/articles/PMC10166436" },
      { n: 3, t: "NHA FAQ (tumour board concept, Annexure 1) and PM-JAY process flow at empanelled hospitals", u: "https://supportbeta.nha.gov.in/kb/faq.php?id=57" },
      { n: 4, t: "NHS England, Streamlining MDT meetings (2020)", u: "https://www.england.nhs.uk/wp-content/uploads/2020/01/multi-disciplinary-team-streamlining-guidance.pdf" },
      { n: 5, t: "Greater Manchester MDT standards (2023)", u: "https://gmcancer.org.uk/wp-content/uploads/2023/06/V3.0-GM-MDT-Standards-June-23.pdf" },
      { n: 6, t: "Victorian cancer MDM quality framework", u: "https://www.health.vic.gov.au/sites/default/files/migrated/files/collections/policies-and-guidelines/v/vic-cancer-mtm-quality-framework-pdf.pdf" },
      { n: 7, t: "Cancer Research UK 2017, MDT meetings under pressure", u: "https://news.cancerresearchuk.org/2017/01/11/expert-cancer-meetings-are-under-growing-pressure" },
      { n: 8, t: "Hartmann 2026, think-aloud study of tumour board preparation", u: "https://pmc.ncbi.nlm.nih.gov/articles/PMC12993274" },
      { n: 9, t: "Lajmi 2026, LLM summary vs manual", u: "https://pmc.ncbi.nlm.nih.gov/articles/PMC12863596" },
      { n: 10, t: "Prades 2022, ICT in MDTs", u: "https://pmc.ncbi.nlm.nih.gov/articles/PMC9540836" },
      { n: 11, t: "UK lung MDT efficiency", u: "https://pmc.ncbi.nlm.nih.gov/articles/PMC10166965" },
      { n: 12, t: "Decision implementation (breast 6.9%; 19.5%)", u: "https://dukespace.lib.duke.edu/items/8a3b45dc-40cd-4e9d-911a-817dc461678e/full" },
      { n: 13, t: "Wihl 2021, patient information in MDT discussions", u: "https://pmc.ncbi.nlm.nih.gov/articles/PMC7985788" },
      { n: 14, t: "Gujarat PM-JAY guidelines 2024 (three-oncologist certificate)", u: "https://www.newsonair.gov.in/gujarat-govt-issues-new-guidelines-for-pmjay-hospitals-to-prevent-irregularities" },
      { n: 15, t: "Roche NAVIFY preparation time (Hammer 2020)", u: "https://pmc.ncbi.nlm.nih.gov/articles/PMC7469605" }
    ],
    unverified: ["Who signs PM-JAY Annexure 1", "Tata Memorial's internal DMG workflow", "How much preparation residents do in India", "Whether WhatsApp is used to share cases"]
  },

  docs: [
    { t: "Plan V2 (source of truth for V2)", p: "docs_Eswar/changes_v2.md" },
    { t: "How Vaidyx-TB works today", p: "docs_Eswar/01_how_vaidyx_tb_works.md" },
    { t: "Plan V1 (finished)", p: "docs_Eswar/changes_v1.md" },
    { t: "Design decisions and measurements", p: "docs/tumour-board/DESIGN.md" },
    { t: "UI plan 15 Oct", p: "docs/tumour-board/UI_PLAN_OCT15.md" },
    { t: "V2 demo walkthrough", p: "docs/tumour-board/DEMO_V2.md" },
    { t: "Pre-Authorization checks for validation (PDF, 15 Oct)", p: "docs/tumour-board/PreAuth_Checks_for_Validation.pdf" },
    { t: "Indian HIS research", p: "docs_Eswar/research/indian_his.md" },
    { t: "Permissions in code", p: "tumour_board/org.py (ACTIONS), access.py, home.py, routes/tumour_board_routes.py" },
    { t: "UI code", p: "static/tb/index.html, tb.js, tb.css" }
  ],

  glossary: [
    ["Tumour Board Case File", "All records of one cancer episode of one patient, owned by one treating department."],
    ["Pre-Authorization", "The check that every record required for this cancer is present, final and signed, with its required values, before the board. Not payer authorisation."],
    ["Level 1 / Level 2", "Level 1: the record is there, final, signed, the right patient. Level 2: the required values inside it are present with a verified quote."],
    ["NCG tiers a / b / c", "National Cancer Grid: a Essential (required everywhere), b Optimal (required at an Optimal-level hospital), c Optional (shown only)."],
    ["NCG setting", "The stage group the doctor picks from the signed reports (for example early / locally advanced / metastatic). The system never works out the stage."],
    ["Responsible Department", "The department that can produce or correct a missing record."],
    ["Points for review", "Items flagged for a clinician to look at; not findings, not treatment recommendations."],
    ["Human oversight (expert-in-the-loop)", "A clinician reviews every AI draft; nothing is final until a person confirms it."],
    ["Treating / supporting department", "Treating departments own Case Files; supporting departments (Radiology, Pathology, labs) report and answer requests."],
    ["Board heads", "Radiology, Medical Oncology, Surgical Oncology, Pathology: an absent head's agent stands in."],
    ["Surgical seat", "Filled by Surgical Oncology or the Case File's own surgeon; else the Surgical Oncology agent stands in."],
    ["UHID / IP No. / OP No.", "Hospital patient ID; in-patient admission number; out-patient visit number."],
    ["ABHA", "Ayushman Bharat Health Account number (14 digits). Aadhaar is never used."],
    ["Accession No.", "The order number of an imaging or lab test in the RIS / LIS."],
    ["HIS / RIS / LIS / PACS", "Hospital information system; radiology and lab information systems; picture archive (images)."],
    ["Re-fetch", "Ask the hospital system again for new or changed records."],
    ["Waive / attest final", "A doctor accepts a missing record (with a reason), or confirms a report is final; both audited."],
    ["Discordance", "Two reports disagree on the same value."],
    ["Adjudication", "Checks on the decision record: required fields, numbers vs sources, doses vs guideline references. Never the decision itself."],
    ["PM-JAY / HBP 2.2", "Ayushman Bharat scheme; Health Benefit Package 2.2 requires a tumour board decision for cancer packages."],
    ["Arogya Mitra / MEDCO", "PM-JAY desk staff at the hospital; the hospital's nominated medical coordinator."],
    ["NCG Virtual Tumour Board", "National Cancer Grid's online board: hub and spoke, a case template, emailed recommendations."],
    ["DMG", "Disease Management Group (Tata Memorial's site-wise teams)."],
    ["Key worker", "The patient's named contact, usually a nurse specialist."],
    ["Quorum", "The minimum specialties present for a valid discussion."],
    ["OHIF / Orthanc", "Image viewer / image server; reached only through the app, people view, no model reads images."]
  ]
};
