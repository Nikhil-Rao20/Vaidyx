// Step 1: find the patient in the hospital system (GET /his/lookup). Shows the registration, its encounters, how many
// reports fall in the window, similar registrations ("link, never merge") and the patient's live Case Files (GET /patient-case-files, night-v3 item 1.1):
// "Open it" or "Ask to join" for each; another cancer gets its own Case File, linked to these.
// One box, two ways (docs/new-case N1): a number and Look up as before, or a name / words with a drop-down (PatientFinder) whose
// pick runs the same lookup. "Not in the hospital system? Make it by hand" (N5) is always there, small, and the main next step
// when the lookup finds nothing or the hospital system does not answer.
// The latest pick wins: a pick (or Look up) while a lookup runs stops that lookup and drops its answer, so the box and the
// registration shown are always the same patient. The Vaidyx admin does not search patients (admin consoles D5): a plain note instead.
import { useEffect, useRef, useState } from "react";
import { motion } from "motion/react";
import { AlertTriangle, CheckCircle2, Link2, PenLine, Search, ShieldAlert, UserSearch } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/Field";
import { ActionButton } from "@/components/ActionButton";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";
import { KeyValue, KeyValueList } from "@/components/KeyValue";
import { DateText } from "@/components/DateText";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { api } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import { isVaidyxAdmin, useSession } from "@/lib/session";
import type { HisLookup, HisPatient } from "@/lib/types";
import { ageSex, formatDate, plural } from "@/lib/format";

/** The server's words (GET /his/find and /his/lookup answer 403 with them): shown before anything is sent. */
export const NO_ADMIN_SEARCH = "The Vaidyx admin does not search patients; open a Case File through break-glass.";

const MATCH_WORDS: Record<string, string> = { uhid: "UHID", mrn: "UHID", ip: "IP No.", ip_no: "IP No.", op: "OP No.", op_no: "OP No.", abha: "ABHA", abha_address: "ABHA address", name: "Name, age and sex", demographics: "Name, age and sex", pmjay: "PM-JAY id", pmjay_id: "PM-JAY id" };

/** "UHID VXH/26/004219" from {kind, value}; a plain string as it is. */
function matchedOn(m: HisPatient["matched_on"]): string {
  if (!m) return "";
  if (typeof m === "string") return MATCH_WORDS[m.toLowerCase()] ?? m;
  const kind = m.kind ? MATCH_WORDS[m.kind.toLowerCase()] ?? m.kind.replace(/_/g, " ") : "";
  return [kind, m.value].filter(Boolean).join(" ");
}
import type { NewCaseForm } from "@/features/newcase/form";
import { PatientCaseFilesCard, patientKey, usePatientCaseFiles } from "@/features/newcase/PatientCaseFiles";
import { PatientFinder } from "@/features/newcase/PatientFinder";

/** "Make it by hand": small under the box always; a full button as the next step when nothing is found or the system is down. */
function ManualLink({ onManual, main }: { onManual?: () => void; main?: boolean }) {
  if (!onManual) return null;
  return main ? (
    <Button type="button" variant="outline" onClick={onManual} data-testid="make-by-hand"><PenLine className="size-4" aria-hidden /> Make it by hand</Button>
  ) : (
    <button type="button" onClick={onManual} className="w-fit text-xs font-medium text-primary underline-offset-4 hover:underline">Not in the hospital system? Make it by hand</button>
  );
}

