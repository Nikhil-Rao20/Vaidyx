// Every path the new interface calls, in one place (docs/ui/build/SPEC-API.md). The Case File list lives at /case-list
// (not under /cases/{id}, which the old guards would read as a Case File id).
import { TB, AUTH } from "@/lib/api";

const id = (s: string) => encodeURIComponent(s);

export const EP = {
  login: `${AUTH}/login`,
  logout: `${AUTH}/logout`,

  me: `${TB}/me`,
  password: `${TB}/me/password`,
  profile: `${TB}/me/profile`,
  myActivity: `${TB}/me/activity`,
  myNotifications: `${TB}/me/notifications`,
  activity: `${TB}/activity`,

  caseList: `${TB}/case-list`,
  cases: `${TB}/cases`,
  case: (c: string) => `${TB}/cases/${id(c)}`,
  urgency: (c: string) => `${TB}/cases/${id(c)}/urgency`,
  /** POST /case-join (not /cases/join: the Case File guard would read "join" as a Case File id). */
  joinCase: `${TB}/case-join`,
  /** POST {case_id, note?}: "Ask to join" a Case File without a code (night-v3 item 1.1). */
  askToJoin: `${TB}/case-join/ask`,
  /** GET ?identifier=<UHID, IP No. or OP No.> or ?case_id=<id>: the patient's live Case Files (night-v3 item 1.1). */
  patientCaseFiles: `${TB}/patient-case-files`,
  team: (c: string) => `${TB}/cases/${id(c)}/team`,
  proposals: (c: string) => `${TB}/cases/${id(c)}/proposals`,
  proposalApprove: (c: string, p: string) => `${TB}/cases/${id(c)}/proposals/${id(p)}/approve`,
  proposalReturn: (c: string, p: string) => `${TB}/cases/${id(c)}/proposals/${id(p)}/return`,
  pendingApprove: (c: string, u: string) => `${TB}/cases/${id(c)}/team/pending/${id(u)}/approve`,
  pendingReject: (c: string, u: string) => `${TB}/cases/${id(c)}/team/pending/${id(u)}/reject`,
  teamCode: (c: string) => `${TB}/cases/${id(c)}/team/code`,
  waiting: `${TB}/waiting`,

  notifications: `${TB}/notifications`,
  notificationsRead: `${TB}/notifications/read`,

  inbox: `${TB}/inbox`,
  requestAcknowledge: (c: string, a: string) => `${TB}/cases/${id(c)}/requests/${id(a)}/acknowledge`,
  requestDone: (c: string, a: string) => `${TB}/cases/${id(c)}/requests/${id(a)}/done`,
  documentImages: (c: string, d: string) => `${TB}/cases/${id(c)}/documents/${id(d)}/images`,

  hisLookup: `${TB}/his/lookup`,
  fromHis: `${TB}/cases/from-his`,
  hisTest: `${TB}/his/test`,
  protocols: `${TB}/protocols`,
  protocol: (p: string) => `${TB}/protocols/${id(p)}`,
  job: (j: string) => `${TB}/jobs/${id(j)}`,
  org: `${TB}/org`,
  meetings: `${TB}/meetings`,
  joinMeeting: `${TB}/meetings/join`,

  setup: `${TB}/setup`,
  setupHospital: `${TB}/setup/hospital`,
  setupHospitalLogo: `${TB}/setup/hospital/logo`,
  hospitalLogo: `${TB}/hospital/logo`,
  setupDepartments: `${TB}/setup/departments`,
  setupPeople: `${TB}/setup/people`,
  setupHis: `${TB}/setup/his`,
  setupBoard: `${TB}/setup/board`,
  accounts: `${TB}/accounts`,
  account: (u: string) => `${TB}/accounts/${id(u)}`,
  resetPassword: (u: string) => `${TB}/accounts/${id(u)}/reset-password`,
  /** The department admin's people list (residents with end dates, a mailto on create); the older doctors route is the fallback. */
  deptPeople: (d: string) => `${TB}/departments/${id(d)}/people`,
  deptPerson: (d: string, u: string) => `${TB}/departments/${id(d)}/people/${id(u)}`,
  deptDoctors: (d: string) => `${TB}/org/departments/${id(d)}/doctors`,
  deptDoctor: (d: string, u: string) => `${TB}/org/departments/${id(d)}/doctors/${id(u)}`,

  totpStatus: `${AUTH}/2fa/status`,
  totpSetup: `${AUTH}/2fa/setup`,
  totpConfirm: `${AUTH}/2fa/confirm`,
  totpDisable: `${AUTH}/2fa/disable`,

  pushKey: `${TB}/push/key`,
  pushSubscribe: `${TB}/push/subscribe`,
};

/** The demo hospital system. On this machine (localhost or 127.0.0.1, with the ssh tunnel) it is on port 7130 of the host
 *  name this page was opened with: the HIMS login is a cookie of that host, and 127.0.0.1 and localhost keep separate
 *  logins. Anywhere else (the public link) the gate serves the hospital system under the same address at /his. */
export function himsBase(): string {
  if (typeof window === "undefined") return "http://127.0.0.1:7130/his";
  const host = window.location.hostname || "127.0.0.1";
  const local = host === "localhost" || host === "127.0.0.1" || host === "[::1]";
  if (!local) return `${window.location.origin}/his`;
  return `${window.location.protocol === "https:" ? "https" : "http"}://${host}:7130/his`;
}

/** Straight to the order of a request in the hospital system (its Pathology, Radiology or Lab page), else to the patient.
 *  Signed out, the HIMS asks for the login first and then opens the same order. */
export function himsLink(t: { accession?: string | null; uhid?: string | null } = {}): string {
  const p = new URLSearchParams();
  if (t.accession) p.set("accession", t.accession);
  if (t.uhid) p.set("uhid", t.uhid);
  const qs = p.toString();
  return qs ? `${himsBase()}/open?${qs}` : himsBase();
}
