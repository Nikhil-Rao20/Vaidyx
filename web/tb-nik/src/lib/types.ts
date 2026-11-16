// The shapes the new interface reads from /api/tb (docs/ui/build/SPEC-API.md and the existing routes).
// Every field the server may leave out is optional here, so a page never crashes on a thin answer.

export type { Me, RoleKind } from "@/lib/session";

// ---- Opened with a reason (POST /break-glass, night-v3 item 1.9) ------------------------------------------------------
/** A doctor's read-only window on a Case File it cannot open otherwise: 24 hours, audited, the owner's consultants told. */
export interface BreakGlassWindow {
  case_id: string;
  /** ISO end of the window (24 hours after opening). */
  until: string;
  reason: string;
  /** Where the doctor came from, e.g. "similar to TB-001" (Phase 7); empty otherwise. */
  via?: string;
}
/** POST /break-glass answer for a doctor. */
export interface BreakGlassOpened extends BreakGlassWindow {
  scope: "read";
  renewed?: boolean;
}
// GET /me lists the doctor's open windows (the Me type itself lives in lib/session.tsx).
declare module "@/lib/session" {
  interface Me {
    break_glass?: BreakGlassWindow[];
  }
}

// ---- Case File list (GET /case-list) ----------------------------------------------------------------------------------
export interface CasePatient {
  name: string;
  agesex: string;
  uhid: string;
}

export interface CaseOwner {
  department: string;
  department_label: string;
  doctor: string;
  doctor_name: string;
}

export interface CaseUrgency {
  level: number | null;
  set_by?: string;
  set_by_name?: string;
  at?: string;
  proposed?: number | null;
}

export type CaseStatusKey = "needs_me" | "waiting_department" | "ready" | "scheduled" | "decided" | "archived" | "draft" | "quiet";

export interface CaseStatus {
  key: CaseStatusKey;
  label: string;
  detail?: string;
}

export type CaseRelation = "owner" | "team" | "creator" | "participant" | "referred" | "coordinator" | "linked" | "asked" | "admin";

export interface CaseListItem {
  case_id: string;
  patient: CasePatient;
  protocol: string | null;
  protocol_label: string;
  setting?: string;
  owner: CaseOwner;
  urgency: CaseUrgency;
  status: CaseStatus;
  board_date?: string | null;
  meeting_id?: string | null;
  left_before_board?: number | null;
  imaging_present?: boolean;
  last_change?: string;
  created?: string;
  residents_count?: number;
  /** A guest reviewer's private Case File (its creator and the MDT Coordinator see it). */
  private?: boolean;
  /** Free text name when the cancer has no built checklist. */
  cancer_name?: string;
  /** The person owns it, is on its team, or created it (server side "mine"). Never true for a linked-only row. */
  mine?: boolean;
  /** Why the person sees it: owner, team, creator, participant, referred, coordinator, linked, asked, admin. */
  relation?: CaseRelation | null;
  /** Another department's Case File seen only because it is linked to one of the person's own: read only, never counted. */
  linked_only?: boolean;
  read_only?: boolean;
  owned_by?: { department: string; label: string };
  scope?: "FULL" | "REQUESTS" | string | null;
  documents?: number;
  gate_passed?: boolean | null;
  /** Every identifier the patient and the file carry (UHID, IP / OP numbers, ABHA, PM-JAY id), for the search. */
  ids?: string[];
  /** Accession / Lab numbers of the records in the file, for the search. */
  accessions?: string[];
  /** The Case File's summary line (night-v3 3.4); "" unless the reader has full access to the Case File. */
  summary_line?: string;
  /** The latest board decision in the board's words (at most 200 characters), for the search; "" unless full access. */
  decision_text?: string;
}

export type FilterOption = string | { id: string; label: string } | { key: string; label: string };

export interface CaseListFilters {
  departments?: FilterOption[];
  organs?: FilterOption[];
  owners?: FilterOption[];
  statuses?: FilterOption[];
}

export interface CaseListResponse {
  cases: CaseListItem[];
  filters?: CaseListFilters;
  total?: number;
  can_create?: boolean;
}

export interface SavedFilter {
  name: string;
  query: Record<string, string>;
}

// ---- Waiting for me (GET /waiting) and proposals --------------------------------------------------------------------
export interface WaitingItem {
  id: string;
  kind: "proposal" | "join" | "review";
  case_id: string;
  patient_line: string;
  title: string;
  by_name?: string;
  /** The login of the person who asks (kind proposal and join). */
  by?: string;
  at: string;
  /** The person asking to join (kind join), when the server sends it apart from `by`. */
  user?: string;
  action?: string;
  note?: string;
  /** A resident's own proposal: pending or returned. */
  status?: "pending" | "returned" | string;
}