export function StepPatient({ form, onChange, autoLookup, onManual }: { form: NewCaseForm; onChange: (patch: Partial<NewCaseForm>) => void; autoLookup?: boolean; onManual?: () => void }) {
  const [text, setText] = useState(form.identifier);
  const [error, setError] = useState<unknown>(null);
  const { me } = useSession();
  const vaidyxAdmin = isVaidyxAdmin(me);
  const latest = useRef("");  // the identifier the person asked for last: an answer for any other is dropped
  const pending = useRef<string | null>(null);  // asked for while a lookup ran: runs as soon as that one ends
  const running = useRef<AbortController | null>(null);
  const lookup = useAsyncAction(async (identifier: string): Promise<HisLookup | null> => {
    setError(null);
    const ctl = new AbortController();
    running.current = ctl;
    const stale = () => ctl.signal.aborted || latest.current !== identifier;
    try {
      const r = await api.get<HisLookup>(`${EP.hisLookup}?identifier=${encodeURIComponent(identifier)}&months=${form.windowMonths === "all" ? 12 : form.windowMonths}`, { signal: ctl.signal });
      if (stale()) return null;
      onChange({ identifier, lookup: r });
      return r;
    } catch (e) {
      if (stale()) return null;
      onChange({ identifier, lookup: null });
      setError(e);
      throw e;
    }
  });
  /** Look up `identifier`; while another lookup runs, stop it and run this one next (the latest pick wins). */
  const start = (identifier: string) => {
    latest.current = identifier;
    if (lookup.state === "loading") {
      pending.current = identifier;
      running.current?.abort();
      return;
    }
    pending.current = null;
    void lookup.run(identifier);
  };
  useEffect(() => {
    if (lookup.state === "loading" || !pending.current) return;
    const next = pending.current;
    pending.current = null;
    void lookup.run(next);
  }, [lookup.state]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (autoLookup && form.identifier && !form.lookup && !vaidyxAdmin) start(form.identifier); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const files = usePatientCaseFiles(patientKey(form));
  const p = form.lookup?.patient;

  return (
    <div className="grid gap-5">
      <div className="grid gap-2">
        <form className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-start" onSubmit={(e) => { e.preventDefault(); if (text.trim() && !vaidyxAdmin) start(text.trim()); }}>
          <Field id="identifier" label="UHID, IP No., OP No. or ABHA, or the patient's name" hint="A number as printed on the hospital record, then Look up. Or type the name or words from a report and pick the patient from the list.">
            <PatientFinder value={text} onValueChange={setText} placeholder="e.g. VXH/2026/000123 or Lakshmi" onManual={onManual}
                           off={vaidyxAdmin ? NO_ADMIN_SEARCH : undefined} onPick={(row) => { setText(row.uhid); start(row.uhid); }} />
          </Field>
          <ActionButton type="submit" className="sm:mt-7" state={lookup.state} doneText="Found" loadingText="Looking up" disabled={!text.trim() || vaidyxAdmin} icon={<Search className="size-4" aria-hidden />}>Look up</ActionButton>
        </form>
        <ManualLink onManual={onManual} />
      </div>

      {vaidyxAdmin ? (
        <div className="flex items-center gap-3 rounded-md status-warn p-4 text-sm" role="status" data-testid="no-admin-search">
          <ShieldAlert className="size-5 shrink-0" aria-hidden /> {NO_ADMIN_SEARCH}
        </div>
      ) : lookup.state === "loading" ? (
        <div className="surface-inner space-y-2 p-4" aria-busy="true" aria-label="Looking up the patient">
          <div className="skeleton-line h-5 w-1/2" /><div className="skeleton-line h-4 w-2/3" /><div className="skeleton-line h-4 w-1/3" />
        </div>
      ) : error ? (
        <div className="grid gap-3">
          <ErrorState compact error={error} what="the hospital system lookup" onRetry={() => start(text.trim() || form.identifier)} />
          {onManual ? <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground"><span>The hospital system cannot be reached now?</span><ManualLink onManual={onManual} main /></div> : null}
        </div>
      ) : form.lookup && !form.lookup.found ? (
        <EmptyState compact kind="search" title={`Nothing found for ${form.lookup.identifier}`} text="Check the number with the registration desk. A temporary registration may carry a different number. Not in the hospital system? Make the Case File by hand."
                    action={onManual ? <ManualLink onManual={onManual} main /> : undefined} />
      ) : form.lookup && p ? (
        <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="grid gap-4">
          <section className="surface-inner p-4" aria-label="Registration found">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <p className="flex items-center gap-2 text-sm font-bold"><CheckCircle2 className="size-4 text-ok" aria-hidden /> Registration found{form.lookup.his ? <span className="font-normal text-muted-foreground">in {form.lookup.his}</span> : null}</p>
              {p.registration_kind && p.registration_kind !== "permanent" ? <span className="rounded-md status-warn px-2 py-0.5 text-xs font-medium">{p.registration_kind} registration</span> : null}
            </div>
            <KeyValueList columns={2}>
              <KeyValue label="Name" value={p.name} />
              <KeyValue label="Age / sex" value={ageSex(p.age, p.sex)} />
              <KeyValue label="UHID" value={p.uhid} mono />
              <KeyValue label="Date of birth" value={formatDate(p.dob)} />
              <KeyValue label="ABHA" value={p.abha || p.abha_address} mono />
              <KeyValue label="PM-JAY id" value={p.pmjay_id} mono />
              <KeyValue label="Registered" value={formatDate(p.registered_on)} />
              <KeyValue label="Matched on" value={matchedOn(p.matched_on)} />
            </KeyValueList>
            <p className="mt-3 text-sm text-body">
              <span className="font-medium">{plural(form.lookup.reports ?? 0, "report")}</span> {form.lookup.window?.all ? "on record" : `in the last ${form.lookup.window?.months ?? (form.windowMonths === "all" ? 12 : form.windowMonths)} months`}
              {form.lookup.older ? <span className="text-muted-foreground">, {form.lookup.older} older (can be fetched later)</span> : null}.
            </p>
          </section>

          {form.lookup.encounters?.length ? (
            <section className="surface-inner p-4" aria-label="Visits and admissions">
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">Visits and admissions</p>
              <ul className="divide-y divide-border text-sm">
                {form.lookup.encounters.slice(0, 8).map((e, i) => (
                  <li key={`${e.number}-${i}`} className="flex flex-wrap items-center gap-x-3 gap-y-0.5 py-1.5">
                    <span className="mono font-medium">{/^(IP|OP)\b/i.test(e.number || "") ? e.number : `${/ip|inpatient|imp/i.test(e.kind || "") ? "IP" : "OP"} ${e.number ?? ""}`}</span>
                    <span className="text-muted-foreground">{e.department}{e.unit ? `, ${e.unit}` : ""}</span>
                    <span className="ml-auto text-xs text-muted-foreground"><DateText value={e.start} />{e.end ? <> to <DateText value={e.end} /></> : e.status ? ` (${e.status})` : ""}</span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {form.lookup.similar?.length ? (
            <section className="rounded-md status-warn p-4" aria-label="Similar registrations">
              <p className="flex items-center gap-2 text-sm font-bold"><AlertTriangle className="size-4" aria-hidden /> {form.lookup.similar.length} similar registration{form.lookup.similar.length > 1 ? "s" : ""}</p>
              <p className="mt-1 text-xs">Possibly the same person under another number. Records stay separate; after creation you can link a registration to this Case File (never merged).</p>
              <ul className="mt-2 grid gap-1 text-sm">
                {form.lookup.similar.map((s, i) => (
                  <li key={`${s.uhid}-${i}`} className="flex flex-wrap items-center gap-2"><Link2 className="size-3.5" aria-hidden /> <span className="font-medium">{s.name}</span> <span>{ageSex(s.age, s.sex)}</span> <span className="mono">{s.uhid}</span> {s.registration_kind ? <span className="text-xs">({s.registration_kind})</span> : null}</li>
                ))}
              </ul>
            </section>
          ) : null}

          {files.data?.cases.length ? <PatientCaseFilesCard files={files.data.cases} /> : files.error ? (
            <ErrorState compact error={files.error} what="this patient's Case Files" onRetry={() => void files.refetch()} retrying={files.isFetching} />
          ) : null}
        </motion.div>
      ) : (
        <div className="flex items-center gap-3 rounded-md bg-muted p-4 text-sm text-muted-foreground">
          <UserSearch className="size-5 shrink-0" aria-hidden /> Type the number and press Look up, or type the name and pick the patient from the list. Nothing is created until the last step.
        </div>
      )}
    </div>
  );
}
