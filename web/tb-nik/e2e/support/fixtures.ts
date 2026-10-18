// SYNTHETIC answers for the screenshot run in mock mode (TBNIK_MOCK=1): fake people, fake UHIDs (VXH/...), the fictitious
// "Vaidyx Demo Hospital". Shapes follow docs/ui/build/SPEC-API.md and the routes in tumour_board/api. No real patient data.

export type Role = "treating" | "resident" | "supporting" | "coordinator" | "root_admin" | "dept_admin" | "auditor";

const DEPTS: Array<[string, string, "treating" | "supporting"]> = [
  ["general_surgery", "General Surgery", "treating"], ["surgical_oncology", "Surgical Oncology", "treating"], ["medical_oncology", "Medical Oncology", "treating"],
  ["radiation_oncology", "Radiation Oncology", "treating"], ["breast_surgery", "Breast Surgery", "treating"], ["gynaecologic_oncology", "Gynaecologic Oncology", "treating"],
  ["ent_head_neck_surgery", "ENT and Head and Neck Surgery", "treating"], ["urology", "Urology", "treating"], ["gastrointestinal_surgery", "Gastrointestinal Surgery", "treating"],
  ["pulmonology", "Pulmonology", "treating"], ["thoracic_surgery", "Thoracic Surgery", "treating"], ["haematology", "Haematology", "treating"],
  ["paediatric_oncology", "Paediatric Oncology", "treating"], ["palliative_medicine", "Palliative Medicine", "treating"],
  ["radiology", "Radiology", "supporting"], ["pathology", "Pathology", "supporting"], ["microbiology", "Microbiology", "supporting"],
  ["biochemistry", "Biochemistry", "supporting"], ["nuclear_medicine", "Nuclear Medicine", "supporting"], ["clinical_pharmacology", "Clinical Pharmacology", "supporting"],
];

export const departments = DEPTS.map(([id, name, group]) => ({ id, name, group }));

const now = new Date();
const iso = (daysAgo: number, h = 10) => { const d = new Date(now); d.setDate(d.getDate() - daysAgo); d.setHours(h, 15, 0, 0); return d.toISOString(); };
const day = (daysAhead: number) => { const d = new Date(now); d.setDate(d.getDate() + daysAhead); return d.toISOString().slice(0, 10); };

export function me(role: Role) {
  const base = {
    must_change_password: false, setup_needed: false,
    profile: { title: "Dr", registration_no: "TNMC 45821", phone: "", phone_visible: false, photo: "", text_size: "normal", start_page: "home",
      saved_filters: role === "treating" ? [{ name: "My urgent ones", query: { urgency: "high", mine: "1" } }, { name: "Ready", query: { status: "ready" } }] : [] },
    counts: { unread: 3, waiting_for_me: role === "treating" ? 2 : 0, open_requests: role === "supporting" ? 4 : 0 },
    hospital: { name: "Vaidyx Demo Hospital", level: "optimal" },
    features: { video: true, push: true },
  };
  const roles = { admin: false, root_admin: false, coordinator: false, auditor: false, outside_expert: false, disabled: false, departments: {} as Record<string, string>, treating: [] as string[], supporting: [] as string[], resident: [] as string[], admin_of: [] as string[] };
  switch (role) {
    case "treating": return { ...base, user: "rao@vxh.example", display_name: "Lakshmi Rao", primary_role: "treating", roles: { ...roles, departments: { breast_surgery: "head" }, treating: ["breast_surgery"] } };
    case "resident": return { ...base, user: "asha@vxh.example", display_name: "Asha Menon", primary_role: "resident", roles: { ...roles, departments: { breast_surgery: "resident" }, resident: ["breast_surgery"] } };
    case "supporting": return { ...base, user: "iqbal@vxh.example", display_name: "Iqbal Khan", primary_role: "supporting", roles: { ...roles, departments: { radiology: "member" }, supporting: ["radiology"] } };
    case "coordinator": return { ...base, user: "mdt@vxh.example", display_name: "Priya Nair", primary_role: "coordinator", profile: { ...base.profile, registration_no: "" }, roles: { ...roles, coordinator: true } };
    case "root_admin": return { ...base, user: "root@vxh.example", display_name: "Hospital IT", primary_role: "root_admin", profile: { ...base.profile, title: "Mr", registration_no: "" }, roles: { ...roles, root_admin: true } };
    case "dept_admin": return { ...base, user: "radadmin@vxh.example", display_name: "Suresh Babu", primary_role: "dept_admin", profile: { ...base.profile, title: "Mr", registration_no: "" }, roles: { ...roles, admin_of: ["radiology"] } };
    case "auditor": return { ...base, user: "audit@vxh.example", display_name: "Meera Iyer", primary_role: "auditor", profile: { ...base.profile, title: "Ms", registration_no: "" }, roles: { ...roles, auditor: true } };
  }
}

