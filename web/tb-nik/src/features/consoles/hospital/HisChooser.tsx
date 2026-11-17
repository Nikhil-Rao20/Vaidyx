// "Choose your hospital system" (docs/new-case/DESIGN.md N7): pick the hospital's system from the presets (GET /his/kinds) with
// their honest labels, or a connection method when it is not listed; fill only the fields that method needs; test WITHOUT saving
// (POST /his/try: the connection, the counts, one UHID as counts only: found, visits, reports, newest report date, never a name or
// any other patient detail, since neither admin has clinical access); "Use this system" is turned on only by a passing test of exactly the values
// on screen (any edit turns it off again) and saves through POST /setup/his with the test's fingerprint, so the server refuses a save
// that differs from what passed. Secrets are never shown: a saved one reads "Saved, leave empty to keep". The hospital admin and a
// Vaidyx admin working inside a hospital (X-TB-Hospital, lib/acting.ts) use the same screen.
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, ChevronRight, FileStack, FolderInput, HelpCircle, PlugZap, Search as SearchIcon, Server, ShieldCheck, TriangleAlert, XCircle } from "lucide-react";
import { motion } from "motion/react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ActionButton } from "@/components/ActionButton";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { Field } from "@/components/Field";
import { SearchBox } from "@/components/SearchBox";
import { Pill } from "@/components/StatusPill";
import { notify } from "@/components/Toasts";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { api } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import type { HisKind, HisKindField, HisKinds, HisPreset, HisTestResult, HisTry, SetupResponse } from "@/lib/types";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

export const hisKindsKey = ["his", "kinds"] as const;

/** GET /his/kinds: the connection methods, the presets and what is saved now (for those who may save the connection). */
export function useHisKinds(enabled = true) {
  return useQuery<HisKinds, Error>({ queryKey: hisKindsKey, queryFn: () => api.get<HisKinds>(EP.hisKinds), enabled, retry: false, staleTime: 30_000 });
}

/** The connection methods a hospital can choose when its system is not in the list (mcp and none are not offered here). */
export const METHODS = ["fhir_generic", "hl7v2_folder", "folder_bridge", "abdm_bundles"] as const;

const GROUPS: Array<{ id: string; title: string; text: string; kinds: string[]; icon: typeof Server }> = [
  { id: "live", title: "A live FHIR server", text: "Vaidyx-TB asks the hospital system for a patient's records when a doctor looks one up.", kinds: ["fhir", "fhir_generic"], icon: Server },
  { id: "hl7", title: "HL7 v2 result files", text: "The lab, radiology or hospital system drops result messages into a folder on this server.", kinds: ["hl7v2_folder"], icon: FileStack },
  { id: "folder", title: "A report folder", text: "No API: report files in a folder with an index file that lists them.", kinds: ["folder_bridge"], icon: FolderInput },
  { id: "abdm", title: "ABDM record bundles", text: "Health-record bundles the hospital hands over as files.", kinds: ["abdm_bundles"], icon: ShieldCheck },
];

/** The preset's honest label: tested with the demo hospital, no public API found, or by standard only. */
export function presetBadge(p: Pick<HisPreset, "status" | "interface">): { word: string; tone: "ok" | "warn" | "info" } {
  const s = (p.status || "").toLowerCase();
  if (s.startsWith("tested")) return { word: "Tested with the demo hospital", tone: "ok" };
  if ((p.interface || "").toLowerCase() === "no public api found") return { word: "No public API found", tone: "warn" };
  return { word: "By standard, not tested with this product", tone: "info" };
}

type Values = Record<string, string>;
interface Choice {
  kind: string;
  preset: HisPreset | null;
}

const SECRET_WORD: Record<string, string> = { token: "token", password: "password", api_key: "API key", client_secret: "client secret" };

function shown(f: HisKindField, values: Values): boolean {
  if (!f.when) return true;
  return Object.entries(f.when).every(([k, allowed]) => allowed.includes(values[k] || ""));
}

function asText(v: unknown): string {
  if (Array.isArray(v)) return v.map(String).join(", ");
  if (v === null || v === undefined || typeof v === "boolean") return "";
  return String(v);
}

