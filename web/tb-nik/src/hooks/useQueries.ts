// React Query hooks for the lists the shell and the home pages read. Every hook keeps the last good answer while it
// refreshes, retries once, and leaves a 404 to the page (an endpoint that is not built yet shows "not available yet").
import { useQuery, useQueryClient, type UseQueryOptions } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import { isRouteMissing } from "@/lib/errors";
import type { FilterQuery } from "@/lib/filters";
import { toSearchParams } from "@/lib/filters";
import type {
  AccountsResponse, ActivityResponse, CaseListResponse, DepartmentDoctor, DepartmentDoctorsResponse, InboxResponse, Job, MeetingsResponse,
  NotificationPrefs, NotificationsResponse, OrgDepartment, OrgResponse, ProtocolsResponse, SetupResponse, TotpStatus, WaitingResponse,
} from "@/lib/types";

export const keys = {
  caseList: (q?: FilterQuery) => ["case-list", q ? toSearchParams(q).toString() : ""] as const,
  /** Every Case File list, whatever its filters (for invalidation). */
  caseLists: ["case-list"] as const,
  accounts: ["accounts"] as const,
  totp: ["totp-status"] as const,
  waiting: ["waiting"] as const,
  notifications: ["notifications"] as const,
  inbox: ["inbox"] as const,
  protocols: ["protocols"] as const,
  org: ["org"] as const,
  meetings: ["meetings"] as const,
  setup: ["setup"] as const,
  myActivity: ["my-activity"] as const,
  activity: (params: string) => ["activity", params] as const,
  job: (id: string) => ["job", id] as const,
  deptDoctors: (dept: string) => ["dept-doctors", dept] as const,
  notificationPrefs: ["notification-prefs"] as const,
};

/** True when the server answered 404 for the endpoint itself (not built yet). */
export function notBuiltYet(err: unknown): boolean {
  return isRouteMissing(err);
}

/** A 404 from an endpoint that does not exist yet is not worth a retry; a network blip is. */
function retry(count: number, err: unknown): boolean {
  if (err instanceof ApiError && (err.status === 404 || err.status === 401 || err.status === 403 || err.status === 400)) return false;
  return count < 1;
}

type Opts<T> = Omit<UseQueryOptions<T, Error>, "queryKey" | "queryFn">;

export function useCaseList(q: FilterQuery = {}, opts: Opts<CaseListResponse> = {}) {
  const sp = toSearchParams(q).toString();
  return useQuery<CaseListResponse, Error>({
    queryKey: keys.caseList(q),
    queryFn: () => api.get<CaseListResponse>(sp ? `${EP.caseList}?${sp}` : EP.caseList),
    retry,
    placeholderData: (prev) => prev,
    ...opts,
  });
}

export function useWaiting(opts: Opts<WaitingResponse> = {}) {
  return useQuery<WaitingResponse, Error>({ queryKey: keys.waiting, queryFn: () => api.get<WaitingResponse>(EP.waiting), retry, refetchInterval: 60_000, ...opts });
}

export function useNotifications(opts: Opts<NotificationsResponse> = {}) {
  return useQuery<NotificationsResponse, Error>({
    queryKey: keys.notifications,
    queryFn: () => api.get<NotificationsResponse>(`${EP.notifications}?limit=50`),
    retry,
    refetchInterval: 45_000,
    ...opts,
  });
}

export function useInbox(opts: Opts<InboxResponse> = {}) {
  return useQuery<InboxResponse, Error>({ queryKey: keys.inbox, queryFn: () => api.get<InboxResponse>(EP.inbox), retry, refetchInterval: 60_000, ...opts });
}

export function useProtocols(opts: Opts<ProtocolsResponse> = {}) {
  return useQuery<ProtocolsResponse, Error>({ queryKey: keys.protocols, queryFn: () => api.get<ProtocolsResponse>(EP.protocols), retry, staleTime: 10 * 60_000, ...opts });
}

