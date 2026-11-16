// SYNTHETIC answers for the screenshot run in mock mode (TBNIK_MOCK=1): fake people, fake UHIDs (VXH/...), the fictitious
// "Vaidyx Demo Hospital". Shapes follow docs/ui/build/SPEC-API.md and the routes in tumour_board/api. No real patient data.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export type Role = "treating" | "resident" | "supporting" | "coordinator" | "root_admin" | "dept_admin" | "auditor" | "vaidyx_admin";

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
  // night-v3 8.4: placed hospital staff (and the MDT Coordinator) may use Messages; the others get no "messages" field.
  const placed = role === "treating" || role === "resident" || role === "supporting" || role === "coordinator";
  const base = {
    ...(placed ? { messages: true } : {}),
    must_change_password: false, setup_needed: false,
    profile: { title: "Dr", registration_no: "TNMC 45821", phone: "", phone_visible: false, photo: "", text_size: "normal", start_page: "home",
      saved_filters: role === "treating" ? [{ name: "My urgent ones", query: { urgency: "high", mine: "1" } }, { name: "Ready", query: { status: "ready" } }] : [] },
    counts: { unread: 3, waiting_for_me: role === "treating" ? 2 : 0, open_requests: role === "supporting" ? 4 : 0, ...(placed ? { messages_unread: 2 } : {}) },
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
    // docs/admin-console: the Vaidyx admin (server administrator): no clinical role, the platform flag of DESIGN 5.3.
    case "vaidyx_admin": return { ...base, user: "vaidyx-admin", display_name: "Vaidyx Admin", primary_role: "root_admin", platform_admin: true, acting_hospital: null, profile: { ...base.profile, title: "", registration_no: "" }, roles: { ...roles, admin: true, vaidyx_admin: true } };
  }
}

const P = (name: string, agesex: string, uhid: string) => ({ name, agesex, uhid });
const ids = (uhid: string, op: string) => [uhid, op];
const owner = (dept: string, label: string, doctor = "rao@vxh.example", doctor_name = "Lakshmi Rao") => ({ department: dept, department_label: label, doctor, doctor_name });
const st = (key: string, label: string, detail = "") => ({ key, label, detail });

