// Overview (B2): where the doctor lands. Warnings at the top, each a plain sentence with its fix; then To do and Waiting (at most five rows
// each, every row with its one action); the question for the board; the patient at a glance in four groups, every value opening its
// report line. No line about how Vaidyx works (owner: no line). "Other Case Files of this patient" (night-v3 item 1.1): the patient's
// other live Case Files (another cancer each), with the owning department and consultant, read-only links where this person may open them.
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, FolderOpen, Hourglass, ListTodo, MessageSquareQuote, OctagonAlert, Phone } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import { drName } from "@/lib/format";
import type { PatientCaseFilesResponse } from "@/lib/types";
import { cn } from "@/lib/utils";
import type { SourceTarget } from "../components/SourceViewer";
import { LoadingButton, fmtDate } from "../components/common";
import type { SectionId, StepAction, Steps, TodoItem, Warning, WaitingItem } from "./types";
import { ValueCell } from "./Value";

export interface OverviewHandlers {
  go: (section: SectionId, target?: string) => void;
  act: (item: TodoItem) => Promise<void> | void;
  fix: (w: Warning, fix: Warning["fixes"][number]) => Promise<void> | void;
  remind: (w: WaitingItem) => Promise<void> | void;
  openSource: (t: SourceTarget) => void;
  busy: (key: string) => boolean;
  /** An in-place note under a row (the Undo bar of a request being sent). */
  rowExtra?: (key: string) => ReactNode;
}

export function Card({ title, icon, count, children, testId, tone }: { title: string; icon?: ReactNode; count?: number; children: ReactNode; testId?: string; tone?: "warn" | "bad" }) {
  return (
    <section className={cn("surface overflow-hidden", tone === "bad" && "border-bad/40", tone === "warn" && "border-warn/40")} data-testid={testId}>
      <header className="flex items-center gap-2 border-b border-border px-4 py-2.5">
        {icon}
        <h2 className="text-[15px]">{title}{typeof count === "number" ? <span className="ml-1.5 text-muted-foreground font-normal">({count})</span> : null}</h2>
      </header>
      <div className="px-4 py-2">{children}</div>
    </section>
  );
}

function WarningBox({ w, h }: { w: Warning; h: OverviewHandlers }) {
  const Icon = w.severity === "bad" ? OctagonAlert : AlertTriangle;
  return (
    <div role="alert" data-testid="warning" data-kind={w.kind}
      className={cn("flex flex-col gap-2 rounded-lg border px-4 py-3 sm:flex-row sm:items-center", w.severity === "bad" ? "border-bad/40 bg-bad-soft" : "border-warn/40 bg-warn-soft")}>
      <Icon className={cn("size-5 shrink-0", w.severity === "bad" ? "text-bad" : "text-warn")} aria-hidden />
      <p className="min-w-0 flex-1 text-sm text-foreground">{w.text}</p>
      <div className="flex shrink-0 flex-wrap gap-1.5">
        {w.fixes.map((f, i) => (
          <LoadingButton key={f.kind} size="sm" variant={i === 0 ? "default" : "outline"} loading={h.busy(`${w.id}:${f.kind}`)} onClick={() => void h.fix(w, f)}>{f.label}</LoadingButton>
        ))}
      </div>
    </div>
  );
}

function ActionButton({ a, onClick, busy }: { a: StepAction; onClick: () => void; busy: boolean }) {
  const primary = a.kind === "ask_department" || a.kind === "go" || a.kind === "check" || a.kind === "signoffs";
  return <LoadingButton size="sm" variant={primary ? "default" : "outline"} loading={busy} onClick={onClick} className="shrink-0">{a.label}</LoadingButton>;
}

