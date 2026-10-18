// The five steps of the guided set-up (SPEC 3.8). Each step is a plain form over the lifted SetupForm; AdminSetup saves
// the step when the admin presses Continue. People and the hospital system also act inside the step (create logins,
// test the connection), because their result is something to look at before moving on.
import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { CheckCircle2, Mail, Plus, PlugZap, Trash2, UserPlus, XCircle } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Field } from "@/components/Field";
import { DateInput } from "@/components/DateInput";
import { SwitchRow } from "@/components/FilterChips";
import { ActionButton } from "@/components/ActionButton";
import { SearchBox } from "@/components/SearchBox";
import { Pill } from "@/components/StatusPill";
import { DateText } from "@/components/DateText";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import type { AccountRow, HisTestResult, Placement, SetupDepartment, SetupResponse } from "@/lib/types";
import { cn } from "@/lib/utils";
import { EMAIL, WEEKDAYS, newRow, type BoardState, type DepartmentsState, type HisState, type HospitalState, type PersonRow } from "@/features/admin/state";

// ---- 1 Hospital ---------------------------------------------------------------------------------------------------------
export function HospitalStep({ value, onChange, setup, error }: { value: HospitalState; onChange: (v: HospitalState) => void; setup: SetupResponse; error?: string | null }) {
  const set = (p: Partial<HospitalState>) => onChange({ ...value, ...p });
  const levels = setup.levels?.length ? setup.levels : ["essential", "optimal"];
  const types = (setup.types ?? ["", "public", "private"]).filter(Boolean);
  return (
    <div className="grid gap-5">
      <Field id="h-name" label="Hospital name" required error={error}>
        <Input value={value.name} onChange={(e) => set({ name: e.target.value })} placeholder="e.g. Vaidyx Demo Hospital" maxLength={120} autoFocus />
      </Field>
      <fieldset className="grid gap-2">
        <legend className="mb-1 text-sm font-medium">NCG level</legend>
        <p className="-mt-1 text-xs text-muted-foreground">The National Cancer Grid resource level; it decides which records the checklists ask for.</p>
        <RadioGroup value={value.level} onValueChange={(v) => set({ level: v })} className="grid gap-2 sm:grid-cols-2">
          {levels.map((l) => (
            <Label key={l} htmlFor={`lvl-${l}`} className="surface-inner flex cursor-pointer items-start gap-2 p-3 font-normal has-[[data-state=checked]]:border-primary has-[[data-state=checked]]:bg-secondary/50">
              <RadioGroupItem id={`lvl-${l}`} value={l} className="mt-0.5" />
              <span>
                <span className="block text-sm font-medium capitalize text-foreground">{l}</span>
                <span className="block text-xs text-muted-foreground">{l === "essential" ? "The basic set every centre can do" : "The full set at a well-resourced centre"}</span>
              </span>
            </Label>
          ))}
        </RadioGroup>
      </fieldset>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="h-type" label="Type" optional>
          <Select value={value.type || "none"} onValueChange={(v) => set({ type: v === "none" ? "" : v })}>
            <SelectTrigger className="w-full" id="h-type" aria-label="Type"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="none">Not said</SelectItem>
              {types.map((t) => <SelectItem key={t} value={t} className="capitalize">{t}</SelectItem>)}
            </SelectContent>
          </Select>
        </Field>
        <Field id="h-window" label="Records fetched for a new Case File" hint="The usual window; a doctor can change it per Case File.">
          <Select value={String(value.fetchWindow)} onValueChange={(v) => set({ fetchWindow: Number(v) })}>
            <SelectTrigger className="w-full" id="h-window" aria-label="Fetch window"><SelectValue /></SelectTrigger>
            <SelectContent>{[6, 12, 18, 24, 36].map((m) => <SelectItem key={m} value={String(m)}>Last {m} months{m === 12 ? " (usual)" : ""}</SelectItem>)}</SelectContent>
          </Select>
        </Field>
      </div>
      <SwitchRow id="h-pmjay" label="Empanelled under PM-JAY" hint="Ayushman Bharat PM-JAY: the board record then carries the Pre-Authorization checks." checked={value.pmjay} onCheckedChange={(v) => set({ pmjay: v })} />
    </div>
  );
}