export const caseList = {
  cases: [
    { case_id: "TB-2026-0031", patient: P("Lakshmi R.", "58 F", "VXH/2026/000123"), ids: ids("VXH/2026/000123", "OP/2026/00123"), protocol: "breast", protocol_label: "Breast cancer", setting: "early", owner: owner("breast_surgery", "Breast Surgery"), urgency: { level: 5, set_by_name: "Lakshmi Rao" }, status: st("needs_me", "Needs you", "2 confirmations needed"), board_date: day(3), left_before_board: 2, imaging_present: true, last_change: iso(0, 9), created: iso(1), mine: true },
    { case_id: "TB-2026-0030", patient: P("Fatima B.", "46 F", "VXH/2026/000118"), ids: ids("VXH/2026/000118", "OP/2026/00118"), protocol: "breast", protocol_label: "Breast cancer", setting: "locally_advanced", owner: owner("breast_surgery", "Breast Surgery"), urgency: { level: 4, set_by_name: "Lakshmi Rao", proposed: null }, status: st("waiting_department", "Waiting on Pathology", "1 open request"), board_date: day(3), left_before_board: 1, imaging_present: true, last_change: iso(0, 8), created: iso(2), mine: true },
    { case_id: "TB-2026-0029", patient: P("Kamala S.", "61 F", "VXH/2026/000102"), ids: ids("VXH/2026/000102", "OP/2026/00102"), protocol: "cervix", protocol_label: "Cervix cancer", setting: "locally_advanced", owner: owner("gynaecologic_oncology", "Gynaecologic Oncology", "devi@vxh.example", "Radha Devi"), urgency: { level: 3 }, status: st("ready", "Ready for the board"), board_date: day(3), left_before_board: 0, imaging_present: true, last_change: iso(1), created: iso(4) },
    { case_id: "TB-2026-0027", patient: P("Ramesh K.", "64 M", "VXH/2026/000097"), ids: ids("VXH/2026/000097", "OP/2026/00097"), protocol: "lung_nsclc", protocol_label: "Lung cancer (NSCLC)", setting: "metastatic", owner: owner("pulmonology", "Pulmonology", "joseph@vxh.example", "Thomas Joseph"), urgency: { level: 2 }, status: st("scheduled", `Scheduled ${day(3)}`), board_date: day(3), left_before_board: 0, imaging_present: true, last_change: iso(2), created: iso(6) },
    { case_id: "TB-2026-0024", patient: P("Venkatesh M.", "55 M", "VXH/2026/000081"), ids: ids("VXH/2026/000081", "OP/2026/00081"), protocol: "oral_cavity", protocol_label: "Oral cavity cancer (head and neck)", setting: "early", owner: owner("ent_head_neck_surgery", "ENT and Head and Neck Surgery", "pillai@vxh.example", "Arun Pillai"), urgency: { level: null }, status: st("draft", "Reading records", "3 record(s) being read"), board_date: "", left_before_board: 4, imaging_present: false, last_change: iso(3), created: iso(8) },
    { case_id: "TB-2026-0019", patient: P("Sunita P.", "50 F", "VXH/2026/000064"), ids: ids("VXH/2026/000064", "OP/2026/00064"), protocol: "breast", protocol_label: "Breast cancer", setting: "early", owner: owner("breast_surgery", "Breast Surgery"), urgency: { level: 1 }, status: st("decided", "Decided"), board_date: day(-11), left_before_board: 0, imaging_present: true, last_change: iso(11), created: iso(20), mine: true,
      summary_line: "50 F, early breast cancer: board decision recorded; adjuvant radiotherapy referral open (SYNTHETIC)", decision_text: "Breast conservation surgery with sentinel node biopsy (SYNTHETIC)" },
    // night-v3 item 1.3: another department's Case File of the same patient, seen only through the link; read only, never counted
    { case_id: "TB-2026-0032", patient: P("Lakshmi R.", "58 F", "VXH/2026/000123"), ids: ids("VXH/2026/000123", "OP/2026/00131"), protocol: "", protocol_label: "Chronic myeloid leukaemia (no checklist yet)", cancer_name: "Chronic myeloid leukaemia", setting: "", owner: owner("haematology", "Haematology", "iyer@vxh.example", "Meera Iyer"), urgency: { level: null }, status: st("needs_me", "Needs the treating team", "no cancer chosen yet"), board_date: "", left_before_board: null, imaging_present: false, last_change: iso(0, 7), created: iso(0, 7), mine: false, relation: "linked", linked_only: true, read_only: true, owned_by: { department: "haematology", label: "Haematology" } },
  ],
  filters: {
    departments: [{ id: "breast_surgery", label: "Breast Surgery" }, { id: "gynaecologic_oncology", label: "Gynaecologic Oncology" }, { id: "pulmonology", label: "Pulmonology" }],
    organs: [{ id: "breast", label: "Breast cancer" }, { id: "cervix", label: "Cervix cancer" }, { id: "lung_nsclc", label: "Lung cancer (NSCLC)" }, { id: "oral_cavity", label: "Oral cavity cancer (head and neck)" }],
    owners: [{ id: "rao@vxh.example", label: "Lakshmi Rao" }, { id: "devi@vxh.example", label: "Radha Devi" }, { id: "joseph@vxh.example", label: "Thomas Joseph" }],
    statuses: [{ key: "needs_me", label: "Needs you" }, { key: "waiting_department", label: "Waiting on a department" }, { key: "ready", label: "Ready for the board" }, { key: "scheduled", label: "Scheduled" }, { key: "decided", label: "Decided" }, { key: "draft", label: "Reading records" }],
  },
  total: 7,
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

// GET /protocols as the backend lists it (protocol.list_protocols(), saved to protocols.json on 27 Oct 2026 for night-v3 item
// 2.10): the 24 checklists with their versions ("0.1-draft" for the new ones) plus generic and generic_haem.
export const protocols: { protocols: Array<{ id: string; label: string; version?: string; note?: string; settings: Array<{ id: string; label: string; definition?: string }> }> } =
  JSON.parse(fs.readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)), "protocols.json"), "utf8"));

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
    { username: "root@vxh.example", display_name: "Hospital IT", root_admin: true },
    { username: "radadmin@vxh.example", display_name: "Suresh Babu", admin_of: ["radiology"] },
    { username: "audit@vxh.example", display_name: "Meera Iyer", auditor: true, must_change_password: true },
    { username: "anil@vxh.example", display_name: "Anil Varma", departments: { radiology: "member" }, disabled: true },
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

