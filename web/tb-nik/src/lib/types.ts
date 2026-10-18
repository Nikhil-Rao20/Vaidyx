// The shapes the new interface reads from /api/tb (docs/ui/build/SPEC-API.md and the existing routes).
// Every field the server may leave out is optional here, so a page never crashes on a thin answer.

export type { Me, RoleKind } from "@/lib/session";

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
  /** Free text name when the cancer has no built checklist. */
  cancer_name?: string;
  /** The person owns it, is on its team, or created it (server side "mine"). */
  mine?: boolean;
  scope?: "FULL" | "REQUESTS" | string | null;
  documents?: number;
  gate_passed?: boolean | null;
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
  hospital: { name?: string; level?: string; type?: string; pmjay_empanelled?: boolean; fetch_window_months?: number; meeting_defaults?: MeetingDefaults };
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
