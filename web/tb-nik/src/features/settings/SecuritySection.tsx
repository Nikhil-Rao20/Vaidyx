// Settings: change the password (POST /me/password) and two-step sign-in with an authenticator app (the Vaidyx login
// system's /api/auth/2fa routes: status, set up with a QR code, confirm with a code, turn off with the password).
import { useMemo, useState, type FormEvent } from "react";
import { Check, Eye, EyeOff, KeyRound, ShieldCheck, ShieldOff, Smartphone } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/Field";
import { ActionButton } from "@/components/ActionButton";
import { CopyButton } from "@/components/CopyButton";
import { ErrorState } from "@/components/ErrorState";
import { Pill } from "@/components/StatusPill";
import { notify } from "@/components/Toasts";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { useInvalidate, useTotpStatus, keys } from "@/hooks/useQueries";
import { api, ApiError } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import { errorCode } from "@/lib/errors";
import { useSession } from "@/lib/session";
import type { TotpSetup } from "@/lib/types";
import { cn } from "@/lib/utils";
import { passwordStrength } from "@/lib/password";
import { SettingsCard } from "@/features/settings/SettingsCard";

function PasswordForm() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [show, setShow] = useState(false);
  const [errors, setErrors] = useState<{ current?: string; next?: string; again?: string }>({});
  const strength = useMemo(() => passwordStrength(next), [next]);
  const save = useAsyncAction(async () => {
    try {
      await api.post(EP.password, { current_password: current, new_password: next });
    } catch (e) {
      const code = errorCode(e);
      if (code === "wrong_password") setErrors({ current: "That is not your current password." });
      else if (code === "weak_password" && e instanceof ApiError) setErrors({ next: e.message });
      throw e;
    }
    setCurrent(""); setNext(""); setAgain("");
    notify.success("Password changed", "Use the new one from your next sign-in.");
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const er: typeof errors = {};
    if (!current) er.current = "Type your current password.";
    if (next.length < 8) er.next = "At least 8 characters.";
    else if (next === current) er.next = "Choose a password different from the current one.";
    if (again !== next) er.again = "The two passwords differ.";
    setErrors(er);
    if (!Object.keys(er).length) void save.run();
  };
  const colour = ["bg-bad", "bg-bad", "bg-warn", "bg-primary", "bg-ok"][strength.score];
  return (
    <form className="grid gap-4" onSubmit={submit} noValidate aria-label="Change password">
      <p className="text-sm font-bold">Change password</p>
      <Field id="pw-current" label="Current password" error={errors.current}>
        <Input type={show ? "text" : "password"} autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          id="pw-next"
          label="New password"
          error={errors.next}
          trailing={
            <button type="button" onClick={() => setShow((s) => !s)} className="absolute right-1 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-muted-foreground hover:text-foreground" aria-label={show ? "Hide passwords" : "Show passwords"} aria-pressed={show}>
              {show ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
            </button>
          }
        >
          <Input type={show ? "text" : "password"} autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} className="pr-10" />
        </Field>
        <Field id="pw-again" label="New password again" error={errors.again}>
          <Input type={show ? "text" : "password"} autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} />
        </Field>
      </div>
      {next ? (
        <div aria-live="polite">
          <div className="flex h-1.5 gap-1" aria-hidden>{[1, 2, 3, 4].map((i) => <span key={i} className={cn("flex-1 rounded-full transition-colors", i <= strength.score ? colour : "bg-muted")} />)}</div>
          <p className="mt-1 text-xs text-muted-foreground">Strength: <span className="font-medium text-foreground">{strength.word}</span></p>
        </div>
      ) : null}
      {save.error && !errors.current && !errors.next ? <p role="alert" className="rounded-md status-bad px-3 py-2 text-sm">{save.error}</p> : null}
      <ActionButton type="submit" state={save.state} doneText="Changed" loadingText="Saving" className="justify-self-start" icon={<KeyRound className="size-4" aria-hidden />}>Change password</ActionButton>
    </form>
  );
}