// ---- Admin consoles (docs/admin-console/DESIGN.md 5.3), SYNTHETIC: fictitious hospitals and people, counts only -----------------

const hospitalRow = (id: string, name: string, city: string, state: string, status: "active" | "suspended", admins: number, people: number, cf: [number, number], setupDone: number, his: string, lastDays: number | null, extra: Record<string, unknown> = {}) => ({
  id, name, city, state, status, admins, people, case_files: { open: cf[0], decided: cf[1], total: cf[0] + cf[1] }, setup: { done: setupDone, total: 5 },
  his: { state: his, url_set: his !== "not_set", tested_at: his === "not_set" ? null : iso(1), ok: his === "connected" ? true : his === "failing" ? false : null },
  last_activity: lastDays === null ? null : iso(lastDays, 11), created: iso(120), type: "private", level: "optimal", pmjay_empanelled: true, ...extra,
});

export const platformHospitals = {
  hospitals: [
    hospitalRow("default", "Vaidyx Demo Hospital", "Hyderabad", "Telangana", "active", 1, 26, [12, 7], 5, "connected", 0, { his: { state: "connected", url_set: true, tested_at: iso(1), ok: true, demo: true } }),
    hospitalRow("svch", "Sri Venkateswara Cancer Hospital", "Tirupati", "Andhra Pradesh", "active", 1, 4, [0, 0], 2, "not_set", 2, { type: "public", level: "essential" }),
    hospitalRow("kmc", "Kaveri Medical College Hospital", "Mysuru", "Karnataka", "active", 0, 0, [0, 0], 0, "not_set", null, { created: iso(3) }),
    hospitalRow("nrh", "Narmada Regional Hospital", "Jabalpur", "Madhya Pradesh", "suspended", 1, 9, [3, 11], 5, "failing", 40, { type: "public", status_reason: "Contract paused by the hospital (test)" }),
  ],
};

export const platformOverview = {
  tiles: { hospitals_active: 3, hospitals_suspended: 1, logins: 40, hospital_admins: 3, case_files: 33, meetings_next_7_days: 2, setup_complete: 2, his_connected: 1 },
  hospitals: platformHospitals.hospitals,
  attention: [
    { hospital: "kmc", hospital_name: "Kaveri Medical College Hospital", kind: "no_admin", text: "No hospital admin yet" },
    { hospital: "svch", hospital_name: "Sri Venkateswara Cancer Hospital", kind: "setup_unfinished", text: "Set-up 2 of 5 steps done" },
    { hospital: "nrh", hospital_name: "Narmada Regional Hospital", kind: "his_failing", text: "Hospital system not answering" },
    { hospital: "svch", hospital_name: "Sri Venkateswara Cancer Hospital", kind: "admin_never_signed_in", text: "Ravi Teja has not signed in yet" },
  ],
};

