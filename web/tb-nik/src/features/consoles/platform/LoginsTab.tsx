// /platform/logins: every login of every hospital (GET /platform/logins?hospital=&role=&q=). Per row: Reset password (the first
// password shown once), Disable / Enable (confirmed), Open its hospital. Vaidyx admins are listed but not changed here (D6).
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Building2, KeyRound, MoreHorizontal, ShieldAlert, UserMinus, UserRoundCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SearchBox } from "@/components/SearchBox";
import { DataList } from "@/components/DataList";
import { EmptyState } from "@/components/EmptyState";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Pill } from "@/components/StatusPill";
import { notify } from "@/components/Toasts";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { useDebounce } from "@/hooks/useDebounce";
import { keys, usePlatformHospitals, usePlatformLogins } from "@/hooks/useQueries";
import { api } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import { initials } from "@/lib/format";
import type { PlatformLogin, PlatformResetResult } from "@/lib/types";
import { OneTimeLoginDialog, roleLabel } from "@/features/consoles/shared";

const ALL = "all";
export const ROLE_FILTERS = ["hospital_admin", "doctor", "head", "resident", "coordinator", "dept_admin", "auditor", "guest", "vaidyx_admin"];

type OneTime = { login: string; password: string; mailto?: string; who?: string } | null;