export interface WaitingResponse {
  items: WaitingItem[];
  /** A resident's own proposals still waiting or returned. */
  mine?: WaitingItem[];
}

export interface Proposal {
  id: string;
  action: string;
  payload?: Record<string, unknown>;
  note?: string;
  by: string;
  by_name: string;
  at: string;
  status: "pending" | "approved" | "returned";
}

// ---- Notifications (GET /notifications) -----------------------------------------------------------------------------
export interface Notification {
  id: string;
  ts: string;
  kind: string;
  case_id?: string;
  meeting_id?: string;
  /** Phase 8: the conversation a "message" item points to. */
  conversation?: string;
  title: string;
  text?: string;
  read: boolean;
}

export interface NotificationsResponse {
  notifications: Notification[];
  unread: number;
}

export interface NotificationPrefs {
  digest_time: string;
  kinds: Record<string, boolean>;
  push?: boolean;
  kinds_available?: string[];
  push_enabled?: boolean;
  subscriptions?: number;
}

// ---- Department inbox (GET /inbox) -----------------------------------------------------------------------------------
export interface RequestStamp {
  by?: string;
  at?: string;
  note?: string;
  message?: string;
  to?: string;
}

export interface InboxRequest {
  case_id: string;
  action_id: string;
  source: "pre_authorization" | "board";
  source_label?: string;
  patient: { name: string; mrn: string; agesex: string };
  protocol?: string;
  board_date?: string;
  requirement?: string | null;
  label: string;
  what?: string;
  level?: number | null;
  level_label?: string;
  due?: string;
  status: "pending" | "overdue" | "completed" | string;
  overdue: boolean;
  days_overdue?: number;
  created?: string;
  completed?: string | null;
  history?: Array<{ at?: string; by?: string; kind?: string; note?: string }>;
  uhid?: string;
  encounter?: { ip_no?: string; op_no?: string };
  accession?: string | null;
  pending_order?: unknown;
  department?: string;
  department_id?: string;
  free?: boolean;
  sent?: RequestStamp | null;
  acknowledged?: RequestStamp | null;
  done?: RequestStamp | null;
  closed_by?: string | null;
  viewer_url?: string | null;
}

export interface InboxDepartment {
  id: string;
  name: string;
  group: "treating" | "supporting" | null;
  requests: InboxRequest[];
  open: number;
  overdue: number;
}

export interface InboxResponse {
  departments: InboxDepartment[];
  open: number;
  overdue: number;
  generated?: string;
  referrals?: unknown;
}

// ---- Hospital system lookup (GET /his/lookup) ----------------------------------------------------------------------
export interface HisPatient {
  id?: string;
  ref?: string;
  uhid?: string;
  registration_kind?: string;
  name?: string;
  sex?: string;
  age?: number | string;
  dob?: string;
  abha?: string;
  abha_address?: string;
  pmjay_id?: string;
  registered_on?: string;
  last_updated?: string;
  /** The HIS adapter sends {kind, value}; older answers send a plain word. */
  matched_on?: string | { kind?: string; value?: string } | null;
}

export interface HisEncounter {
  kind?: string;
  number?: string;
  department?: string;
  unit?: string;
  start?: string;
  end?: string;
  status?: string;
}

export interface HisLookup {
  found: boolean;
  identifier: string;
  his?: string;
  patient?: HisPatient;
  similar?: HisPatient[];
  encounters?: HisEncounter[];
  window?: { months?: number; all?: boolean; from?: string };
  window_start?: string;
  reports?: number;
  older?: number;
  note?: string;
}

// ---- Protocols (GET /protocols) -------------------------------------------------------------------------------------
export interface ProtocolSetting {
  id: string;
  label: string;
  definition?: string;
}

export interface ProtocolSummary {
  id: string;
  label: string;
  version?: string;
  note?: string;
  settings: ProtocolSetting[];
}

export interface ProtocolsResponse {
  protocols: ProtocolSummary[];
}

// ---- Jobs (GET /jobs/{id}) ------------------------------------------------------------------------------------------
export interface Job {
  id: string;
  case_id?: string;
  total: number;
  done: number;
  state: "running" | "finished" | "failed" | string;
  events?: Array<{ t: number; doc_id: string; state: string }>;
  doc_states?: Record<string, string>;
  error?: string;
  seconds?: number;
  started_iso?: string;
  doc_ids?: string[];
  gate?: { passed?: boolean; readiness?: string; satisfied?: number; total?: number } | null;
}