const P = (name: string, agesex: string, uhid: string) => ({ name, agesex, uhid });
const owner = (dept: string, label: string, doctor = "rao@vxh.example", doctor_name = "Lakshmi Rao") => ({ department: dept, department_label: label, doctor, doctor_name });
const st = (key: string, label: string, detail = "") => ({ key, label, detail });

export const caseList = {
  cases: [
    { case_id: "TB-2026-0031", patient: P("Lakshmi R.", "58 F", "VXH/2026/000123"), protocol: "breast", protocol_label: "Breast cancer", setting: "early", owner: owner("breast_surgery", "Breast Surgery"), urgency: { level: 5, set_by_name: "Lakshmi Rao" }, status: st("needs_me", "Needs you", "2 confirmations needed"), board_date: day(3), left_before_board: 2, imaging_present: true, last_change: iso(0, 9), created: iso(1), mine: true },
    { case_id: "TB-2026-0030", patient: P("Fatima B.", "46 F", "VXH/2026/000118"), protocol: "breast", protocol_label: "Breast cancer", setting: "locally_advanced", owner: owner("breast_surgery", "Breast Surgery"), urgency: { level: 4, set_by_name: "Lakshmi Rao", proposed: null }, status: st("waiting_department", "Waiting on Pathology", "1 open request"), board_date: day(3), left_before_board: 1, imaging_present: true, last_change: iso(0, 8), created: iso(2), mine: true },
    { case_id: "TB-2026-0029", patient: P("Kamala S.", "61 F", "VXH/2026/000102"), protocol: "cervix", protocol_label: "Cervix cancer", setting: "locally_advanced", owner: owner("gynaecologic_oncology", "Gynaecologic Oncology", "devi@vxh.example", "Radha Devi"), urgency: { level: 3 }, status: st("ready", "Ready for the board"), board_date: day(3), left_before_board: 0, imaging_present: true, last_change: iso(1), created: iso(4) },
    { case_id: "TB-2026-0027", patient: P("Ramesh K.", "64 M", "VXH/2026/000097"), protocol: "lung_nsclc", protocol_label: "Lung cancer (NSCLC)", setting: "metastatic", owner: owner("pulmonology", "Pulmonology", "joseph@vxh.example", "Thomas Joseph"), urgency: { level: 2 }, status: st("scheduled", `Scheduled ${day(3)}`), board_date: day(3), left_before_board: 0, imaging_present: true, last_change: iso(2), created: iso(6) },
    { case_id: "TB-2026-0024", patient: P("Venkatesh M.", "55 M", "VXH/2026/000081"), protocol: "oral_cavity", protocol_label: "Oral cavity cancer (head and neck)", setting: "early", owner: owner("ent_head_neck_surgery", "ENT and Head and Neck Surgery", "pillai@vxh.example", "Arun Pillai"), urgency: { level: null }, status: st("draft", "Reading records", "3 record(s) being read"), board_date: "", left_before_board: 4, imaging_present: false, last_change: iso(3), created: iso(8) },
    { case_id: "TB-2026-0019", patient: P("Sunita P.", "50 F", "VXH/2026/000064"), protocol: "breast", protocol_label: "Breast cancer", setting: "early", owner: owner("breast_surgery", "Breast Surgery"), urgency: { level: 1 }, status: st("decided", "Decided"), board_date: day(-11), left_before_board: 0, imaging_present: true, last_change: iso(11), created: iso(20), mine: true },
  ],
  filters: {
    departments: [{ id: "breast_surgery", label: "Breast Surgery" }, { id: "gynaecologic_oncology", label: "Gynaecologic Oncology" }, { id: "pulmonology", label: "Pulmonology" }],
    organs: [{ id: "breast", label: "Breast cancer" }, { id: "cervix", label: "Cervix cancer" }, { id: "lung_nsclc", label: "Lung cancer (NSCLC)" }, { id: "oral_cavity", label: "Oral cavity cancer (head and neck)" }],
    owners: [{ id: "rao@vxh.example", label: "Lakshmi Rao" }, { id: "devi@vxh.example", label: "Radha Devi" }, { id: "joseph@vxh.example", label: "Thomas Joseph" }],
    statuses: [{ key: "needs_me", label: "Needs you" }, { key: "waiting_department", label: "Waiting on a department" }, { key: "ready", label: "Ready for the board" }, { key: "scheduled", label: "Scheduled" }, { key: "decided", label: "Decided" }, { key: "draft", label: "Reading records" }],
  },
  total: 6,
  can_create: true,
};

