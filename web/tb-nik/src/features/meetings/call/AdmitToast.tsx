// The coordinator's admit toast on the stage: who waits to join (up to three names), Admit each, and Admit all. It stays until acted
// on and hides while the People panel (which has the full waiting room) is open.
import { useState } from "react";
import { UserRoundCheck } from "lucide-react";
import { LoadingButton } from "@/features/casefile/components/common";
import { useCall } from "./context";
import { cn } from "@/lib/utils";

export function AdmitToast({ className }: { className?: string }) {
  const c = useCall();
  const [busy, setBusy] = useState<string | null>(null);
  if (c.variant !== "coordinator" || !c.canManage || c.panel === "people") return null;
  const waiting = c.state.attendance.filter((a) => a.status === "waiting");
  if (!waiting.length) return null;
  const run = (key: string, fn: () => Promise<unknown>) => { setBusy(key); void fn().catch(() => {}).finally(() => setBusy(null)); };
  return (
    <ul className={cn("z-10 max-w-[min(26rem,calc(100%-1.5rem))] space-y-1.5", className)} data-testid="waiting-banner" aria-label="Waiting to be admitted">
      {waiting.slice(0, 3).map((a) => (
        <li key={a.user} className="flex items-center gap-2 rounded-xl border border-stage-line bg-stage-panel/95 px-3 py-2 text-sm text-stage-fg shadow-[var(--shadow-lift)] backdrop-blur">
          <span className="min-w-0 flex-1"><span className="font-medium">{a.name}</span>{a.department_name || a.department ? <span className="text-stage-muted"> ({a.department_name ?? a.department})</span> : null} wants to join</span>
          <LoadingButton size="xs" loading={busy === a.user} disabled={!!busy} onClick={() => run(a.user, () => c.actions.admit(a.user))} aria-label={`Admit ${a.name}`}>Admit</LoadingButton>
        </li>
      ))}
      <li className="flex items-center gap-2 px-1 text-xs text-stage-muted">
        {waiting.length > 3 ? <span className="flex-1">and {waiting.length - 3} more in People</span> : <span className="flex-1" />}
        {waiting.length > 1 ? <LoadingButton size="xs" variant="outline" loading={busy === "*"} disabled={!!busy} onClick={() => run("*", c.actions.admitAll)} data-testid="admit-all"><UserRoundCheck className="size-3" />Admit all</LoadingButton> : null}
      </li>
    </ul>
  );
}
