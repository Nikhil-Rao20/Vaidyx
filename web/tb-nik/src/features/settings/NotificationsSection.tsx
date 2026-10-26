// Settings: which notifications arrive (PUT /me/notifications), the time of the morning digest, and browser push on this
// device (GET /push/key, POST /push/subscribe; public/sw.js shows them). Push text never carries a UHID or a name.
import { useEffect, useState } from "react";
import { BellRing, BellOff, Clock, MonitorSmartphone, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ActionButton } from "@/components/ActionButton";
import { TimeInput } from "@/components/TimeInput";
import { SwitchRow } from "@/components/SwitchRow";
import { ErrorState } from "@/components/ErrorState";
import { Pill } from "@/components/StatusPill";
import { notify } from "@/components/Toasts";
import { useAsyncAction, errorMessage } from "@/hooks/useAsyncAction";
import { useInvalidate, useNotificationPrefs, keys, notBuiltYet } from "@/hooks/useQueries";
import { api } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import { PREF_KINDS } from "@/lib/notifications";
import { pushState, pushSupported, subscribePush, unsubscribePush, type PushState } from "@/lib/push";
import { useSession } from "@/lib/session";
import type { NotificationPrefs } from "@/lib/types";
import { SettingsCard } from "@/features/settings/SettingsCard";

function PushRow({ serverReady }: { serverReady: boolean }) {
  const [state, setState] = useState<PushState | "checking">("checking");
  useEffect(() => { let on = true; void pushState().then((s) => { if (on) setState(s); }); return () => { on = false; }; }, []);
  const turnOn = useAsyncAction(async () => { await subscribePush(); setState("on"); notify.success("Push is on for this browser"); }, { onError: (m) => notify.error("Push could not be turned on", m) });
  const turnOff = useAsyncAction(async () => { await unsubscribePush(); setState("off"); notify.success("Push is off for this browser"); }, { onError: (m) => notify.error("Push could not be turned off", m) });
  const words: Record<string, { tone: "ok" | "neutral" | "warn" | "bad"; text: string }> = {
    checking: { tone: "neutral", text: "Checking" },
    on: { tone: "ok", text: "On for this browser" },
    off: { tone: "neutral", text: "Off" },
    blocked: { tone: "bad", text: "Blocked by the browser" },
    unsupported: { tone: "warn", text: "Not supported here" },
  };
  const w = words[state];
  return (
    <div className="surface-inner grid gap-3 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <MonitorSmartphone className="size-4 text-muted-foreground" aria-hidden />
          <p className="text-sm font-medium">Browser push on this device</p>
        </div>
        <Pill tone={w.tone}>{w.text}</Pill>
      </div>
      <p className="text-xs text-muted-foreground">A small alert even when this tab is closed, like "You have 2 new requests". Never a patient's name or UHID.</p>
      {!serverReady ? (
        <p className="flex items-start gap-2 rounded-md status-warn px-3 py-2 text-xs"><ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden /> Push is not set up on this server yet. The in-app bell works as usual.</p>
      ) : state === "blocked" ? (
        <p className="text-xs text-bad">Notifications are blocked for this site. Allow them in the browser's site settings (the lock icon by the address), then reload.</p>
      ) : state === "unsupported" || !pushSupported() ? (
        <p className="text-xs text-muted-foreground">This browser cannot show push notifications. The in-app bell works as usual.</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {state === "on" ? (
            <ActionButton type="button" variant="outline" size="sm" state={turnOff.state} doneText="Off" onClick={() => void turnOff.run()} icon={<BellOff className="size-4" aria-hidden />}>Turn off</ActionButton>
          ) : (
            <ActionButton type="button" size="sm" state={turnOn.state} doneText="On" loadingText="Asking the browser" disabled={state === "checking"} onClick={() => void turnOn.run()} icon={<BellRing className="size-4" aria-hidden />}>Turn on push</ActionButton>
          )}
        </div>
      )}
    </div>
  );
}

export function NotificationsSection() {
  const { me } = useSession();
  const prefs = useNotificationPrefs();
  const invalidate = useInvalidate();
  const [digest, setDigest] = useState("08:00");
  const [savingKind, setSavingKind] = useState<string | null>(null);
  useEffect(() => { if (prefs.data?.digest_time) setDigest(prefs.data.digest_time); }, [prefs.data?.digest_time]);
  const save = async (patch: Partial<NotificationPrefs>) => {
    const r = await api.put<NotificationPrefs>(EP.myNotifications, patch);
    await invalidate(keys.notificationPrefs);
    return r;
  };
  const saveDigest = useAsyncAction(async () => {
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(digest)) throw new Error("Type the time as HH:MM, for example 08:00.");
    await save({ digest_time: digest });
  });
  const toggle = async (kind: string, on: boolean) => {
    setSavingKind(kind);
    try {
      await save({ kinds: { [kind]: on } });
    } catch (e) {
      notify.error("Could not save", errorMessage(e));
    } finally {
      setSavingKind(null);
    }
  };
  const available = prefs.data?.kinds_available;
  const kinds = PREF_KINDS.filter((k) => !available || available.includes(k.id));
  const serverPush = Boolean(prefs.data?.push_enabled ?? me?.features?.push);

  return (
    <SettingsCard id="notifications" icon={BellRing} title="Notifications" text="The bell at the top shows them all; here you choose what reaches you.">
      {prefs.isLoading && !prefs.data ? (
        <div className="grid gap-2" aria-busy="true">{[0, 1, 2, 3].map((i) => <div key={i} className="skeleton-line h-10" />)}</div>
      ) : prefs.error && !prefs.data ? (
        <ErrorState compact error={prefs.error} what="notification settings" onRetry={() => void prefs.refetch()} retrying={prefs.isFetching} text={notBuiltYet(prefs.error) ? "Notification choices are not available on this server yet. The bell still shows everything." : undefined} />
      ) : (
        <div className="grid gap-5">
          <div className="divide-y divide-border rounded-md border border-border px-3">
            {kinds.map((k) => (
              <SwitchRow key={k.id} id={`kind-${k.id}`} label={k.label} hint={k.hint} checked={prefs.data?.kinds?.[k.id] ?? true} onCheckedChange={(v) => void toggle(k.id, v)} disabled={savingKind === k.id} />
            ))}
          </div>
          <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); void saveDigest.run(); }}>
            <div className="grid gap-1.5">
              <label htmlFor="digest" className="flex items-center gap-1.5 text-sm font-medium"><Clock className="size-4 text-muted-foreground" aria-hidden /> Morning digest at</label>
              <TimeInput id="digest" value={digest} onChange={setDigest} wrapperClassName="w-36" aria-describedby="digest-hint" />
            </div>
            <ActionButton type="submit" variant="outline" size="sm" state={saveDigest.state} doneText="Saved" disabled={digest === prefs.data?.digest_time}>Save time</ActionButton>
            <p id="digest-hint" className="w-full text-xs text-muted-foreground">One message a day with what is unread, at the time you choose.</p>
            {saveDigest.error ? <p role="alert" className="w-full text-xs text-bad">{saveDigest.error}</p> : null}
          </form>
        </div>
      )}
      <div className="mt-5"><PushRow serverReady={serverPush} /></div>
      {!prefs.data && !prefs.isLoading ? <Button type="button" variant="link" size="sm" className="mt-2 h-auto p-0" onClick={() => void prefs.refetch()}>Check again</Button> : null}
    </SettingsCard>
  );
}
