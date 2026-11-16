// /platform/activity: the platform audit, newest first (GET /platform/activity?hospital=&kind=&limit=). Hospitals added, admins,
// password resets, logins disabled, suspensions, a Vaidyx admin working inside a hospital. No patient data.
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import { Activity, Building2, KeyRound, LogIn, PauseCircle, PlayCircle, Pencil, ShieldCheck, ShieldMinus, UserMinus, UserRoundCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SearchBox } from "@/components/SearchBox";
import { DataList } from "@/components/DataList";
import { EmptyState } from "@/components/EmptyState";
import { DateText } from "@/components/DateText";
import { usePlatformActivity, usePlatformHospitals } from "@/hooks/useQueries";
import type { PlatformEvent } from "@/lib/types";

const ALL = "all";
export const KINDS: Record<string, { label: string; icon: LucideIcon }> = {
  hospital_created: { label: "Hospital added", icon: Building2 },
  hospital_updated: { label: "Details changed", icon: Pencil },
  hospital_suspended: { label: "Hospital suspended", icon: PauseCircle },
  hospital_reactivated: { label: "Hospital reactivated", icon: PlayCircle },
  admin_added: { label: "Hospital admin added", icon: ShieldCheck },
  admin_removed: { label: "Hospital admin removed", icon: ShieldMinus },
  password_reset: { label: "Password reset", icon: KeyRound },
  login_disabled: { label: "Login disabled", icon: UserMinus },
  login_enabled: { label: "Login enabled", icon: UserRoundCheck },
  acting_in: { label: "Worked inside a hospital", icon: LogIn },
};

export function EventLine({ e, hospitalName }: { e: PlatformEvent; hospitalName?: string }) {
  const k = KINDS[e.kind];
  const Icon = k?.icon ?? Activity;
  return (
    <div className="surface-inner flex min-h-12 items-start gap-3 px-3 py-2.5">
      <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-md bg-muted text-muted-foreground"><Icon className="size-4" aria-hidden /></span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-foreground">{e.text || k?.label || e.kind}</p>
        <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
          <DateText value={e.ts} mode="datetime" />
          {e.by_name || e.by ? <span>{e.by_name || e.by}</span> : null}
          {e.hospital ? <Link to={`/platform/hospitals/${encodeURIComponent(e.hospital)}`} className="text-link hover:underline">{e.hospital_name || hospitalName || e.hospital}</Link> : null}
        </p>
      </div>
    </div>
  );
}

export default function PlatformActivity() {
  const hospitals = usePlatformHospitals();
  const [hospital, setHospital] = useState(ALL);
  const [kind, setKind] = useState(ALL);
  const [limit, setLimit] = useState("200");
  const [search, setSearch] = useState("");
  const q = usePlatformActivity({ hospital: hospital === ALL ? "" : hospital, kind: kind === ALL ? "" : kind, limit });
  const names = useMemo(() => new Map((hospitals.data?.hospitals ?? []).map((h) => [h.id, h.name])), [hospitals.data]);
  const rows = useMemo(() => {
    const n = search.trim().toLowerCase();
    return (q.data?.events ?? [])
      .filter((e) => hospital === ALL || e.hospital === hospital)
      .filter((e) => kind === ALL || e.kind === kind)
      .filter((e) => !n || [e.text, e.by, e.by_name, e.hospital_name, names.get(e.hospital ?? "")].filter(Boolean).join(" ").toLowerCase().includes(n));
  }, [q.data, hospital, kind, search, names]);
  const filtered = Boolean(search || hospital !== ALL || kind !== ALL);
  return (
    <div className="grid grid-cols-1 gap-3">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_200px_200px_140px]">
        <SearchBox value={search} onChange={setSearch} placeholder="Search the activity" label="Search the activity" />
        <Select value={hospital} onValueChange={setHospital}>
          <SelectTrigger className="w-full" aria-label="Hospital"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Every hospital</SelectItem>
            {(hospitals.data?.hospitals ?? []).map((h) => <SelectItem key={h.id} value={h.id}>{h.name}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={kind} onValueChange={setKind}>
          <SelectTrigger className="w-full" aria-label="Kind"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Every kind</SelectItem>
            {Object.entries(KINDS).map(([k, v]) => <SelectItem key={k} value={k}>{v.label}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={limit} onValueChange={setLimit}>
          <SelectTrigger className="w-full" aria-label="How many"><SelectValue /></SelectTrigger>
          <SelectContent>{["100", "200", "500"].map((n) => <SelectItem key={n} value={n}>Newest {n}</SelectItem>)}</SelectContent>
        </Select>
      </div>
      <DataList
        items={rows}
        loading={q.isLoading}
        error={q.error}
        onRetry={() => void q.refetch()}
        retrying={q.isFetching}
        what="the Vaidyx activity"
        keyFor={(e, i) => `${e.ts}-${i}`}
        renderRow={(e) => <EventLine e={e} hospitalName={names.get(e.hospital ?? "")} />}
        empty={<div className="surface"><EmptyState kind={filtered ? "search" : "empty"} title={filtered ? "Nothing matches" : "No activity yet"} text={filtered ? "Clear a filter to see more." : "Every change made in the Vaidyx console is recorded here."} action={filtered ? <Button type="button" variant="outline" size="sm" onClick={() => { setSearch(""); setHospital(ALL); setKind(ALL); }}>Clear filters</Button> : undefined} /></div>}
      />
    </div>
  );
}