export function platformHospitalDetail(id: string) {
  const h = platformHospitals.hospitals.find((x) => x.id === id) ?? platformHospitals.hospitals[0];
  const big = h.id === "default";
  return {
    hospital: h,
    counts: { people: h.people, case_files_open: h.case_files.open, case_files_decided: h.case_files.decided, meetings_next_7_days: big ? 2 : 0 },
    admins: h.admins ? [{ username: big ? "root@vxh.example" : `it.admin@${h.id}.example`, display_name: big ? "Hospital IT" : "Ravi Teja", must_change_password: !big, last_sign_in: big ? iso(0, 9) : null }] : [],
    people_by_role: big ? { doctors: 14, heads: 5, residents: 3, coordinators: 2, dept_admins: 3, hospital_admins: 1, auditors: 1, guests: 2, disabled: 1, never_signed_in: 2 } : { doctors: 2, heads: 1, residents: 0, coordinators: 0, dept_admins: 0, hospital_admins: 1, auditors: 0, guests: 0, disabled: 0, never_signed_in: 1 },
    setup: { steps: setup.steps.map((s, i) => ({ ...s, done: i < h.setup.done })) },
    his: h.his,
    recent: [
      { ts: iso(0, 9), by: "root@vxh.example", by_name: "Hospital IT", kind: "account_created", text: "Login created for Kiran Shetty (Resident, Radiology)" },
      { ts: iso(1, 15), by: "root@vxh.example", by_name: "Hospital IT", kind: "setup_saved", text: "Set-up saved: Board" },
      { ts: iso(2, 12), by: "vaidyx-admin", by_name: "Vaidyx Admin", kind: "password_reset", text: "Password reset for Asha Menon" },
    ],
  };
}

export const platformLogins = {
  logins: [
    { username: "vaidyx-admin", display_name: "Vaidyx Admin", hospital: "default", roles: ["vaidyx_admin"], disabled: false, must_change_password: false, vaidyx_admin: true },
    { username: "root@vxh.example", display_name: "Hospital IT", hospital: "default", roles: ["hospital_admin"], disabled: false, must_change_password: false, vaidyx_admin: false },
    { username: "rao@vxh.example", display_name: "Lakshmi Rao", hospital: "default", roles: ["head"], disabled: false, must_change_password: false, vaidyx_admin: false },
    { username: "mdt@vxh.example", display_name: "Priya Nair", hospital: "default", roles: ["coordinator"], disabled: false, must_change_password: false, vaidyx_admin: false },
    { username: "anil@vxh.example", display_name: "Anil Varma", hospital: "default", roles: ["doctor"], disabled: true, must_change_password: false, vaidyx_admin: false },
    { username: "it.admin@svch.example", display_name: "Ravi Teja", hospital: "svch", roles: ["hospital_admin"], disabled: false, must_change_password: true, vaidyx_admin: false },
    { username: "onco@svch.example", display_name: "Dr Kavitha Reddy", hospital: "svch", roles: ["doctor", "dept_admin"], disabled: false, must_change_password: true, vaidyx_admin: false },
    { username: "it.admin@nrh.example", display_name: "Mohan Verma", hospital: "nrh", roles: ["hospital_admin"], disabled: false, must_change_password: false, vaidyx_admin: false },
  ],
};

export const platformActivity = {
  events: [
    { ts: iso(0, 10), by: "vaidyx-admin", by_name: "Vaidyx Admin", hospital: "kmc", hospital_name: "Kaveri Medical College Hospital", kind: "hospital_created", text: "Hospital added: Kaveri Medical College Hospital" },
    { ts: iso(1, 16), by: "vaidyx-admin", by_name: "Vaidyx Admin", hospital: "svch", hospital_name: "Sri Venkateswara Cancer Hospital", kind: "admin_added", text: "Hospital admin added: Ravi Teja" },
    { ts: iso(2, 12), by: "vaidyx-admin", by_name: "Vaidyx Admin", hospital: "default", hospital_name: "Vaidyx Demo Hospital", kind: "password_reset", text: "Password reset for Asha Menon" },
    { ts: iso(5, 9), by: "vaidyx-admin", by_name: "Vaidyx Admin", hospital: "nrh", hospital_name: "Narmada Regional Hospital", kind: "hospital_suspended", text: "Hospital suspended: contract paused (test)" },
    { ts: iso(6, 14), by: "vaidyx-admin", by_name: "Vaidyx Admin", hospital: "default", hospital_name: "Vaidyx Demo Hospital", kind: "acting_in", text: "Worked inside Vaidyx Demo Hospital" },
  ],
};

