// /admin: the root admin's guided set-up (GET /setup), five steps saved as you go: Hospital, Departments, People and
// roles, Hospital system (must pass its test), Board. Continue saves the step; the list on the right shows what is done.
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import { Building2, CalendarDays, CheckCircle2, Circle, Hospital, PlugZap, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { PageHeader } from "@/components/PageHeader";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";
import { Stepper, Step, StepTitle } from "@/components/Stepper";
import { notify } from "@/components/Toasts";
import { errorMessage } from "@/hooks/useAsyncAction";
import { keys, useAccounts, useInvalidate, useSetup } from "@/hooks/useQueries";
import { api, ApiError } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import { useSession } from "@/lib/session";
import type { HisTestResult, SetupPeopleResult, SetupResponse } from "@/lib/types";
import { cn } from "@/lib/utils";
import { formFrom, newRow, type PersonRow, type SetupForm } from "@/features/admin/state";
import { BoardStep, DepartmentsStep, HisStep, HospitalStep, PeopleStep, departmentsInvalid } from "@/features/admin/SetupSteps";
import { SetupReview } from "@/features/admin/SetupReview";

const STEP_IDS = ["hospital", "departments", "people", "his", "board"] as const;
const STEP_ICON = { hospital: Hospital, departments: Building2, people: Users, his: PlugZap, board: CalendarDays } as const;


/** "13 login(s), 1 coordinator(s)" from the server reads "13 logins, 1 coordinator". */
function plainCounts(text?: string): string {
  return (text ?? "").replace(/\b(\d+) ([\w ]*?\w)\(s\)/g, (_m, n, w) => `${n} ${w}${n === "1" ? "" : "s"}`);
}
export default function AdminSetup() {
  const { me } = useSession();
  const setup = useSetup({ enabled: Boolean(me?.roles.root_admin || me?.roles.admin) });
  const accounts = useAccounts({ enabled: Boolean(setup.data) });
  const qc = useQueryClient();
  const invalidate = useInvalidate();
  const [form, setForm] = useState<SetupForm | null>(null);
  const [step, setStep] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [stepError, setStepError] = useState<string | null>(null);
  const [hisResult, setHisResult] = useState<HisTestResult | null>(null);

  useEffect(() => {
    if (setup.data && !form) {
      setForm(formFrom(setup.data));
      const firstOpen = setup.data.steps.findIndex((s) => !s.done);
      setStep(firstOpen < 0 ? 6 : firstOpen + 1);  // all done: open on the review of every choice
    }
  }, [setup.data, form]);

  const store = (r: Partial<SetupResponse>) => { if (r && Array.isArray(r.steps)) qc.setQueryData(keys.setup, r); };
  const done = setup.data?.steps.filter((s) => s.done).length ?? 0;
  const pct = 20 + Math.round((done / 5) * 80);

  const createPeople = async (rows: PersonRow[]) => {
    if (!form || !rows.length) return;
    const body = {
      accounts: rows.map((r) => ({
        email: r.email.trim().toLowerCase(),
        display_name: r.name.trim(),
        departments: r.dept ? { [r.dept]: r.role } : {},
        coordinator: r.coordinator,
        admin_of: r.deptAdmin && r.dept ? [r.dept] : [],
        root_admin: r.rootAdmin,
        end_date: r.role === "resident" && r.endDate ? r.endDate : undefined,
      })),
    };
    const r = await api.post<SetupPeopleResult & Partial<SetupResponse>>(EP.setupPeople, body);
    store(r);
    const made = new Map((r.created ?? []).map((c) => [String(c.email || c.username || "").toLowerCase(), c]));
    const errs = new Map((r.errors ?? []).map((e) => (typeof e === "string" ? ["", e] : [String(e.email || "").toLowerCase(), e.message || "Not created"])));
    setForm((f) => f && ({
      ...f,
      people: f.people.map((row) => {
        const key = row.email.trim().toLowerCase();
        const c = made.get(key);
        if (c) return { ...row, created: true, mailto: c.mailto || "", error: undefined };
        const e = errs.get(key);
        return e ? { ...row, error: e } : row;
      }),
    }));
    void invalidate(keys.accounts, keys.org);
    const n = r.created?.length ?? 0;
    if (n) notify.success(n === 1 ? "Login created" : `${n} logins created`, "Press Send login by email on each row.");
    if (r.errors?.length) throw new Error(`${r.errors.length} could not be created: see the rows.`);
  };

  const testHis = async () => {
    if (!form) return;
    const r = await api.post<{ ok: boolean; test: HisTestResult } & Partial<SetupResponse>>(EP.setupHis, { url: form.his.url.trim(), token: form.his.token.trim() || undefined });
    store(r);
    setHisResult(r.test);
    setForm((f) => f && ({ ...f, his: { ...f.his, token: "" } }));
    if (r.test?.ok) notify.success("The hospital system answers");
  };

  const retestHis = async () => {
    const r = await api.post<HisTestResult>(EP.hisTest);
    setHisResult(r);
    await invalidate(keys.setup);
    if (r.ok) notify.success("The hospital system answers");
  };

  /** Saves the step being left by Continue; false keeps the admin on it. */
  const saveStep = async (n: number): Promise<boolean> => {
    if (!form || !setup.data) return false;
    setStepError(null);
    setSaving(true);
    try {
      const id = STEP_IDS[n - 1];
      if (id === "hospital") {
        if (!form.hospital.name.trim()) { setStepError("Give the hospital's name."); return false; }
        store(await api.post<SetupResponse>(EP.setupHospital, { name: form.hospital.name.trim(), level: form.hospital.level, type: form.hospital.type, pmjay_empanelled: form.hospital.pmjay, fetch_window_months: form.hospital.fetchWindow }));
      } else if (id === "departments") {
        const bad = departmentsInvalid(form.departments);
        if (bad) { setStepError(bad); return false; }
        const contacts = Object.fromEntries(Object.entries(form.departments.contacts).filter(([dept]) => form.departments.enabled.includes(dept)).map(([dept, c]) => [dept, { email: c.email.trim(), phone: c.phone.trim() }]));
        store(await api.post<SetupResponse>(EP.setupDepartments, { enabled: form.departments.enabled, contacts }));
      } else if (id === "people") {
        const pending = form.people.filter((r) => !r.created && r.email.trim());
        if (pending.length) await createPeople(pending);
      } else if (id === "his") {
        const tested = setup.data.his?.ok && !form.his.token && form.his.url.trim() === (setup.data.his?.url || "");
        if (!tested) await testHis();
        const ok = tested || (qc.getQueryData<SetupResponse>(keys.setup)?.his?.ok ?? false);
        if (!ok) { setStepError("The test must pass before Case Files can come from a UHID. Fix the address or token and test again, or go on to the Board step and come back."); return false; }
      } else if (id === "board") {
        if (!form.board.heads.length) { setStepError("Tick at least one board head."); return false; }
        store(await api.post<SetupResponse>(EP.setupBoard, {
          coordinators: form.board.coordinators,
          heads: form.board.heads,
          meeting_defaults: { weekday: form.board.weekday || null, time: form.board.time, room: form.board.room.trim(), minutes_per_case: form.board.minutes },
        }));
        void invalidate(keys.accounts, keys.org);
      }
      notify.success("Saved", setup.data.steps[n - 1]?.label);
      return true;
    } catch (e) {
      setStepError(e instanceof ApiError || e instanceof Error ? errorMessage(e) : "Could not save this step.");
      return false;
    } finally {
      setSaving(false);
    }
  };

  const go = async (n: number) => {
    if (step === null) return;
    if (n === step + 1 && !(await saveStep(step))) return;
    setStepError(null);
    setStep(n);
  };

  const summary = useMemo(() => setup.data?.steps ?? [], [setup.data]);

  if (!me) return null;
  if (!me.roles.root_admin && !me.roles.admin) {
    return (
      <div className="mx-auto max-w-2xl">
        <PageHeader title="Hospital set-up" />
        <div className="surface"><EmptyState kind="lock" title="Only the root admin sets up the hospital" text={(me.roles.admin_of || []).length ? "You manage your department's people on the People page." : "Ask the root admin of the hospital."} action={(me.roles.admin_of || []).length ? <Button type="button" asChild><Link to="/people">Open People</Link></Button> : undefined} /></div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Hospital set-up"
        subtitle={setup.data?.complete ? "Everything is set. Change any step at any time; each saves at once." : "Five steps, each saved as you go. You can stop and come back."}
        actions={<Button type="button" variant="outline" asChild><Link to="/people"><Users className="size-4" aria-hidden /> People</Link></Button>}
      >
        {setup.data ? <div className="max-w-md"><Progress value={pct} className="h-1.5" aria-label={`${done} of 5 steps done`} /><p className="mt-1 text-xs text-muted-foreground">{done} of 5 steps done</p></div> : null}
      </PageHeader>
      {setup.isLoading ? (
        <div className="surface space-y-3 p-6" aria-busy="true"><div className="skeleton-line h-8 w-1/2" /><div className="skeleton-line h-40" /></div>
      ) : setup.error && !setup.data ? (
        <div className="surface"><ErrorState error={setup.error} what="the hospital set-up" onRetry={() => void setup.refetch()} retrying={setup.isFetching} /></div>
      ) : setup.data && form && step !== null ? (
        <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
          <div className="min-w-0">
            <Stepper
              step={step}
              onStepChange={(n) => void go(n)}
              onFinalStepCompleted={() => void (async () => { if (await saveStep(5)) setStep(6); })()}
              nextLoading={saving}
              nextButtonText={saving ? "Saving" : "Save and continue"}
              completeButtonText={saving ? "Saving" : "Save and finish"}
              completedContent={
                <div className="flex flex-col items-center gap-3 py-4 text-center">
                  <CheckCircle2 className="size-10 text-ok" aria-hidden />
                  <h2 className="text-lg">{setup.data.complete ? "The hospital is set up" : "Saved. Some steps still need a look"}</h2>
                  <p className="max-w-md text-sm text-muted-foreground">{setup.data.complete ? "Here is everything you chose. Edit any part; each step saves again on its own." : "Here is what is saved so far; open the steps marked not done to finish them."}</p>
                  <SetupReview setup={setup.data} accounts={accounts.data?.accounts ?? []} onEdit={(n) => { setStepError(null); setStep(n); }} />
                  <div className="flex flex-wrap justify-center gap-2 pt-2">
                    <Button type="button" asChild><Link to="/people">Open People</Link></Button>
                  </div>
                </div>
              }
            >
              <Step title="Hospital">
                <StepTitle title="The hospital" text="Its name, NCG level and PM-JAY status." />
                <HospitalStep value={form.hospital} onChange={(v) => setForm({ ...form, hospital: v })} setup={setup.data} />
              </Step>
              <Step title="Departments">
                <StepTitle title="Departments" text="Which departments the hospital has and how to reach their desks." />
                <DepartmentsStep value={form.departments} onChange={(v) => setForm({ ...form, departments: v })} departments={setup.data.departments} />
              </Step>
              <Step title="People">
                <StepTitle title="People and roles" text="Invite by email; each login is a plain account with a random first password." />
                <PeopleStep rows={form.people} onChange={(rows) => setForm({ ...form, people: rows.length ? rows : [newRow()] })} departments={setup.data.departments} accounts={accounts.data?.accounts ?? []} onCreate={createPeople} />
              </Step>
              <Step title="Hospital system">
                <StepTitle title="Hospital system" text="Where Vaidyx reads the reports from." />
                <HisStep value={form.his} onChange={(v) => setForm({ ...form, his: v })} setup={setup.data} result={hisResult} onTest={testHis} onRetest={retestHis} />
              </Step>
              <Step title="Board">
                <StepTitle title="The board" text="Coordinators, the heads at every board, and the meeting defaults." />
                <BoardStep value={form.board} onChange={(v) => setForm({ ...form, board: v })} departments={setup.data.departments} accounts={accounts.data?.accounts ?? []} />
              </Step>
            </Stepper>
            {stepError ? <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} role="alert" className="mt-3 rounded-md status-bad px-3 py-2 text-sm">{stepError}</motion.p> : null}
          </div>
          <aside className="surface h-fit p-4 lg:sticky lg:top-20" aria-label="Set-up so far">
            <p className="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">Set-up so far</p>
            <ol className="grid gap-1">
              {summary.map((s, i) => {
                const Icon = STEP_ICON[s.id as keyof typeof STEP_ICON] ?? Circle;
                return (
                  <li key={s.id}>
                    <button type="button" onClick={() => { setStepError(null); setStep(i + 1); }} className={cn("flex w-full items-start gap-2 rounded-md p-2 text-left outline-none transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring", step === i + 1 && "bg-secondary/60")} aria-current={step === i + 1 ? "step" : undefined}>
                      <span className={cn("mt-0.5 grid size-6 shrink-0 place-items-center rounded-full", s.done ? "status-ok" : "bg-muted text-muted-foreground")}>
                        {s.done ? <CheckCircle2 className="size-4" aria-hidden /> : <Icon className="size-3.5" aria-hidden />}
                      </span>
                      <span className="min-w-0">
                        <span className="block text-sm font-medium text-foreground">{s.label}</span>
                        <span className="block text-xs text-muted-foreground">{s.done ? plainCounts(s.summary) : "not done yet"}</span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ol>
          </aside>
        </div>
      ) : null}
    </div>
  );
}
