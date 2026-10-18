// Step 1: find the patient in the hospital system (GET /his/lookup). Shows the registration, its encounters, how many
// reports fall in the window, similar registrations ("link, never merge") and any existing Case File for the same UHID.
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "motion/react";
import { AlertTriangle, CheckCircle2, Link2, Search, UserSearch } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/Field";
import { ActionButton } from "@/components/ActionButton";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";
import { KeyValue, KeyValueList } from "@/components/KeyValue";
import { DateText } from "@/components/DateText";
import { StatusPill } from "@/components/StatusPill";
import { JoinDialog } from "@/components/JoinDialog";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { useCaseList } from "@/hooks/useQueries";
import { api } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import type { HisLookup, HisPatient } from "@/lib/types";
import { ageSex, formatDate, plural } from "@/lib/format";

const MATCH_WORDS: Record<string, string> = { uhid: "UHID", mrn: "UHID", ip: "IP No.", ip_no: "IP No.", op: "OP No.", op_no: "OP No.", abha: "ABHA", abha_address: "ABHA address", name: "Name, age and sex", demographics: "Name, age and sex", pmjay: "PM-JAY id", pmjay_id: "PM-JAY id" };

/** "UHID VXH/26/004219" from {kind, value}; a plain string as it is. */
function matchedOn(m: HisPatient["matched_on"]): string {
  if (!m) return "";
  if (typeof m === "string") return MATCH_WORDS[m.toLowerCase()] ?? m;
  const kind = m.kind ? MATCH_WORDS[m.kind.toLowerCase()] ?? m.kind.replace(/_/g, " ") : "";
  return [kind, m.value].filter(Boolean).join(" ");
}
import type { NewCaseForm } from "@/features/newcase/form";

export function StepPatient({ form, onChange, autoLookup }: { form: NewCaseForm; onChange: (patch: Partial<NewCaseForm>) => void; autoLookup?: boolean }) {
  const [text, setText] = useState(form.identifier);
  const [error, setError] = useState<unknown>(null);
  const [joinOpen, setJoinOpen] = useState(false);
  const lookup = useAsyncAction(async (identifier: string): Promise<HisLookup> => {
    setError(null);
    try {
      const r = await api.get<HisLookup>(`${EP.hisLookup}?identifier=${encodeURIComponent(identifier)}&months=${form.windowMonths === "all" ? 12 : form.windowMonths}`);
      onChange({ identifier, lookup: r });
      return r;
    } catch (e) {
      onChange({ identifier, lookup: null });
      setError(e);
      throw e;
    }
  });
  useEffect(() => { if (autoLookup && form.identifier && !form.lookup) void lookup.run(form.identifier); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const uhid = form.lookup?.patient?.uhid;
  const existing = useCaseList({}, { enabled: Boolean(uhid) });
  const sameUhid = useMemo(() => (uhid ? (existing.data?.cases ?? []).filter((c) => c.patient?.uhid === uhid) : []), [existing.data, uhid]);
  const p = form.lookup?.patient;

  return (
    <div className="grid gap-5">
      <form className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-start" onSubmit={(e) => { e.preventDefault(); if (text.trim()) void lookup.run(text.trim()); }}>
        <Field id="identifier" label="UHID, IP No., OP No. or ABHA" hint="As printed on the hospital record. A name with age and sex also works when the hospital system allows it.">
          <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. VXH/2026/000123" className="mono" autoFocus autoComplete="off" />
        </Field>
        <ActionButton type="submit" className="sm:mt-7" state={lookup.state} doneText="Found" loadingText="Looking up" disabled={!text.trim()} icon={<Search className="size-4" aria-hidden />}>Look up</ActionButton>
      </form>

      {lookup.state === "loading" ? (
        <div className="surface-inner space-y-2 p-4" aria-busy="true" aria-label="Looking up the patient">
          <div className="skeleton-line h-5 w-1/2" /><div className="skeleton-line h-4 w-2/3" /><div className="skeleton-line h-4 w-1/3" />
        </div>
      ) : error ? (
        <ErrorState compact error={error} what="the hospital system lookup" onRetry={() => void lookup.run(text.trim() || form.identifier)} />
      ) : form.lookup && !form.lookup.found ? (
        <EmptyState compact kind="search" title={`Nothing found for ${form.lookup.identifier}`} text="Check the number with the registration desk. A temporary registration may carry a different number." />
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

          {sameUhid.length ? (
            <section className="rounded-md status-review p-4" aria-label="Existing Case Files">
              <p className="text-sm font-bold">This patient already has {sameUhid.length === 1 ? "a Case File" : `${sameUhid.length} Case Files`}</p>
              <ul className="mt-2 grid gap-2">
                {sameUhid.map((c) => (
                  <li key={c.case_id} className="flex flex-wrap items-center gap-2 rounded-md bg-card/70 p-2 text-sm">
                    <span className="font-medium">{c.protocol_label || c.cancer_name || "Cancer not set"}</span>
                    <StatusPill status={c.status} />
                    <span className="text-xs text-muted-foreground">from {c.owner?.doctor_name || c.owner?.department_label}</span>
                    <span className="ml-auto flex gap-1">
                      <Button type="button" size="sm" variant="outline" asChild><Link to={`/cases/${encodeURIComponent(c.case_id)}`}>Open it</Link></Button>
                      {c.mine ? <span className="self-center px-2 text-xs text-muted-foreground">yours</span> : <Button type="button" size="sm" variant="ghost" onClick={() => setJoinOpen(true)}>Join</Button>}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs">For the same cancer, join the existing one instead of starting a second. A new cancer gets its own Case File.</p>
            </section>
          ) : null}
        </motion.div>
      ) : (
        <div className="flex items-center gap-3 rounded-md bg-muted p-4 text-sm text-muted-foreground">
          <UserSearch className="size-5 shrink-0" aria-hidden /> Type the number and press Look up. Nothing is created until the last step.
        </div>
      )}
      <JoinDialog kind="case" open={joinOpen} onOpenChange={setJoinOpen} />
    </div>
  );
}
