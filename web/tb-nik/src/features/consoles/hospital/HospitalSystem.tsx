// /hospital/system: the hospital system's connection, its state and its test (POST /his/test), and "Choose your hospital system"
// (HisChooser: pick, details, test without saving, use; docs/new-case/DESIGN.md N7). A FHIR connection keeps today's address and token
// form (the set-up step, POST /setup/his). A hospital with no hospital system starts from "Not connected" with the chooser as the main
// action. ?choose=1 opens the chooser (the admin set-up's step links here).
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { PlugZap, Repeat2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ActionButton } from "@/components/ActionButton";
import { DateText } from "@/components/DateText";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { KeyValue, KeyValueList } from "@/components/KeyValue";
import { Pill } from "@/components/StatusPill";
import { notify } from "@/components/Toasts";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { keys, useHospitalOverview, useInvalidate, useSetup } from "@/hooks/useQueries";
import { api } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import type { HisTestResult, SetupResponse } from "@/lib/types";
import { HisStep } from "@/features/admin/SetupSteps";
import type { HisState as HisForm } from "@/features/admin/state";
import { Card, CardSkeleton, HisPill } from "@/features/consoles/shared";
import { HisChooser, hisKindsKey, presetBadge, useHisKinds } from "@/features/consoles/hospital/HisChooser";

