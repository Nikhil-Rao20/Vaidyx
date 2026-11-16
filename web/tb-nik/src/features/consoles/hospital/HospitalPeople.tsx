// /hospital/people: everyone with a login in this hospital (GET /accounts), with search and role chips. Add a person, change the
// role and departments, reset a password (the first password shown once), disable / enable. Department view: /people.
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { CalendarClock, KeyRound, MoreHorizontal, ShieldAlert, UserCog, UserMinus, UserPlus, UserRoundCheck, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { SearchBox } from "@/components/SearchBox";
import { DataList } from "@/components/DataList";
import { EmptyState } from "@/components/EmptyState";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Pill } from "@/components/StatusPill";
import { DateText } from "@/components/DateText";
import { loginFromMailto } from "@/components/LoginHandover";
import { notify } from "@/components/Toasts";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { keys, useAccounts } from "@/hooks/useQueries";
import { api } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import { useSession } from "@/lib/session";
import { initials } from "@/lib/format";
import type { AccountRow, ResetResult } from "@/lib/types";
import { cn } from "@/lib/utils";
import { OneTimeLoginDialog } from "@/features/consoles/shared";
import { ChangeRoleDialog, PERSON_ROLES, rolesOf, useDepartmentChoices, type PersonRole } from "@/features/consoles/hospital/PersonDialogs";
import { useHospitalContext } from "@/features/consoles/hospital/HospitalConsole";

type Chip = "all" | PersonRole | "disabled" | "not_signed_in";
const CHIPS: Array<{ id: Chip; label: string }> = [
  { id: "all", label: "Everyone" },
  { id: "doctor", label: "Doctors" },
  { id: "head", label: "Heads" },
  { id: "resident", label: "Residents" },
  { id: "coordinator", label: "MDT Coordinators" },
  { id: "dept_admin", label: "Department admins" },
  { id: "hospital_admin", label: "Hospital admins" },
  { id: "auditor", label: "Auditors" },
  { id: "not_signed_in", label: "Not signed in yet" },
  { id: "disabled", label: "Disabled" },
];
const ROLE_LABEL = Object.fromEntries(PERSON_ROLES.map((r) => [r.id, r.label])) as Record<PersonRole, string>;

function matches(a: AccountRow, chip: Chip): boolean {
  if (chip === "all") return true;
  if (chip === "disabled") return Boolean(a.disabled);
  if (chip === "not_signed_in") return Boolean(a.must_change_password);
  return rolesOf(a).includes(chip);
}

type OneTime = { login: string; password: string; mailto?: string; who?: string } | null;

