// /hospital/setup: today's guided set-up (the same screen as /admin, which keeps working as it was), inside the Hospital console.
import AdminSetup from "@/features/admin/AdminSetup";

export default function HospitalSetup() {
  return <AdminSetup embedded />;
}
