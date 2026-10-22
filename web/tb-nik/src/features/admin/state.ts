// The guided set-up's form state, built once from GET /setup and kept while the root admin moves between steps.
import type { Placement, SetupResponse } from "@/lib/types";

export const PLACEHOLDER_DOMAIN = "hospital.example";
export const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
export const DEFAULT_HEADS = ["radiology", "medical_oncology", "surgical_oncology", "pathology", "radiation_oncology"];

export interface HospitalState { name: string; level: string; type: string; pmjay: boolean; fetchWindow: number }
export interface DepartmentsState { enabled: string[]; contacts: Record<string, { email: string; phone: string }> }
export interface PersonRow {
  key: string;
  email: string;
  name: string;
  dept: string;
  role: Placement;
  coordinator: boolean;
  deptAdmin: boolean;
  rootAdmin: boolean;
  endDate: string;
  /** After POST /setup/people: the mail draft with the first password, or the server's reason. */
  mailto?: string;
  error?: string;
  created?: boolean;
}
export interface HisState { url: string; token: string }
export interface BoardState { coordinators: string[]; heads: string[]; weekday: string; time: string; room: string; minutes: number }

export interface SetupForm {
  hospital: HospitalState;
  departments: DepartmentsState;
  people: PersonRow[];
  his: HisState;
  board: BoardState;
}

let n = 0;
export function newRow(dept = ""): PersonRow {
  n += 1;
  return { key: `row-${Date.now()}-${n}`, email: "", name: "", dept, role: "member", coordinator: false, deptAdmin: false, rootAdmin: false, endDate: "" };
}

function weekdayName(w: unknown): string {
  if (typeof w === "number" && w >= 0 && w <= 6) return WEEKDAYS[w];
  if (typeof w === "string" && WEEKDAYS.includes(w)) return w;
  return "";
}

export function formFrom(s: SetupResponse): SetupForm {
  const md = s.board?.meeting_defaults ?? s.hospital?.meeting_defaults ?? {};
  const contacts: DepartmentsState["contacts"] = {};
  for (const d of s.departments ?? []) {
    const email = d.email && !d.email.endsWith(`@${PLACEHOLDER_DOMAIN}`) ? d.email : "";
    contacts[d.id] = { email, phone: d.phone ?? "" };
  }
  return {
    hospital: {
      name: s.hospital?.name ?? "",
      level: s.hospital?.level || "essential",
      type: s.hospital?.type ?? "",
      pmjay: s.hospital?.pmjay_empanelled ?? true,
      fetchWindow: s.hospital?.fetch_window_months ?? 12,
    },
    departments: { enabled: (s.departments ?? []).filter((d) => d.enabled).map((d) => d.id), contacts },
    people: [newRow()],
    his: { url: s.his?.url || "http://127.0.0.1:7130", token: "" },
    board: {
      coordinators: s.board?.coordinators ?? [],
      heads: s.board?.heads?.length ? s.board.heads : DEFAULT_HEADS,
      weekday: weekdayName(md.weekday),
      time: md.time ?? "",
      room: md.room ?? "",
      minutes: Number(md.minutes_per_case) || 10,
    },
  };
}

export const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
