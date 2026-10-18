// Who is signed in. One fetch of /api/tb/me on load; every page reads it through useSession().
// The sign-in page calls signIn(); a 401 anywhere sends the person back to /sign-in with the page they wanted.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, AUTH, TB, onUnauthenticated, onMustChangePassword, ApiError } from "@/lib/api";
import { applyTheme, applyTextSize, type Theme, type TextSize } from "@/lib/appearance";

export type RoleKind = "member" | "head" | "resident";

export interface Me {
  user: string;
  display_name: string;
  roles: {
    admin: boolean;
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
  counts: { unread: number; waiting_for_me: number; open_requests: number };
  hospital: { name: string; level?: string };
  features: { video: boolean; push: boolean };
}

interface SessionState {
  me: Me | null;
  loading: boolean;
  error: ApiError | null;
  refresh: () => Promise<Me | null>;
  signIn: (username: string, password: string, totp?: string) => Promise<{ ok: boolean; requires_totp?: boolean }>;
  signOut: () => Promise<void>;
  setMe: (m: Me | null) => void;
}

const Ctx = createContext<SessionState | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const m = await api.get<Me>(`${TB}/me`, { quiet401: true });
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
    const off = onUnauthenticated(() => setMe(null));
    const off2 = onMustChangePassword(() => setMe((m) => (m ? { ...m, must_change_password: true } : m)));
    return () => { off(); off2(); };
  }, []);

  const signIn = useCallback(async (username: string, password: string, totp?: string) => {
    const r = await api.post<{ ok: boolean; requires_totp?: boolean }>(`${AUTH}/login`, { username, password, remember: true, totp_code: totp || undefined }, { quiet401: true });
    if (r.ok) await refresh();
    return r;
  }, [refresh]);

  const signOut = useCallback(async () => {
    try { await api.post(`${AUTH}/logout`); } catch { /* the cookie is gone either way */ }
    setMe(null);
  }, []);

  const value = useMemo(() => ({ me, loading, error, refresh, signIn, signOut, setMe }), [me, loading, error, refresh, signIn, signOut]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession(): SessionState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useSession outside SessionProvider");
  return v;
}