// ---- 2 Departments ------------------------------------------------------------------------------------------------------
export function DepartmentsStep({ value, onChange, departments }: { value: DepartmentsState; onChange: (v: DepartmentsState) => void; departments: SetupDepartment[] }) {
  const [q, setQ] = useState("");
  const on = new Set(value.enabled);
  const toggle = (id: string, yes: boolean) => onChange({ ...value, enabled: yes ? [...value.enabled.filter((x) => x !== id), id] : value.enabled.filter((x) => x !== id) });
  const setContact = (id: string, p: Partial<{ email: string; phone: string }>) => onChange({ ...value, contacts: { ...value.contacts, [id]: { ...(value.contacts[id] ?? { email: "", phone: "" }), ...p } } });
  const groups: Array<{ id: "treating" | "supporting"; label: string; hint: string }> = [
    { id: "treating", label: "Treating departments", hint: "They own Case Files." },
    { id: "supporting", label: "Supporting departments", hint: "They receive requests for records (reports, slides, scans)." },
  ];
  const needle = q.trim().toLowerCase();
  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">Tick the departments this hospital has. Add the desk email and phone so requests reach a person.</p>
        <SearchBox value={q} onChange={setQ} placeholder="Find a department" wrapperClassName="w-full sm:w-60" />
      </div>
      {groups.map((g) => {
        const list = departments.filter((d) => d.group === g.id && (!needle || d.name.toLowerCase().includes(needle)));
        const count = departments.filter((d) => d.group === g.id && on.has(d.id)).length;
        if (!list.length) return null;
        return (
          <section key={g.id} aria-label={g.label}>
            <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="text-sm">{g.label} <span className="font-normal text-muted-foreground">({count} ticked)</span></h3>
              <span className="flex gap-1">
                <Button type="button" variant="ghost" size="sm" onClick={() => onChange({ ...value, enabled: [...new Set([...value.enabled, ...departments.filter((d) => d.group === g.id).map((d) => d.id)])] })}>Tick all</Button>
                <Button type="button" variant="ghost" size="sm" onClick={() => onChange({ ...value, enabled: value.enabled.filter((id) => departments.find((d) => d.id === id)?.group !== g.id) })}>Clear</Button>
              </span>
            </div>
            <p className="mb-2 text-xs text-muted-foreground">{g.hint}</p>
            <ul className="grid gap-2">
              {list.map((d) => {
                const checked = on.has(d.id);
                const c = value.contacts[d.id] ?? { email: "", phone: "" };
                const badEmail = Boolean(c.email && !EMAIL.test(c.email));
                return (
                  <li key={d.id} className={cn("rounded-md border p-3 transition-colors", checked ? "border-tint-line bg-card" : "border-border bg-muted/50")}>
                    <div className="flex flex-wrap items-center gap-3">
                      <Checkbox id={`dept-${d.id}`} checked={checked} onCheckedChange={(v) => toggle(d.id, v === true)} />
                      <Label htmlFor={`dept-${d.id}`} className="min-w-40 flex-1 cursor-pointer text-sm font-medium">{d.name}</Label>
                      {checked ? (
                        <div className="grid w-full gap-2 sm:w-auto sm:grid-cols-[220px_160px]">
                          <Input aria-label={`${d.name} desk email`} type="email" value={c.email} onChange={(e) => setContact(d.id, { email: e.target.value })} placeholder="desk email" aria-invalid={badEmail || undefined} className={cn("h-9", badEmail && "border-bad")} />
                          <Input aria-label={`${d.name} desk phone`} inputMode="tel" value={c.phone} onChange={(e) => setContact(d.id, { phone: e.target.value })} placeholder="desk phone / ext." className="h-9" />
                        </div>
                      ) : null}
                    </div>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

export function departmentsInvalid(v: DepartmentsState): string | null {
  const bad = Object.entries(v.contacts).filter(([id, c]) => v.enabled.includes(id) && c.email && !EMAIL.test(c.email));
  if (bad.length) return "One or more desk emails do not look like email addresses.";
  if (!v.enabled.length) return "Tick at least one department.";
  return null;
}

// ---- 3 People -----------------------------------------------------------------------------------------------------------
const ROLES: Array<{ id: Placement; label: string }> = [
  { id: "member", label: "Doctor" },
  { id: "head", label: "Head" },
  { id: "resident", label: "Resident" },
];

export function PeopleStep({ rows, onChange, departments, accounts, onCreate }: {
  rows: PersonRow[];
  onChange: (rows: PersonRow[]) => void;
  departments: SetupDepartment[];
  accounts: AccountRow[];
  onCreate: (rows: PersonRow[]) => Promise<void>;
}) {
  const enabled = departments.filter((d) => d.enabled);
  // Editing a row clears its last error; the server's answer comes back through onCreate.
  const set = (key: string, p: Partial<PersonRow>) => onChange(rows.map((r) => (r.key === key ? { ...r, ...p, error: undefined } : r)));
  const pending = rows.filter((r) => !r.created && r.email.trim());
  const invalid = pending.filter((r) => !EMAIL.test(r.email.trim()) || (!r.dept && !r.coordinator && !r.rootAdmin));
  const create = useAsyncAction(async () => { await onCreate(pending); });
  const existing = accounts.filter((a) => a.username);
  return (
    <div className="grid gap-5">
      <p className="text-sm text-muted-foreground">
        Each person gets a login made from their email and a random first password. Press <span className="font-medium text-foreground">Send login by email</span>: your own mail program opens a draft with the password; Vaidyx sends nothing. They choose their own password at the first sign-in.
      </p>
      <ul className="grid gap-3">
        <AnimatePresence initial={false}>
          {rows.map((r) => {
            const emailBad = Boolean(r.email.trim() && !EMAIL.test(r.email.trim()));
            return (
              <motion.li key={r.key} layout initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, height: 0 }} className={cn("surface-inner grid gap-3 p-3", r.created && "border-ok/40")}>
                <div className="grid gap-2 md:grid-cols-[1.3fr_1fr_1fr_130px]">
                  <Input aria-label="Email" type="email" value={r.email} onChange={(e) => set(r.key, { email: e.target.value })} placeholder="email@hospital.in" disabled={r.created} aria-invalid={emailBad || undefined} className={cn(emailBad && "border-bad")} />
                  <Input aria-label="Name" value={r.name} onChange={(e) => set(r.key, { name: e.target.value })} placeholder="Name, e.g. Dr Asha Menon" disabled={r.created} />
                  <Select value={r.dept || "none"} onValueChange={(v) => set(r.key, { dept: v === "none" ? "" : v })} disabled={r.created}>
                    <SelectTrigger className="w-full" aria-label="Department"><SelectValue placeholder="Department" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">No department</SelectItem>
                      {enabled.map((d) => <SelectItem key={d.id} value={d.id}>{d.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                  <Select value={r.role} onValueChange={(v) => set(r.key, { role: v as Placement })} disabled={r.created || !r.dept}>
                    <SelectTrigger className="w-full" aria-label="Role"><SelectValue /></SelectTrigger>
                    <SelectContent>{ROLES.map((x) => <SelectItem key={x.id} value={x.id}>{x.label}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
                  {[["coordinator", "MDT Coordinator"], ["deptAdmin", "Department admin"], ["rootAdmin", "Root admin"]].map(([k, label]) => (
                    <label key={k} className="inline-flex items-center gap-2">
                      <Checkbox checked={Boolean(r[k as keyof PersonRow])} onCheckedChange={(v) => set(r.key, { [k]: v === true } as Partial<PersonRow>)} disabled={r.created || (k === "deptAdmin" && !r.dept)} />
                      {label}
                    </label>
                  ))}
                  {r.role === "resident" && r.dept ? (
                    <label className="inline-flex items-center gap-2">End of rotation <DateInput value={r.endDate} onChange={(v) => set(r.key, { endDate: v })} className="h-8" wrapperClassName="w-40" disabled={r.created} aria-label="End of rotation" /></label>
                  ) : null}
                  <span className="ml-auto flex items-center gap-2">
                    {r.created && r.mailto ? (
                      <Button type="button" size="sm" asChild><a href={r.mailto}><Mail className="size-4" aria-hidden /> Send login by email</a></Button>
                    ) : r.created ? (
                      <Pill tone="ok" icon={CheckCircle2}>Placed (login existed)</Pill>
                    ) : (
                      <Button type="button" variant="ghost" size="icon-sm" aria-label="Remove this row" onClick={() => onChange(rows.length > 1 ? rows.filter((x) => x.key !== r.key) : [newRow()])}><Trash2 className="size-4" aria-hidden /></Button>
                    )}
                  </span>
                </div>
                {r.error ? <p role="alert" className="flex items-center gap-1.5 text-xs font-medium text-bad"><XCircle className="size-3.5" aria-hidden /> {r.error}</p> : null}
                {!r.created && r.email.trim() && !r.dept && !r.coordinator && !r.rootAdmin ? <p className="text-xs text-muted-foreground">Pick a department, or tick MDT Coordinator or Root admin.</p> : null}
              </motion.li>
            );
          })}
        </AnimatePresence>
      </ul>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => onChange([...rows, newRow(rows[rows.length - 1]?.dept ?? "")])}><Plus className="size-4" aria-hidden /> Add a person</Button>
        <ActionButton type="button" size="sm" state={create.state} doneText="Created" loadingText="Creating logins" disabled={!pending.length || invalid.length > 0} onClick={() => void create.run()} icon={<UserPlus className="size-4" aria-hidden />}>
          Create {pending.length > 1 ? `${pending.length} logins` : "the login"}
        </ActionButton>
        {create.error ? <span role="alert" className="text-xs text-bad">{create.error}</span> : null}
      </div>
      {existing.length ? (
        <details className="rounded-md border border-border p-3 text-sm">
          <summary className="cursor-pointer font-medium">{existing.length} login{existing.length > 1 ? "s" : ""} already in the Tumour Board</summary>
          <ul className="mt-2 grid gap-1 sm:grid-cols-2">
            {existing.slice(0, 60).map((a) => (
              <li key={a.username} className="truncate text-muted-foreground"><span className="text-foreground">{a.display_name || a.username}</span> <span className="mono text-xs">{a.username}</span>{a.coordinator ? ", coordinator" : ""}{a.root_admin ? ", root admin" : ""}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}

// ---- 4 Hospital system --------------------------------------------------------------------------------------------------
export function HisStep({ value, onChange, setup, result, onTest, onRetest }: { value: HisState; onChange: (v: HisState) => void; setup: SetupResponse; result: HisTestResult | null; onTest: () => Promise<void>; onRetest: () => Promise<void> }) {
  const test = useAsyncAction(onTest);
  const retest = useAsyncAction(onRetest);
  const saved = Boolean(setup.his?.url) && value.url.trim() === setup.his?.url && !value.token;
  const last = result ?? (setup.his?.tested_at ? { ok: Boolean(setup.his.ok), error: setup.his.error } as HisTestResult : null);
  return (
    <div className="grid gap-5">
      <p className="text-sm text-muted-foreground">Vaidyx reads the reports from the hospital system (FHIR R4, read only). The test must pass before Case Files can be made from a UHID.</p>
      <div className="grid gap-4 sm:grid-cols-[1fr_260px]">
        <Field id="his-url" label="Hospital system address (URL)" required hint="This server's hospital system is on the same machine.">
          <Input value={value.url} onChange={(e) => onChange({ ...value, url: e.target.value })} placeholder="http://127.0.0.1:7130" className="mono" inputMode="url" />
        </Field>
        <Field id="his-token" label="Access token" optional hint={setup.his?.has_token ? "A token is saved; leave empty to keep it." : "Given by the hospital system's admin."}>
          <Input type="password" value={value.token} onChange={(e) => onChange({ ...value, token: e.target.value })} autoComplete="off" placeholder={setup.his?.has_token ? "saved" : ""} />
        </Field>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <ActionButton type="button" state={test.state} doneText={result?.ok ? "It answers" : "Tested"} loadingText="Testing" disabled={!value.url.trim()} onClick={() => void test.run()} icon={<PlugZap className="size-4" aria-hidden />}>Save and test</ActionButton>
        {saved ? <ActionButton type="button" variant="outline" state={retest.state} doneText="Tested" loadingText="Testing" onClick={() => void retest.run()}>Test again</ActionButton> : null}
        {setup.his?.tested_at ? <span className="text-xs text-muted-foreground">Last test <DateText value={setup.his.tested_at} mode="ago" /></span> : null}
      </div>
      {test.error || retest.error ? <p role="alert" className="text-sm text-bad">{test.error || retest.error}</p> : null}
      {last ? (
        <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} className={cn("rounded-md p-4 text-sm", last.ok ? "status-ok" : "status-bad")} role="status">
          <p className="flex items-center gap-2 font-bold">{last.ok ? <CheckCircle2 className="size-4" aria-hidden /> : <XCircle className="size-4" aria-hidden />} {last.ok ? "The hospital system answers" : "The hospital system did not answer"}</p>
          {last.ok ? (
            <p className="mt-1">
              {last.hospital_name ? `${last.hospital_name}. ` : ""}
              {typeof last.patients === "number" ? `${last.patients} patients, ` : ""}{typeof last.reports === "number" ? `${last.reports} reports. ` : ""}
              {typeof last.latency_ms === "number" ? `Answered in ${Math.round(last.latency_ms)} ms.` : ""}
            </p>
          ) : (
            <p className="mt-1">{last.error || "No answer."} Check the address and the token, then test again.</p>
          )}
        </motion.div>
      ) : null}
    </div>
  );
}

// ---- 5 Board ------------------------------------------------------------------------------------------------------------
export function BoardStep({ value, onChange, departments, accounts }: { value: BoardState; onChange: (v: BoardState) => void; departments: SetupDepartment[]; accounts: AccountRow[] }) {
  const set = (p: Partial<BoardState>) => onChange({ ...value, ...p });
  const people = useMemo(() => accounts.filter((a) => !a.disabled), [accounts]);
  const toggle = (list: string[], id: string, yes: boolean) => (yes ? [...list.filter((x) => x !== id), id] : list.filter((x) => x !== id));
  const enabled = departments.filter((d) => d.enabled || value.heads.includes(d.id));
  return (
    <div className="grid gap-6">
      <section aria-label="Coordinators">
        <h3 className="text-sm">MDT Coordinators</h3>
        <p className="mb-2 text-xs text-muted-foreground">They run the meetings and record the decisions. Create the login first (People).</p>
        {people.length ? (
          <div className="grid max-h-56 gap-1 overflow-auto rounded-md border border-border p-2 sm:grid-cols-2">
            {people.map((a) => (
              <label key={a.username} className="flex items-center gap-2 rounded px-1.5 py-1 text-sm hover:bg-accent">
                <Checkbox checked={value.coordinators.includes(a.username)} onCheckedChange={(v) => set({ coordinators: toggle(value.coordinators, a.username, v === true) })} />
                <span className="truncate">{a.display_name || a.username}</span>
              </label>
            ))}
          </div>
        ) : <p className="text-sm text-muted-foreground">No logins yet: add people in step 3 first.</p>}
      </section>
      <section aria-label="Board heads">
        <h3 className="text-sm">The heads at every board ({value.heads.length})</h3>
        <p className="mb-2 text-xs text-muted-foreground">Each head gets a card to agree or note a concern after every case. The usual five are ticked.</p>
        <div className="grid gap-1 rounded-md border border-border p-2 sm:grid-cols-2 lg:grid-cols-3">
          {enabled.map((d) => (
            <label key={d.id} className="flex items-center gap-2 rounded px-1.5 py-1 text-sm hover:bg-accent">
              <Checkbox checked={value.heads.includes(d.id)} onCheckedChange={(v) => set({ heads: toggle(value.heads, d.id, v === true) })} />
              <span className="truncate">{d.name}</span>
            </label>
          ))}
        </div>
      </section>
      <section aria-label="Meeting defaults" className="grid gap-4 sm:grid-cols-4">
        <Field id="b-day" label="Usual day">
          <Select value={value.weekday || "none"} onValueChange={(v) => set({ weekday: v === "none" ? "" : v })}>
            <SelectTrigger className="w-full" id="b-day" aria-label="Usual day"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="none">Not fixed</SelectItem>{WEEKDAYS.map((w) => <SelectItem key={w} value={w}>{w}</SelectItem>)}</SelectContent>
          </Select>
        </Field>
        <Field id="b-time" label="Usual time"><Input type="time" value={value.time} onChange={(e) => set({ time: e.target.value })} /></Field>
        <Field id="b-room" label="Room"><Input value={value.room} onChange={(e) => set({ room: e.target.value })} placeholder="e.g. Seminar hall 2" maxLength={60} /></Field>
        <Field id="b-min" label="Minutes per case"><Input type="number" min={2} max={60} value={value.minutes} onChange={(e) => set({ minutes: Math.max(1, Number(e.target.value) || 10) })} /></Field>
      </section>
    </div>
  );
}