/** The values a method starts with: the preset's defaults, then what is saved now when it is the same method (never a secret). */
function startValues(kind: HisKind, choice: Choice, data: HisKinds): Values {
  const out: Values = {};
  const defaults = choice.preset?.defaults ?? {};
  for (const f of kind.fields) {
    if (f.type === "secret") { out[f.name] = ""; continue; }
    out[f.name] = asText(defaults[f.name]);
    if (f.type === "select" && !out[f.name]) out[f.name] = f.options?.[0]?.value ?? "";
  }
  const cur = data.current;
  const same = cur.kind === choice.kind && cur.enabled !== false && (!choice.preset || !cur.preset || cur.preset === choice.preset.id);
  if (same && cur.settings) {
    const s = cur.settings;
    const a = s.adapter ?? {};
    const saved: Record<string, unknown> = { url: s.url, label: s.label, ...a };
    for (const f of kind.fields) {
      if (f.type === "secret") continue;
      const v = asText(saved[f.name]);
      if (v) out[f.name] = v;
    }
  }
  return out;
}

/** Whether a secret is saved for this method now (shown as "Saved, leave empty to keep"). */
function secretSaved(name: string, choice: Choice, data: HisKinds): boolean {
  const cur = data.current;
  if (cur.kind !== choice.kind || cur.enabled === false) return false;
  if (choice.kind === "fhir") return name === "token" && Boolean(cur.settings?.has_token);
  return cur.settings?.adapter?.secrets?.[name] === "set";
}

/** The body POST /his/try and POST /setup/his take: the preset (or the method) and the fields on screen. */
function bodyFor(choice: Choice, kind: HisKind, values: Values): Record<string, string> {
  const b: Record<string, string> = choice.preset ? { preset: choice.preset.id } : { kind: choice.kind };
  for (const f of kind.fields) {
    if (!shown(f, values)) continue;
    const v = (values[f.name] ?? "").trim();
    if (v || f.type !== "secret") b[f.name] = v;
  }
  return b;
}

// ---- the dialog ----------------------------------------------------------------------------------------------------------------

export function HisChooser({ open, onOpenChange, onSaved, caseFiles }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** After a save: the set-up answer (with the test of the saved connection). */
  onSaved?: (r: { ok: boolean; test: HisTestResult } & Partial<SetupResponse>) => void;
  /** How many Case Files this hospital has (they keep their link to the old system). */
  caseFiles?: number;
}) {
  const kinds = useHisKinds(open);
  const [choice, setChoice] = useState<Choice | null>(null);
  useEffect(() => { if (!open) setChoice(null); }, [open]);
  const kind = choice ? kinds.data?.kinds.find((k) => k.kind === choice.kind) ?? null : null;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92dvh] w-[calc(100vw-1rem)] max-w-[calc(100vw-1rem)] overflow-y-auto p-4 sm:max-w-3xl sm:p-6" aria-describedby="his-chooser-text" data-testid="his-chooser">
        <DialogHeader>
          <DialogTitle>Choose your hospital system</DialogTitle>
          <DialogDescription id="his-chooser-text">
            Vaidyx-TB only reads from the hospital system; nothing is written back. Nothing changes until you test the settings and press Use this system.
          </DialogDescription>
        </DialogHeader>
        <Steps at={choice ? 2 : 1} />
        {kinds.isLoading ? (
          <div className="space-y-2" aria-busy="true" aria-label="Loading the hospital systems">
            {Array.from({ length: 4 }).map((_, i) => <div key={i} className="skeleton-line h-14 rounded-md" />)}
          </div>
        ) : kinds.error || !kinds.data ? (
          <ErrorState error={kinds.error} what="the list of hospital systems" onRetry={() => void kinds.refetch()} retrying={kinds.isFetching} compact />
        ) : choice && kind ? (
          <Details key={`${choice.kind}:${choice.preset?.id ?? ""}`} data={kinds.data} choice={choice} kind={kind} onBack={() => setChoice(null)} caseFiles={caseFiles}
            onSaved={(r) => { onSaved?.(r); void kinds.refetch(); onOpenChange(false); }} />
        ) : (
          <Pick data={kinds.data} onPick={setChoice} />
        )}
      </DialogContent>
    </Dialog>
  );
}