export interface CreateFromHisResponse {
  case: { case_id: string; patient?: CasePatient & { mrn?: string } };
  job: string;
  total: number;
  his?: unknown;
}

/** One Case File of a patient as the New Case File page and the Overview see it (GET /patient-case-files, night-v3 item 1.1):
 * the cancer, the owning department and consultant, a status word and whether this person may open it; no clinical content. */
export interface PatientCaseFile {
  case_id: string;
  protocol: string;
  cancer_name?: string;
  cancer_label: string;
  department: string;
  department_name: string;
  owner: string;
  owner_name: string;
  /** "Breast Surgery, Dr Rao" */
  owner_words?: string;
  can_open: boolean;
  created_at?: string;
  status_label?: string;
}

export interface PatientCaseFilesResponse {
  cases: PatientCaseFile[];
}

/** The 409 body when a Case File for this patient and this cancer exists (code "duplicate_case_file"). */
export interface DuplicateCaseFileBody {
  detail: string;
  code: "duplicate_case_file";
  existing: PatientCaseFile;
}

// ---- Meetings (GET /meetings) ---------------------------------------------------------------------------------------
export interface Meeting {
  id: string;
  date: string;
  time?: string;
  room?: string;
  status: "planned" | "in_session" | "closed";
  video?: boolean;
  counts?: { discussion: number; noting: number; not_ready: number };
  agenda_sent_at?: string | null;
}

export interface MeetingsResponse {
  meetings: Meeting[];
  can_manage?: boolean;
}

// ---- Activity (GET /me/activity, GET /activity) ------------------------------------------------------------------
export interface ActivityEvent {
  ts: string;
  kind: string;
  case_id?: string | null;
  title: string;
  detail?: string;
  by?: string;
  by_name?: string;
  source?: "case" | "organisation" | "session" | string;
}

export interface ActivityResponse {
  events: ActivityEvent[];
  total?: number;
}

// ---- Organisation (GET /org) ----------------------------------------------------------------------------------------
export interface OrgDepartment {
  id: string;
  name: string;
  group: "treating" | "supporting";
  aliases?: string[];
  email?: string;
  phone?: string;
  role?: string;
}

export interface OrgHospital {
  name: string;
  level?: "essential" | "optimal" | string;
  type?: string;
  pmjay_empanelled?: boolean;
  fetch_window_months?: number;
  board_heads?: string[];
}

export interface OrgResponse {
  hospital: OrgHospital;
  departments: OrgDepartment[];
  my_departments?: OrgDepartment[];
  inbox_departments?: string[];
  admin_departments?: OrgDepartment[];
  can?: Record<string, boolean>;
  reset_note?: string;
  version?: string;
  users?: Record<string, OrgUser>;
  admins?: string[];
}

export interface OrgUser {
  display_name?: string;
  departments?: Record<string, string>;
  admin_of?: string[];
  coordinator?: boolean;
  disabled?: boolean;
  end_date?: string;
}

// ---- Guided set-up (GET /setup) -------------------------------------------------------------------------------------
export interface SetupStep {
  id: "hospital" | "departments" | "people" | "his" | "board";
  label: string;
  done: boolean;
  summary?: string;
}

export interface SetupDepartment {
  id: string;
  name: string;
  group: "treating" | "supporting";
  enabled: boolean;
  email?: string;
  phone?: string;
  receives_requests?: boolean;
}

export interface SetupResponse {
  steps: SetupStep[];
  complete: boolean;
  hospital: { name?: string; level?: string; type?: string; pmjay_empanelled?: boolean; fetch_window_months?: number; meeting_defaults?: MeetingDefaults; logo?: { file?: string; type?: string; at?: string } | null };
  departments: SetupDepartment[];
  board: { coordinators: string[]; heads: string[]; meeting_defaults?: MeetingDefaults };
  his: { url?: string; kind?: string; enabled?: boolean; has_token?: boolean; tested_at?: string | null; ok?: boolean | null; error?: string };
  people?: Array<{ email: string; display_name?: string }>;
  levels?: string[];
  types?: string[];
  weekdays?: string[];
}

export interface MeetingDefaults {
  /** 0 (Monday) to 6 (Sunday) as stored, or a weekday name when sent. */
  weekday?: string | number | null;
  time?: string;
  room?: string;
  minutes_per_case?: number;
}

