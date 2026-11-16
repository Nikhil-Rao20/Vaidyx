// /platform/hospitals/:id: one hospital for the Vaidyx admin (docs/admin-console 4.1). Header with status and actions (Manage inside
// this hospital, Edit details, Suspend / Reactivate with a reason); cards: counts, hospital admins (add, remove, reset password),
// people by role, set-up steps, hospital system, recent activity. Counts and people only, never patient data.
import { useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Activity, CalendarDays, CheckCircle2, Circle, FolderOpen, KeyRound, LogIn, MoreHorizontal, PauseCircle, Pencil, PlayCircle, PlugZap, ShieldCheck, Trash2, UserPlus, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PageHeader } from "@/components/PageHeader";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ActionButton } from "@/components/ActionButton";
import { Field } from "@/components/Field";
import { Pill } from "@/components/StatusPill";
import { DateText } from "@/components/DateText";
import { notify } from "@/components/Toasts";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { keys, usePlatformHospital } from "@/hooks/useQueries";
import { api } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import { isVaidyxAdmin, useSession } from "@/lib/session";
import { initials } from "@/lib/format";
import type { AddAdminResult, HospitalAdminRow, PlatformHospitalDetail, PlatformResetResult } from "@/lib/types";
import { cn } from "@/lib/utils";
import { EMAIL } from "@/features/admin/state";
import { Card, CardSkeleton, HisPill, HospitalStatusPill, OneTimeLoginDialog, SetupProgress, StatTile, TileGrid, plainSummary, roleLabel } from "@/features/consoles/shared";
import { INDIAN_STATES } from "@/features/consoles/platform/AddHospitalDialog";
import { NotVaidyxAdmin } from "@/features/consoles/platform/PlatformConsole";
import { useManageHospital } from "@/features/consoles/useManage";

type OneTime = { login: string; password: string; mailto?: string; who?: string } | null;

const COUNT_LABEL: Record<string, string> = {
  people: "People", case_files_open: "Open Case Files", case_files_decided: "Decided Case Files", case_files_total: "Case Files",
  meetings_next_7_days: "Meetings in the next 7 days", open_requests: "Open requests",
};
const COUNT_ICON: Record<string, typeof Users> = { people: Users, case_files_open: FolderOpen, case_files_decided: CheckCircle2, case_files_total: FolderOpen, meetings_next_7_days: CalendarDays, open_requests: Activity };
const ROLE_ORDER = ["doctors", "heads", "residents", "coordinators", "dept_admins", "hospital_admins", "auditors", "guests", "disabled", "never_signed_in"];
const ROLE_PLURAL: Record<string, string> = {
  doctors: "Doctors", heads: "Heads of department", residents: "Residents", coordinators: "MDT Coordinators", dept_admins: "Department admins",
  hospital_admins: "Hospital admins", auditors: "Auditors", guests: "Guest reviewers", disabled: "Disabled logins", never_signed_in: "Never signed in",
};