export const waiting = {
  items: [
    { id: "PR-1", kind: "proposal", case_id: "TB-2026-0031", patient_line: "Lakshmi R., 58 F, UHID VXH/2026/000123", title: "Sign off: not needed (CT chest)", by: "asha@vxh.example", by_name: "Asha Menon", at: iso(0, 9), note: "Chest X-ray is clear; CT not planned" },
    { id: "TB-2026-0030:join:kiran@vxh.example", kind: "join", case_id: "TB-2026-0030", patient_line: "Fatima B., 46 F, UHID VXH/2026/000118", title: "Join request", by: "kiran@vxh.example", by_name: "Kiran Shetty", at: iso(0, 8) },
  ],
  mine: [
    { id: "PR-1", kind: "proposal", case_id: "TB-2026-0031", patient_line: "Lakshmi R., 58 F, UHID VXH/2026/000123", title: "Waiting for Lakshmi Rao", status: "pending", at: iso(0, 9) },
    { id: "PR-0", kind: "proposal", case_id: "TB-2026-0030", patient_line: "Fatima B., 46 F, UHID VXH/2026/000118", title: "Returned by Lakshmi Rao: the IHC is still pending", status: "returned", at: iso(1) },
  ],
};

export const notifications = {
  unread: 3,
  notifications: [
    { id: "N3", ts: iso(0, 9), kind: "sign_off", case_id: "TB-2026-0031", title: "Asha Menon asks you to sign off: not needed", read: false },
    { id: "N2", ts: iso(0, 8), kind: "record_arrived", case_id: "TB-2026-0030", title: "A record arrived: HPE report (final, signed)", read: false },
    { id: "N1", ts: iso(0, 7), kind: "request_done", case_id: "TB-2026-0030", title: "Pathology sent done for IHC panel", text: "Signed today; addendum on Ki-67 follows", read: false },
    { id: "N0", ts: iso(2), kind: "agenda", meeting_id: "M-1", title: "Agenda sent for the board on Thursday", read: true },
  ],
};

const req = (o: Record<string, unknown>) => ({ source: "pre_authorization", status: "pending", overdue: false, days_overdue: 0, created: iso(1), history: [], ...o });
export const inbox = {
  open: 3, overdue: 1, generated: iso(0),
  departments: [{
    id: "radiology", name: "Radiology", group: "supporting", open: 3, overdue: 1,
    requests: [
      req({ case_id: "TB-2026-0031", action_id: "A-11", patient: { name: "Lakshmi R.", mrn: "VXH/2026/000123", agesex: "58 F" }, uhid: "VXH/2026/000123", encounter: { op_no: "OP/2026/00987" }, accession: "ACC-26-004512", label: "CT chest, abdomen and pelvis", what: "staging scan report, final and signed", due: day(-1), status: "overdue", overdue: true, days_overdue: 1, sent: { by: "rao@vxh.example", at: iso(3) } }),
      req({ case_id: "TB-2026-0030", action_id: "A-07", patient: { name: "Fatima B.", mrn: "VXH/2026/000118", agesex: "46 F" }, uhid: "VXH/2026/000118", encounter: { ip_no: "IP/2026/00412" }, accession: "ACC-26-004498", label: "Mammogram report", what: "BI-RADS category as reported", due: day(2), sent: { by: "rao@vxh.example", at: iso(1) }, acknowledged: { by: "iqbal@vxh.example", at: iso(0, 8) } }),
      req({ case_id: "TB-2026-0029", action_id: "B-02", source: "board", patient: { name: "Kamala S.", mrn: "VXH/2026/000102", agesex: "61 F" }, label: "MRI pelvis review before chemoradiation", due: day(5) }),
      req({ case_id: "TB-2026-0019", action_id: "A-03", patient: { name: "Sunita P.", mrn: "VXH/2026/000064", agesex: "50 F" }, uhid: "VXH/2026/000064", accession: "ACC-26-003870", label: "Ultrasound axilla", status: "completed", completed: iso(2), done: { by: "iqbal@vxh.example", at: iso(2), note: "Signed; no change from the prior study" } }),
    ],
  }],
};