function TodoList({ items, h }: { items: TodoItem[]; h: OverviewHandlers }) {
  const [all, setAll] = useState(false);
  const shown = all ? items : items.slice(0, 5);
  return (
    <>
      <ol className="divide-y divide-border">
        {shown.map((t, i) => (
          <li key={t.id} className="py-2.5" data-testid="todo-row">
            <div className="flex gap-3">
              <span className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full bg-secondary text-xs font-bold text-secondary-foreground">{i + 1}</span>
              <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1.5">
                <div className="min-w-[12rem] flex-1">
                  <p className="text-sm font-medium text-foreground">{t.label}</p>
                  {t.why ? <p className="text-xs text-muted-foreground">{t.why}</p> : null}
                </div>
                <ActionButton a={t.action} busy={h.busy(t.id)} onClick={() => void h.act(t)} />
              </div>
            </div>
            {h.rowExtra?.(t.id)}
          </li>
        ))}
      </ol>
      {items.length > 5 ? <button type="button" className="mt-1 text-sm text-link hover:underline" onClick={() => setAll((x) => !x)}>{all ? "Show fewer" : `See all ${items.length}`}</button> : null}
    </>
  );
}

function WaitingList({ items, h }: { items: WaitingItem[]; h: OverviewHandlers }) {
  const [all, setAll] = useState(false);
  const shown = all ? items : items.slice(0, 5);
  return (
    <>
      <ul className="divide-y divide-border">
        {shown.map((w) => {
          const overdue = !!w.request?.overdue;
          return (
            <li key={w.id} className="flex flex-wrap items-center gap-3 py-2.5" data-testid="waiting-row">
              <Hourglass className={cn("size-4 shrink-0", overdue ? "text-bad" : "text-warn")} aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-foreground">{w.label}</p>
                <p className={cn("text-xs", overdue ? "font-medium text-bad" : "text-muted-foreground")}>
                  {overdue ? "Overdue. " : ""}Request sent to {w.department?.label ?? "the department"}{w.request?.sent_at ? `, ${fmtDate(w.request.sent_at)}` : ""}{w.request?.due ? ` · reply due ${fmtDate(w.request.due)}` : ""}
                  {w.request?.reminders ? ` · ${w.request.reminders} reminder${w.request.reminders === 1 ? "" : "s"} sent` : ""}
                </p>
              </div>
              {overdue && w.department?.phone ? <Button asChild size="sm" variant="outline"><a href={`tel:${w.department.phone}`}><Phone className="size-4" />Call the department</a></Button> : null}
              {w.action.action_id ? <LoadingButton size="sm" variant="outline" loading={h.busy(w.id)} onClick={() => void h.remind(w)}>Send reminder</LoadingButton> : null}
              {h.rowExtra?.(w.id)}
            </li>
          );
        })}
      </ul>
      {items.length > 5 ? <button type="button" className="mt-1 text-sm text-link hover:underline" onClick={() => setAll((x) => !x)}>{all ? "Show fewer" : `See all ${items.length}`}</button> : null}
    </>
  );
}