export default function HospitalSystem() {
  const setup = useSetup();
  const kinds = useHisKinds();
  const overview = useHospitalOverview();
  const qc = useQueryClient();
  const invalidate = useInvalidate();
  const [params, setParams] = useSearchParams();
  const [form, setForm] = useState<HisForm | null>(null);
  const [result, setResult] = useState<HisTestResult | null>(null);
  const [choosing, setChoosing] = useState(params.get("choose") === "1");
  useEffect(() => { if (params.get("choose") === "1") setChoosing(true); }, [params]);
  const value: HisForm = form ?? { url: setup.data?.his?.url || "", token: "" };

  const openChooser = (open: boolean) => {
    setChoosing(open);
    if (!open && params.get("choose")) { const p = new URLSearchParams(params); p.delete("choose"); setParams(p, { replace: true }); }
  };
  const store = (r: Partial<SetupResponse>) => { if (r && Array.isArray(r.steps)) qc.setQueryData(keys.setup, r); };
  const onTest = async () => {
    const r = await api.post<{ ok: boolean; test: HisTestResult } & Partial<SetupResponse>>(EP.setupHis, { url: value.url.trim(), token: value.token.trim() || undefined });
    store(r);
    setResult(r.test);
    setForm({ ...value, token: "" });
    void invalidate(keys.hospitalOverview, hisKindsKey);
    if (r.test?.ok) notify.success("The hospital system answers");
  };
  const onRetest = async () => {
    const r = await api.post<HisTestResult>(EP.hisTest);
    setResult(r);
    await invalidate(keys.setup, keys.hospitalOverview);
    if (r.ok) notify.success("The hospital system answers");
  };
  const retest = useAsyncAction(onRetest);
  const onSaved = (r: { ok: boolean; test: HisTestResult } & Partial<SetupResponse>) => {
    store(r);
    setResult(r.test ?? null);
    setForm(null);
    void invalidate(keys.hospitalOverview, hisKindsKey);
  };

  if (setup.error && !setup.data) return <div className="surface"><ErrorState error={setup.error} what="the hospital system settings" onRetry={() => void setup.refetch()} retrying={setup.isFetching} /></div>;
  const his = setup.data?.his;
  const cur = kinds.data?.current;
  const kind = cur?.kind ?? his?.kind ?? "fhir";
  const enabled = cur?.enabled ?? his?.enabled ?? true;
  const connected = enabled && kind !== "none" && (kind !== "fhir" || Boolean(his?.url));
  const state = { state: !connected ? "not_set" : his?.ok ? "connected" : his?.ok === false ? "failing" : "not_tested", url_set: connected, tested_at: his?.tested_at ?? null, ok: his?.ok ?? null } as const;
  const method = kinds.data?.kinds.find((k) => k.kind === kind);
  const preset = kinds.data?.presets.find((p) => p.id === cur?.preset) ?? (kind === "fhir" ? kinds.data?.presets.find((p) => p.kind === "fhir" && p.defaults?.url === cur?.settings?.url) : undefined);
  const folder = typeof cur?.settings?.adapter?.folder === "string" ? cur.settings.adapter.folder : "";
  const address = cur?.settings?.url || his?.url || "";
  const badge = preset ? presetBadge(preset) : null;
  const changeButton = (
    <Button type="button" variant={connected ? "outline" : "default"} onClick={() => openChooser(true)} disabled={Boolean(kinds.error)}>
      <Repeat2 className="size-4" aria-hidden />{connected ? "Change hospital system" : "Choose your hospital system"}
    </Button>
  );

  return (
    <div className="grid max-w-4xl gap-5">
      <Card title="Connection" icon={PlugZap} id="hs-conn" action={setup.data ? <HisPill his={state} /> : null}>
        {setup.isLoading || !setup.data ? <CardSkeleton lines={4} /> : !connected ? (
          <EmptyState kind="empty" compact title="Not connected"
            text="Doctors cannot look up a patient by UHID until this hospital's system is chosen and tested. Case Files can still be made by hand."
            action={changeButton} />
        ) : (
          <div className="grid gap-5">
            {cur ? (
              <KeyValueList columns={2} className="rounded-md bg-muted/60 p-3">
                <KeyValue label="System" value={<span className="flex flex-wrap items-center gap-2"><span>{cur.settings?.label || preset?.name || method?.label}</span>{badge ? <Pill tone={badge.tone}>{badge.word}</Pill> : null}</span>} />
                <KeyValue label="Connects by" value={method?.label ?? kind} />
                {folder ? <KeyValue label="Folder" value={folder} mono /> : address ? <KeyValue label="Address" value={address} mono /> : null}
                <KeyValue label="Last test" value={his?.tested_at ? <DateText value={his.tested_at} mode="ago" /> : ""} fallback="not tested yet" />
              </KeyValueList>
            ) : null}
            {kind === "fhir" ? (
              <HisStep value={value} onChange={setForm} setup={setup.data} result={result} onTest={onTest} onRetest={onRetest} chooserLink={false} />
            ) : (
              <div className="grid gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <ActionButton type="button" variant="outline" state={retest.state} doneText="Tested" loadingText="Testing" onClick={() => void retest.run()} icon={<PlugZap className="size-4" aria-hidden />}>Test again</ActionButton>
                </div>
                {retest.error ? <p role="alert" className="text-sm text-bad">{retest.error}</p> : null}
                {(result ?? his) ? (
                  <p className={(result ?? his)?.ok ? "rounded-md status-ok p-3 text-sm" : (result ?? his)?.ok === false ? "rounded-md status-bad p-3 text-sm" : "text-sm text-muted-foreground"} role="status">
                    {(result ?? his)?.ok ? "The hospital system answers." : (result ?? his)?.ok === false ? `The hospital system did not answer. ${(result ?? his)?.error || ""}` : "Not tested yet."}
                    {result?.ok && typeof result.patients === "number" ? ` ${result.patients} patients${typeof result.reports === "number" ? `, ${result.reports} reports` : ""}.` : ""}
                  </p>
                ) : null}
              </div>
            )}
            <div className="flex flex-wrap items-center gap-3 border-t border-border pt-4">
              {changeButton}
              <p className="text-xs text-muted-foreground">Pick another system or connection method, test it, then use it. Nothing changes until it passes.</p>
            </div>
          </div>
        )}
      </Card>
      {kinds.error ? <p className="text-xs text-muted-foreground">The list of hospital systems could not be loaded, so the system cannot be changed here now. {kinds.error.message}</p> : null}
      <p className="text-xs text-muted-foreground">The connection is also in the <Link to="/hospital/setup" className="text-link hover:underline">set-up</Link>.</p>
      <HisChooser open={choosing} onOpenChange={openChooser} onSaved={onSaved} caseFiles={overview.data?.case_files?.total} />
    </div>
  );
}
