// First sign-in: the password the admin sent must be replaced before anything else.
import { useMemo, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "motion/react";
import { Check, Eye, EyeOff, KeyRound } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/Field";
import { ActionButton } from "@/components/ActionButton";
import { Illustration } from "@/components/Illustration";
import { useSession } from "@/lib/session";
import { api, ApiError } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { cn } from "@/lib/utils";
import { passwordStrength } from "@/lib/password";
import { errorCode } from "@/lib/errors";

export default function FirstLogin() {
  const { me, refresh } = useSession();
  const navigate = useNavigate();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [show, setShow] = useState(false);
  const [errors, setErrors] = useState<{ current?: string; next?: string; again?: string }>({});
  const strength = useMemo(() => passwordStrength(next), [next]);
  const action = useAsyncAction(async () => {
    try {
      await api.post(EP.password, { current_password: current, new_password: next });
    } catch (e) {
      const code = errorCode(e);
      if (code === "wrong_password" || (e instanceof ApiError && e.status === 401)) { setErrors({ current: "That is not your current password." }); throw e; }
      if (e instanceof ApiError && e.status === 400) { setErrors({ next: e.message }); throw e; }
      throw e;
    }
    const m = await refresh();
    window.setTimeout(() => navigate(m?.setup_needed ? "/welcome" : "/home", { replace: true }), 500);
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const er: typeof errors = {};
    if (!current) er.current = "Type the password you signed in with.";
    if (next.length < 8) er.next = "At least 8 characters.";
    else if (next === current) er.next = "Choose a password different from the current one.";
    if (again !== next) er.again = "The two passwords differ.";
    setErrors(er);
    if (Object.keys(er).length) return;
    void action.run();
  };

  const colour = ["bg-bad", "bg-bad", "bg-warn", "bg-primary", "bg-ok"][strength.score];
  return (
    <div className="mx-auto grid max-w-3xl gap-6 md:grid-cols-[1fr_260px] md:items-start">
      <motion.form initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="surface grid gap-4 p-6" onSubmit={submit} noValidate>
        <div>
          <h1>Set your own password</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Hello {me?.display_name || me?.user}. The password you signed in with was made by your admin; replace it with one only you know.
          </p>
        </div>
        <Field id="current" label="Current password" error={errors.current}>
          <Input type={show ? "text" : "password"} autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} autoFocus />
        </Field>
        <Field
          id="next"
          label="New password"
          error={errors.next}
          hint="Nobody at Vaidyx can see it. Your admin can only reset it."
          trailing={
            <button type="button" onClick={() => setShow((s) => !s)} className="absolute right-1 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-muted-foreground hover:text-foreground" aria-label={show ? "Hide passwords" : "Show passwords"} aria-pressed={show}>
              {show ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
            </button>
          }
        >
          <Input type={show ? "text" : "password"} autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} className="pr-10" />
        </Field>
        {next ? (
          <div aria-live="polite">
            <div className="flex h-1.5 gap-1" aria-hidden>
              {[1, 2, 3, 4].map((i) => <span key={i} className={cn("flex-1 rounded-full transition-colors", i <= strength.score ? colour : "bg-muted")} />)}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">Strength: <span className="font-medium text-foreground">{strength.word}</span></p>
            <ul className="mt-1 grid gap-0.5 text-xs sm:grid-cols-2">
              {strength.checks.map((c) => (
                <li key={c.text} className={cn("flex items-center gap-1", c.ok ? "text-ok" : "text-muted-foreground")}>
                  <Check className={cn("size-3", !c.ok && "opacity-30")} aria-hidden /> {c.text}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        <Field id="again" label="New password again" error={errors.again}>
          <Input type={show ? "text" : "password"} autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} />
        </Field>
        {action.error && !errors.current && !errors.next ? <p role="alert" className="rounded-md status-bad px-3 py-2 text-sm">{action.error}</p> : null}
        <ActionButton type="submit" state={action.state} doneText="Password set" loadingText="Saving" className="h-10 w-full sm:w-auto sm:justify-self-end" icon={<KeyRound className="size-4" aria-hidden />}>
          Save and continue
        </ActionButton>
      </motion.form>
      <aside className="surface hidden flex-col items-center gap-2 p-5 text-center md:flex">
        <Illustration kind="lock" />
        <p className="text-sm font-bold">Why now?</p>
        <p className="text-xs text-muted-foreground">Every action on a Case File is recorded under your name. A password only you know keeps that record yours.</p>
      </aside>
    </div>
  );
}