function LoginRow({ l, hospitalName, onOneTime }: { l: PlatformLogin; hospitalName: string; onOneTime: (v: OneTime) => void }) {
  const qc = useQueryClient();
  const [toggling, setToggling] = useState(false);
  const who = l.display_name || l.username;
  const reset = useAsyncAction(async () => {
    const r = await api.post<PlatformResetResult>(EP.platformLoginReset(l.username), {});
    onOneTime({ login: l.username, password: r.password_once, mailto: r.mailto, who });
    void qc.invalidateQueries({ queryKey: keys.platform });
  }, { onError: (m) => notify.error("Could not reset", m) });
  return (
    <div className="surface-inner flex min-h-12 flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2.5" data-testid="login-row">
      <span className="grid size-9 shrink-0 place-items-center rounded-full bg-secondary text-sm font-bold text-secondary-foreground" aria-hidden>{initials(who)}</span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-foreground">{who}</p>
        <p className="truncate text-xs text-muted-foreground"><span className="mono">{l.username}</span> · {hospitalName}</p>
      </div>
      <div className="order-2 flex w-full flex-wrap items-center gap-1.5 pl-12 sm:order-none sm:w-auto sm:pl-0">
        {(l.roles as string[]).map((r) => <Pill key={r} tone={r === "hospital_admin" || r === "vaidyx_admin" ? "info" : "neutral"}>{roleLabel(r)}</Pill>)}
        {l.must_change_password ? <Pill tone="warn" icon={KeyRound}>Not signed in yet</Pill> : null}
        {l.disabled ? <Pill tone="bad" icon={UserMinus}>Disabled</Pill> : null}
      </div>
      {l.vaidyx_admin ? (
        <span className="order-1 inline-flex items-center gap-1 text-xs text-muted-foreground sm:order-none" title="Managed on the server, not here"><ShieldAlert className="size-3.5" aria-hidden /> Server login</span>
      ) : (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button type="button" variant="ghost" size="icon-sm" className="order-1 sm:order-none" aria-label={`Actions for ${who}`} disabled={reset.state === "loading"}><MoreHorizontal className="size-4" aria-hidden /></Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuItem onSelect={() => void reset.run()}><KeyRound className="size-4" aria-hidden /> Reset the password</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => setToggling(true)}>
              {l.disabled ? <UserRoundCheck className="size-4" aria-hidden /> : <UserMinus className="size-4" aria-hidden />} {l.disabled ? "Enable the login" : "Disable the login"}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem asChild><Link to={`/platform/hospitals/${encodeURIComponent(l.hospital)}`}><Building2 className="size-4" aria-hidden /> Open its hospital</Link></DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
      <ConfirmDialog
        open={toggling}
        onOpenChange={setToggling}
        title={l.disabled ? `Enable ${who}?` : `Disable ${who}?`}
        text={l.disabled ? "They can sign in again with their own password." : "They cannot sign in until the login is enabled again. Nothing they did is removed."}
        confirmText={l.disabled ? "Enable" : "Disable"}
        destructive={!l.disabled}
        doneText={l.disabled ? "Enabled" : "Disabled"}
        onConfirm={async () => {
          await api.post(l.disabled ? EP.platformLoginEnable(l.username) : EP.platformLoginDisable(l.username), {});
          notify.success(l.disabled ? "Login enabled" : "Login disabled", who);
          await qc.invalidateQueries({ queryKey: keys.platform });
        }}
      />
    </div>
  );
}

export default function LoginsTab() {
  const hospitals = usePlatformHospitals();
  const [search, setSearch] = useState("");
  const [hospital, setHospital] = useState(ALL);
  const [role, setRole] = useState(ALL);
  const [oneTime, setOneTime] = useState<OneTime>(null);
  const q = useDebounce(search.trim(), 300);
  const logins = usePlatformLogins({ hospital: hospital === ALL ? "" : hospital, role: role === ALL ? "" : role, q });
  const names = useMemo(() => new Map((hospitals.data?.hospitals ?? []).map((h) => [h.id, h.name])), [hospitals.data]);
  const rows = useMemo(() => {
    // The server filters; the same filters here keep the list right while a new answer is on its way.
    const n = search.trim().toLowerCase();
    return (logins.data?.logins ?? [])
      .filter((l) => hospital === ALL || l.hospital === hospital)
      .filter((l) => role === ALL || (l.roles as string[]).includes(role))
      .filter((l) => !n || [l.display_name, l.username].filter(Boolean).join(" ").toLowerCase().includes(n));
  }, [logins.data, hospital, role, search]);
  const filtered = Boolean(search || hospital !== ALL || role !== ALL);

  return (
    <div className="grid grid-cols-1 gap-4">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_220px_200px]">
        <SearchBox value={search} onChange={setSearch} placeholder="Find a login or name" label="Find a login" loading={logins.isFetching && !logins.isLoading} />
        <Select value={hospital} onValueChange={setHospital}>
          <SelectTrigger className="w-full" aria-label="Hospital"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Every hospital</SelectItem>
            {(hospitals.data?.hospitals ?? []).map((h) => <SelectItem key={h.id} value={h.id}>{h.name}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={role} onValueChange={setRole}>
          <SelectTrigger className="w-full" aria-label="Role"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Every role</SelectItem>
            {ROLE_FILTERS.map((r) => <SelectItem key={r} value={r}>{roleLabel(r)}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      <p className="text-xs text-muted-foreground" aria-live="polite">{logins.data ? `${rows.length} ${rows.length === 1 ? "login" : "logins"}${filtered ? " match" : ""}.` : ""} Vaidyx admins are server logins and are not changed here.</p>
      <DataList
        items={rows}
        loading={logins.isLoading}
        error={logins.error}
        onRetry={() => void logins.refetch()}
        retrying={logins.isFetching}
        what="the logins"
        keyFor={(l) => `${l.hospital}:${l.username}`}
        renderRow={(l) => <LoginRow l={l} hospitalName={l.hospital_name || names.get(l.hospital) || l.hospital} onOneTime={setOneTime} />}
        empty={<div className="surface"><EmptyState kind="search" title={filtered ? "No login matches" : "No logins yet"} text={filtered ? "Clear a filter to see more." : "Add a hospital: its first admin is the first login."} action={filtered ? <Button type="button" variant="outline" size="sm" onClick={() => { setSearch(""); setHospital(ALL); setRole(ALL); }}>Clear filters</Button> : undefined} /></div>}
      />
      <OneTimeLoginDialog value={oneTime} onClose={() => setOneTime(null)} />
    </div>
  );
}