/** POST /platform/hospitals: a synthetic first password (fake, for the mock run only). */
export const newHospitalResult = (name: string) => ({
  hospital: { ...platformHospitals.hospitals[2], id: "new-hospital", name, admins: 1, people: 1 },
  admin: { username: "first.admin@newhospital.example", password_once: "Mock-First-Pass-7Q2", mailto: "mailto:first.admin@newhospital.example?subject=Your%20Vaidyx%20login&body=Login%20name%3A%20first.admin%40newhospital.example%0AFirst%20password%3A%20Mock-First-Pass-7Q2" },
});

export const platformReset = { password_once: "Mock-Reset-Pass-4K9", mailto: "mailto:someone@vxh.example?subject=Your%20Vaidyx%20login&body=Login%20name%3A%20someone%40vxh.example%0AFirst%20password%3A%20Mock-Reset-Pass-4K9" };

/** POST /accounts and POST /accounts/{u}/reset-password: the first password only inside the mail draft (fake, mock run only). */
export const accountMailto = (login: string) => `mailto:${encodeURIComponent(login)}?subject=Your%20Vaidyx%20login&body=${encodeURIComponent(`Login name: ${login}\nFirst password: Mock-Acct-Pass-8T3\nChange it at the first sign-in.`)}`;

export function hospitalOverview(name = "Vaidyx Demo Hospital") {
  return {
    hospital: { id: "default", name, city: "Hyderabad", state: "Telangana", status: "active", level: "optimal" },
    people: { doctors: 14, heads: 5, residents: 3, coordinators: 1, dept_admins: 3, hospital_admins: 1, auditors: 1, guests: 2, disabled: 1, never_signed_in: 2 },
    case_files: { by_status: { draft: 2, needs_team: 3, waiting_department: 4, ready: 2, scheduled: 1, decided: 7 }, total: 19 },
    meetings: { next_7_days: 2, upcoming: [{ id: "M-2026-0042", title: "Tumour Board (weekly)", date: day(3) }, { id: "M-2026-0043", title: "Head and neck board", date: day(6) }] },
    requests: { open: 4 },
    setup: { steps: setup.steps, done: 3, total: 5 },
    his: { state: "not_tested", url_set: true, tested_at: null, ok: null },
    attention: [
      { kind: "department_no_head", text: "Microbiology has no head yet", link: "/hospital/departments" },
      { kind: "resident_ending", text: "Asha Menon's rotation ends within 30 days", link: "/hospital/people?role=resident" },
      { kind: "never_signed_in", text: "2 people have not signed in yet", link: "/hospital/people?role=not_signed_in" },
      { kind: "disabled_logins", text: "1 login is disabled", link: "/hospital/people?role=disabled" },
    ],
    recent: [
      { ts: iso(0, 9), by: "root@vxh.example", by_name: "Hospital IT", kind: "account_created", text: "Login created for Kiran Shetty (Resident, Radiology)" },
      { ts: iso(1, 15), by: "root@vxh.example", by_name: "Hospital IT", kind: "setup_saved", text: "Set-up saved: Board" },
      { ts: iso(2, 11), by: "radadmin@vxh.example", by_name: "Suresh Babu", kind: "person_placed", text: "Iqbal Khan placed in Radiology" },
    ],
  };
}

export const hospitalDepartments = {
  departments: setup.departments.map((d, i) => ({
    id: d.id, name: d.name, group: d.group, enabled: d.enabled,
    heads: d.id === "microbiology" ? [] : d.id === "breast_surgery" ? [{ username: "rao@vxh.example", display_name: "Lakshmi Rao" }] : d.id === "radiology" ? [{ username: "shanthi@vxh.example", display_name: "Shanthi Raman" }] : i % 3 ? [] : [{ username: `head.${d.id}@vxh.example`, display_name: `Dr ${d.name.split(" ")[0]} Head` }],
    people: (i * 7) % 6, residents: i % 4 === 1 ? 1 : 0, email: d.email, phone: d.phone, receives_requests: d.group === "supporting",
  })),
};