function Steps({ at }: { at: 1 | 2 }) {
  const steps = ["Pick", "Details", "Test", "Use"];
  return (
    <ol aria-label="Steps" className="flex flex-wrap items-center gap-x-1 gap-y-1 text-xs">
      {steps.map((s, i) => {
        const n = i + 1;
        const current = at === 1 ? n === 1 : n >= 2;
        return (
          <li key={s} className="flex items-center gap-1" aria-current={current && (at === 1 || n === 2) ? "step" : undefined}>
            <span className={cn("inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 font-medium", current ? "bg-primary text-primary-foreground" : n < at ? "bg-muted text-foreground" : "bg-muted text-muted-foreground")}>
              <span className="tabular-nums">{n}</span> {s}
            </span>
            {n < steps.length ? <ChevronRight className="size-3 text-muted-foreground" aria-hidden /> : null}
          </li>
        );
      })}
    </ol>
  );
}

// ---- step 1: pick --------------------------------------------------------------------------------------------------------------

function Pick({ data, onPick }: { data: HisKinds; onPick: (c: Choice) => void }) {
  const [q, setQ] = useState("");
  const [unlisted, setUnlisted] = useState(false);
  const words = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const match = (p: HisPreset) => words.every((w) => `${p.name} ${p.vendor ?? ""} ${p.notes ?? ""} ${p.sector ?? ""}`.toLowerCase().includes(w));
  const presets = data.presets.filter(match);
  // the preset in use: the one saved, or for a FHIR connection saved without one, the preset whose address it is (the demo hospital)
  const cur = data.current;
  const currentPreset = cur.enabled === false ? "" : cur.preset || (cur.kind === "fhir" ? data.presets.find((p) => p.kind === "fhir" && p.defaults?.url && p.defaults.url === cur.settings?.url)?.id ?? "" : "");
  if (unlisted) return <Methods data={data} onPick={onPick} onBack={() => setUnlisted(false)} />;
  return (
    <div className="grid gap-4">
      <SearchBox value={q} onChange={setQ} label="Find your hospital system" placeholder="Find by name or maker, for example Bahmni" />
      {presets.length === 0 ? (
        <EmptyState kind="search" compact title="No hospital system matches" text="Try another word, or choose how it connects below." />
      ) : GROUPS.map((g) => {
        const rows = presets.filter((p) => g.kinds.includes(p.kind));
        if (!rows.length) return null;
        const Icon = g.icon;
        return (
          <section key={g.id} aria-labelledby={`his-group-${g.id}`} className="grid gap-2">
            <div>
              <h3 id={`his-group-${g.id}`} className="flex items-center gap-2 text-sm"><Icon className="size-4 text-brand-text" aria-hidden />{g.title}</h3>
              <p className="text-xs text-muted-foreground">{g.text}</p>
            </div>
            <ul className="grid gap-2 sm:grid-cols-2">
              {rows.map((p) => {
                const badge = presetBadge(p);
                return (
                  <li key={p.id}>
                    <button type="button" onClick={() => onPick({ kind: p.kind, preset: p })} data-testid="his-preset" aria-labelledby={`his-pn-${p.id} his-pb-${p.id}`} aria-describedby={`his-p-${p.id}`}
                      className="row-lift flex h-full w-full flex-col items-start gap-1.5 rounded-md border border-border bg-card p-3 text-left outline-none transition-colors hover:border-border-strong focus-visible:ring-2 focus-visible:ring-ring">
                      <span className="flex w-full min-w-0 items-start justify-between gap-2">
                        <span id={`his-pn-${p.id}`} className="min-w-0 break-words text-sm font-semibold text-foreground">{p.name}</span>
                        {currentPreset && currentPreset === p.id ? <Pill tone="ok" className="shrink-0">In use</Pill> : null}
                      </span>
                      <span id={`his-pb-${p.id}`} className="max-w-full"><Pill tone={badge.tone} className="max-w-full" icon={badge.tone === "ok" ? CheckCircle2 : badge.tone === "warn" ? TriangleAlert : HelpCircle}>{badge.word}</Pill></span>
                      <span id={`his-p-${p.id}`} className="line-clamp-2 text-xs text-muted-foreground">{p.notes}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-dashed border-border-strong p-3">
        <p className="text-sm text-muted-foreground">Not in the list? Choose how your hospital system can share its reports.</p>
        <Button type="button" variant="outline" onClick={() => setUnlisted(true)}><SearchIcon className="size-4" aria-hidden />My system is not listed</Button>
      </div>
    </div>
  );
}

function Methods({ data, onPick, onBack }: { data: HisKinds; onPick: (c: Choice) => void; onBack: () => void }) {
  const methods = METHODS.map((m) => data.kinds.find((k) => k.kind === m)).filter(Boolean) as HisKind[];
  const first = useRef<HTMLButtonElement>(null);
  useEffect(() => { first.current?.focus(); }, []);
  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm">How can your hospital system share its reports?</h3>
        <Button type="button" variant="ghost" size="sm" onClick={onBack}><ArrowLeft className="size-4" aria-hidden />Back to the list</Button>
      </div>
      <ul className="grid gap-2">
        {methods.map((k, i) => (
          <li key={k.kind}>
            <button ref={i === 0 ? first : undefined} type="button" onClick={() => onPick({ kind: k.kind, preset: null })} data-testid="his-method"
              className="row-lift grid w-full gap-1 rounded-md border border-border bg-card p-3 text-left outline-none hover:border-border-strong focus-visible:ring-2 focus-visible:ring-ring">
              <span className="text-sm font-semibold text-foreground">{k.label}</span>
              <span className="text-xs text-foreground">{k.description}</span>
              {k.cannot.length ? <span className="text-xs text-muted-foreground">Cannot: {k.cannot.slice(0, 3).join("; ")}{k.cannot.length > 3 ? "; and more" : ""}.</span> : null}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---- steps 2 to 4: details, test, use ---------------------------------------------------------------------------------------------

function Details({ data, choice, kind, onBack, onSaved, caseFiles }: {
  data: HisKinds;
  choice: Choice;
  kind: HisKind;
  onBack: () => void;
  onSaved: (r: { ok: boolean; test: HisTestResult } & Partial<SetupResponse>) => void;
  caseFiles?: number;
}) {
  const [values, setValues] = useState<Values>(() => startValues(kind, choice, data));
  const [identifier, setIdentifier] = useState("");
  const [result, setResult] = useState<HisTry | null>(null);
  const [testedKey, setTestedKey] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const body = useMemo(() => bodyFor(choice, kind, values), [choice, kind, values]);
  const key = JSON.stringify(body);
  const fields = kind.fields.filter((f) => shown(f, values));
  const missing = fields.filter((f) => f.required && f.type !== "secret" && !(values[f.name] ?? "").trim()).map((f) => f.label);
  const missingSecret = fields.filter((f) => f.required && f.type === "secret" && !(values[f.name] ?? "").trim() && !secretSaved(f.name, choice, data)).map((f) => f.label);
  const blocked = [...missing, ...missingSecret];
  const fresh = result !== null && testedKey === key;
  const canUse = fresh && Boolean(result?.ok && result.fingerprint);
  const name = choice.preset?.name ?? kind.label;
  const label = (values.label ?? "").trim() || name;

  const test = useAsyncAction(async () => {
    const r = await api.post<HisTry>(EP.hisTry, { ...body, ...(identifier.trim() ? { identifier: identifier.trim() } : {}) });
    setResult(r);
    setTestedKey(key);
    return r;
  });
  const set = (n: string, v: string) => setValues((old) => ({ ...old, [n]: v }));
  const save = async () => {
    if (!result?.fingerprint) throw new Error("Test these settings first.");
    const r = await api.post<{ ok: boolean; test: HisTestResult } & Partial<SetupResponse>>(EP.setupHis, { ...body, tested_fingerprint: result.fingerprint });
    if (r.test?.ok) notify.success(`${label} is now the hospital system`, "Doctors look up patients in it from now on.");
    else notify.error(`${label} is saved, but its test after saving did not pass`, r.test?.error || "Check it on this page.");
    onSaved(r);
  };
  const badge = choice.preset ? presetBadge(choice.preset) : null;
  const roots = data.folder_roots;
  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-start justify-between gap-2 rounded-md bg-muted/60 p-3">
        <div className="min-w-0">
          <p className="break-words text-sm font-semibold text-foreground">{name}</p>
          <p className="text-xs text-muted-foreground">{kind.label}</p>
          {badge ? <Pill tone={badge.tone} className="mt-1.5" icon={badge.tone === "ok" ? CheckCircle2 : badge.tone === "warn" ? TriangleAlert : HelpCircle}>{badge.word}</Pill> : null}
        </div>
        <Button type="button" variant="ghost" size="sm" onClick={onBack}><ArrowLeft className="size-4" aria-hidden />Choose another</Button>
      </div>
      {choice.preset?.notes ? <p className="text-sm text-muted-foreground">{choice.preset.notes}</p> : null}
      {kind.cannot.length ? (
        <details className="rounded-md border border-border p-3 text-sm">
          <summary className="cursor-pointer font-medium text-foreground">What this connection cannot do ({kind.cannot.length})</summary>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-muted-foreground">{kind.cannot.map((c) => <li key={c}>{c[0].toUpperCase() + c.slice(1)}</li>)}</ul>
        </details>
      ) : null}

      <section aria-labelledby="his-details-h" className="grid gap-4">
        <h3 id="his-details-h" className="text-sm">2. Details</h3>
        <div className="grid gap-4 sm:grid-cols-2">
          {fields.map((f, i) => (
            <FieldFor key={f.name} f={f} value={values[f.name] ?? ""} onChange={(v) => set(f.name, v)} autoFocus={i === 0}
              saved={f.type === "secret" && secretSaved(f.name, choice, data)} roots={roots} remote={data.remote_allowed} />
          ))}
        </div>
      </section>

      <section aria-labelledby="his-test-h" className="grid gap-3">
        <h3 id="his-test-h" className="text-sm">3. Test</h3>
        <p className="text-xs text-muted-foreground">The test reads from the hospital system and saves nothing. It takes up to 15 seconds.</p>
        <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
          <Field id="his-try-uhid" label="Try one UHID" optional hint="A hospital number you know, to see that its visits and reports come back. Only counts are shown, no patient details.">
            <Input value={identifier} onChange={(e) => setIdentifier(e.target.value)} className="mono" autoComplete="off" spellCheck={false} />
          </Field>
          <ActionButton type="button" state={test.state} loadingText="Testing" doneText={test.state === "done" && result?.ok ? "It answers" : "Tested"} disabled={blocked.length > 0}
            onClick={() => void test.run()} icon={<PlugZap className="size-4" aria-hidden />}>Test these settings</ActionButton>
        </div>
        {blocked.length ? <p className="text-xs text-muted-foreground">Fill in first: {blocked.join(", ")}.</p> : null}
        {test.error ? <p role="alert" className="text-sm text-bad">{test.error}</p> : null}
        {result ? <TryResult r={result} stale={!fresh} /> : null}
      </section>

      <section aria-labelledby="his-use-h" className="grid gap-2 border-t border-border pt-4">
        <h3 id="his-use-h" className="text-sm">4. Use this system</h3>
        <div className="flex flex-wrap items-center gap-3">
          <Button type="button" disabled={!canUse} onClick={() => setConfirm(true)} aria-describedby="his-use-why"><CheckCircle2 className="size-4" aria-hidden />Use this system</Button>
          <p id="his-use-why" className="text-xs text-muted-foreground">
            {canUse ? "These exact settings passed the test." : result && !fresh ? "A value changed after the test. Test again to use it." : "Turned on after a passing test of these settings."}
          </p>
        </div>
      </section>

      <ConfirmDialog open={confirm} onOpenChange={setConfirm} title={`Use ${label}?`} confirmText="Use this system" doneText="Saved"
        text={<>Doctors will look up patients in this hospital system from now on. {caseFiles ? <>The {caseFiles} Case File{caseFiles === 1 ? "" : "s"} already made</> : <>Case Files already made</>} keep their link to the old system and its reports.</>}
        onConfirm={save} />
    </div>
  );
}

function FieldFor({ f, value, onChange, autoFocus, saved, roots, remote }: { f: HisKindField; value: string; onChange: (v: string) => void; autoFocus?: boolean; saved: boolean; roots: string[]; remote: boolean }) {
  const id = `his-f-${f.name}`;
  const required = f.required && !(f.type === "secret" && saved);
  let hint: ReactNode = f.help;
  if (f.type === "secret") hint = saved ? `Saved, leave empty to keep. A saved ${SECRET_WORD[f.name] ?? "secret"} is kept only while the address stays the same.` : f.help;
  if (f.type === "folder") hint = <>{f.help} {roots.length ? <>Allowed: {roots.map((r, i) => <span key={r}>{i ? ", " : ""}<span className="mono break-all">{r}</span></span>)}</> : null}</>;
  if (f.type === "url" && !remote) hint = <>{f.help} Only this server or a host the Vaidyx admin has allowed.</>;
  if (f.type === "select") {
    return (
      <Field id={id} label={f.label} required={f.required} hint={hint}>
        <Select value={value} onValueChange={onChange}>
          <SelectTrigger className="w-full" aria-label={f.label} autoFocus={autoFocus}><SelectValue /></SelectTrigger>
          <SelectContent>{(f.options ?? []).map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent>
        </Select>
      </Field>
    );
  }
  return (
    <Field id={id} label={f.label} required={required} optional={!required} hint={hint} className={f.type === "folder" || f.type === "url" ? "sm:col-span-2" : undefined}>
      <Input value={value} onChange={(e) => onChange(e.target.value)} autoFocus={autoFocus}
        type={f.type === "secret" ? "password" : "text"} inputMode={f.type === "url" ? "url" : undefined}
        autoComplete={f.type === "secret" ? "new-password" : "off"} placeholder={f.type === "secret" && saved ? "Saved" : f.type === "folder" && roots[0] ? `${roots[0]}/...` : undefined}
        className={f.type === "text" && f.name === "label" ? undefined : "mono"} spellCheck={false} />
    </Field>
  );
}

function TryResult({ r, stale }: { r: HisTry; stale: boolean }) {
  const s = r.sample;
  return (
    <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} role="status" data-testid="his-try-result"
      className={cn("grid gap-2 rounded-md p-4 text-sm", r.ok ? "status-ok" : "status-bad", stale && "opacity-70")}>
      <p className="flex items-center gap-2 font-bold">
        {r.ok ? <CheckCircle2 className="size-4" aria-hidden /> : <XCircle className="size-4" aria-hidden />}
        {r.ok ? "The hospital system answers" : "The test did not pass"}
      </p>
      {r.ok ? (
        <p>
          {r.ping?.name ? `${r.ping.name}. ` : ""}{r.ping?.fhir_version ? `FHIR ${r.ping.fhir_version}. ` : ""}
          {typeof r.counts?.patients === "number" ? `${r.counts.patients} patients` : ""}{typeof r.counts?.patients === "number" && typeof r.counts?.reports === "number" ? ", " : ""}
          {typeof r.counts?.reports === "number" ? `${r.counts.reports} reports. ` : r.counts ? ". " : ""}
          {typeof r.latency_ms === "number" ? `Answered in ${Math.round(r.latency_ms)} ms.` : ""}
        </p>
      ) : (
        <>
          <p>{r.error || "No answer."}</p>
          {r.hint ? <p className="font-medium">{r.hint}</p> : null}
        </>
      )}
      {r.ok && s ? (
        s.found ? (
          <p className="rounded-md bg-card/70 p-3 text-foreground" data-testid="his-try-sample">
            Found: {s.visits ?? 0} visit{s.visits === 1 ? "" : "s"}, {s.reports ?? 0} report{s.reports === 1 ? "" : "s"}{s.newest_report_date ? `, newest ${formatDate(s.newest_report_date, s.newest_report_date)}` : ""}.
          </p>
        ) : (
          <p className="rounded-md bg-card/70 p-3 text-foreground">{s.error || <>No patient with <span className="mono">{s.identifier}</span> in this hospital system. Check the number; the connection itself works.</>}</p>
        )
      ) : null}
      {stale ? <p className="text-xs font-medium">A value changed after this test.</p> : null}
    </motion.div>
  );
}
