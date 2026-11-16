// /hospital/system: the hospital system's connection and its test (today's set-up step, POST /setup/his and POST /his/test).
// Later the "Choose your hospital system" screen goes here.
import { useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { PlugZap } from "lucide-react";
import { ErrorState } from "@/components/ErrorState";
import { notify } from "@/components/Toasts";
import { keys, useInvalidate, useSetup } from "@/hooks/useQueries";
import { api } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import type { HisTestResult, SetupResponse } from "@/lib/types";
import { HisStep } from "@/features/admin/SetupSteps";
import type { HisState as HisForm } from "@/features/admin/state";
import { Card, CardSkeleton, HisPill } from "@/features/consoles/shared";

export default function HospitalSystem() {
  const setup = useSetup();
  const qc = useQueryClient();
  const invalidate = useInvalidate();
  const [form, setForm] = useState<HisForm | null>(null);
  const [result, setResult] = useState<HisTestResult | null>(null);
  const value: HisForm = form ?? { url: setup.data?.his?.url || "", token: "" };

  const store = (r: Partial<SetupResponse>) => { if (r && Array.isArray(r.steps)) qc.setQueryData(keys.setup, r); };
  const onTest = async () => {
    const r = await api.post<{ ok: boolean; test: HisTestResult } & Partial<SetupResponse>>(EP.setupHis, { url: value.url.trim(), token: value.token.trim() || undefined });
    store(r);
    setResult(r.test);
    setForm({ ...value, token: "" });
    void invalidate(keys.hospitalOverview);
    if (r.test?.ok) notify.success("The hospital system answers");
  };
  const onRetest = async () => {
    const r = await api.post<HisTestResult>(EP.hisTest);
    setResult(r);
    await invalidate(keys.setup, keys.hospitalOverview);
    if (r.ok) notify.success("The hospital system answers");
  };

  if (setup.error && !setup.data) return <div className="surface"><ErrorState error={setup.error} what="the hospital system settings" onRetry={() => void setup.refetch()} retrying={setup.isFetching} /></div>;
  const his = setup.data?.his;
  const state = { state: his?.ok ? "connected" : his?.ok === false ? "failing" : his?.url ? "not_tested" : "not_set", url_set: Boolean(his?.url), tested_at: his?.tested_at ?? null, ok: his?.ok ?? null } as const;
  return (
    <div className="grid max-w-4xl gap-5">
      <Card title="Connection" icon={PlugZap} id="hs-conn" action={setup.data ? <HisPill his={state} /> : null}>
        {setup.isLoading || !setup.data ? <CardSkeleton lines={4} /> : (
          <HisStep value={value} onChange={setForm} setup={setup.data} result={result} onTest={onTest} onRetest={onRetest} />
        )}
      </Card>
      <p className="text-xs text-muted-foreground">A screen to choose other kinds of hospital system comes later. This's connection is also in the <Link to="/hospital/setup" className="text-link hover:underline">set-up</Link>.</p>
    </div>
  );
}
