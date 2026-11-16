// /home: the right home for the person's roles. Vaidyx admin only: the Vaidyx console. Hospital admin only: the Hospital console. Auditor only: Activity. Department admin
// only: People. Supporting doctor: the request cards. Everyone else: the Case File list.
import { Navigate } from "react-router-dom";
import { CaseFileHome } from "@/features/home/CaseFileHome";
import RequestsPage from "@/features/requests/RequestsPage";
import { useSession } from "@/lib/session";
import { isDoctor, isRootAdminOnly, isVaidyxAdminOnly } from "@/lib/nav";
import { PageSkeleton } from "@/app/PageSkeleton";

export default function Home() {
  const { me } = useSession();
  if (!me) return <PageSkeleton />;
  if (isVaidyxAdminOnly(me)) return <Navigate to="/platform" replace />;
  if (isRootAdminOnly(me)) return <Navigate to="/hospital" replace />;
  const doctor = isDoctor(me);
  if (!doctor && !me.roles.coordinator && me.roles.auditor) return <Navigate to="/activity" replace />;
  if (!doctor && !me.roles.coordinator && (me.roles.admin_of || []).length) return <Navigate to="/people" replace />;
  if (me.primary_role === "supporting" || (!(me.roles.treating || []).length && !me.roles.coordinator && (me.roles.supporting || []).length && !Object.values(me.roles.departments || {}).includes("resident"))) {
    return <RequestsPage embedded />;
  }
  if (me.primary_role === "outside_expert" && !doctor) return <Navigate to="/meetings" replace />;
  return <CaseFileHome me={me} />;
}
