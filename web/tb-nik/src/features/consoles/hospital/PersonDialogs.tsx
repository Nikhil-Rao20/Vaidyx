// The Hospital console's "Add a person" and "Change the role" dialogs, on the existing accounts API (tumour_board/api/setup.py:
// POST /accounts, PUT /accounts/{u}). One role per person here: Doctor, Head of department, Resident (with an end date), MDT
// Coordinator, Department admin, Hospital admin, Auditor. A new login's first password comes back inside the mail draft only;
// it is shown once here (read from the draft) with Copy and "Open mail draft".
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import { CheckCircle2, Search, UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/Field";
import { DateInput } from "@/components/DateInput";
import { ActionButton } from "@/components/ActionButton";
import { loginFromMailto } from "@/components/LoginHandover";
import { notify } from "@/components/Toasts";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { keys, useHospitalDepartments, useOrg } from "@/hooks/useQueries";
import { api } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import type { AccountCreated, AccountRow } from "@/lib/types";
import { cn } from "@/lib/utils";
import { EMAIL } from "@/features/admin/state";
import { OneTimeLoginPanel } from "@/features/consoles/shared";

export type PersonRole = "doctor" | "head" | "resident" | "coordinator" | "dept_admin" | "hospital_admin" | "auditor";

export const PERSON_ROLES: Array<{ id: PersonRole; label: string; text: string; dept: boolean }> = [
  { id: "doctor", label: "Doctor", text: "Works on the Case Files of their departments.", dept: true },
  { id: "head", label: "Head of department", text: "A doctor who also approves and speaks for the department.", dept: true },
  { id: "resident", label: "Resident", text: "Proposes changes for a consultant to approve. Access ends on a date.", dept: true },
  { id: "coordinator", label: "MDT Coordinator", text: "Plans the board meetings and the agenda for the whole hospital.", dept: false },
  { id: "dept_admin", label: "Department admin", text: "Adds and changes the people of their departments.", dept: true },
  { id: "hospital_admin", label: "Hospital admin", text: "Runs this console: people, departments, set-up. No clinical access.", dept: false },
  { id: "auditor", label: "Auditor", text: "Reads the full activity log. No clinical access.", dept: false },
];
const ROLE_OF = Object.fromEntries(PERSON_ROLES.map((r) => [r.id, r])) as Record<PersonRole, (typeof PERSON_ROLES)[number]>;
/** "a doctor", "an MDT Coordinator": the role with its article, for titles and buttons. */
export const ROLE_A: Record<PersonRole, string> = {
  doctor: "a doctor", head: "a head of department", resident: "a resident", coordinator: "an MDT Coordinator",
  dept_admin: "a department admin", hospital_admin: "a hospital admin", auditor: "an auditor",
};
const PLACEMENT: Partial<Record<PersonRole, "member" | "head" | "resident">> = { doctor: "member", head: "head", resident: "resident" };

/** Every role a login holds, in console words (a login may hold more than one). */
export function rolesOf(a: AccountRow): PersonRole[] {
  const out = new Set<PersonRole>();
  for (const p of Object.values(a.departments ?? {})) out.add(p === "head" ? "head" : p === "resident" ? "resident" : "doctor");
  if ((a.admin_of ?? []).length) out.add("dept_admin");
  if (a.coordinator) out.add("coordinator");
  if (a.root_admin) out.add("hospital_admin");
  if (a.auditor) out.add("auditor");
  return PERSON_ROLES.map((r) => r.id).filter((r) => out.has(r));
}

/** The departments a role applies to, for this login. */
function deptsOf(a: AccountRow, role: PersonRole): string[] {
  if (role === "dept_admin") return a.admin_of ?? [];
  const want = PLACEMENT[role];
  return Object.entries(a.departments ?? {}).filter(([, p]) => !want || p === want || (want === "member" && p !== "head" && p !== "resident")).map(([d]) => d);
}

/** The body of POST /accounts (new) or PUT /accounts/{u} (the role replaced): one role, its departments, the end date. */
function roleBody(role: PersonRole, depts: string[], end: string) {
  const placement = PLACEMENT[role];
  return {
    departments: placement ? Object.fromEntries(depts.map((d) => [d, placement])) : {},
    admin_of: role === "dept_admin" ? depts : [],
    coordinator: role === "coordinator",
    root_admin: role === "hospital_admin",
    auditor: role === "auditor",
    end_date: role === "resident" ? end : "",
  };
}

/** The enabled departments of this hospital: GET /hospital/departments, else the older /org list. */
export function useDepartmentChoices() {
  const hd = useHospitalDepartments();
  const org = useOrg({ enabled: Boolean(hd.error) });
  return useMemo(() => {
    const list = hd.data?.departments?.filter((d) => d.enabled !== false).map((d) => ({ id: d.id, name: d.name, group: d.group }))
      ?? org.data?.departments?.map((d) => ({ id: d.id, name: d.name, group: d.group ?? "" })) ?? [];
    return [...list].sort((a, b) => a.name.localeCompare(b.name));
  }, [hd.data, org.data]);
}

function DepartmentPicker({ value, onChange, error, id }: { value: string[]; onChange: (v: string[]) => void; error?: string; id: string }) {
  const choices = useDepartmentChoices();
  const [q, setQ] = useState("");
  const shown = choices.filter((d) => !q.trim() || d.name.toLowerCase().includes(q.trim().toLowerCase()));
  const toggle = (d: string, on: boolean) => onChange(on ? [...value, d] : value.filter((x) => x !== d));
  return (
    <fieldset className="grid grid-cols-1 gap-1.5" aria-describedby={error ? `${id}-error` : undefined}>
      <legend className="mb-1.5 flex items-baseline gap-2 text-sm font-medium">Department{value.length > 1 ? "s" : ""} <span className="text-xs font-normal text-bad">required</span>{value.length ? <span className="text-xs font-normal text-muted-foreground">{value.length} chosen</span> : null}</legend>
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a department" aria-label="Find a department" className="h-8 pl-8 text-sm" />
      </div>
      <div className="max-h-44 overflow-y-auto rounded-md border border-border p-1 scroll-thin" role="group" aria-label="Departments">
        {shown.length ? shown.map((d) => {
          const cid = `${id}-${d.id}`;
          const on = value.includes(d.id);
          return (
            <label key={d.id} htmlFor={cid} className={cn("flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-accent", on && "bg-secondary/60")}>
              <Checkbox id={cid} checked={on} onCheckedChange={(c) => toggle(d.id, c === true)} />
              <span className="min-w-0 flex-1 truncate text-foreground">{d.name}</span>
              {d.group ? <span className="text-xs text-muted-foreground">{d.group === "supporting" ? "Supporting" : "Treating"}</span> : null}
            </label>
          );
        }) : <p className="px-2 py-3 text-sm text-muted-foreground">No department matches.</p>}
      </div>
      {error ? <p id={`${id}-error`} role="alert" className="text-xs font-medium text-bad">{error}</p> : null}
    </fieldset>
  );
}

function RolePicker({ value, onChange, id }: { value: PersonRole; onChange: (r: PersonRole) => void; id: string }) {
  return (
    <fieldset className="grid grid-cols-1 gap-1.5">
      <legend className="mb-1.5 text-sm font-medium">Role</legend>
      <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2" role="radiogroup" aria-label="Role">
        {PERSON_ROLES.map((r) => {
          const on = value === r.id;
          return (
            <button
              key={r.id}
              type="button"
              role="radio"
              aria-checked={on}
              id={`${id}-${r.id}`}
              onClick={() => onChange(r.id)}
              onKeyDown={(e) => {
                const i = PERSON_ROLES.findIndex((x) => x.id === value);
                if (e.key === "ArrowDown" || e.key === "ArrowRight") { e.preventDefault(); const n = PERSON_ROLES[(i + 1) % PERSON_ROLES.length]; onChange(n.id); document.getElementById(`${id}-${n.id}`)?.focus(); }
                if (e.key === "ArrowUp" || e.key === "ArrowLeft") { e.preventDefault(); const n = PERSON_ROLES[(i - 1 + PERSON_ROLES.length) % PERSON_ROLES.length]; onChange(n.id); document.getElementById(`${id}-${n.id}`)?.focus(); }
              }}
              tabIndex={on ? 0 : -1}
              className={cn("flex items-start gap-2 rounded-md border px-3 py-2 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring", on ? "border-tint-line bg-secondary/70" : "border-border bg-card hover:bg-accent")}
            >
              <span className={cn("mt-1 grid size-3.5 shrink-0 place-items-center rounded-full border", on ? "border-primary" : "border-border-strong")} aria-hidden>{on ? <span className="size-2 rounded-full bg-primary" /> : null}</span>
              <span className="min-w-0">
                <span className="block text-sm font-medium text-foreground">{r.label}</span>
                <span className="block text-xs text-muted-foreground">{r.text}</span>
              </span>
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

function validate(role: PersonRole, depts: string[], end: string): { depts?: string; end?: string } {
  const e: { depts?: string; end?: string } = {};
  if (ROLE_OF[role].dept && !depts.length) e.depts = "Pick at least one department.";
  if (role === "resident" && !end) e.end = "A resident needs the end of the rotation; access stops then.";
  return e;
}

export function AddPersonDialog({ open, onOpenChange, initialRole, hospitalName }: { open: boolean; onOpenChange: (o: boolean) => void; initialRole?: PersonRole; hospitalName: string }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<PersonRole>(initialRole ?? "doctor");
  const [depts, setDepts] = useState<string[]>([]);
  const [end, setEnd] = useState("");
  const [err, setErr] = useState<{ name?: string; email?: string; depts?: string; end?: string }>({});
  const [done, setDone] = useState<{ login: string; password: string; mailto: string; who: string } | null>(null);
  useEffect(() => { if (open) { setRole(initialRole ?? "doctor"); } }, [open, initialRole]);

  const save = useAsyncAction(async () => {
    const who = name.trim();
    const r = await api.post<AccountCreated>(EP.accounts, { email: email.trim().toLowerCase(), display_name: who, ...roleBody(role, depts, end), end_date: role === "resident" ? end : undefined });
    void qc.invalidateQueries({ queryKey: keys.accounts });
    void qc.invalidateQueries({ queryKey: keys.hospital });
    void qc.invalidateQueries({ queryKey: keys.org });
    const info = r.mailto ? loginFromMailto(r.mailto) : null;
    if (info && r.mailto) {
      setDone({ login: info.login || r.username, password: info.password, mailto: r.mailto, who });
      notify.success("Login created", `${who}, ${ROLE_OF[role].label}`);
    } else {
      notify.success(r.created === false ? "Role given to an existing login" : "Added", `${who || r.username}, ${ROLE_OF[role].label}`);
      onOpenChange(false);
    }
  });
  useEffect(() => {
    if (!open) {
      const t = window.setTimeout(() => { setName(""); setEmail(""); setDepts([]); setEnd(""); setErr({}); setDone(null); save.reset(); }, 200);
      return () => window.clearTimeout(t);
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const x: typeof err = { ...validate(role, depts, end) };
    if (!name.trim()) x.name = "Give the person's name.";
    if (!EMAIL.test(email.trim())) x.email = "Type the person's email address; it becomes their login.";
    setErr(x);
    if (!Object.keys(x).length) void save.run();
  };
  const r = ROLE_OF[role];
  return (
    <Dialog open={open} onOpenChange={(o) => { if (save.state !== "loading") onOpenChange(o); }}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-xl">
        {done ? (
          <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="grid grid-cols-1 gap-4">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2"><CheckCircle2 className="size-5 text-ok" aria-hidden /> {done.who} is added</DialogTitle>
              <DialogDescription>{r.label} at {hospitalName}. Send them the login; they choose their own password at the first sign-in.</DialogDescription>
            </DialogHeader>
            <OneTimeLoginPanel login={done.login} password={done.password} mailto={done.mailto} />
            <DialogFooter className="gap-2 sm:gap-2">
              <Button type="button" variant="outline" onClick={() => { setDone(null); setName(""); setEmail(""); setEnd(""); save.reset(); }}><UserPlus className="size-4" aria-hidden /> Add another</Button>
              <Button type="button" onClick={() => onOpenChange(false)}>Done</Button>
            </DialogFooter>
          </motion.div>
        ) : (
          <form onSubmit={submit} noValidate className="grid grid-cols-1 gap-4" aria-label="Add a person">
            <DialogHeader>
              <DialogTitle>{initialRole ? `Add ${ROLE_A[initialRole]}` : "Add a person"}</DialogTitle>
              <DialogDescription>Their email becomes the login. Vaidyx makes a first password, shown once on the next screen.</DialogDescription>
            </DialogHeader>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Field id="ap-name" label="Name" required error={err.name}><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Dr Asha Menon" autoFocus /></Field>
              <Field id="ap-email" label="Email (the login)" required error={err.email}><Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="e.g. name@hospital.in" autoComplete="off" /></Field>
            </div>
            <RolePicker value={role} onChange={(v) => { setRole(v); setErr((x) => ({ ...x, depts: undefined, end: undefined })); }} id="ap-role" />
            {r.dept ? <DepartmentPicker value={depts} onChange={(v) => { setDepts(v); setErr((x) => ({ ...x, depts: undefined })); }} error={err.depts} id="ap-dept" /> : null}
            {role === "resident" ? <Field id="ap-end" label="Rotation ends" required error={err.end} hint="Access to Case Files stops on this date."><DateInput value={end} onChange={(v) => { setEnd(v); setErr((x) => ({ ...x, end: undefined })); }} /></Field> : null}
            {save.error ? <p role="alert" className="rounded-md status-bad px-3 py-2 text-sm">{save.error}</p> : null}
            <DialogFooter className="gap-2 sm:gap-2">
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
              <ActionButton type="submit" state={save.state} loadingText="Adding" doneText="Added" icon={<UserPlus className="size-4" aria-hidden />}>Add {ROLE_A[role]}</ActionButton>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

/** Change one login's role and departments (and a resident's end date). Several roles are replaced by the one picked. */
export function ChangeRoleDialog({ account, onOpenChange }: { account: AccountRow | null; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const current = account ? rolesOf(account) : [];
  const [role, setRole] = useState<PersonRole>("doctor");
  const [depts, setDepts] = useState<string[]>([]);
  const [end, setEnd] = useState("");
  const [err, setErr] = useState<{ depts?: string; end?: string }>({});
  useEffect(() => {
    if (account) {
      const r = rolesOf(account)[0] ?? "doctor";
      setRole(r);
      setDepts(deptsOf(account, r));
      setEnd(account.end_date ?? "");
      setErr({});
    }
  }, [account]);
  const save = useAsyncAction(async () => {
    if (!account) return;
    await api.put(EP.account(account.username), roleBody(role, depts, end));
    await qc.invalidateQueries({ queryKey: keys.accounts });
    void qc.invalidateQueries({ queryKey: keys.hospital });
    notify.success(`Now ${ROLE_A[role]}`, account.display_name || account.username);
    window.setTimeout(() => onOpenChange(false), 300);
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const x = validate(role, depts, end);
    setErr(x);
    if (!Object.keys(x).length) void save.run();
  };
  const who = account?.display_name || account?.username || "";
  return (
    <Dialog open={Boolean(account)} onOpenChange={(o) => { if (save.state !== "loading") onOpenChange(o); }}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-xl">
        <form onSubmit={submit} noValidate className="grid grid-cols-1 gap-4" aria-label="Change the role">
          <DialogHeader>
            <DialogTitle>Change the role of {who}</DialogTitle>
            <DialogDescription>{current.length > 1 ? `Now: ${current.map((r) => ROLE_OF[r].label).join(", ")}. The role you pick replaces them all.` : "The role you pick replaces the current one. Their login and password stay."}</DialogDescription>
          </DialogHeader>
          <RolePicker value={role} onChange={(v) => { setRole(v); if (account) setDepts(deptsOf(account, v).length ? deptsOf(account, v) : depts); setErr({}); }} id="cr-role" />
          {ROLE_OF[role].dept ? <DepartmentPicker value={depts} onChange={(v) => { setDepts(v); setErr((x) => ({ ...x, depts: undefined })); }} error={err.depts} id="cr-dept" /> : null}
          {role === "resident" ? <Field id="cr-end" label="Rotation ends" required error={err.end}><DateInput value={end} onChange={(v) => { setEnd(v); setErr((x) => ({ ...x, end: undefined })); }} /></Field> : null}
          {save.error ? <p role="alert" className="rounded-md status-bad px-3 py-2 text-sm">{save.error}</p> : null}
          <DialogFooter className="gap-2 sm:gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <ActionButton type="submit" state={save.state} loadingText="Saving" doneText="Saved">Save</ActionButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