export const meetings = {
  can_manage: true,
  meetings: [
    { id: "M-1", date: day(3), time: "16:00", room: "Seminar hall 2", status: "planned", video: true, counts: { discussion: 4, noting: 2, not_ready: 1 }, agenda_sent_at: null },
    { id: "M-0", date: day(-4), time: "16:00", room: "Seminar hall 2", status: "closed", video: false, counts: { discussion: 5, noting: 1, not_ready: 0 }, agenda_sent_at: iso(6) },
  ],
};

export const org = { hospital: { name: "Vaidyx Demo Hospital", level: "optimal" }, departments, admin_departments: [{ id: "radiology", name: "Radiology", group: "supporting" }] };

export const protocols = {
  protocols: [
    { id: "breast", label: "Breast cancer", settings: [{ id: "early", label: "Early (operable), as recorded" }, { id: "locally_advanced", label: "Locally advanced, as recorded" }, { id: "metastatic", label: "Metastatic, as recorded" }] },
    { id: "cervix", label: "Cervix cancer", settings: [{ id: "early", label: "Early (FIGO 2018 IA1 to IIA1), as recorded" }, { id: "locally_advanced", label: "Locally advanced (FIGO 2018 IB3, IIA2 to IVA), as recorded" }, { id: "metastatic", label: "Metastatic (FIGO 2018 IVB) or recurrent, as recorded" }] },
    { id: "colorectal_rectum", label: "Rectal cancer", settings: [{ id: "non_metastatic", label: "Non-metastatic (no distant disease recorded)" }, { id: "metastatic", label: "Metastatic (distant disease recorded)" }] },
    { id: "cup", label: "Cancer of Unknown Primary (CUP)", note: "DRAFT, not approved for real use.", settings: [{ id: "provisional_cup", label: "Provisional CUP, as recorded" }] },
    { id: "lung_nsclc", label: "Lung cancer (NSCLC)", settings: [{ id: "non_metastatic", label: "Non-metastatic (no distant disease recorded)" }, { id: "metastatic", label: "Metastatic (distant disease recorded)" }] },
    { id: "oral_cavity", label: "Oral cavity cancer (head and neck)", settings: [{ id: "early", label: "Early (Stage I and II), as recorded" }, { id: "locally_advanced", label: "Locally advanced (Stage III to IVB), as recorded" }] },
  ],
};

export const hisLookup = {
  found: true, identifier: "VXH/2026/000140", his: "DemoHIMS",
  patient: { id: "p140", uhid: "VXH/2026/000140", registration_kind: "permanent", name: "Geetha V.", sex: "female", age: 52, dob: "1974-03-12", abha: "91-4410-2286-7731", pmjay_id: "PMJAY-TN-0099812", registered_on: iso(40), matched_on: "UHID" },
  similar: [{ uhid: "VXH/2026/T00031", name: "Geetha V", sex: "female", age: 52, registration_kind: "temporary" }],
  encounters: [
    { kind: "op", number: "OP/2026/01022", department: "Breast Surgery", unit: "Unit 2", start: iso(12), status: "finished" },
    { kind: "ip", number: "IP/2026/00431", department: "Surgical Oncology", start: iso(5), status: "in-progress" },
  ],
  window: { months: 12 }, window_start: iso(365), reports: 9, older: 2,
};

export const job = (state: "running" | "finished") => ({
  id: "J1a2b3c4d", case_id: "TB-2026-0032", total: 9, done: state === "finished" ? 9 : 5, state,
  doc_states: state === "finished" ? Object.fromEntries(Array.from({ length: 9 }, (_, i) => [`d${i}`, "ready"])) : { d0: "ready", d1: "ready", d2: "ready", d3: "ready", d4: "ready", d5: "extracting", d6: "classifying", d7: "reading", d8: "queued" },
  gate: state === "finished" ? { passed: false, satisfied: 7, total: 10 } : null,
});

