// /platform/hospitals: every hospital with search and a status filter; open one, manage inside it, or add a new one.
import { useMemo, useState } from "react";
import { plural } from "@/lib/format";
import { Link } from "react-router-dom";
import { Building2, LogIn, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SearchBox } from "@/components/SearchBox";
import { DataList, RowArrow } from "@/components/DataList";
import { EmptyState } from "@/components/EmptyState";
import { DateText } from "@/components/DateText";
import { usePlatformHospitals } from "@/hooks/useQueries";
import { cn } from "@/lib/utils";
import { HisPill, HospitalStatusPill, SetupProgress } from "@/features/consoles/shared";
import { usePlatformContext } from "@/features/consoles/platform/PlatformConsole";
import { useManageHospital } from "@/features/consoles/useManage";

const FILTERS = [
  { id: "all", label: "All" },
  { id: "active", label: "Active" },
  { id: "suspended", label: "Suspended" },
] as const;

export default function HospitalsTab() {
  const q = usePlatformHospitals();
  const { openAddHospital } = usePlatformContext();
  const { manage } = useManageHospital();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<(typeof FILTERS)[number]["id"]>("all");
  const all = useMemo(() => q.data?.hospitals ?? [], [q.data]);
  const rows = useMemo(() => {
    const n = search.trim().toLowerCase();
    return all
      .filter((h) => status === "all" || h.status === status)
      .filter((h) => !n || [h.name, h.city, h.state, h.id].filter(Boolean).join(" ").toLowerCase().includes(n))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [all, search, status]);
  const count = (id: string) => (id === "all" ? all.length : all.filter((h) => h.status === id).length);

  return (
    <div className="grid grid-cols-1 gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <SearchBox value={search} onChange={setSearch} placeholder="Find a hospital or city" label="Find a hospital" wrapperClassName="sm:max-w-sm sm:flex-1" />
        <div role="group" aria-label="Status" className="flex flex-wrap gap-1.5">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              aria-pressed={status === f.id}
              onClick={() => setStatus(f.id)}
              className={cn("inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-[13px] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring", status === f.id ? "border-tint-line bg-secondary text-secondary-foreground" : "border-border bg-card text-muted-foreground hover:text-foreground")}
            >
              {f.label} <span className="tabular-nums text-xs opacity-80">{count(f.id)}</span>
            </button>
          ))}
        </div>
      </div>
      <DataList
        items={rows}
        loading={q.isLoading}
        error={q.error}
        onRetry={() => void q.refetch()}
        retrying={q.isFetching}
        what="the hospitals"
        keyFor={(h) => h.id}
        renderRow={(h) => (
          <div className="group surface-inner row-lift relative flex flex-wrap items-center gap-x-4 gap-y-2 px-3 py-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-md bg-secondary text-secondary-foreground"><Building2 className="size-5" aria-hidden /></span>
            <div className="min-w-0 flex-1">
              <Link to={`/platform/hospitals/${encodeURIComponent(h.id)}`} className="font-medium text-foreground outline-none after:absolute after:inset-0 after:rounded-md hover:underline focus-visible:after:ring-2 focus-visible:after:ring-ring">
                {h.name}
              </Link>
              <p className="text-xs text-muted-foreground">
                {[h.city, h.state].filter(Boolean).join(", ") || "Place not given"} · {h.admins} {h.admins === 1 ? "admin" : "admins"}, {plural(h.people, "person", "people")}, {plural(h.case_files.total, "Case File")}
                {h.created ? <> · Added <DateText value={h.created} /></> : null}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <HospitalStatusPill status={h.status} />
              <HisPill his={h.his} />
              <SetupProgress done={h.setup.done} total={h.setup.total} />
            </div>
            <Button type="button" variant="outline" size="sm" className="relative z-10" disabled={h.status === "suspended"} onClick={() => void manage({ id: h.id, name: h.name })} aria-label={`Manage inside ${h.name}`}>
              <LogIn className="size-4" aria-hidden /> Manage inside
            </Button>
            <RowArrow />
          </div>
        )}
        empty={
          <div className="surface">
            <EmptyState kind={search || status !== "all" ? "search" : "empty"} title={search || status !== "all" ? "No hospital matches" : "No hospital yet"} text={search || status !== "all" ? "Try another name, or show all." : "Add the first hospital and its admin."} action={<Button type="button" onClick={openAddHospital}><Plus className="size-4" aria-hidden /> Add a hospital</Button>} />
          </div>
        }
      />
    </div>
  );
}
