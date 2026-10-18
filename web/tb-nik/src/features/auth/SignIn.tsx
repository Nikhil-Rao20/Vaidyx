import { useEffect, useRef, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { motion } from "motion/react";
import { Eye, EyeOff, KeyRound, LogIn, ShieldCheck } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/Field";
import { ActionButton } from "@/components/ActionButton";
import { Wordmark } from "@/components/Wordmark";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Toasts } from "@/components/Toasts";
import { Illustration } from "@/components/Illustration";
import { useSession } from "@/lib/session";
import { ApiError } from "@/lib/api";
import type { ActionState } from "@/hooks/useAsyncAction";

export default function SignIn() {
  const { signIn, error: sessionError } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from;
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totp, setTotp] = useState("");
  const [needTotp, setNeedTotp] = useState(false);
  const [show, setShow] = useState(false);
  const [state, setState] = useState<ActionState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<{ email?: string; password?: string; totp?: string }>({});
  const totpRef = useRef<HTMLInputElement>(null);
  useEffect(() => { if (needTotp) totpRef.current?.focus(); }, [needTotp]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const fe: typeof fieldError = {};
    if (!email.trim()) fe.email = "Type your email address.";
    if (!password) fe.password = "Type your password.";
    if (needTotp && totp.replace(/\D/g, "").length !== 6) fe.totp = "The code has 6 digits.";
    setFieldError(fe);
    if (Object.keys(fe).length) return;
    setState("loading");
    setError(null);
    try {
      const r = await signIn(email.trim().toLowerCase(), password, needTotp ? totp.replace(/\D/g, "") : undefined);
      if (!r.ok && r.requires_totp) {
        setNeedTotp(true);
        setState("idle");
        return;
      }
      setState("done");
      // With no "from", the PublicOnly guard sends the signed-in person to their start page (profile.start_page).
      if (from && from !== "/sign-in") navigate(from, { replace: true });
    } catch (err) {
      setState("error");
      if (err instanceof ApiError) {
        if (err.status === 401) setError(needTotp ? "That code is not right. Open your authenticator app and type the current 6 digits." : "The email or password is not right.");
        else if (err.status === 429) setError("Too many tries. Wait 15 minutes, then try again.");
        else if (err.status === 0) setError("No connection to the server. Check the network and try again.");
        else setError(err.message);
      } else setError("Something went wrong. Please try again.");
    }
  };

  return (
    <main className="grid min-h-dvh place-items-center bg-background p-4">
      <div className="absolute right-4 top-4"><ThemeToggle saveToProfile={false} /></div>
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }} className="surface w-full max-w-md p-6 sm:p-8">
        <Wordmark to={null} size="lg" />
        <h1 className="mt-6">{needTotp ? "One more step" : "Sign in"}</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {needTotp ? "Your account asks for a 6-digit code from your authenticator app." : "The Tumour Board Case File assistant. Use the email address your department admin set up."}
        </p>
        {sessionError ? (
          <p role="status" className="mt-4 rounded-md status-warn px-3 py-2 text-sm">The server part for the new interface answered {sessionError.status}. Signing in may still work; if not, tell the root admin.</p>
        ) : null}
        <form className="mt-6 grid gap-4" onSubmit={submit} noValidate>
          {!needTotp ? (
            <>
              <Field id="email" label="Email" error={fieldError.email}>
                <Input type="email" autoComplete="username" inputMode="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@hospital.in" autoFocus />
              </Field>
              <Field
                id="password"
                label="Password"
                error={fieldError.password}
                trailing={
                  <button type="button" onClick={() => setShow((s) => !s)} className="absolute right-1 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-muted-foreground hover:text-foreground" aria-label={show ? "Hide password" : "Show password"} aria-pressed={show}>
                    {show ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
                  </button>
                }
              >
                <Input type={show ? "text" : "password"} autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} className="pr-10" />
              </Field>
            </>
          ) : (
            <Field id="totp" label="6-digit code" error={fieldError.totp} hint="From your authenticator app; it changes every 30 seconds.">
              <Input ref={totpRef} inputMode="numeric" autoComplete="one-time-code" value={totp} onChange={(e) => setTotp(e.target.value.replace(/\D/g, "").slice(0, 6))} className="mono text-center text-lg tracking-[0.3em]" maxLength={6} />
            </Field>
          )}
          {error ? (
            <div role="alert" className="flex items-start gap-2 rounded-md status-bad px-3 py-2 text-sm">
              <ShieldCheck className="mt-0.5 size-4 shrink-0" aria-hidden /> <span>{error}</span>
            </div>
          ) : null}
          <ActionButton type="submit" state={state} doneText="Signed in" loadingText="Checking" className="h-10 w-full" icon={needTotp ? <KeyRound className="size-4" aria-hidden /> : <LogIn className="size-4" aria-hidden />}>
            {needTotp ? "Confirm code" : "Sign in"}
          </ActionButton>
          {needTotp ? (
            <Button type="button" variant="ghost" size="sm" onClick={() => { setNeedTotp(false); setTotp(""); setError(null); }}>Use a different account</Button>
          ) : null}
        </form>
        <p className="mt-6 text-center text-xs text-muted-foreground">Forgot password? Ask your department admin to reset it.</p>
        <div className="mt-4 flex justify-center opacity-70"><Illustration kind="lock" className="h-12 w-20" /></div>
      </motion.div>
      <Toasts />
    </main>
  );
}
