// "Add a hospital" (docs/admin-console 4.1): three steps in one dialog (Hospital details, First hospital admin, Review), then the
// result: the first admin's login and first password, shown once, with Copy and the mail draft. POST /platform/hospitals.
import { useEffect, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import { Building2, Check, CheckCircle2, ChevronLeft, ChevronRight, LogIn, UserRoundPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/Field";
import { SwitchRow } from "@/components/SwitchRow";
import { ActionButton } from "@/components/ActionButton";
import { KeyValue, KeyValueList } from "@/components/KeyValue";
import { notify } from "@/components/Toasts";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { keys } from "@/hooks/useQueries";
import { api } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import type { NewHospital, NewHospitalResult } from "@/lib/types";
import { cn } from "@/lib/utils";
import { EMAIL } from "@/features/admin/state";
import { OneTimeLoginPanel } from "@/features/consoles/shared";
import { useManageHospital } from "@/features/consoles/useManage";

export const INDIAN_STATES = [
  "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
  "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu",
  "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal", "Andaman and Nicobar Islands", "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu",
  "Delhi", "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
];

const STEPS = ["Hospital details", "First hospital admin", "Review"];

interface Form {
  name: string; city: string; state: string; type: "public" | "private" | ""; level: string; pmjay: boolean; demoHis: boolean;
  adminName: string; adminEmail: string;
}
const EMPTY: Form = { name: "", city: "", state: "", type: "", level: "essential", pmjay: true, demoHis: false, adminName: "", adminEmail: "" };

function StepDots({ step }: { step: number }) {
  return (
    <ol className="grid grid-cols-3 gap-2" aria-label="Steps">
      {STEPS.map((label, i) => {
        const n = i + 1;
        const done = n < step;
        const current = n === step;
        return (
          <li key={label} aria-current={current ? "step" : undefined} className="min-w-0">
            <span className={cn("block h-1 rounded-full", done || current ? "bg-primary" : "bg-muted")} aria-hidden />
            <span className={cn("mt-1.5 flex items-center gap-1 text-xs", current ? "font-medium text-foreground" : "text-muted-foreground")}>
              {done ? <Check className="size-3 shrink-0 text-ok" aria-hidden /> : <span className="tabular-nums">{n}.</span>}
              <span className="truncate">{label}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export function AddHospitalDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const { manage } = useManageHospital();
  const [step, setStep] = useState(1);
  const [f, setF] = useState<Form>(EMPTY);
  const [errors, setErrors] = useState<Partial<Record<keyof Form, string>>>({});
  const [result, setResult] = useState<NewHospitalResult | null>(null);

  const set = <K extends keyof Form>(k: K, v: Form[K]) => { setF((x) => ({ ...x, [k]: v })); setErrors((e) => ({ ...e, [k]: undefined })); };

  const save = useAsyncAction(async () => {
    const body: NewHospital = {
      name: f.name.trim(), city: f.city.trim() || undefined, state: f.state || undefined, type: f.type || undefined, level: f.level || undefined,
      pmjay_empanelled: f.pmjay, demo_his: f.demoHis, admin: { display_name: f.adminName.trim(), email: f.adminEmail.trim().toLowerCase() },
    };
    const r = await api.post<NewHospitalResult>(EP.platformHospitals, body);
    setResult(r);
    void qc.invalidateQueries({ queryKey: keys.platform });
    notify.success("Hospital added", r.hospital?.name || body.name);
  });

  // Closed: start again next time (after the closing animation).
  useEffect(() => { if (!open) { const t = window.setTimeout(() => { setStep(1); setF(EMPTY); setErrors({}); setResult(null); save.reset(); }, 200); return () => window.clearTimeout(t); } }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const check = (n: number): boolean => {
    const e: Partial<Record<keyof Form, string>> = {};
    if (n === 1 && !f.name.trim()) e.name = "Give the hospital's name.";
    if (n === 2) {
      if (!f.adminName.trim()) e.adminName = "Give the admin's name.";
      if (!EMAIL.test(f.adminEmail.trim())) e.adminEmail = "Type the admin's email address; it becomes their login.";
    }
    setErrors(e);
    return !Object.keys(e).length;
  };
  const next = (e?: FormEvent) => {
    e?.preventDefault();
    if (step < 3) { if (check(step)) setStep(step + 1); return; }
    void save.run();
  };

  const busy = save.state === "loading";
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!busy) onOpenChange(o); }}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-lg" aria-describedby="add-hospital-text">
        {result ? (
          <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="grid grid-cols-1 gap-4">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2"><CheckCircle2 className="size-5 text-ok" aria-hidden /> {result.hospital?.name || f.name} is added</DialogTitle>
              <DialogDescription id="add-hospital-text">Send the first hospital admin their login. They choose their own password at the first sign-in and then set up the hospital.</DialogDescription>
            </DialogHeader>
            <OneTimeLoginPanel login={result.admin.username} password={result.admin.password_once} mailto={result.admin.mailto} />
            <DialogFooter className="gap-2 sm:gap-2">
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Done</Button>
              {result.hospital?.id ? (
                <Button type="button" onClick={() => { onOpenChange(false); void manage({ id: result.hospital.id, name: result.hospital.name || f.name }); }}>
                  <LogIn className="size-4" aria-hidden /> Manage inside this hospital
                </Button>
              ) : null}
            </DialogFooter>
          </motion.div>
        ) : (
          <form onSubmit={next} noValidate className="grid grid-cols-1 gap-4" aria-label="Add a hospital">
            <DialogHeader>
              <DialogTitle>Add a hospital</DialogTitle>
              <DialogDescription id="add-hospital-text">It starts empty and separate: its own people, departments and Case Files. Nothing of another hospital is visible to it.</DialogDescription>
            </DialogHeader>
            <StepDots step={step} />
            {step === 1 ? (
              <div className="grid grid-cols-1 gap-3">
                <Field id="nh-name" label="Hospital name" required error={errors.name}><Input value={f.name} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Sri Venkateswara Cancer Hospital" autoFocus /></Field>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <Field id="nh-city" label="City" optional><Input value={f.city} onChange={(e) => set("city", e.target.value)} placeholder="e.g. Tirupati" /></Field>
                  <Field id="nh-state" label="State" optional>
                    <Select value={f.state || undefined} onValueChange={(v) => set("state", v)}>
                      <SelectTrigger className="w-full" id="nh-state"><SelectValue placeholder="Choose a state" /></SelectTrigger>
                      <SelectContent className="max-h-72">{INDIAN_STATES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
                    </Select>
                  </Field>
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <Field id="nh-type" label="Type" optional>
                    <Select value={f.type || undefined} onValueChange={(v) => set("type", v as Form["type"])}>
                      <SelectTrigger className="w-full" id="nh-type"><SelectValue placeholder="Public or private" /></SelectTrigger>
                      <SelectContent><SelectItem value="public">Public</SelectItem><SelectItem value="private">Private</SelectItem></SelectContent>
                    </Select>
                  </Field>
                  <Field id="nh-level" label="NCG level">
                    <Select value={f.level} onValueChange={(v) => set("level", v)}>
                      <SelectTrigger className="w-full" id="nh-level"><SelectValue /></SelectTrigger>
                      <SelectContent><SelectItem value="essential">Essential</SelectItem><SelectItem value="optimal">Optimal</SelectItem></SelectContent>
                    </Select>
                  </Field>
                </div>
                <div className="rounded-md border border-border px-3 py-1">
                  <SwitchRow id="nh-pmjay" label="PM-JAY empanelled" checked={f.pmjay} onCheckedChange={(v) => set("pmjay", v)} />
                  <SwitchRow id="nh-demo" label="Use the demo hospital system (synthetic)" hint="For a demo only: fake patients and reports. Leave off for a real hospital; its admin connects its own system." checked={f.demoHis} onCheckedChange={(v) => set("demoHis", v)} />
                </div>
              </div>
            ) : step === 2 ? (
              <div className="grid grid-cols-1 gap-3">
                <p className="flex items-start gap-2 text-sm text-muted-foreground"><UserRoundPlus className="mt-0.5 size-4 shrink-0 text-brand-text" aria-hidden /> The first hospital admin sets up the hospital and adds its people. Add more admins later from the hospital's page.</p>
                <Field id="nh-admin-name" label="Name" required error={errors.adminName}><Input value={f.adminName} onChange={(e) => set("adminName", e.target.value)} placeholder="e.g. Ravi Teja" autoFocus /></Field>
                <Field id="nh-admin-email" label="Email (the login)" required error={errors.adminEmail}><Input type="email" value={f.adminEmail} onChange={(e) => set("adminEmail", e.target.value)} placeholder="e.g. it.admin@hospital.in" autoComplete="off" /></Field>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-3">
                <div className="rounded-md border border-border p-3">
                  <p className="mb-2 flex items-center gap-2 text-sm font-medium text-foreground"><Building2 className="size-4 text-brand-text" aria-hidden /> Hospital</p>
                  <KeyValueList>
                    <KeyValue label="Name" value={f.name.trim()} />
                    <KeyValue label="Place" value={[f.city.trim(), f.state].filter(Boolean).join(", ")} />
                    <KeyValue label="Type" value={f.type ? (f.type === "public" ? "Public" : "Private") : ""} />
                    <KeyValue label="NCG level" value={f.level === "optimal" ? "Optimal" : "Essential"} />
                    <KeyValue label="PM-JAY" value={f.pmjay ? "Empanelled" : "Not empanelled"} />
                    <KeyValue label="Hospital system" value={f.demoHis ? "Demo (synthetic)" : "Not connected yet"} />
                  </KeyValueList>
                </div>
                <div className="rounded-md border border-border p-3">
                  <p className="mb-2 flex items-center gap-2 text-sm font-medium text-foreground"><UserRoundPlus className="size-4 text-brand-text" aria-hidden /> First hospital admin</p>
                  <KeyValueList>
                    <KeyValue label="Name" value={f.adminName.trim()} />
                    <KeyValue label="Login" value={f.adminEmail.trim().toLowerCase()} mono />
                  </KeyValueList>
                </div>
                <p className="text-xs text-muted-foreground">Vaidyx makes a first password for the admin. You see it once on the next screen.</p>
              </div>
            )}
            {save.error ? <p role="alert" className="rounded-md status-bad px-3 py-2 text-sm">{save.error}</p> : null}
            <DialogFooter className="gap-2 sm:gap-2">
              {step > 1 ? <Button type="button" variant="outline" onClick={() => setStep(step - 1)} disabled={busy}><ChevronLeft className="size-4" aria-hidden /> Back</Button> : <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>}
              {step < 3 ? (
                <Button type="submit">Continue <ChevronRight className="size-4" aria-hidden /></Button>
              ) : (
                <ActionButton type="submit" state={save.state} loadingText="Adding" doneText="Added">Add the hospital</ActionButton>
              )}
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
