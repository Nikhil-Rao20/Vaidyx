// /platform: the Vaidyx console (docs/admin-console/DESIGN.md 4.1), for the Vaidyx admin only. Tabs as sub-routes: Overview,
// Hospitals, Logins, Activity. "Add a hospital" sits in the header on every tab. Counts and names of people only, never patient data.
import { Suspense, useState } from "react";
import { Outlet, useOutletContext } from "react-router-dom";
import { Activity, Building2, KeyRound, LayoutDashboard, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState } from "@/components/EmptyState";
import { isVaidyxAdmin, useSession } from "@/lib/session";
import { ConsoleTabs, TabSkeleton } from "@/features/consoles/shared";
import { AddHospitalDialog } from "@/features/consoles/platform/AddHospitalDialog";

export interface PlatformContext {
  openAddHospital: () => void;
}

export function usePlatformContext(): PlatformContext {
  return useOutletContext<PlatformContext>();
}

const TABS = [
  { to: "/platform", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/platform/hospitals", label: "Hospitals", icon: Building2 },
  { to: "/platform/logins", label: "Logins", icon: KeyRound },
  { to: "/platform/activity", label: "Activity", icon: Activity },
];

export function NotVaidyxAdmin() {
  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="Vaidyx console" />
      <div className="surface"><EmptyState kind="lock" title="Only the Vaidyx admin opens the Vaidyx console" text="It lists every hospital on this Vaidyx server. Your own hospital's work is in the menu above." /></div>
    </div>
  );
}

export default function PlatformConsole() {
  const { me } = useSession();
  const [adding, setAddingState] = useState(false);
  const [opened, setOpened] = useState(0);  // a fresh dialog each time it opens
  const setAdding = (o: boolean) => { if (o) setOpened((n) => n + 1); setAddingState(o); };
  if (!me) return null;
  if (!isVaidyxAdmin(me)) return <NotVaidyxAdmin />;
  const ctx: PlatformContext = { openAddHospital: () => setAdding(true) };
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Vaidyx console"
        subtitle="Every hospital on this Vaidyx server: counts and people, never patient data."
        actions={<Button type="button" onClick={() => setAdding(true)}><Plus className="size-4" aria-hidden /> Add a hospital</Button>}
      />
      <ConsoleTabs tabs={TABS} label="Vaidyx console sections" id="platform" />
      <Suspense fallback={<TabSkeleton />}>
        <Outlet context={ctx} />
      </Suspense>
      <AddHospitalDialog key={opened} open={adding} onOpenChange={setAdding} />
    </div>
  );
}