export interface HisTestResult {
  ok: boolean;
  hospital_name?: string;
  patients?: number | null;
  reports?: number | null;
  latency_ms?: number;
  error?: string;
  fhir_version?: string;
  token_ok?: boolean | null;
}

export type Placement = "member" | "head" | "resident";

export interface NewAccount {
  email: string;
  display_name: string;
  departments: Record<string, Placement>;
  coordinator?: boolean;
  admin_of?: string[];
  root_admin?: boolean;
  auditor?: boolean;
  end_date?: string;
}

export interface SetupPeopleResult {
  ok?: boolean;
  created: Array<{ email: string; mailto: string; username?: string; created?: boolean }>;
  errors: Array<string | { email?: string; message?: string }>;
}

export interface AccountRow {
  username: string;
  display_name?: string;
  departments?: Record<string, string>;
  admin_of?: string[];
  coordinator?: boolean;
  auditor?: boolean;
  disabled?: boolean;
  end_date?: string;
  root_admin?: boolean;
  account?: boolean | null;
  must_change_password?: boolean;
  expired?: boolean;
  vaidyx_admin?: boolean;
  outside_expert?: boolean;
  is_email?: boolean;
}

export interface AccountsResponse {
  accounts: AccountRow[];
  admins?: string[];
  reset_note?: string;
}

// ---- Department people (GET /org/departments/{dept}/doctors) ---------------------------------------------------------
export interface DepartmentDoctor {
  username: string;
  display_name: string;
  role: Placement | null;
  admin: boolean;
  coordinator: boolean;
  disabled: boolean;
  root_admin: boolean;
  auditor?: boolean;
  other_departments: Array<{ id: string; name: string }>;
  admin_of_others: string[];
  account: boolean | null;
  vaidyx_admin: boolean;
  end_date?: string;
  expired?: boolean;
  must_change_password?: boolean;
}

/** GET /departments/{dept}/people (people) or the older GET /org/departments/{dept}/doctors (doctors), read as one shape. */
export interface DepartmentDoctorsResponse {
  department: OrgDepartment;
  doctors: DepartmentDoctor[];
  can_reset?: boolean;
  reset_note?: string;
  roles?: string[];
}

export interface PersonSaved {
  ok?: boolean;
  created?: boolean;
  mailto?: string;
  username?: string;
  must_change_password?: boolean;
}

export interface ResetResult {
  ok?: boolean;
  mailto?: string;
  username?: string;
}

// ---- Push (GET /push/key) ---------------------------------------------------------------------------------------------
export interface PushKey {
  public_key: string | null;
  enabled?: boolean;
}

// ---- Two-factor sign-in (core /api/auth/2fa) -------------------------------------------------------------------------
export interface TotpStatus {
  enabled: boolean;
}

export interface TotpSetup {
  secret: string;
  uri: string;
  qr_code: string;
}

// ---- Admin consoles (docs/admin-console/DESIGN.md section 5.3) -------------------------------------------------------------
// Counts and names of people only: never a patient name, UHID or report text (D5).

export type HospitalStatus = "active" | "suspended";
/** The hospital system's state as the consoles show it. */
export type HisState = "connected" | "failing" | "not_tested" | "not_set";

export interface HospitalHis {
  state: HisState;
  url_set?: boolean;
  tested_at?: string | null;
  ok?: boolean | null;
  /** Demo hospital system (synthetic) chosen at creation. */
  demo?: boolean;
}

/** One row of GET /platform/overview hospitals[] and GET /platform/hospitals. */
export interface HospitalRow {
  id: string;
  name: string;
  city?: string;
  state?: string;
  status: HospitalStatus;
  /** How many hospital admins. */
  admins: number;
  /** How many logins (people) in the hospital. */
  people: number;
  case_files: { open: number; decided: number; total: number };
  setup: { done: number; total: number };
  his: HospitalHis;
  last_activity?: string | null;
  type?: "public" | "private" | "";
  level?: string;
  pmjay_empanelled?: boolean;
  created?: string;
  /** Why it was suspended (shown on the detail page). */
  status_reason?: string;
}

/** The overview tiles (all optional: the page shows the ones the server sends). */
export interface PlatformTiles {
  hospitals_active?: number;
  hospitals_suspended?: number;
  logins?: number;
  hospital_admins?: number;
  case_files?: number;
  meetings_next_7_days?: number;
  setup_complete?: number;
  his_connected?: number;
}