export function useOrg(opts: Opts<OrgResponse> = {}) {
  return useQuery<OrgResponse, Error>({ queryKey: keys.org, queryFn: () => api.get<OrgResponse>(EP.org), retry, staleTime: 5 * 60_000, ...opts });
}

export function useMeetings(opts: Opts<MeetingsResponse> = {}) {
  return useQuery<MeetingsResponse, Error>({ queryKey: keys.meetings, queryFn: () => api.get<MeetingsResponse>(EP.meetings), retry, ...opts });
}

export function useSetup(opts: Opts<SetupResponse> = {}) {
  return useQuery<SetupResponse, Error>({ queryKey: keys.setup, queryFn: () => api.get<SetupResponse>(EP.setup), retry, ...opts });
}

export function useMyActivity(opts: Opts<ActivityResponse> = {}) {
  return useQuery<ActivityResponse, Error>({ queryKey: keys.myActivity, queryFn: () => api.get<ActivityResponse>(`${EP.myActivity}?limit=200`), retry, ...opts });
}

export function useActivity(params: Record<string, string>, opts: Opts<ActivityResponse> = {}) {
  const sp = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
  return useQuery<ActivityResponse, Error>({ queryKey: keys.activity(sp), queryFn: () => api.get<ActivityResponse>(sp ? `${EP.activity}?${sp}` : EP.activity), retry, ...opts });
}

export function useNotificationPrefs(opts: Opts<NotificationPrefs> = {}) {
  return useQuery<NotificationPrefs, Error>({ queryKey: keys.notificationPrefs, queryFn: () => api.get<NotificationPrefs>(EP.myNotifications), retry, ...opts });
}

/** The department's people: the new route (residents, end dates) first; the older doctors route when the new one is not there. */
async function departmentPeople(dept: string): Promise<DepartmentDoctorsResponse> {
  try {
    const r = await api.get<{ department: OrgDepartment; people: DepartmentDoctor[]; can_reset?: boolean; roles?: string[]; reset_note?: string }>(EP.deptPeople(dept));
    return { department: r.department, doctors: r.people ?? [], can_reset: r.can_reset, roles: r.roles, reset_note: r.reset_note };
  } catch (e) {
    if (isRouteMissing(e)) return api.get<DepartmentDoctorsResponse>(EP.deptDoctors(dept));
    throw e;
  }
}

export function useDepartmentDoctors(dept: string | null, opts: Opts<DepartmentDoctorsResponse> = {}) {
  return useQuery<DepartmentDoctorsResponse, Error>({
    queryKey: keys.deptDoctors(dept || ""),
    queryFn: () => departmentPeople(dept as string),
    enabled: Boolean(dept),
    retry,
    ...opts,
  });
}

export function useAccounts(opts: Opts<AccountsResponse> = {}) {
  return useQuery<AccountsResponse, Error>({ queryKey: keys.accounts, queryFn: () => api.get<AccountsResponse>(EP.accounts), retry, ...opts });
}

export function useTotpStatus(opts: Opts<TotpStatus> = {}) {
  return useQuery<TotpStatus, Error>({ queryKey: keys.totp, queryFn: () => api.get<TotpStatus>(EP.totpStatus), retry, ...opts });
}

/** Polls a fetch job every 1.5 s until it finishes or fails. */
export function useJob(jobId: string | null, opts: Opts<Job> = {}) {
  return useQuery<Job, Error>({
    queryKey: keys.job(jobId || ""),
    queryFn: () => api.get<Job>(EP.job(jobId as string)),
    enabled: Boolean(jobId),
    retry,
    refetchInterval: (q) => {
      const j = q.state.data;
      return j && j.state !== "running" ? false : 1500;
    },
    ...opts,
  });
}

export function useInvalidate() {
  const qc = useQueryClient();
  return (...ks: Array<readonly unknown[]>) => Promise.all(ks.map((k) => qc.invalidateQueries({ queryKey: k })));
}
