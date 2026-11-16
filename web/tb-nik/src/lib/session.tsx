// Who is signed in. One fetch of /api/tb/me on load; every page reads it through useSession().
// The sign-in page calls signIn(); a 401 anywhere sends the person back to /sign-in with the page they wanted.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, AUTH, TB, onUnauthenticated, onMustChangePassword, onTwoFactorRequired, ApiError } from "@/lib/api";
import { unsubscribePush } from "@/lib/push";
import { applyTheme, applyTextSize, type Theme, type TextSize } from "@/lib/appearance";
import { clearActing, setActing, setVaidyxAdmin, type ActingHospital } from "@/lib/acting";

export type RoleKind = "member" | "head" | "resident";

/** Set by signOut; the sign-in page takes it and plays the Vaidyx entrance once. */
export const OUT_FLAG = "tbnik.splash.out";

export interface Me {
  user: string;
  display_name: string;
  roles: {
    admin: boolean;
    /** The Vaidyx admin (server administrator, docs/admin-console D4): the Vaidyx console, and work inside one hospital at a time. */
    vaidyx_admin?: boolean;
    /** The hospital admin of this hospital (org.json admins). The screens say "Hospital admin"; the field keeps its old name. */
    root_admin: boolean;
    coordinator: boolean;
    auditor?: boolean;
    outside_expert?: boolean;
    disabled?: boolean;
    departments: Record<string, RoleKind>;
    treating: string[];
    supporting: string[];
    admin_of: string[];
  };
  primary_role: "treating" | "resident" | "supporting" | "coordinator" | "dept_admin" | "root_admin" | "auditor" | "outside_expert" | "none";
  must_change_password: boolean;
  setup_needed: boolean;
  profile: {
    title?: string;
    registration_no?: string;
    phone?: string;
    phone_visible?: boolean;
    photo?: string;
    theme?: Theme;
    text_size?: TextSize;
    start_page?: "home" | "last_case" | "meetings";
    saved_filters?: Array<{ name: string; query: Record<string, string> }>;
  };
  counts: { unread: number; waiting_for_me: number; open_requests: number; messages_unread?: number };
  hospital: { id?: string; name: string; level?: string; status?: "active" | "suspended" };
  /** docs/admin-console 5.3: true for the Vaidyx admin (the platform admin). */
  platform_admin?: boolean;
  /** For a Vaidyx admin: the hospital named by the X-TB-Hospital header of this request, when it was accepted. */
  acting_hospital?: { id: string; name: string; status?: "active" | "suspended" } | null;
  features: { video: boolean; push: boolean };
  /** Phase 8: this person may use Messages (placed, or the MDT Coordinator). */
  messages?: boolean;
  /** A guest reviewer with anonymized real files: their Case Files are private (5 Nov 2026). */
  real_data?: boolean;
  /** A guest reviewer who has not turned on two-step sign-in yet: Settings, Security comes first. */
  two_factor_required?: boolean;
  /** "private_only": on this site only guest reviewers upload, into their own private Case Files. */
  upload_policy?: "all" | "private_only";
}

interface SessionState {
  me: Me | null;
  loading: boolean;
  error: ApiError | null;
  /** quiet: keep the current page on screen while it reloads (no full-page skeleton). */
  refresh: (opts?: { quiet?: boolean }) => Promise<Me | null>;
  signIn: (username: string, password: string, totp?: string) => Promise<{ ok: boolean; requires_totp?: boolean }>;
  signOut: () => Promise<void>;
  setMe: (m: Me | null) => void;
  /** A Vaidyx admin starts (or stops, with null) working inside a hospital: every cached answer is dropped and /me reloads. */
  setActingHospital: (h: ActingHospital | null) => Promise<void>;
}

/** The Vaidyx admin: the platform flag of DESIGN 5.3, or the role word of /me (either is enough). */
export function isVaidyxAdmin(me: Me | null | undefined): boolean {
  return Boolean(me && (me.platform_admin || me.roles?.vaidyx_admin));
}

const Ctx = createContext<SessionState | null>(null);

// What this browser keeps about the person: dropped on sign out and when the server ends the session (idle timeout), so the next
// person at a shared workstation sees nothing of the last one.
const LOCAL_KEYS = ["tbnik.lastCase"];

function forgetLocal() {
  for (const k of LOCAL_KEYS) {
    try { localStorage.removeItem(k); } catch { /* storage blocked */ }
  }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);

  const refresh = useCallback(async (opts: { quiet?: boolean } = {}) => {
    if (!opts.quiet) setLoading(true);
    try {
      const m = await api.get<Me>(`${TB}/me`, { quiet401: true });
      setVaidyxAdmin(isVaidyxAdmin(m));  // anyone else never sends or keeps an acting hospital
      setMe(m);
      setError(null);
      if (m.profile?.theme) applyTheme(m.profile.theme);
      if (m.profile?.text_size) applyTextSize(m.profile.text_size);
      return m;
    } catch (e) {
      setMe(null);
      setError(e instanceof ApiError && e.status !== 401 ? e : null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  useEffect(() => {
    const off = onUnauthenticated((err) => {
      setMe(null);
      clearActing();
      if (err.code === "idle_timeout") { queryClient.clear(); forgetLocal(); }  // the server ended an idle session
    });
    const off2 = onMustChangePassword(() => setMe((m) => (m ? { ...m, must_change_password: true } : m)));
    const off3 = onTwoFactorRequired(() => setMe((m) => (m ? { ...m, two_factor_required: true } : m)));
    return () => { off(); off2(); off3(); };
  }, [queryClient]);

  const signIn = useCallback(async (username: string, password: string, totp?: string) => {
    const r = await api.post<{ ok: boolean; requires_totp?: boolean }>(`${AUTH}/login`, { username, password, remember: true, totp_code: totp || undefined }, { quiet401: true });
    if (r.ok) await refresh();
    return r;
  }, [refresh]);

  const signOut = useCallback(async () => {
    // Best effort: this device stops receiving the person's push notifications (needs the session, so before the logout).
    try { await unsubscribePush(); } catch { /* no subscription, or the browser refused */ }
    try { await api.post(`${AUTH}/logout`); } catch { /* the cookie is gone either way */ }
    setMe(null);
    clearActing();  // the next person at this tab starts in no hospital
    queryClient.clear();  // no Case File, list or meeting of this person stays in memory for the next one
    forgetLocal();
    try { sessionStorage.setItem(OUT_FLAG, "1"); } catch { /* no storage */ }   // the sign-in page plays the entrance once
  }, [queryClient]);

  const setActingHospital = useCallback(async (h: ActingHospital | null) => {
    setActing(h);
    // Nothing of the last hospital may stay on screen: drop every cached answer (active lists show their skeleton and reload).
    await queryClient.cancelQueries();
    void queryClient.resetQueries();
    await refresh({ quiet: true });
  }, [queryClient, refresh]);

  const value = useMemo(() => ({ me, loading, error, refresh, signIn, signOut, setMe, setActingHospital }), [me, loading, error, refresh, signIn, signOut, setActingHospital]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession(): SessionState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useSession outside SessionProvider");
  return v;
}