function EditDetails({ open, onOpenChange, data }: { open: boolean; onOpenChange: (o: boolean) => void; data: PlatformHospitalDetail }) {
  const qc = useQueryClient();
  const h = data.hospital;
  const [name, setName] = useState(h.name);
  const [city, setCity] = useState(h.city ?? "");
  const [state, setState] = useState(h.state ?? "");
  const [err, setErr] = useState<string | null>(null);
  const save = useAsyncAction(async () => {
    await api.put(EP.platformHospital(h.id), { name: name.trim(), city: city.trim(), state });
    await qc.invalidateQueries({ queryKey: keys.platform });
    notify.success("Details saved", name.trim());
    window.setTimeout(() => onOpenChange(false), 300);
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) { setErr("Give the hospital's name."); return; }
    setErr(null);
    void save.run();
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-md">
        <form onSubmit={submit} noValidate className="grid grid-cols-1 gap-4">
          <DialogHeader>
            <DialogTitle>Edit details</DialogTitle>
            <DialogDescription>The name and place of the hospital. Its admin changes everything else in the set-up.</DialogDescription>
          </DialogHeader>
          <Field id="ed-name" label="Hospital name" required error={err}><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field id="ed-city" label="City" optional><Input value={city} onChange={(e) => setCity(e.target.value)} /></Field>
            <Field id="ed-state" label="State" optional>
              <Select value={state || undefined} onValueChange={setState}>
                <SelectTrigger className="w-full" id="ed-state"><SelectValue placeholder="Choose a state" /></SelectTrigger>
                <SelectContent className="max-h-72">{INDIAN_STATES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
          </div>
          {save.error ? <p role="alert" className="text-sm text-bad">{save.error}</p> : null}
          <DialogFooter className="gap-2 sm:gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <ActionButton type="submit" state={save.state} loadingText="Saving" doneText="Saved">Save</ActionButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function AddAdmin({ open, onOpenChange, hospitalId, hospitalName, onOneTime }: { open: boolean; onOpenChange: (o: boolean) => void; hospitalId: string; hospitalName: string; onOneTime: (v: OneTime) => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [err, setErr] = useState<{ name?: string; email?: string }>({});
  const save = useAsyncAction(async () => {
    const r = await api.post<AddAdminResult>(EP.platformHospitalAdmins(hospitalId), { display_name: name.trim(), email: email.trim().toLowerCase() });
    await qc.invalidateQueries({ queryKey: keys.platform });
    onOpenChange(false);
    setName(""); setEmail("");
    if (r.password_once) onOneTime({ login: r.username, password: r.password_once, mailto: r.mailto, who: name.trim() || r.username });
    else notify.success("Now a hospital admin", r.username);
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const x: typeof err = {};
    if (!name.trim()) x.name = "Give the admin's name.";
    if (!EMAIL.test(email.trim())) x.email = "Type the admin's email address; it becomes their login.";
    setErr(x);
    if (!Object.keys(x).length) void save.run();
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-md">
        <form onSubmit={submit} noValidate className="grid grid-cols-1 gap-4">
          <DialogHeader>
            <DialogTitle>Add a hospital admin</DialogTitle>
            <DialogDescription>For {hospitalName}. A new login gets a first password, shown once on the next screen.</DialogDescription>
          </DialogHeader>
          <Field id="aa-name" label="Name" required error={err.name}><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Ravi Teja" /></Field>
          <Field id="aa-email" label="Email (the login)" required error={err.email}><Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="e.g. it.admin@hospital.in" autoComplete="off" /></Field>
          {save.error ? <p role="alert" className="text-sm text-bad">{save.error}</p> : null}
          <DialogFooter className="gap-2 sm:gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <ActionButton type="submit" state={save.state} loadingText="Adding" doneText="Added" icon={<UserPlus className="size-4" aria-hidden />}>Add admin</ActionButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function AdminRow({ a, hospitalId, lastOne, onOneTime }: { a: HospitalAdminRow; hospitalId: string; lastOne: boolean; onOneTime: (v: OneTime) => void }) {
  const qc = useQueryClient();
  const [removing, setRemoving] = useState(false);
  const who = a.display_name || a.username;
  const reset = useAsyncAction(async () => {
    const r = await api.post<PlatformResetResult>(EP.platformLoginReset(a.username), {});
    onOneTime({ login: a.username, password: r.password_once, mailto: r.mailto, who });
    void qc.invalidateQueries({ queryKey: keys.platform });
  }, { onError: (m) => notify.error("Could not reset", m) });
  return (
    <li className="flex min-h-12 items-center gap-3 rounded-md px-2 py-2 hover:bg-accent/50">
      <span className="grid size-9 shrink-0 place-items-center rounded-full bg-secondary text-sm font-bold text-secondary-foreground" aria-hidden>{initials(who)}</span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium text-foreground">{who}</span>
        <span className="block truncate text-xs text-muted-foreground"><span className="mono">{a.username}</span>{a.last_sign_in ? <> · signed in <DateText value={a.last_sign_in} mode="ago" /></> : null}</span>
      </span>
      {a.must_change_password ? <Pill tone="warn" icon={KeyRound}>Not signed in yet</Pill> : null}
      {a.disabled ? <Pill tone="bad">Disabled</Pill> : null}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button type="button" variant="ghost" size="icon-sm" aria-label={`Actions for ${who}`} disabled={reset.state === "loading"}><MoreHorizontal className="size-4" aria-hidden /></Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuItem onSelect={() => void reset.run()}><KeyRound className="size-4" aria-hidden /> Reset the password</DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem className="text-bad focus:text-bad" disabled={lastOne} onSelect={() => setRemoving(true)}><Trash2 className="size-4" aria-hidden /> {lastOne ? "The last admin stays" : "Remove as hospital admin"}</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <ConfirmDialog
        open={removing}
        onOpenChange={setRemoving}
        title={`Remove ${who} as hospital admin?`}
        text="The login stays; it no longer manages this hospital. You can add it back later."
        confirmText="Remove"
        destructive
        doneText="Removed"
        onConfirm={async () => { await api.del(EP.platformHospitalAdmin(hospitalId, a.username)); notify.success("Removed as hospital admin", who); await qc.invalidateQueries({ queryKey: keys.platform }); }}
      />
    </li>
  );
}

export default function HospitalDetail() {
  const { id = "" } = useParams();
  const { me } = useSession();
  const q = usePlatformHospital(id, { enabled: Boolean(id) && isVaidyxAdmin(me) });
  const qc = useQueryClient();
  const { manage } = useManageHospital();
  const [editing, setEditing] = useState(false);
  const [statusOpen, setStatusOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const [oneTime, setOneTime] = useState<OneTime>(null);
  if (!me) return null;
  if (!isVaidyxAdmin(me)) return <NotVaidyxAdmin />;
  const d = q.data;
  const h = d?.hospital;
  const suspended = h?.status === "suspended";
  const crumbs = [{ label: "Vaidyx console", to: "/platform" }, { label: "Hospitals", to: "/platform/hospitals" }, { label: h?.name || id }];

  if (q.error && !d) {
    return (
      <div className="mx-auto max-w-6xl">
        <PageHeader title="Hospital" crumbs={crumbs} />
        <div className="surface"><ErrorState error={q.error} what="this hospital" onRetry={() => void q.refetch()} retrying={q.isFetching} /></div>
      </div>
    );
  }
  const counts = Object.entries(d?.counts ?? {});
  const roles = ROLE_ORDER.filter((k) => d?.people_by_role?.[k] !== undefined).map((k) => [k, d?.people_by_role[k] ?? 0] as const)
    .concat(Object.entries(d?.people_by_role ?? {}).filter(([k]) => !ROLE_ORDER.includes(k)));
  const steps = d?.setup?.steps ?? [];
  const activeAdmins = (d?.admins ?? []).filter((a) => !a.disabled).length;

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        crumbs={crumbs}
        title={h ? <span className="inline-flex flex-wrap items-center gap-2">{h.name} <HospitalStatusPill status={h.status} /></span> : <span className="skeleton-line inline-block h-7 w-64 align-middle" aria-label="Loading" />}
        subtitle={h ? [[h.city, h.state].filter(Boolean).join(", "), h.type ? (h.type === "public" ? "Public" : "Private") : "", h.level ? `NCG ${h.level}` : "", h.pmjay_empanelled ? "PM-JAY" : ""].filter(Boolean).join(" · ") || "Place not given" : undefined}
        actions={h ? (
          <>
            <Button type="button" onClick={() => void manage({ id: h.id, name: h.name })} disabled={suspended}><LogIn className="size-4" aria-hidden /> Manage inside this hospital</Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild><Button type="button" variant="outline" size="icon" aria-label="More actions"><MoreHorizontal className="size-4" aria-hidden /></Button></DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-52">
                <DropdownMenuItem onSelect={() => setEditing(true)}><Pencil className="size-4" aria-hidden /> Edit details</DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem className={suspended ? "" : "text-bad focus:text-bad"} onSelect={() => setStatusOpen(true)}>
                  {suspended ? <PlayCircle className="size-4" aria-hidden /> : <PauseCircle className="size-4" aria-hidden />} {suspended ? "Reactivate" : "Suspend"}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </>
        ) : null}
      />
      {suspended ? (
        <p role="status" className="mb-4 flex items-start gap-2 rounded-md status-warn px-3 py-2 text-sm">
          <PauseCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span>Suspended: its people cannot sign in. Nothing is deleted; reactivate it any time.{h?.status_reason ? ` Reason: ${h.status_reason}` : ""}</span>
        </p>
      ) : null}

      <div className="grid grid-cols-1 gap-5">
        <TileGrid>
          {q.isLoading ? Array.from({ length: 4 }).map((_, i) => <StatTile key={i} loading label="" />) : counts.length ? counts.slice(0, 8).map(([k, v]) => (
            <StatTile key={k} value={v} label={COUNT_LABEL[k] ?? roleLabel(k)} icon={COUNT_ICON[k] ?? Activity} />
          )) : <StatTile value={h?.people} label="People" icon={Users} />}
        </TileGrid>

        <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-2">
          <Card title="Hospital admins" icon={ShieldCheck} id="hd-admins" action={<Button type="button" variant="outline" size="sm" onClick={() => setAdding(true)}><UserPlus className="size-4" aria-hidden /> Add admin</Button>}>
            {q.isLoading ? <CardSkeleton /> : (d?.admins ?? []).length ? (
              <ul className="grid grid-cols-1 gap-0.5">{(d?.admins ?? []).map((a) => <AdminRow key={a.username} a={a} hospitalId={id} lastOne={!suspended && activeAdmins <= 1 && !a.disabled} onOneTime={setOneTime} />)}</ul>
            ) : <EmptyState compact kind="people" title="No hospital admin" text="Add one: they set up the hospital and add its people." />}
          </Card>

          <Card title="People by role" icon={Users} id="hd-roles">
            {q.isLoading ? <CardSkeleton /> : roles.length ? (
              <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
                {roles.map(([k, v]) => (
                  <div key={k} className="rounded-md bg-muted/60 px-3 py-2">
                    <dt className="text-xs text-muted-foreground">{ROLE_PLURAL[k] ?? roleLabel(k)}</dt>
                    <dd className={cn("text-lg font-semibold tabular-nums", (k === "disabled" || k === "never_signed_in") && v ? "text-warn" : "text-foreground")}>{v}</dd>
                  </div>
                ))}
              </dl>
            ) : <p className="text-sm text-muted-foreground">Nobody yet.</p>}
          </Card>

          <Card title="Set-up" icon={CheckCircle2} id="hd-setup" action={steps.length ? <SetupProgress done={steps.filter((s) => s.done).length} total={steps.length} /> : null}>
            {q.isLoading ? <CardSkeleton /> : steps.length ? (
              <ol className="grid grid-cols-1 gap-1.5">
                {steps.map((s) => (
                  <li key={s.id} className="flex items-start gap-2 text-sm">
                    {s.done ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-ok" aria-hidden /> : <Circle className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />}
                    <span className="min-w-0"><span className="text-foreground">{s.label}</span><span className="sr-only">{s.done ? ", done" : ", not done"}</span>{s.summary ? <span className="block text-xs text-muted-foreground">{plainSummary(s.summary)}</span> : null}</span>
                  </li>
                ))}
              </ol>
            ) : <p className="text-sm text-muted-foreground">Not started.</p>}
          </Card>

          <Card title="Hospital system" icon={PlugZap} id="hd-his">
            {q.isLoading ? <CardSkeleton lines={2} /> : (
              <div className="grid grid-cols-1 gap-2 text-sm">
                <p className="flex flex-wrap items-center gap-2"><HisPill his={d?.his} />{d?.his?.tested_at ? <span className="text-xs text-muted-foreground">Last test <DateText value={d.his.tested_at} mode="ago" /></span> : <span className="text-xs text-muted-foreground">Never tested</span>}</p>
                <p className="text-xs text-muted-foreground">The hospital admin connects and tests it in the set-up. Manage inside this hospital to see it.</p>
              </div>
            )}
          </Card>
        </div>

        <Card title="Recent activity" icon={Activity} id="hd-recent">
          {q.isLoading ? <CardSkeleton lines={4} /> : (d?.recent ?? []).length ? (
            <ul className="grid grid-cols-1 gap-1">
              {(d?.recent ?? []).slice(0, 12).map((e, i) => (
                <li key={`${e.ts}-${i}`} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 rounded-md px-2 py-1.5 text-sm hover:bg-accent/50">
                  <span className="min-w-0 flex-1 text-foreground">{e.text}</span>
                  <span className="text-xs text-muted-foreground">{e.by_name || e.by ? `${e.by_name || e.by}, ` : ""}<DateText value={e.ts} mode="ago" /></span>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-muted-foreground">Nothing yet.</p>}
        </Card>
      </div>

      {d ? <EditDetails key={`${d.hospital.name}-${editing}`} open={editing} onOpenChange={setEditing} data={d} /> : null}
      <AddAdmin open={adding} onOpenChange={setAdding} hospitalId={id} hospitalName={h?.name || id} onOneTime={setOneTime} />
      <ConfirmDialog
        open={statusOpen}
        onOpenChange={setStatusOpen}
        title={suspended ? `Reactivate ${h?.name ?? "this hospital"}?` : `Suspend ${h?.name ?? "this hospital"}?`}
        text={suspended ? "Its people can sign in again. Everything is as it was." : "Its people cannot sign in until you reactivate it. Nothing is deleted: Case Files, people and set-up stay."}
        confirmText={suspended ? "Reactivate" : "Suspend"}
        destructive={!suspended}
        requireReason
        reasonLabel="Reason (kept in the record)"
        doneText={suspended ? "Reactivated" : "Suspended"}
        onConfirm={async (reason) => {
          await api.post(EP.platformHospitalStatus(id), { status: suspended ? "active" : "suspended", reason });
          notify.success(suspended ? "Reactivated" : "Suspended", h?.name);
          await qc.invalidateQueries({ queryKey: keys.platform });
        }}
      />
      <OneTimeLoginDialog value={oneTime} onClose={() => setOneTime(null)} />
    </div>
  );
}
