// /hospital/departments: GET /hospital/departments (group, heads, people, residents, desk contact, receives requests). Edit a desk
// contact and turn on a department through the existing set-up route (POST /setup/departments {contacts} / {enabled}).
import { useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Building2, Inbox, Mail, Pencil, Phone, Plus, UserRound, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { SearchBox } from "@/components/SearchBox";
import { DataList } from "@/components/DataList";
import { EmptyState } from "@/components/EmptyState";
import { Field } from "@/components/Field";
import { ActionButton } from "@/components/ActionButton";
import { Pill } from "@/components/StatusPill";
import { notify } from "@/components/Toasts";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { keys, useHospitalDepartments } from "@/hooks/useQueries";
import { api } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import type { HospitalDepartment } from "@/lib/types";
import { cn } from "@/lib/utils";
import { PLACEHOLDER_DOMAIN } from "@/features/admin/state";

const realEmail = (e?: string) => (e && !e.endsWith(`@${PLACEHOLDER_DOMAIN}`) ? e : "");
const headNames = (d: HospitalDepartment) => (d.heads ?? []).map((h) => (typeof h === "string" ? h : h.display_name || h.username));

function useSaveDepartments() {
  const qc = useQueryClient();
  return async (body: Record<string, unknown>) => {
    await api.post(EP.setupDepartments, body);
    await qc.invalidateQueries({ queryKey: keys.hospitalDepartments });
    void qc.invalidateQueries({ queryKey: keys.setup });
    void qc.invalidateQueries({ queryKey: keys.org });
    void qc.invalidateQueries({ queryKey: keys.hospitalOverview });
  };
}

function EditContact({ dept, onOpenChange }: { dept: HospitalDepartment | null; onOpenChange: (o: boolean) => void }) {
  const save = useSaveDepartments();
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [key, setKey] = useState("");
  if (dept && key !== dept.id) { setKey(dept.id); setEmail(realEmail(dept.email)); setPhone(dept.phone ?? ""); }
  const run = useAsyncAction(async () => {
    if (!dept) return;
    await save({ contacts: { [dept.id]: { email: email.trim(), phone: phone.trim() } } });
    notify.success("Contact saved", dept.name);
    window.setTimeout(() => onOpenChange(false), 300);
  });
  const submit = (e: FormEvent) => { e.preventDefault(); void run.run(); };
  return (
    <Dialog open={Boolean(dept)} onOpenChange={(o) => { if (!o) setKey(""); onOpenChange(o); }}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-md">
        <form onSubmit={submit} noValidate className="grid grid-cols-1 gap-4">
          <DialogHeader>
            <DialogTitle>Desk contact of {dept?.name}</DialogTitle>
            <DialogDescription>Shown to doctors who send this department a request. Leave empty if there is none.</DialogDescription>
          </DialogHeader>
          <Field id="dc-email" label="Desk email" optional><Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="e.g. radiology.desk@hospital.in" /></Field>
          <Field id="dc-phone" label="Desk phone" optional><Input type="tel" inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="e.g. 040 2312 4101" /></Field>
          {run.error ? <p role="alert" className="text-sm text-bad">{run.error}</p> : null}
          <DialogFooter className="gap-2 sm:gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <ActionButton type="submit" state={run.state} loadingText="Saving" doneText="Saved">Save</ActionButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function TurnOn({ open, onOpenChange, all }: { open: boolean; onOpenChange: (o: boolean) => void; all: HospitalDepartment[] }) {
  const save = useSaveDepartments();
  const off = all.filter((d) => !d.enabled).sort((a, b) => a.name.localeCompare(b.name));
  const [busy, setBusy] = useState<string | null>(null);
  const turnOn = async (d: HospitalDepartment) => {
    setBusy(d.id);
    try {
      await save({ enabled: [...all.filter((x) => x.enabled).map((x) => x.id), d.id] });
      notify.success("Department added", d.name);
      onOpenChange(false);
    } catch (e) {
      notify.error("Could not add", e instanceof Error ? e.message : undefined);
    } finally {
      setBusy(null);
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add a department</DialogTitle>
          <DialogDescription>The departments Vaidyx knows that this hospital has not turned on yet.</DialogDescription>
        </DialogHeader>
        {off.length ? (
          <ul className="grid grid-cols-1 gap-1">
            {off.map((d) => (
              <li key={d.id} className="flex items-center gap-3 rounded-md px-2 py-1.5 hover:bg-accent/50">
                <span className="min-w-0 flex-1 text-sm text-foreground">{d.name}<span className="block text-xs text-muted-foreground">{d.group === "supporting" ? "Supporting" : "Treating"}</span></span>
                <Button type="button" size="sm" variant="outline" disabled={Boolean(busy)} aria-busy={busy === d.id} onClick={() => void turnOn(d)}><Plus className="size-4" aria-hidden /> {busy === d.id ? "Adding" : "Add"}</Button>
              </li>
            ))}
          </ul>
        ) : <p className="text-sm text-muted-foreground">Every department is on already.</p>}
        <DialogFooter><Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Close</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function HospitalDepartments() {
  const q = useHospitalDepartments();
  const [search, setSearch] = useState("");
  const [group, setGroup] = useState<"all" | "treating" | "supporting">("all");
  const [editing, setEditing] = useState<HospitalDepartment | null>(null);
  const [adding, setAdding] = useState(false);
  const all = useMemo(() => q.data?.departments ?? [], [q.data]);
  const rows = useMemo(() => {
    const n = search.trim().toLowerCase();
    return all
      .filter((d) => d.enabled)
      .filter((d) => group === "all" || d.group === group)
      .filter((d) => !n || [d.name, ...headNames(d), d.email, d.phone].filter(Boolean).join(" ").toLowerCase().includes(n))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [all, search, group]);
  const on = all.filter((d) => d.enabled);
  return (
    <div className="grid grid-cols-1 gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <SearchBox value={search} onChange={setSearch} placeholder="Find a department or head" label="Find a department" wrapperClassName="sm:w-72" />
          <div role="group" aria-label="Group" className="flex flex-wrap gap-1.5">
            {(["all", "treating", "supporting"] as const).map((g) => (
              <button key={g} type="button" aria-pressed={group === g} onClick={() => setGroup(g)} className={cn("inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-[13px] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring", group === g ? "border-tint-line bg-secondary text-secondary-foreground" : "border-border bg-card text-muted-foreground hover:text-foreground")}>
                {g === "all" ? "All" : g === "treating" ? "Treating" : "Supporting"} <span className="tabular-nums text-xs opacity-80">{g === "all" ? on.length : on.filter((d) => d.group === g).length}</span>
              </button>
            ))}
          </div>
        </div>
        <Button type="button" variant="outline" onClick={() => setAdding(true)} disabled={!all.some((d) => !d.enabled)}><Plus className="size-4" aria-hidden /> Add a department</Button>
      </div>
      <DataList
        items={rows}
        loading={q.isLoading}
        error={q.error}
        onRetry={() => void q.refetch()}
        retrying={q.isFetching}
        what="the departments"
        keyFor={(d) => d.id}
        renderRow={(d) => {
          const heads = headNames(d);
          const email = realEmail(d.email);
          return (
            <div className="surface-inner grid gap-2 px-3 py-3 md:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_minmax(0,1.2fr)_auto] md:items-center md:gap-4" data-testid="department-row">
              <div className="flex min-w-0 items-center gap-3">
                <span className="grid size-9 shrink-0 place-items-center rounded-md bg-secondary text-secondary-foreground"><Building2 className="size-4" aria-hidden /></span>
                <span className="min-w-0">
                  <span className="block truncate font-medium text-foreground">{d.name}</span>
                  <span className="flex flex-wrap items-center gap-1.5 pt-0.5">
                    <Pill tone="neutral">{d.group === "supporting" ? "Supporting" : "Treating"}</Pill>
                    {d.receives_requests ? <Pill tone="info" icon={Inbox}>Receives requests</Pill> : null}
                  </span>
                </span>
              </div>
              <div className="min-w-0 text-sm">
                <span className="flex items-center gap-1.5 text-foreground"><UserRound className="size-3.5 shrink-0 text-muted-foreground" aria-hidden /><span className="truncate">{heads.length ? heads.join(", ") : <span className="text-warn">No head yet</span>}</span></span>
                <span className="flex items-center gap-1.5 text-xs text-muted-foreground"><Users className="size-3.5 shrink-0" aria-hidden />{d.people} {d.people === 1 ? "person" : "people"}{d.residents ? `, ${d.residents} ${d.residents === 1 ? "resident" : "residents"}` : ""}</span>
              </div>
              <div className="min-w-0 text-xs text-muted-foreground">
                {email || d.phone ? (
                  <>
                    {email ? <span className="flex items-center gap-1.5"><Mail className="size-3.5 shrink-0" aria-hidden /><span className="truncate">{email}</span></span> : null}
                    {d.phone ? <span className="flex items-center gap-1.5"><Phone className="size-3.5 shrink-0" aria-hidden />{d.phone}</span> : null}
                  </>
                ) : <span className="text-warn">No desk contact</span>}
              </div>
              <div className="flex flex-wrap gap-1.5 md:justify-end">
                <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(d)} aria-label={`Edit the contact of ${d.name}`}><Pencil className="size-4" aria-hidden /> Contact</Button>
                <Button type="button" variant="ghost" size="sm" asChild><Link to={`/people?dept=${encodeURIComponent(d.id)}`} aria-label={`People of ${d.name}`}><Users className="size-4" aria-hidden /> People</Link></Button>
              </div>
            </div>
          );
        }}
        empty={<div className="surface"><EmptyState kind={search || group !== "all" ? "search" : "empty"} title={search || group !== "all" ? "No department matches" : "No department turned on"} text={search || group !== "all" ? "Try another name." : "Turn on the hospital's departments in the set-up."} action={<Button type="button" variant="outline" asChild><Link to="/hospital/setup">Open the set-up</Link></Button>} /></div>}
      />
      <EditContact dept={editing} onOpenChange={(o) => { if (!o) setEditing(null); }} />
      <TurnOn open={adding} onOpenChange={setAdding} all={all} />
    </div>
  );
}
