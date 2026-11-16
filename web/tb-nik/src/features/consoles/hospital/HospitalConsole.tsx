// /hospital: the Hospital console (docs/admin-console/DESIGN.md 4.2) for the hospital admin, and for a Vaidyx admin working inside
// one hospital. Tabs as sub-routes: Overview, People, Departments, Set-up, Hospital system, Activity. "Add a person" is one dialog
// for the whole console (the overview's quick actions open it preset to a role).
import { Suspense, useState } from "react";
import { plural } from "@/lib/format";
import { Outlet, useLocation, useOutletContext } from "react-router-dom";
import { Activity, Building2, LayoutDashboard, LogIn, PlugZap, Settings2, UserPlus, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState } from "@/components/EmptyState";
import { DataList } from "@/components/DataList";
import { usePlatformHospitals } from "@/hooks/useQueries";
import { isVaidyxAdmin, useSession, type Me } from "@/lib/session";
import { useActingHospital } from "@/lib/acting";
import { ConsoleTabs, HisPill, HospitalStatusPill, TabSkeleton, greeting } from "@/features/consoles/shared";
import { useManageHospital } from "@/features/consoles/useManage";
import { AddPersonDialog, type PersonRole } from "@/features/consoles/hospital/PersonDialogs";

export interface HospitalContext {
  openAddPerson: (role?: PersonRole) => void;
  hospitalName: string;
}

export function useHospitalContext(): HospitalContext {
  return useOutletContext<HospitalContext>();
}

const TABS = [
  { to: "/hospital", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/hospital/people", label: "People", icon: Users },
  { to: "/hospital/departments", label: "Departments", icon: Building2 },
  { to: "/hospital/setup", label: "Set-up", icon: Settings2 },
  { to: "/hospital/system", label: "Hospital system", icon: PlugZap },
  { to: "/hospital/activity", label: "Activity", icon: Activity },
];

const SUBTITLE: Record<string, string> = {
  "/hospital/people": "Everyone with a login in this hospital. Add a person, change a role, reset a password.",
  "/hospital/departments": "The hospital's departments, their heads, people and desk contacts.",
  "/hospital/setup": "The guided set-up: hospital, departments, people, hospital system and board. Each step saves as you go.",
  "/hospital/system": "Where Vaidyx reads the reports from. The test must pass before Case Files come from a UHID.",
  "/hospital/activity": "Every action in this hospital's Tumour Board is recorded.",
};

/** Who may open the Hospital console: the hospital admin, or a Vaidyx admin working inside a hospital. */
export function mayManageHospital(me: Me, acting: { id: string } | null): boolean {
  return Boolean(me.roles.root_admin) || (isVaidyxAdmin(me) && Boolean(acting));
}

/** A Vaidyx admin who has not chosen a hospital yet. */
function ChooseHospital() {
  const q = usePlatformHospitals();
  const { manage } = useManageHospital();
  const rows = (q.data?.hospitals ?? []).filter((h) => h.status !== "suspended");
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title="Hospital console" subtitle="Choose the hospital to work inside, as Vaidyx admin. You can switch at any time from the bar at the top." />
      <DataList
        items={rows}
        loading={q.isLoading}
        error={q.error}
        onRetry={() => void q.refetch()}
        what="the hospitals"
        keyFor={(h) => h.id}
        renderRow={(h) => (
          <div className="surface-inner flex flex-wrap items-center gap-3 px-3 py-3">
            <span className="grid size-9 shrink-0 place-items-center rounded-md bg-secondary text-secondary-foreground"><Building2 className="size-4" aria-hidden /></span>
            <span className="min-w-0 flex-1">
              <span className="block font-medium text-foreground">{h.name}</span>
              <span className="block text-xs text-muted-foreground">{[h.city, h.state].filter(Boolean).join(", ") || "Place not given"} · {plural(h.people, "person", "people")}</span>
            </span>
            <HospitalStatusPill status={h.status} />
            <HisPill his={h.his} />
            <Button type="button" size="sm" onClick={() => void manage({ id: h.id, name: h.name })}><LogIn className="size-4" aria-hidden /> Manage</Button>
          </div>
        )}
        empty={<div className="surface"><EmptyState kind="empty" title="No hospital to manage" text="Add a hospital in the Vaidyx console first." /></div>}
      />
    </div>
  );
}

export default function HospitalConsole() {
  const { me } = useSession();
  const acting = useActingHospital();
  const { pathname } = useLocation();
  // A fresh dialog each time it opens (no state of the last person left behind).
  const [adding, setAddingState] = useState<{ role?: PersonRole; n: number } | null>(null);
  const [opened, setOpened] = useState(0);
  const setAdding = (v: { role?: PersonRole } | null) => { if (v) { setOpened((n) => n + 1); setAddingState({ ...v, n: opened + 1 }); } else setAddingState(null); };
  if (!me) return null;
  if (!mayManageHospital(me, acting)) {
    if (isVaidyxAdmin(me)) return <ChooseHospital />;
    return (
      <div className="mx-auto max-w-2xl">
        <PageHeader title="Hospital console" />
        <div className="surface"><EmptyState kind="lock" title="Only a hospital admin opens the Hospital console" text={(me.roles.admin_of || []).length ? "You manage your department's people on the People page." : "Ask the hospital admin of your hospital."} /></div>
      </div>
    );
  }
  const vaidyx = isVaidyxAdmin(me) && Boolean(acting);
  const hospitalName = (vaidyx ? me.acting_hospital?.name || acting?.name : me.hospital?.name) || me.hospital?.name || "Your hospital";
  const ctx: HospitalContext = { openAddPerson: (role) => setAdding({ role }), hospitalName };
  const subtitle = SUBTITLE[pathname] ?? `${greeting()}, ${me.display_name || me.user}. Here is how ${hospitalName} stands today.`;
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title={hospitalName}
        subtitle={subtitle}
        actions={<Button type="button" onClick={() => setAdding({})}><UserPlus className="size-4" aria-hidden /> Add a person</Button>}
      />
      <ConsoleTabs tabs={TABS} label="Hospital console sections" id="hospital" />
      <Suspense fallback={<TabSkeleton />}>
        <Outlet context={ctx} />
      </Suspense>
      <AddPersonDialog key={adding?.n ?? opened} open={Boolean(adding)} initialRole={adding?.role} onOpenChange={(o) => { if (!o) setAdding(null); }} hospitalName={hospitalName} />
    </div>
  );
}