function TwoStep() {
  const { me, refresh } = useSession();
  const status = useTotpStatus();
  const invalidate = useInvalidate();
  const [setup, setSetup] = useState<TotpSetup | null>(null);
  const [code, setCode] = useState("");
  const [backup, setBackup] = useState<string[] | null>(null);
  const [offOpen, setOffOpen] = useState(false);
  const [password, setPassword] = useState("");
  const required = Boolean(me && (me.real_data || me.roles.coordinator || me.roles.root_admin || (me.roles.admin_of || []).length));
  const start = useAsyncAction(async () => { setSetup(await api.post<TotpSetup>(EP.totpSetup)); setCode(""); });
  const confirm = useAsyncAction(async () => {
    const r = await api.post<{ ok: boolean; backup_codes?: string[] }>(EP.totpConfirm, { code: code.replace(/\D/g, "") });
    setBackup(r.backup_codes ?? []);
    setSetup(null);
    await invalidate(keys.totp);
    if (me?.two_factor_required) await refresh();  // a guest reviewer may now open the rest of the site
    notify.success("Two-step sign-in is on");
  });
  const disable = useAsyncAction(async () => {
    await api.post(EP.totpDisable, { password });
    setPassword(""); setOffOpen(false);
    await invalidate(keys.totp);
    notify.success("Two-step sign-in is off");
  });
  const on = Boolean(status.data?.enabled);
  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-2 text-sm font-bold"><Smartphone className="size-4 text-muted-foreground" aria-hidden /> Two-step sign-in</p>
        {status.isLoading ? <Pill>Checking</Pill> : status.error ? null : on ? <Pill tone="ok" icon={ShieldCheck}>On</Pill> : <Pill tone={required ? "warn" : "neutral"} icon={ShieldOff}>Off</Pill>}
      </div>
      <p className="text-xs text-muted-foreground">
        After the password, a 6-digit code from an authenticator app on your phone.
        {me?.real_data ? " Required for this account: it works with real, anonymized files." : required ? " It will be required for MDT Coordinators and admins when the hospital deploys Vaidyx; turning it on now saves a step later." : ""}
      </p>
      {status.error && !status.data ? <ErrorState compact error={status.error} what="two-step sign-in" onRetry={() => void status.refetch()} /> : null}
      {backup ? (
        <div className="rounded-md status-ok p-3 text-sm">
          <p className="font-medium">Keep these backup codes somewhere safe. Each one signs you in once if the phone is lost. They are shown only now.</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {backup.map((b) => <span key={b} className="mono rounded bg-card px-2 py-0.5 text-foreground">{b}</span>)}
            {backup.length ? <CopyButton text={backup.join("\n")} label="Copy the backup codes" /> : null}
          </div>
          <Button type="button" variant="ghost" size="sm" className="mt-2" onClick={() => setBackup(null)}><Check className="size-4" aria-hidden /> I have kept them</Button>
        </div>
      ) : null}
      {!on && !setup && status.data ? (
        <ActionButton type="button" size="sm" className="justify-self-start" state={start.state} doneText="Ready" onClick={() => void start.run()} icon={<ShieldCheck className="size-4" aria-hidden />}>Turn on two-step sign-in</ActionButton>
      ) : null}
      {start.error ? <p role="alert" className="text-xs text-bad">{start.error}</p> : null}
      {setup ? (
        <form className="surface-inner grid gap-3 p-4 sm:grid-cols-[auto_1fr]" onSubmit={(e) => { e.preventDefault(); if (code.replace(/\D/g, "").length === 6) void confirm.run(); }}>
          <img src={setup.qr_code} alt="QR code to scan with the authenticator app" className="size-40 rounded-md border border-border bg-white p-1" />
          <div className="grid content-start gap-3">
            <p className="text-sm">1. Scan the code with an authenticator app (Google Authenticator, Microsoft Authenticator, or similar).</p>
            <p className="text-xs text-muted-foreground">Cannot scan? Type this key in the app: <span className="mono break-all text-foreground">{setup.secret}</span> <CopyButton text={setup.secret} label="Copy the key" size="icon-xs" /></p>
            <Field id="totp-code" label="2. Type the 6-digit code the app shows" error={confirm.state === "error" ? "That code is not right. Type the current one; it changes every 30 seconds." : null}>
              <Input value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} inputMode="numeric" autoComplete="one-time-code" className="mono w-40 text-center tracking-[0.3em]" maxLength={6} />
            </Field>
            <div className="flex gap-2">
              <ActionButton type="submit" size="sm" state={confirm.state} doneText="On" disabled={code.length !== 6}>Confirm</ActionButton>
              <Button type="button" variant="ghost" size="sm" onClick={() => setSetup(null)}>Cancel</Button>
            </div>
          </div>
        </form>
      ) : null}
      {on ? (
        offOpen ? (
          <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); if (password) void disable.run(); }}>
            <Field id="totp-off-pw" label="Your password, to turn it off" error={disable.state === "error" ? "That password is not right." : null}>
              <Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} className="w-56" />
            </Field>
            <ActionButton type="submit" variant="destructive" size="sm" state={disable.state} doneText="Off" disabled={!password}>Turn off</ActionButton>
            <Button type="button" variant="ghost" size="sm" onClick={() => { setOffOpen(false); setPassword(""); }}>Cancel</Button>
          </form>
        ) : (
          <Button type="button" variant="outline" size="sm" className="justify-self-start" onClick={() => setOffOpen(true)}><ShieldOff className="size-4" aria-hidden /> Turn off</Button>
        )
      ) : null}
    </div>
  );
}

export function SecuritySection() {
  const { me } = useSession();
  return (
    <SettingsCard id="security" icon={ShieldCheck} title="Security" text="Your password and how you sign in. Forgot the password? Your department admin resets it.">
      <div className="grid gap-6">
        {me?.two_factor_required ? (
          <p role="alert" className="rounded-md status-warn p-3 text-sm">
            This account works with real, anonymized files. Turn on two-step sign-in below to open the rest of the Tumour Board.
          </p>
        ) : null}
        <PasswordForm />
        <div className="border-t border-border pt-5"><TwoStep /></div>
      </div>
    </SettingsCard>
  );
}
