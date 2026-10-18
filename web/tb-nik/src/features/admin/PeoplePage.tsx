// /people: a department admin's doctors, heads and residents (with end dates), for each department they administer; the
// root admin picks any department. Add a person (a new login gets a random first password inside a mail draft), change
// the role or the end date, mark someone away (the Tumour Board disabled flag), reset a password (a new mail draft),
// remove from the department. Passwords travel only inside mailto: links opened in the admin's own mail program.
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CalendarClock, KeyRound, Mail, MoreHorizontal, Settings2, ShieldAlert, Trash2, UserMinus, UserPlus, UserRoundCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { PageHeader } from "@/components/PageHeader";
import { Field } from "@/components/Field";
import { DateInput } from "@/components/DateInput";
import { ActionButton } from "@/components/ActionButton";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataList } from "@/components/DataList";
import { EmptyState } from "@/components/EmptyState";
import { SearchBox } from "@/components/SearchBox";
import { Pill } from "@/components/StatusPill";
import { DateText } from "@/components/DateText";
import { notify } from "@/components/Toasts";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { keys, useAccounts, useDepartmentDoctors, useInvalidate, useOrg } from "@/hooks/useQueries";
import { api } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import { useSession } from "@/lib/session";
import type { AccountRow, DepartmentDoctor, Placement, PersonSaved, ResetResult } from "@/lib/types";
import { initials, plural } from "@/lib/format";
import { EMAIL } from "@/features/admin/state";

const ROLE_WORD: Record<string, string> = { member: "Doctor", head: "Head", resident: "Resident" };