export interface PlatformAttention {
  /** Hospital id. */
  hospital: string;
  hospital_name?: string;
  kind: "no_admin" | "setup_unfinished" | "his_failing" | "admin_never_signed_in" | string;
  text: string;
}

export interface PlatformOverview {
  tiles: PlatformTiles;
  hospitals: HospitalRow[];
  attention: PlatformAttention[];
}

export interface PlatformHospitalsResponse {
  hospitals: HospitalRow[];
}

export interface NewHospital {
  name: string;
  city?: string;
  state?: string;
  type?: "public" | "private" | "";
  level?: string;
  pmjay_empanelled?: boolean;
  demo_his?: boolean;
  admin: { display_name: string; email: string };
}

/** A first password, shown once with Copy and the mail draft (D10). */
export interface OneTimeLogin {
  username: string;
  password_once: string;
  mailto?: string;
}

export interface NewHospitalResult {
  hospital: HospitalRow;
  admin: OneTimeLogin;
}

export interface HospitalAdminRow {
  username: string;
  display_name?: string;
  disabled?: boolean;
  must_change_password?: boolean;
  last_sign_in?: string | null;
}

export interface SetupStepRow {
  id: string;
  label: string;
  done: boolean;
  summary?: string;
}

export interface PlatformEvent {
  ts: string;
  by?: string;
  by_name?: string;
  /** Hospital id (platform activity); absent inside one hospital. */
  hospital?: string;
  hospital_name?: string;
  kind: string;
  text: string;
}

export interface PlatformHospitalDetail {
  hospital: HospitalRow;
  /** Named counts, e.g. people, case_files_open, case_files_decided, meetings_next_7_days, open_requests. */
  counts: Record<string, number>;
  admins: HospitalAdminRow[];
  /** doctors, heads, residents, coordinators, dept_admins, hospital_admins, auditors, guests, disabled. */
  people_by_role: Record<string, number>;
  setup: { steps: SetupStepRow[] };
  his: HospitalHis;
  recent: PlatformEvent[];
}

export interface AddAdminResult {
  username: string;
  created: boolean;
  password_once?: string;
  mailto?: string;
}

export type PlatformRole = "hospital_admin" | "doctor" | "head" | "resident" | "coordinator" | "dept_admin" | "auditor" | "guest" | "vaidyx_admin";

export interface PlatformLogin {
  username: string;
  display_name?: string;
  /** Hospital id. */
  hospital: string;
  hospital_name?: string;
  roles: PlatformRole[] | string[];
  disabled: boolean;
  must_change_password: boolean;
  vaidyx_admin: boolean;
}

export interface PlatformLoginsResponse {
  logins: PlatformLogin[];
}

export interface PlatformResetResult {
  password_once: string;
  mailto?: string;
}

export interface PlatformActivityResponse {
  events: PlatformEvent[];
}

export interface HospitalPeopleCounts {
  doctors: number;
  heads: number;
  residents: number;
  coordinators: number;
  dept_admins: number;
  hospital_admins: number;
  auditors: number;
  guests: number;
  disabled: number;
  never_signed_in: number;
}

export interface HospitalOverview {
  hospital: { id?: string; name: string; city?: string; state?: string; status?: HospitalStatus; level?: string };
  people: HospitalPeopleCounts;
  /** by_status keys: draft, needs_team, waiting_department, ready, scheduled, decided. */
  case_files: { by_status: Record<string, number>; total: number };
  meetings: { next_7_days: number; upcoming: Array<{ id: string; title: string; date: string }> };
  requests: { open: number };
  setup: { steps: SetupStepRow[]; done: number; total: number };
  his: HospitalHis;
  /** link: an in-app path (/hospital/people?role=coordinator) */
  attention: Array<{ kind: string; text: string; link?: string }>;
  recent: Array<{ ts: string; by?: string; by_name?: string; kind: string; text: string }>;
}

export interface HospitalDepartment {
  id: string;
  name: string;
  group: "treating" | "supporting" | string;
  enabled: boolean;
  heads: Array<{ username: string; display_name?: string }> | string[];
  people: number;
  residents: number;
  email?: string;
  phone?: string;
  receives_requests?: boolean;
}

export interface HospitalDepartmentsResponse {
  departments: HospitalDepartment[];
}

/** POST /accounts: the existing route (tumour_board/api/setup.py), the first password inside the mailto only. */
export interface AccountCreated {
  ok?: boolean;
  email?: string;
  username: string;
  created: boolean;
  mailto?: string;
  must_change_password?: boolean;
}
