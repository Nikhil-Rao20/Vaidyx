// The slim bar under the top bar while the Vaidyx admin works inside a hospital (docs/admin-console 4.1): "Managing <hospital> as
// Vaidyx admin", Switch hospital (a small picker) and Back to Vaidyx console (stops working inside the hospital).
import { useState } from "react";
import { ArrowLeftRight, Building2, Check, LayoutDashboard, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { usePlatformHospitals } from "@/hooks/useQueries";
import { useActingHospital } from "@/lib/acting";
import { isVaidyxAdmin, useSession } from "@/lib/session";
import { cn } from "@/lib/utils";
import { useManageHospital } from "@/features/consoles/useManage";

function SwitchPicker({ currentId, onPick }: { currentId: string; onPick: (h: { id: string; name: string }) => void }) {
  const q = usePlatformHospitals();
  const [search, setSearch] = useState("");
  const rows = (q.data?.hospitals ?? [])
    .filter((h) => h.status !== "suspended")
    .filter((h) => !search.trim() || [h.name, h.city].filter(Boolean).join(" ").toLowerCase().includes(search.trim().toLowerCase()))
    .sort((a, b) => a.name.localeCompare(b.name));
  return (
    <div className="grid grid-cols-1 gap-2">
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
        <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Find a hospital" aria-label="Find a hospital" className="h-8 pl-8 text-sm" autoFocus />
      </div>
      <ul className="max-h-64 overflow-y-auto scroll-thin" aria-label="Hospitals" data-testid="switch-list">
        {q.isLoading ? <li className="space-y-1.5 p-1" aria-busy="true">{[0, 1, 2].map((i) => <div key={i} className="skeleton-line h-8" />)}</li> : null}
        {q.error ? <li className="p-2 text-sm text-bad" role="alert">Could not load the hospitals.</li> : null}
        {rows.map((h) => (
          <li key={h.id}>
            <button
              type="button"
              onClick={() => onPick({ id: h.id, name: h.name })}
              aria-current={h.id === currentId ? "true" : undefined}
              className={cn("flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring", h.id === currentId && "bg-secondary/70")}
            >
              <Building2 className="size-4 shrink-0 text-muted-foreground" aria-hidden />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-foreground">{h.name}</span>
                {h.city ? <span className="block truncate text-xs text-muted-foreground">{[h.city, h.state].filter(Boolean).join(", ")}</span> : null}
              </span>
              {h.id === currentId ? <Check className="size-4 shrink-0 text-ok" aria-label="Now" /> : null}
            </button>
          </li>
        ))}
        {!q.isLoading && !q.error && !rows.length ? <li className="p-2 text-sm text-muted-foreground">No hospital matches.</li> : null}
      </ul>
    </div>
  );
}

export function ActingBar() {
  const { me } = useSession();
  const acting = useActingHospital();
  const { manage, leave } = useManageHospital();
  const [open, setOpen] = useState(false);
  if (!me || !isVaidyxAdmin(me) || !acting) return null;
  const name = me.acting_hospital?.name || acting.name;
  return (
    <div role="region" aria-label="Working inside a hospital" className="border-t border-tint-line bg-secondary/80" data-testid="acting-bar">
      <div className="mx-auto flex h-10 max-w-[1440px] items-center gap-2 px-4 text-[13px]">
        <Building2 className="size-4 shrink-0 text-secondary-foreground" aria-hidden />
        <p className="min-w-0 flex-1 truncate text-secondary-foreground">
          <span className="hidden sm:inline">Managing </span><strong className="font-semibold">{name}</strong><span className="hidden sm:inline"> as Vaidyx admin</span>
        </p>
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button type="button" variant="ghost" size="sm" className="h-7 shrink-0 px-2 text-secondary-foreground hover:bg-card/60" aria-label="Switch hospital">
              <ArrowLeftRight className="size-4" aria-hidden /> <span className="hidden sm:inline">Switch hospital</span><span className="sm:hidden">Switch</span>
            </Button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-72 p-2">
            <p className="px-1 pb-2 text-xs font-medium text-muted-foreground">Work inside another hospital</p>
            <SwitchPicker currentId={acting.id} onPick={(h) => { setOpen(false); if (h.id !== acting.id) void manage(h); }} />
          </PopoverContent>
        </Popover>
        <Button type="button" variant="ghost" size="sm" className="h-7 shrink-0 px-2 text-secondary-foreground hover:bg-card/60" onClick={() => void leave()} aria-label="Back to Vaidyx console">
          <LayoutDashboard className="size-4" aria-hidden /> <span className="hidden sm:inline">Back to Vaidyx console</span><span className="sm:hidden">Console</span>
        </Button>
      </div>
    </div>
  );
}