/** The mail draft with the password: shown as one button, opened in the admin's own mail program. */
function MailDraft({ mailto, who, onClose }: { mailto: string | null; who: string; onClose: () => void }) {
  return (
    <Dialog open={Boolean(mailto)} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Send the login to {who}</DialogTitle>
          <DialogDescription>Your mail program opens a draft with the login name and the first password. Vaidyx sends nothing and keeps no copy of the password. They choose their own at the first sign-in.</DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2 sm:gap-2">
          <Button type="button" variant="outline" onClick={onClose}>Done</Button>
          {mailto ? <Button type="button" asChild><a href={mailto} onClick={() => window.setTimeout(onClose, 400)}><Mail className="size-4" aria-hidden /> Open the mail draft</a></Button> : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AddPerson({ dept, onSaved }: { dept: string; onSaved: (mailto: string, who: string) => void }) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<Placement>("member");
  const [end, setEnd] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const save = useAsyncAction(async () => {
    const r = await api.post<PersonSaved>(EP.deptPeople(dept), { email: email.trim().toLowerCase(), display_name: name.trim() || undefined, role, end_date: role === "resident" ? end || undefined : undefined });
    const who = name.trim() || email.trim();
    if (r.mailto) onSaved(r.mailto, who);
    else notify.success(r.created ? "Login created" : "Placed in the department", who);
    setEmail(""); setName(""); setEnd(""); setRole("member");
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!EMAIL.test(email.trim())) { setErr("Type the person's email address; it becomes their login."); return; }
    if (role === "resident" && !end) { setErr("A resident needs the end of the rotation; access stops then."); return; }
    setErr(null);
    void save.run();
  };
  return (
    <form className="surface grid gap-3 p-4" onSubmit={submit} noValidate aria-label="Add a person">
      <p className="flex items-center gap-2 text-sm font-bold"><UserPlus className="size-4 text-primary" aria-hidden /> Add a person</p>
      <div className="grid gap-3 md:grid-cols-[1.3fr_1fr_140px_160px_auto] md:items-end">
        <Field id="add-email" label="Email (the login)" error={err}><Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="e.g. name@hospital.in" autoComplete="off" /></Field>
        <Field id="add-name" label="Name" optional><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Dr Asha Menon" /></Field>
        <Field id="add-role" label="Role">
          <Select value={role} onValueChange={(v) => setRole(v as Placement)}>
            <SelectTrigger className="w-full" id="add-role" aria-label="Role"><SelectValue /></SelectTrigger>
            <SelectContent>{Object.entries(ROLE_WORD).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
          </Select>
        </Field>
        <Field id="add-end" label="Rotation ends" optional={role !== "resident"} required={role === "resident"}><DateInput value={end} onChange={setEnd} disabled={role !== "resident"} /></Field>
        <ActionButton type="submit" state={save.state} doneText="Added" loadingText="Adding" icon={<UserPlus className="size-4" aria-hidden />}>Add</ActionButton>
      </div>
      {save.error ? <p role="alert" className="text-sm text-bad">{save.error}</p> : null}
    </form>
  );
}

function PersonRow({ p, dept, canReset, onChanged, onMail }: { p: DepartmentDoctor; dept: string; canReset: boolean; onChanged: () => void; onMail: (mailto: string, who: string) => void }) {
  const [removing, setRemoving] = useState(false);
  const [endOpen, setEndOpen] = useState(false);
  const [end, setEnd] = useState(p.end_date || "");
  const who = p.display_name || p.username;
  const run = async (body: Record<string, unknown>, ok: string) => {
    try {
      await api.put(EP.deptPerson(dept, p.username), body);
      notify.success(ok, who);
      onChanged();
    } catch (e) {
      notify.error("Could not change", e instanceof Error ? e.message : undefined);
    }
  };
  const reset = useAsyncAction(async () => {
    const r = await api.post<ResetResult>(EP.resetPassword(p.username), {});
    if (r.mailto) onMail(r.mailto, who);
    else notify.success("Password reset", who);
  }, { onError: (m) => notify.error("Could not reset", m) });
  const saveEnd = useAsyncAction(async () => { await api.put(EP.deptPerson(dept, p.username), { end_date: end }); setEndOpen(false); notify.success("End date saved", who); onChanged(); });
  const locked = p.root_admin || p.vaidyx_admin;
  return (
    <div className="surface-inner flex min-h-12 flex-wrap items-center gap-3 px-3 py-2.5">
      <span className="grid size-9 shrink-0 place-items-center rounded-full bg-secondary text-sm font-bold text-secondary-foreground" aria-hidden>{initials(who)}</span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-foreground">{who}</p>
        <p className="truncate text-xs text-muted-foreground"><span className="mono">{p.username}</span>{p.other_departments?.length ? `, also in ${p.other_departments.map((d) => d.name).join(", ")}` : ""}</p>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {p.role ? <Pill tone={p.role === "head" ? "info" : "neutral"}>{ROLE_WORD[p.role] ?? p.role}</Pill> : null}
        {p.admin ? <Pill tone="info" icon={Settings2}>Dept admin</Pill> : null}
        {p.coordinator ? <Pill tone="info">Coordinator</Pill> : null}
        {p.role === "resident" ? (p.end_date ? <Pill tone={p.expired ? "bad" : "neutral"} icon={CalendarClock}>{p.expired ? "Ended " : "Until "}<DateText value={p.end_date} /></Pill> : <Pill tone="warn" icon={CalendarClock}>No end date</Pill>) : null}
        {p.disabled ? <Pill tone="warn" icon={UserMinus}>Away</Pill> : null}
        {p.must_change_password ? <Pill tone="review" icon={KeyRound}>First sign-in pending</Pill> : null}
        {p.account === false ? <Pill tone="bad" icon={ShieldAlert}>No login yet</Pill> : null}
      </div>
      {endOpen ? (
        <form className="flex w-full items-center gap-2 sm:w-auto" onSubmit={(e) => { e.preventDefault(); void saveEnd.run(); }}>
          <DateInput value={end} onChange={setEnd} className="h-8" wrapperClassName="w-40" aria-label="End of rotation" />
          <ActionButton type="submit" size="sm" state={saveEnd.state} doneText="Saved">Save</ActionButton>
          <Button type="button" variant="ghost" size="sm" onClick={() => setEndOpen(false)}>Cancel</Button>
        </form>
      ) : null}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button type="button" variant="ghost" size="icon-sm" aria-label={`Actions for ${who}`} disabled={reset.state === "loading"}><MoreHorizontal className="size-4" aria-hidden /></Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          {(["member", "head", "resident"] as Placement[]).filter((r) => r !== p.role).map((r) => (
            <DropdownMenuItem key={r} disabled={locked} onSelect={() => void run({ role: r }, `Now ${ROLE_WORD[r].toLowerCase()}`)}>Make {ROLE_WORD[r].toLowerCase()}</DropdownMenuItem>
          ))}
          {p.role === "resident" ? <DropdownMenuItem onSelect={() => setEndOpen(true)}><CalendarClock className="size-4" aria-hidden /> Set the end date</DropdownMenuItem> : null}
          <DropdownMenuItem disabled={locked} onSelect={() => void run({ disabled: !p.disabled }, p.disabled ? "Back" : "Marked away")}>
            {p.disabled ? <UserRoundCheck className="size-4" aria-hidden /> : <UserMinus className="size-4" aria-hidden />} {p.disabled ? "Mark back" : "Mark away (leave, left)"}
          </DropdownMenuItem>
          {canReset ? <DropdownMenuItem disabled={p.vaidyx_admin} onSelect={() => void reset.run()}><KeyRound className="size-4" aria-hidden /> Reset the password</DropdownMenuItem> : null}
          <DropdownMenuSeparator />
          <DropdownMenuItem className="text-bad focus:text-bad" disabled={locked} onSelect={() => setRemoving(true)}><Trash2 className="size-4" aria-hidden /> Remove from the department</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <ConfirmDialog
        open={removing}
        onOpenChange={setRemoving}
        title={`Remove ${who} from the department?`}
        text="Their login stays; they lose this department's Case Files and requests. You can add them back later."
        confirmText="Remove"
        destructive
        doneText="Removed"
        onConfirm={async () => { await api.del(EP.deptPerson(dept, p.username)); notify.success("Removed", who); onChanged(); }}
      />
    </div>
  );
}

export default function PeoplePage() {
  const { me } = useSession();
  const org = useOrg();
  const [params, setParams] = useSearchParams();
  const invalidate = useInvalidate();
  const [q, setQ] = useState("");
  const [mail, setMail] = useState<{ mailto: string; who: string } | null>(null);
  const root = Boolean(me?.roles.root_admin || me?.roles.admin);
  const choices = useMemo(() => {
    const all = org.data?.departments ?? [];
    if (root) return [{ id: EVERYONE, name: "Everyone" }, ...all.map((d) => ({ id: d.id, name: d.name }))];  // the root admin starts with every login
    const mine = new Set(me?.roles.admin_of ?? []);
    const named = (org.data?.admin_departments ?? []).map((d) => ({ id: d.id, name: d.name }));
    return named.length ? named : all.filter((d) => mine.has(d.id)).map((d) => ({ id: d.id, name: d.name }));
  }, [org.data, root, me]);
  const dept = params.get("dept") || choices[0]?.id || me?.roles.admin_of?.[0] || "";
  useEffect(() => { if (!params.get("dept") && dept) setParams({ dept }, { replace: true }); }, [dept]); // eslint-disable-line react-hooks/exhaustive-deps
  const everyone = dept === EVERYONE;
  const people = useDepartmentDoctors(dept && !everyone ? dept : null);
  const accounts = useAccounts({ enabled: root && everyone });
  const list = useMemo(() => {
    const n = q.trim().toLowerCase();
    const rows = [...(people.data?.doctors ?? [])].sort((a, b) => Number(a.disabled) - Number(b.disabled) || (a.role === "head" ? -1 : 0) - (b.role === "head" ? -1 : 0) || (a.display_name || a.username).localeCompare(b.display_name || b.username));
    return n ? rows.filter((p) => [p.display_name, p.username, p.role].filter(Boolean).join(" ").toLowerCase().includes(n)) : rows;
  }, [people.data, q]);
  const refresh = () => void invalidate(keys.deptDoctors(dept), keys.org);
  const deptName = choices.find((c) => c.id === dept)?.name || people.data?.department?.name || dept;
  const counts = useMemo(() => {
    const rows = people.data?.doctors ?? [];
    return { doctors: rows.filter((p) => p.role === "member" || p.role === "head").length, residents: rows.filter((p) => p.role === "resident").length, away: rows.filter((p) => p.disabled).length };
  }, [people.data]);

  if (!me) return null;
  if (!root && !(me.roles.admin_of || []).length) {
    return (
      <div className="mx-auto max-w-2xl">
        <PageHeader title="People" />
        <div className="surface"><EmptyState kind="lock" title="Only department admins manage people" text="Ask your department admin to add, change or reset a login." /></div>
      </div>
    );
  }
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="People"
        subtitle={everyone ? "Every login, with its roles. Pick a department to add or change someone." : people.data ? `${deptName}: ${plural(counts.doctors, "doctor")}, ${plural(counts.residents, "resident")}${counts.away ? `, ${counts.away} away` : ""}` : deptName}
        actions={
          <>
            {choices.length > 1 ? (
              <Select value={dept} onValueChange={(v) => setParams({ dept: v }, { replace: true })}>
                <SelectTrigger className="w-full sm:w-56" aria-label="Department"><SelectValue placeholder="Department" /></SelectTrigger>
                <SelectContent>{choices.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
              </Select>
            ) : null}
            {root ? <Button type="button" variant="outline" asChild><Link to="/admin"><Settings2 className="size-4" aria-hidden /> Hospital set-up</Link></Button> : null}
          </>
        }
      />
      {everyone ? (
        <EveryoneList accounts={accounts.data?.accounts ?? []} loading={accounts.isLoading} error={accounts.error} onRetry={() => void accounts.refetch()} deptName={(id) => (org.data?.departments ?? []).find((d) => d.id === id)?.name || id} onOpen={(d) => setParams({ dept: d }, { replace: true })} />
      ) : dept ? (
        <div className="grid gap-4">
          <AddPerson dept={dept} onSaved={(mailto, who) => { setMail({ mailto, who }); refresh(); }} />
          {people.data?.department && (people.data.department.email || people.data.department.phone) ? (
            <p className="text-xs text-muted-foreground">Desk contact: {[people.data.department.email && !people.data.department.email.endsWith("@hospital.example") ? people.data.department.email : "", people.data.department.phone].filter(Boolean).join(", ") || "not given"} (the root admin changes it in the set-up).</p>
          ) : null}
          <SearchBox value={q} onChange={setQ} placeholder="Find a person" wrapperClassName="sm:max-w-sm" />
          <DataList
            items={list}
            loading={people.isLoading}
            error={people.error}
            onRetry={() => void people.refetch()}
            retrying={people.isFetching}
            what="the department's people"
            keyFor={(p) => p.username}
            renderRow={(p) => <PersonRow p={p} dept={dept} canReset={people.data?.can_reset !== false} onChanged={refresh} onMail={(mailto, who) => setMail({ mailto, who })} />}
            empty={<EmptyState kind="people" title={q ? "Nobody matches" : "Nobody in this department yet"} text={q ? "Try another name." : "Add the first person above: their email becomes the login."} />}
          />
        </div>
      ) : (
        <div className="surface"><EmptyState kind="people" title="No department to manage" text="The root admin makes you the admin of a department." /></div>
      )}
      <MailDraft mailto={mail?.mailto ?? null} who={mail?.who ?? ""} onClose={() => setMail(null)} />
    </div>
  );
}

const EVERYONE = "all";

/** The root admin's first view: every placed login across departments, so nobody looks missing because the first department is empty. */
function EveryoneList({ accounts, loading, error, onRetry, deptName, onOpen }: {
  accounts: AccountRow[]; loading: boolean; error: Error | null; onRetry: () => void; deptName: (id: string) => string; onOpen: (dept: string) => void;
}) {
  const [q, setQ] = useState("");
  const rows = useMemo(() => {
    const n = q.trim().toLowerCase();
    const list = [...accounts].sort((a, b) => (a.display_name || a.username).localeCompare(b.display_name || b.username));
    return n ? list.filter((a) => [a.display_name, a.username, ...Object.keys(a.departments ?? {}).map(deptName)].filter(Boolean).join(" ").toLowerCase().includes(n)) : list;
  }, [accounts, q, deptName]);
  return (
    <div className="grid gap-4">
      <SearchBox value={q} onChange={setQ} placeholder="Find a person or department" wrapperClassName="sm:max-w-sm" />
      <DataList
        items={rows}
        loading={loading}
        error={error}
        onRetry={onRetry}
        what="the logins"
        keyFor={(a) => a.username}
        renderRow={(a) => {
          const depts = Object.entries(a.departments ?? {});
          const roles = [
            ...depts.map(([d, r]) => `${ROLE_WORD[r] || r}, ${deptName(d)}`),
            ...(a.admin_of ?? []).map((d) => `Department admin, ${deptName(d)}`),
            a.coordinator ? "MDT Coordinator" : "",
            a.root_admin ? "Root admin" : "",
            a.auditor ? "Auditor" : "",
          ].filter(Boolean);
          const first = depts[0]?.[0] || (a.admin_of ?? [])[0];
          return (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3">
              <span className="grid size-9 shrink-0 place-items-center rounded-full bg-secondary text-sm font-bold text-secondary-foreground" aria-hidden>{initials(a.display_name || a.username)}</span>
              <span className="min-w-0 flex-1">
                <span className="block font-medium text-foreground">{a.display_name || a.username}</span>
                <span className="block text-xs text-muted-foreground"><span className="mono">{a.username}</span>{roles.length ? `: ${roles.join("; ")}` : ""}</span>
              </span>
              {a.end_date ? <Pill tone={a.expired ? "bad" : "neutral"} icon={CalendarClock}>{a.expired ? "Ended " : "Until "}<DateText value={a.end_date} /></Pill> : null}
              {a.must_change_password ? <Pill tone="warn" icon={KeyRound}>Not signed in yet</Pill> : null}
              {a.disabled ? <Pill tone="bad" icon={UserMinus}>Away</Pill> : null}
              {first ? <Button type="button" variant="outline" size="sm" onClick={() => onOpen(first)}>Manage in {deptName(first)}</Button> : null}
            </div>
          );
        }}
        empty={<EmptyState kind="people" title={q ? "Nobody matches" : "No logins yet"} text={q ? "Try another name." : "Add people in the hospital set-up or pick a department above."} />}
      />
    </div>
  );
}