export const setup = {
  complete: false,
  steps: [
    { id: "hospital", label: "Hospital", done: true, summary: "Vaidyx Demo Hospital (optimal, PM-JAY)" },
    { id: "departments", label: "Departments", done: true, summary: "14 treating, 6 supporting; contacts for 9" },
    { id: "people", label: "People and roles", done: true, summary: "12 login(s): 10 placed, 1 coordinator(s), 1 root admin(s)" },
    { id: "his", label: "Hospital system", done: false, summary: "not tested" },
    { id: "board", label: "Board", done: false, summary: "5 head(s), 1 coordinator(s)" },
  ],
  hospital: { name: "Vaidyx Demo Hospital", level: "optimal", type: "private", pmjay_empanelled: true, fetch_window_months: 12 },
  departments: departments.map((d, i) => ({ ...d, enabled: i < 18, email: i % 2 ? `${d.id}@vxh.example` : "", phone: i % 3 ? `044 2345 ${1000 + i}` : "", receives_requests: d.group === "supporting" })),
  board: { coordinators: ["mdt@vxh.example"], heads: ["radiology", "medical_oncology", "surgical_oncology", "pathology", "radiation_oncology"], meeting_defaults: { weekday: 3, time: "16:00", room: "Seminar hall 2", minutes_per_case: 10 } },
  his: { url: "http://127.0.0.1:7130", kind: "fhir", enabled: true, has_token: true, tested_at: "", ok: null, error: "" },
  levels: ["essential", "optimal"], types: ["", "public", "private"], weekdays: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
};

export const accounts = {
  accounts: [
    { username: "mdt@vxh.example", display_name: "Priya Nair", coordinator: true },
    { username: "rao@vxh.example", display_name: "Lakshmi Rao", departments: { breast_surgery: "head" } },
    { username: "asha@vxh.example", display_name: "Asha Menon", departments: { breast_surgery: "resident" }, end_date: day(90) },
    { username: "iqbal@vxh.example", display_name: "Iqbal Khan", departments: { radiology: "member" } },
    { username: "devi@vxh.example", display_name: "Radha Devi", departments: { gynaecologic_oncology: "head" } },
  ],
};

export const people = {
  department: { id: "radiology", name: "Radiology", group: "supporting", email: "radiology@vxh.example", phone: "044 2345 1014" },
  can_reset: true, roles: ["member", "head", "resident"],
  people: [
    { username: "iqbal@vxh.example", display_name: "Iqbal Khan", role: "member", admin: false, coordinator: false, disabled: false, root_admin: false, other_departments: [], admin_of_others: [], account: true, vaidyx_admin: false, end_date: "" },
    { username: "shanthi@vxh.example", display_name: "Shanthi Raman", role: "head", admin: false, coordinator: false, disabled: false, root_admin: false, other_departments: [], admin_of_others: [], account: true, vaidyx_admin: false },
    { username: "kiran@vxh.example", display_name: "Kiran Shetty", role: "resident", admin: false, coordinator: false, disabled: false, root_admin: false, other_departments: [], admin_of_others: [], account: true, vaidyx_admin: false, end_date: day(75), must_change_password: true },
    { username: "radadmin@vxh.example", display_name: "Suresh Babu", role: null, admin: true, coordinator: false, disabled: false, root_admin: false, other_departments: [], admin_of_others: [], account: true, vaidyx_admin: false },
    { username: "anil@vxh.example", display_name: "Anil Varma", role: "member", admin: false, coordinator: false, disabled: true, root_admin: false, other_departments: [{ id: "nuclear_medicine", name: "Nuclear Medicine" }], admin_of_others: [], account: true, vaidyx_admin: false },
  ],
};

export const activity = {
  total: 5,
  events: [
    { ts: iso(0, 9), kind: "proposal_approved", case_id: "TB-2026-0031", title: "Proposal approved", detail: "action: not_needed", by: "rao@vxh.example", source: "case" },
    { ts: iso(0, 8), kind: "request_sent", case_id: "TB-2026-0031", title: "Request sent", detail: "department: Radiology; requirement: ct_staging", by: "rao@vxh.example", source: "case" },
    { ts: iso(1), kind: "urgency_set", case_id: "TB-2026-0030", title: "Urgency set", detail: "level: 4", by: "rao@vxh.example", source: "case" },
    { ts: iso(1, 15), kind: "profile_updated", title: "Profile updated", detail: "fields: theme, text_size", by: "rao@vxh.example", source: "organisation" },
    { ts: iso(4), kind: "board_session_decision", case_id: "TB-2026-0019", title: "Board session decision", by: "mdt@vxh.example", source: "session" },
  ],
};

export const notificationPrefs = { digest_time: "08:00", kinds: { reminder_automatic: false }, push: true, kinds_available: ["request", "request_done", "sign_off", "join_request", "record_arrived", "summary_stale", "agenda", "outcome", "reminder_automatic"], push_enabled: true, subscriptions: 0 };
