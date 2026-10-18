// Sign in: a brand panel (the Vaidyx mark on the icon's own blues, three plain promises) beside the form on a laptop, a compact
// brand header above it on a phone. A successful sign-in asks for the splash (components/Splash) and hands over to the guard.
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { motion, useReducedMotion } from "motion/react";
import { Eye, EyeOff, FileCheck2, KeyRound, LogIn, ShieldCheck, Smartphone, Users } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/Field";
import { ActionButton } from "@/components/ActionButton";
import { VaidyxIcon, VaidyxWordmark, Wordmark } from "@/components/Wordmark";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Toasts } from "@/components/Toasts";
import { requestSplash } from "@/components/Splash";
import { useSession } from "@/lib/session";
import { ApiError } from "@/lib/api";
import { EASE } from "@/lib/motion";
import type { ActionState } from "@/hooks/useAsyncAction";

const PROMISES = [
  { icon: FileCheck2, title: "Every value has its source", text: "A fact is shown only with the report line it came from." },
  { icon: Users, title: "One Case File, the whole team", text: "Treating doctors, residents, Pathology, Radiology and the MDT Coordinator work on the same file." },
  { icon: Smartphone, title: "Laptop in the OPD, phone on the ward", text: "The same Case File, the same meeting, on both." },
];

function BrandPanel() {
  const reduce = useReducedMotion();
  return (
    <aside className="brand-gradient relative hidden overflow-hidden text-white lg:flex lg:flex-col lg:justify-between lg:p-10" aria-hidden>
      {/* soft orbs that drift: a calm, living surface, never busy */}
      {!reduce ? (
        <>
          <motion.span className="absolute -left-24 top-10 size-72 rounded-full bg-white/10 blur-3xl" animate={{ x: [0, 30, 0], y: [0, 20, 0] }} transition={{ duration: 18, repeat: Infinity, ease: "easeInOut" }} />
          <motion.span className="absolute -right-20 bottom-16 size-80 rounded-full bg-[#01c0c8]/25 blur-3xl" animate={{ x: [0, -24, 0], y: [0, -28, 0] }} transition={{ duration: 22, repeat: Infinity, ease: "easeInOut" }} />
        </>
      ) : null}
      <div className="relative flex items-center gap-3">
        <VaidyxIcon tone="white" className="h-8" />
        <VaidyxWordmark tone="white" className="h-6" />
      </div>
      <div className="relative max-w-md">
        <motion.h2 className="text-3xl font-semibold leading-tight tracking-[-0.02em] text-white" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: EASE }}>
          The hospital's Tumour Board, one Case File per patient.
        </motion.h2>
        <ul className="mt-8 space-y-5">
          {PROMISES.map((p, i) => (
            <motion.li key={p.title} className="flex gap-3" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, delay: 0.15 + i * 0.1, ease: EASE }}>
              <span className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-lg bg-white/15 text-white ring-1 ring-white/25"><p.icon className="size-[18px]" strokeWidth={2} /></span>
              <span>
                <span className="block font-medium text-white">{p.title}</span>
                <span className="block text-sm text-white/75">{p.text}</span>
              </span>
            </motion.li>
          ))}
        </ul>
      </div>
      <p className="relative text-xs text-white/60">Checks, routes, summarises and flags. Never a diagnosis, a stage or a treatment advice.</p>
    </aside>
  );
}

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
    if (!email.trim()) fe.email = "Type your email address or login name.";
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
      requestSplash();
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
    <main className="grid min-h-dvh bg-background lg:grid-cols-[5fr_7fr] lg:grid-rows-1">
      <BrandPanel />
      <section className="relative grid place-items-center p-4 sm:p-8">
        <div className="absolute right-4 top-4"><ThemeToggle saveToProfile={false} /></div>
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, ease: EASE }} className="w-full max-w-sm">
          <div className="mb-8 lg:hidden"><Wordmark to={null} size="lg" /></div>
          <h1 className="text-2xl">{needTotp ? "One more step" : "Sign in"}</h1>
          <p className="mt-1.5 text-sm text-muted-foreground">
            {needTotp ? "Your account asks for a 6-digit code from your authenticator app." : "Use the email address or login name your department admin set up."}
          </p>
          {sessionError ? (
            <p role="status" className="mt-4 rounded-md status-warn px-3 py-2 text-sm">The server part for the new interface answered {sessionError.status}. Signing in may still work; if not, tell the root admin.</p>
          ) : null}
          <form className="mt-6 grid gap-4" onSubmit={submit} noValidate>
            {!needTotp ? (
              <>
                <Field id="email" label="Email or login name" error={fieldError.email}>
                  <Input type="text" autoComplete="username" inputMode="email" autoCapitalize="none" spellCheck={false} value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@hospital.in" autoFocus className="h-10" />
                </Field>
                <Field
                  id="password"
                  label="Password"
                  error={fieldError.password}
                  trailing={
                    <button type="button" onClick={() => setShow((s) => !s)} className="absolute right-1 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-muted-foreground hover:text-foreground" aria-label={show ? "Hide password" : "Show password"}>
                      {show ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
                    </button>
                  }
                >
                  <Input type={show ? "text" : "password"} autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} className="h-10 pr-10" />
                </Field>
              </>
            ) : (
              <Field id="totp" label="6-digit code" error={fieldError.totp} hint="From your authenticator app; it changes every 30 seconds.">
                <Input ref={totpRef} inputMode="numeric" autoComplete="one-time-code" value={totp} onChange={(e) => setTotp(e.target.value.replace(/\D/g, "").slice(0, 6))} className="num h-11 text-center text-xl tracking-[0.35em]" />
              </Field>
            )}
            {error ? (
              <motion.div role="alert" initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} className="flex items-start gap-2 rounded-md status-bad px-3 py-2 text-sm">
                <ShieldCheck className="mt-0.5 size-4 shrink-0" aria-hidden /> <span>{error}</span>
              </motion.div>
            ) : null}
            <ActionButton type="submit" state={state} doneText="Signed in" loadingText="Checking" className="h-10 w-full" icon={needTotp ? <KeyRound className="size-4" aria-hidden /> : <LogIn className="size-4" aria-hidden />}>
              {needTotp ? "Confirm code" : "Sign in"}
            </ActionButton>
            {needTotp ? (
              <Button type="button" variant="ghost" size="sm" onClick={() => { setNeedTotp(false); setTotp(""); setError(null); }}>Use a different account</Button>
            ) : null}
          </form>
          <p className="mt-8 text-center text-xs text-muted-foreground">Forgot your password? Your department admin can reset it.</p>
        </motion.div>
        <Toasts />
      </section>
    </main>
  );
}