/** The patient's other live Case Files (GET /patient-case-files?case_id=): nothing is shown when there are none or the server says no. */
function OtherCaseFiles({ caseId }: { caseId: string }) {
  const q = useQuery<PatientCaseFilesResponse, Error>({
    queryKey: ["patient-case-files", "case", caseId],
    queryFn: () => api.get<PatientCaseFilesResponse>(`${EP.patientCaseFiles}?case_id=${encodeURIComponent(caseId)}`),
    enabled: Boolean(caseId),
    staleTime: 5 * 60_000,
    retry: false,
  });
  const rows = q.data?.cases ?? [];
  if (!rows.length) return null;
  return (
    <section className="surface px-4 py-2.5" aria-labelledby="h-other-files" data-testid="other-case-files">
      <h2 id="h-other-files" className="text-sm font-semibold text-foreground">Other Case Files of this patient</h2>
      <ul className="mt-1 divide-y divide-border">
        {rows.map((f) => {
          const who = f.owner_words || [f.department_name, drName(f.owner_name)].filter(Boolean).join(", ");
          return (
            <li key={f.case_id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-1.5 text-sm">
              <span className="min-w-0 flex-1"><span className="font-medium text-foreground">{f.cancer_label}</span>{who ? <span className="text-muted-foreground">, {who}</span> : null}</span>
              {f.can_open ? (
                <Button asChild size="sm" variant="outline"><Link to={`/cases/${encodeURIComponent(f.case_id)}`}><FolderOpen className="size-4" aria-hidden />Open it</Link></Button>
              ) : <span className="text-xs text-muted-foreground">you cannot open it</span>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function Overview({ steps, h, signoffs, staging }: { steps: Steps; h: OverviewHandlers; signoffs?: ReactNode; staging?: ReactNode }) {
  const prepare = steps.mode === "prepare";
  const q = steps.question;
  return (
    <div className="space-y-4" data-testid="section-overview">
      {steps.warnings.length ? <div className="space-y-2">{steps.warnings.map((w) => <WarningBox key={w.id} w={w} h={h} />)}</div> : null}
      {signoffs}

      {prepare ? (
        <div className="grid items-start gap-4 xl:grid-cols-2">
          <Card title="To do" count={steps.todo.length} icon={<ListTodo className="size-4 text-brand" aria-hidden />} testId="todo">
            {steps.todo.length ? <TodoList items={steps.todo} h={h} /> : <p className="py-2 text-sm text-muted-foreground">Nothing to do right now.</p>}
          </Card>
          <Card title="Waiting" count={steps.waiting.length} icon={<Hourglass className="size-4 text-warn" aria-hidden />} testId="waiting">
            {steps.waiting.length ? <WaitingList items={steps.waiting} h={h} /> : <p className="py-2 text-sm text-muted-foreground">No request is waiting on another department.</p>}
          </Card>
        </div>
      ) : null}

      <Card title="Question for the board" icon={<MessageSquareQuote className="size-4 text-brand" aria-hidden />} testId="overview-question">
        {q.text ? (
          <div className="py-1">
            <p className="text-[1.05rem] text-foreground">{q.text}</p>
            <p className="mt-1 text-xs text-muted-foreground">{[q.reason?.label, q.by ? `written by ${q.by}` : "", q.at ? fmtDate(q.at) : ""].filter(Boolean).join(" · ")}</p>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-3 py-1">
            <p className="flex-1 text-sm text-muted-foreground">Not written yet. The treating doctor writes what the board should decide.</p>
            {prepare ? <Button size="sm" onClick={() => h.go("question")}>Write the question<ArrowRight className="size-4" /></Button> : null}
          </div>
        )}
      </Card>

      <OtherCaseFiles caseId={steps.case_id} />

      {staging}

      <section aria-labelledby="h-glance" data-testid="glance">
        <h2 id="h-glance" className="mb-2 text-[15px]">The patient at a glance</h2>
        {steps.glance.length ? (
          <div className="grid gap-4 lg:grid-cols-2">
            {steps.glance.map((g) => (
              <div key={g.id} className="surface px-4 py-2" data-testid={`glance-${g.id}`}>
                <h3 className="py-1.5 text-sm font-semibold text-foreground">{g.label}</h3>
                <dl className="divide-y divide-border">
                  {g.rows.map((r) => (
                    <div key={r.slot_id} className="grid gap-x-3 gap-y-0.5 py-2 sm:grid-cols-[minmax(8rem,11rem)_1fr]">
                      <dt className="text-sm text-muted-foreground">{r.label}</dt>
                      <dd className="min-w-0 text-sm"><ValueCell row={r} onOpen={h.openSource} onCheck={prepare ? () => h.go("check", r.slot_id) : undefined} /></dd>
                    </div>
                  ))}
                </dl>
              </div>
            ))}
          </div>
        ) : <p className="text-sm text-muted-foreground">No cancer is chosen yet, so nothing is looked for.</p>}
      </section>
    </div>
  );
}