function PersonRow({ a, deptName, self, onEdit, onOneTime }: { a: AccountRow; deptName: (id: string) => string; self: boolean; onEdit: (a: AccountRow) => void; onOneTime: (v: OneTime) => void }) {
  const qc = useQueryClient();
  const [toggling, setToggling] = useState(false);
  const who = a.display_name || a.username;
  const roles = rolesOf(a);
  const depts = [...new Set([...Object.keys(a.departments ?? {}), ...(a.admin_of ?? [])])];
  const locked = Boolean(a.vaidyx_admin);
  const reset = useAsyncAction(async () => {
    const r = await api.post<ResetResult>(EP.resetPassword(a.username), {});
    const info = r.mailto ? loginFromMailto(r.mailto) : null;
    if (info) onOneTime({ login: info.login || a.username, password: info.password, mailto: r.mailto, who });
    else notify.success("Password reset", who);
    void qc.invalidateQueries({ queryKey: keys.accounts });
  }, { onError: (m) => notify.error("Could not reset", m) });
  return (
    <div className={cn("surface-inner flex min-h-12 flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2.5", a.disabled && "opacity-80")} data-testid="hospital-person-row">
      <span className="grid size-9 shrink-0 place-items-center rounded-full bg-secondary text-sm font-bold text-secondary-foreground" aria-hidden>{initials(who)}</span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-foreground">{who}{self ? <span className="ml-1.5 text-xs font-normal text-muted-foreground">(you)</span> : null}</p>
        <p className="truncate text-xs text-muted-foreground"><span className="mono">{a.username}</span>{depts.length ? ` · ${depts.map(deptName).join(", ")}` : ""}</p>
      </div>
      <div className="order-2 flex w-full flex-wrap items-center gap-1.5 pl-12 sm:order-none sm:w-auto sm:pl-0">
        {roles.length ? roles.map((r) => <Pill key={r} tone={r === "hospital_admin" || r === "dept_admin" ? "info" : "neutral"}>{ROLE_LABEL[r]}</Pill>) : a.outside_expert ? <Pill>Outside expert</Pill> : <Pill tone="warn">No role</Pill>}
        {a.end_date ? <Pill tone={a.expired ? "bad" : "neutral"} icon={CalendarClock}>{a.expired ? "Ended " : "Until "}<DateText value={a.end_date} /></Pill> : null}
        {a.must_change_password ? <Pill tone="warn" icon={KeyRound}>Not signed in yet</Pill> : null}
        {a.disabled ? <Pill tone="bad" icon={UserMinus}>Disabled</Pill> : null}
      </div>
      {locked ? (
        <span className="order-1 inline-flex items-center gap-1 text-xs text-muted-foreground sm:order-none"><ShieldAlert className="size-3.5" aria-hidden /> Vaidyx admin</span>
      ) : (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button type="button" variant="ghost" size="icon-sm" className="order-1 sm:order-none" aria-label={`Actions for ${who}`} disabled={reset.state === "loading"}><MoreHorizontal className="size-4" aria-hidden /></Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-60">
            <DropdownMenuItem onSelect={() => onEdit(a)}><UserCog className="size-4" aria-hidden /> Change the role or departments</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => void reset.run()}><KeyRound className="size-4" aria-hidden /> Reset the password</DropdownMenuItem>
            {depts[0] ? <DropdownMenuItem asChild><Link to={`/people?dept=${encodeURIComponent(depts[0])}`}><Users className="size-4" aria-hidden /> Open in {deptName(depts[0])}</Link></DropdownMenuItem> : null}
            <DropdownMenuSeparator />
            <DropdownMenuItem className={a.disabled ? "" : "text-bad focus:text-bad"} disabled={self} onSelect={() => setToggling(true)}>
              {a.disabled ? <UserRoundCheck className="size-4" aria-hidden /> : <UserMinus className="size-4" aria-hidden />} {a.disabled ? "Enable the login" : "Disable the login"}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
      <ConfirmDialog
        open={toggling}
        onOpenChange={setToggling}
        title={a.disabled ? `Enable ${who}?` : `Disable ${who}?`}
        text={a.disabled ? "They can use the Tumour Board again with their own password." : "They cannot use the Tumour Board until you enable the login again (leave, left the hospital). Nothing they did is removed."}
        confirmText={a.disabled ? "Enable" : "Disable"}
        destructive={!a.disabled}
        doneText={a.disabled ? "Enabled" : "Disabled"}
        onConfirm={async () => {
          await api.put(EP.account(a.username), { disabled: !a.disabled });
          notify.success(a.disabled ? "Login enabled" : "Login disabled", who);
          await qc.invalidateQueries({ queryKey: keys.accounts });
          void qc.invalidateQueries({ queryKey: keys.hospital });
        }}
      />
    </div>
  );
}

export default function HospitalPeople() {
  const { me } = useSession();
  const { openAddPerson } = useHospitalContext();
  const q = useAccounts();
  const depts = useDepartmentChoices();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<AccountRow | null>(null);
  const [oneTime, setOneTime] = useState<OneTime>(null);
  const chip = (CHIPS.some((c) => c.id === params.get("role")) ? params.get("role") : "all") as Chip;
  const setChip = (c: Chip) => setParams(c === "all" ? {} : { role: c }, { replace: true });
  const names = useMemo(() => new Map(depts.map((d) => [d.id, d.name])), [depts]);
  const deptName = (id: string) => names.get(id) ?? id.replace(/_/g, " ");
  const all = useMemo(() => q.data?.accounts ?? [], [q.data]);
  const rows = useMemo(() => {
    const n = search.trim().toLowerCase();
    return all
      .filter((a) => matches(a, chip))
      .filter((a) => !n || [a.display_name, a.username, ...Object.keys(a.departments ?? {}).map((d) => names.get(d) ?? d), ...(a.admin_of ?? []).map((d) => names.get(d) ?? d)].filter(Boolean).join(" ").toLowerCase().includes(n))
      .sort((x, y) => Number(Boolean(x.disabled)) - Number(Boolean(y.disabled)) || (x.display_name || x.username).localeCompare(y.display_name || y.username));
  }, [all, chip, search, names]);
  const count = (c: Chip) => all.filter((a) => matches(a, c)).length;
  const presetRole: PersonRole | undefined = PERSON_ROLES.some((r) => r.id === chip) ? (chip as PersonRole) : undefined;

  return (
    <div className="grid grid-cols-1 gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <SearchBox value={search} onChange={setSearch} placeholder="Find a person or department" label="Find a person" wrapperClassName="sm:max-w-sm sm:flex-1" />
        <Button type="button" variant="outline" asChild className="w-fit"><Link to="/people"><Users className="size-4" aria-hidden /> By department</Link></Button>
      </div>
      <div role="group" aria-label="Show" className="-mx-4 flex gap-1.5 overflow-x-auto px-4 pb-1 scroll-thin sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0">
        {CHIPS.map((c) => {
          const n = count(c.id);
          if (c.id !== "all" && !n && chip !== c.id) return null;
          return (
            <button
              key={c.id}
              type="button"
              aria-pressed={chip === c.id}
              onClick={() => setChip(c.id)}
              className={cn("inline-flex h-8 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-3 text-[13px] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring", chip === c.id ? "border-tint-line bg-secondary text-secondary-foreground" : "border-border bg-card text-muted-foreground hover:text-foreground")}
            >
              {c.label} <span className="tabular-nums text-xs opacity-80">{n}</span>
            </button>
          );
        })}
      </div>
      <DataList
        items={rows}
        loading={q.isLoading}
        error={q.error}
        onRetry={() => void q.refetch()}
        retrying={q.isFetching}
        what="the people of the hospital"
        keyFor={(a) => a.username}
        renderRow={(a) => <PersonRow a={a} deptName={deptName} self={a.username === me?.user} onEdit={setEditing} onOneTime={setOneTime} />}
        empty={<div className="surface"><EmptyState kind={search || chip !== "all" ? "search" : "people"} title={search || chip !== "all" ? "Nobody matches" : "Nobody yet"} text={search || chip !== "all" ? "Try another name, or show everyone." : "Add the first person: their email becomes the login."} action={<Button type="button" onClick={() => openAddPerson(presetRole)}><UserPlus className="size-4" aria-hidden /> Add a person</Button>} /></div>}
      />
      <ChangeRoleDialog account={editing} onOpenChange={(o) => { if (!o) setEditing(null); }} />
      <OneTimeLoginDialog value={oneTime} onClose={() => setOneTime(null)} />
    </div>
  );
}
