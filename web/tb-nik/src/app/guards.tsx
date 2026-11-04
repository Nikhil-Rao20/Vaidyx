import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useSession } from "@/lib/session";
import { PageSkeleton } from "@/app/PageSkeleton";

/** Pages that need a signed-in person. A forced password change or an unfinished profile is handled first. */
export function RequireSession() {
  const { me, loading } = useSession();
  const loc = useLocation();
  if (loading) return <PageSkeleton />;
  if (!me) return <Navigate to="/sign-in" replace state={{ from: loc.pathname + loc.search }} />;
  if (me.must_change_password && loc.pathname !== "/first-login") return <Navigate to="/first-login" replace />;
  // a guest reviewer (real, anonymized files) turns on two-step sign-in before anything else
  if (!me.must_change_password && me.two_factor_required && loc.pathname !== "/settings") return <Navigate to="/settings#security" replace />;
  if (!me.must_change_password && !me.two_factor_required && me.setup_needed && loc.pathname !== "/welcome" && loc.pathname !== "/first-login") return <Navigate to="/welcome" replace />;
  return <Outlet />;
}

/** Pages for people who are not signed in (sign-in). A signed-in person goes to their start page. */
export function PublicOnly() {
  const { me, loading } = useSession();
  if (loading) return <PageSkeleton />;
  if (me) return <Navigate to={startPage(me.profile?.start_page)} replace />;
  return <Outlet />;
}

export function startPage(pref?: string) {
  if (pref === "meetings") return "/meetings";
  if (pref === "last_case") {
    try { const last = localStorage.getItem("tbnik.lastCase"); if (last) return `/cases/${last}`; } catch { /* no storage */ }
  }
  return "/cases";
}
