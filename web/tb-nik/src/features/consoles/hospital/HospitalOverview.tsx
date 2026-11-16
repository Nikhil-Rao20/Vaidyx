// /hospital (Overview): GET /hospital/overview. Tiles, the set-up checklist, the hospital system with Test now (POST /his/test),
// "Needs attention" with links, quick actions (each opens "Add a person" preset to the role) and recent people and set-up events.
// Counts only: no patient name, UHID or report text.
import { Link } from "react-router-dom";
import { plural } from "@/lib/format";
import { useQueryClient } from "@tanstack/react-query";
import type { LucideIcon } from "lucide-react";
import { Activity, AlertTriangle, CalendarDays, CheckCircle2, ChevronRight, Circle, FolderOpen, Inbox, KeyRound, PlugZap, ShieldCheck, Stethoscope, UserCog, UserMinus, UserPlus, Users, UserRoundX, CalendarClock, Building2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ErrorState";
import { ActionButton } from "@/components/ActionButton";
import { ProgressRing } from "@/components/ProgressRing";
import { DateText } from "@/components/DateText";
import { notify } from "@/components/Toasts";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { keys, useHospitalOverview } from "@/hooks/useQueries";
import { api } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import type { HisTestResult } from "@/lib/types";
import { Card, CardSkeleton, HisPill, StatTile, TileGrid, plainSummary } from "@/features/consoles/shared";
import { useHospitalContext } from "@/features/consoles/hospital/HospitalConsole";
import type { PersonRole } from "@/features/consoles/hospital/PersonDialogs";

const CASE_STATUS: Array<[string, string]> = [
  ["draft", "Draft"], ["needs_team", "Needs the treating team"], ["waiting_department", "Waiting on a department"],
  ["ready", "Ready"], ["scheduled", "Scheduled"], ["decided", "Decided"],
];
const ATTENTION_ICON: Record<string, LucideIcon> = {
  no_coordinator: UserRoundX, department_no_head: Building2, department_no_contact: Building2, resident_ending: CalendarClock,
  never_signed_in: KeyRound, disabled_logins: UserMinus, setup_unfinished: AlertTriangle, his_failing: PlugZap,
};
const QUICK: Array<{ role: PersonRole; label: string; icon: LucideIcon }> = [
  { role: "doctor", label: "Add a doctor", icon: Stethoscope },
  { role: "coordinator", label: "Add an MDT Coordinator", icon: CalendarDays },
  { role: "dept_admin", label: "Add a department admin", icon: UserCog },
  { role: "hospital_admin", label: "Add a hospital admin", icon: ShieldCheck },
];
const STEP_LINK = "/hospital/setup";

export default function HospitalOverview() {
  const q = useHospitalOverview();
  const qc = useQueryClient();
  const { openAddPerson } = useHospitalContext();
  const test = useAsyncAction(async () => {
    const r = await api.post<HisTestResult>(EP.hisTest);
    await qc.invalidateQueries({ queryKey: keys.hospitalOverview });
    if (r.ok) notify.success("The hospital system answers", typeof r.latency_ms === "number" ? `In ${Math.round(r.latency_ms)} ms` : undefined);
    else notify.error("The hospital system did not answer", r.error || "Check the address and the token in Hospital system.");
  }, { onError: (m) => notify.error("Could not test", m) });

  if (q.error && !q.data) return <div className="surface"><ErrorState error={q.error} what="the hospital overview" onRetry={() => void q.refetch()} retrying={q.isFetching} /></div>;
  const d = q.data;
  const loading = q.isLoading;
  const p = d?.people;
  const people = p ? p.doctors + p.heads + p.residents + p.coordinators + p.dept_admins + p.hospital_admins + p.auditors + (p.guests ?? 0) : undefined;
  const setupDone = d?.setup?.done ?? 0;
  const setupTotal = d?.setup?.total || d?.setup?.steps?.length || 5;

  return (
    <div className="grid grid-cols-1 gap-5">
      <TileGrid>
        <StatTile loading={loading} value={people} label="People" icon={Users} to="/hospital/people" hint={p ? `${plural(p.doctors + p.heads, "doctor")}, ${plural(p.residents, "resident")}` : undefined} />
        <StatTile loading={loading} value={d?.case_files?.total} label="Case Files" icon={FolderOpen} hint={d ? `${d.case_files.by_status?.decided ?? 0} decided` : undefined} />
        <StatTile loading={loading} value={d?.meetings?.next_7_days} label="Meetings in the next 7 days" icon={CalendarDays} />
        <StatTile loading={loading} value={d?.requests?.open} label="Open requests" icon={Inbox} />
      </TileGrid>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <Card title="Needs attention" icon={AlertTriangle} id="ho-attention" className="lg:col-span-2">
          {loading ? <CardSkeleton /> : (d?.attention ?? []).length ? (
            <ul className="grid grid-cols-1 gap-1">
              {(d?.attention ?? []).map((a, i) => {
                const Icon = ATTENTION_ICON[a.kind] ?? AlertTriangle;
                const inner = (
                  <>
                    <span className="grid size-7 shrink-0 place-items-center rounded-md status-warn"><Icon className="size-4" aria-hidden /></span>
                    <span className="min-w-0 flex-1 text-sm text-foreground">{a.text}</span>
                    {a.link ? <ChevronRight className="size-4 shrink-0 text-muted-foreground" aria-hidden /> : null}
                  </>
                );
                return (
                  <li key={`${a.kind}-${i}`}>
                    {a.link ? <Link to={a.link} className="flex items-center gap-3 rounded-md p-2 outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring">{inner}</Link> : <div className="flex items-center gap-3 p-2">{inner}</div>}
                  </li>
                );
              })}
            </ul>
          ) : <p className="flex items-center gap-2 text-sm text-muted-foreground"><CheckCircle2 className="size-4 text-ok" aria-hidden /> Nothing needs you now.</p>}
        </Card>

        <Card title="Quick actions" icon={UserPlus} id="ho-quick">
          <div className="grid grid-cols-1 gap-2">
            {QUICK.map((x) => (
              <Button key={x.role} type="button" variant="outline" className="justify-start" onClick={() => openAddPerson(x.role)}>
                <x.icon className="size-4 text-brand-text" aria-hidden /> {x.label}
              </Button>
            ))}
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-3">
        <Card title="Set-up" icon={CheckCircle2} id="ho-setup" action={!loading ? <ProgressRing value={(setupDone / setupTotal) * 100} size={36} label={`${setupDone} of ${setupTotal} steps done`} /> : null}>
          {loading ? <CardSkeleton lines={5} /> : (
            <>
              <ol className="grid grid-cols-1 gap-1">
                {(d?.setup?.steps ?? []).map((s) => (
                  <li key={s.id}>
                    <Link to={STEP_LINK} className="flex items-start gap-2 rounded-md p-1.5 text-sm outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring">
                      {s.done ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-ok" aria-hidden /> : <Circle className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />}
                      <span className="min-w-0"><span className="text-foreground">{s.label}</span><span className="sr-only">{s.done ? ", done" : ", not done"}</span>{s.summary ? <span className="block text-xs text-muted-foreground">{plainSummary(s.summary)}</span> : null}</span>
                    </Link>
                  </li>
                ))}
              </ol>
              <p className="mt-2 text-xs text-muted-foreground">{setupDone >= setupTotal ? "Everything is set." : `${setupTotal - setupDone} ${setupTotal - setupDone === 1 ? "step" : "steps"} to go.`} <Link to={STEP_LINK} className="text-link hover:underline">Open the set-up</Link></p>
            </>
          )}
        </Card>

        <Card title="Hospital system" icon={PlugZap} id="ho-his">
          {loading ? <CardSkeleton lines={2} /> : (
            <div className="grid grid-cols-1 gap-3">
              <p className="flex flex-wrap items-center gap-2"><HisPill his={d?.his} /></p>
              <p className="text-xs text-muted-foreground">{d?.his?.tested_at ? <>Last test <DateText value={d.his.tested_at} mode="ago" />.</> : "Not tested yet."} {d?.his?.url_set ? "" : "No address saved yet."}</p>
              <div className="flex flex-wrap gap-2">
                {d?.his?.url_set ? <ActionButton type="button" variant="outline" size="sm" state={test.state} loadingText="Testing" doneText="Tested" onClick={() => void test.run()} icon={<PlugZap className="size-4" aria-hidden />}>Test now</ActionButton> : null}
                <Button type="button" variant="ghost" size="sm" asChild><Link to="/hospital/system">{d?.his?.url_set ? "Change" : "Connect"} <ChevronRight className="size-4" aria-hidden /></Link></Button>
              </div>
            </div>
          )}
        </Card>

        <Card title="People by role" icon={Users} id="ho-people" action={<Button type="button" variant="ghost" size="sm" asChild><Link to="/hospital/people">All <ChevronRight className="size-4" aria-hidden /></Link></Button>}>
          {loading || !p ? <CardSkeleton lines={4} /> : (
            <div className="grid grid-cols-2 gap-2">
              {([["Doctors", p.doctors, "doctor"], ["Heads", p.heads, "head"], ["Residents", p.residents, "resident"], ["MDT Coordinators", p.coordinators, "coordinator"], ["Department admins", p.dept_admins, "dept_admin"], ["Hospital admins", p.hospital_admins, "hospital_admin"]] as const).map(([label, n, role]) => (
                <Link key={label} to={`/hospital/people?role=${role}`} className="rounded-md bg-muted/60 px-3 py-2 outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring">
                  <span className="block text-xs text-muted-foreground">{label}</span>
                  <span className="block text-lg font-semibold tabular-nums text-foreground">{n}</span>
                </Link>
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <Card title="Case Files by status" icon={FolderOpen} id="ho-cases">
          {loading ? <CardSkeleton lines={4} /> : (
            <ul className="grid grid-cols-1 gap-1.5">
              {CASE_STATUS.map(([k, label]) => {
                const n = d?.case_files?.by_status?.[k] ?? 0;
                const total = d?.case_files?.total || 1;
                return (
                  <li key={k} className="grid grid-cols-[1fr_auto] items-center gap-x-3 text-sm">
                    <span className="text-foreground">{label}</span>
                    <span className="tabular-nums text-foreground">{n}</span>
                    <span className="col-span-2 mt-0.5 h-1 overflow-hidden rounded-full bg-muted" aria-hidden><span className="block h-full rounded-full bg-primary/70" style={{ width: `${Math.round((n / total) * 100)}%` }} /></span>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        <Card title="Recent activity" icon={Activity} id="ho-recent" className="lg:col-span-2" action={<Button type="button" variant="ghost" size="sm" asChild><Link to="/hospital/activity">All <ChevronRight className="size-4" aria-hidden /></Link></Button>}>
          {loading ? <CardSkeleton lines={4} /> : (d?.recent ?? []).length ? (
            <ul className="grid grid-cols-1 gap-0.5">
              {(d?.recent ?? []).slice(0, 8).map((e, i) => (
                <li key={`${e.ts}-${i}`} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 rounded-md px-2 py-1.5 text-sm hover:bg-accent/50">
                  <span className="min-w-0 flex-1 text-foreground">{e.text}</span>
                  <span className="text-xs text-muted-foreground">{e.by_name || e.by ? `${e.by_name || e.by}, ` : ""}<DateText value={e.ts} mode="ago" /></span>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-muted-foreground">Nothing yet.</p>}
          {d?.meetings?.upcoming?.length ? (
            <div className="mt-3 border-t border-border pt-3">
              <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Next meetings</p>
              <ul className="grid grid-cols-1 gap-1 text-sm">
                {d.meetings.upcoming.slice(0, 3).map((m) => <li key={m.id} className="flex flex-wrap justify-between gap-2"><span className="text-foreground">{m.title}</span><span className="text-xs text-muted-foreground"><DateText value={m.date} mode="words" /></span></li>)}
              </ul>
            </div>
          ) : null}
        </Card>
      </div>
    </div>
  );
}
