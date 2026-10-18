// Profile set-up on the first sign-in (the IKEA effect: the doctor builds their own account). Four steps, each saved as
// it is left, and the gift at the end: one UHID typed here jumps straight into the New Case File flow.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "motion/react";
import { Building2, Gift, Sparkles } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Field } from "@/components/Field";
import { Stepper, Step, StepTitle } from "@/components/Stepper";
import { AvatarPicker, initialsAvatar, AVATAR_COLOURS } from "@/components/AvatarPicker";
import { ThemeToggle } from "@/components/ThemeToggle";
import { TextSizeToggle } from "@/components/TextSizeToggle";
import { SwitchRow } from "@/components/FilterChips";
import { Illustration } from "@/components/Illustration";
import { notify } from "@/components/Toasts";
import { useProfile } from "@/hooks/useProfile";
import { useOrg } from "@/hooks/useQueries";
import { useTheme, useTextSize } from "@/hooks/useTheme";
import { isDoctor } from "@/lib/nav";
import { errorMessage } from "@/hooks/useAsyncAction";

const TITLES = ["Dr", "Prof", "Mr", "Ms", "Mrs"];

export default function Welcome() {
  const { me, update } = useProfile();
  const navigate = useNavigate();
  const { theme } = useTheme(false);
  const { size } = useTextSize(false);
  const [step, setStep] = useState(1);
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState(me?.display_name && me.display_name !== me.user ? me.display_name : "");
  const [title, setTitle] = useState(me?.profile?.title || "Dr");
  const [reg, setReg] = useState(me?.profile?.registration_no || "");
  const [photo, setPhoto] = useState(me?.profile?.photo || "");
  const [start, setStart] = useState<"home" | "last_case" | "meetings">(me?.profile?.start_page || "home");
  const [phone, setPhone] = useState(me?.profile?.phone || "");
  const [visible, setVisible] = useState(Boolean(me?.profile?.phone_visible));
  const [uhid, setUhid] = useState("");
  const [errors, setErrors] = useState<{ name?: string; reg?: string; phone?: string }>({});
  const doctor = me ? isDoctor(me) : false;
  const org = useOrg();
  const deptNames = new Map((org.data?.departments ?? []).map((d) => [d.id, d.name]));
  const canCreate = Boolean(me && ((me.roles.treating || []).length || me.roles.coordinator));
  const total = 4;

  const save = async (patch: Parameters<typeof update>[0]) => {
    setSaving(true);
    try {
      await update(patch);
      return true;
    } catch (e) {
      notify.error("Could not save", errorMessage(e));
      return false;
    } finally {
      setSaving(false);
    }
  };

  const validate = (s: number): boolean => {
    const er: typeof errors = {};
    if (s === 1) {
      if (name.trim().length < 2) er.name = "Type your name as colleagues know it.";
      if (doctor && !reg.trim()) er.reg = "Your medical council registration number.";
    }
    if (s === 3 && phone && !/^\+?[\d\s-]{8,15}$/.test(phone)) er.phone = "Type a mobile number with digits only, e.g. +91 98765 43210.";
    setErrors(er);
    return Object.keys(er).length === 0;
  };

  const onStepChange = async (next: number) => {
    if (next > step) {
      if (!validate(step)) return;
      let ok = true;
      if (step === 1) ok = await save({ display_name: name.trim(), title, registration_no: reg.trim(), photo: photo || initialsAvatar(name.trim(), AVATAR_COLOURS[0]) });
      if (step === 2) ok = await save({ theme, text_size: size });
      if (step === 3) ok = await save({ start_page: start, phone: phone.trim(), phone_visible: visible });
      if (!ok) return;
    }
    setStep(next);
  };

  const finish = async (withUhid: boolean) => {
    const ok = await save({ start_page: start });
    if (!ok) return;
    if (withUhid && uhid.trim()) navigate(`/cases/new?identifier=${encodeURIComponent(uhid.trim())}`, { replace: true });
    else navigate("/home", { replace: true });
  };

  // Momentum: the bar never starts at zero (owner's UX note 5).
  const progress = 20 + Math.round(((step - 1) / total) * 80);

  return (
    <div className="mx-auto max-w-2xl">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mb-4">
        <h1>Make it yours</h1>
        <p className="mt-1 text-sm text-muted-foreground">Four short steps. Everything can be changed later in Settings.</p>
        <Progress value={progress} className="mt-3 h-1.5" aria-label={`Set-up ${progress} percent done`} />
      </motion.div>
      <Stepper step={step} onStepChange={(n) => void onStepChange(n)} onFinalStepCompleted={() => void finish(false)} linear nextLoading={saving} completeButtonText="Go to Home">
        <Step title="You">
          <StepTitle title="Who you are" text="Your name appears on every Case File you work on." />
          <div className="grid gap-4">
            <div className="grid gap-4 sm:grid-cols-[120px_1fr]">
              <Field id="title" label="Title">
                <Select value={title} onValueChange={setTitle}>
                  <SelectTrigger className="w-full" id="title" aria-label="Title"><SelectValue /></SelectTrigger>
                  <SelectContent>{TITLES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
                </Select>
              </Field>
              <Field id="name" label="Name" required error={errors.name}>
                <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Lakshmi Rao" autoFocus autoComplete="name" />
              </Field>
            </div>
            {doctor ? (
              <p className="flex flex-wrap items-center gap-1.5 text-sm text-muted-foreground">
                <Building2 className="size-4" aria-hidden /> Your department{Object.keys(me?.roles.departments || {}).length > 1 ? "s" : ""}:
                {Object.entries(me?.roles.departments || {}).map(([id, role]) => (
                  <span key={id} className="quote-chip">{deptNames.get(id) ?? id}{role === "head" ? ", head" : role === "resident" ? ", resident" : ""}</span>
                ))}
                <span className="text-xs">(set by your department admin)</span>
              </p>
            ) : null}
            {doctor ? (
              <Field id="reg" label="Registration number" required error={errors.reg} hint="State or National Medical Council; printed on the board record.">
                <Input value={reg} onChange={(e) => setReg(e.target.value)} placeholder="e.g. TNMC 12345" className="mono" />
              </Field>
            ) : null}
            <div>
              <p className="mb-2 text-sm font-medium">Your picture</p>
              <AvatarPicker name={name.trim()} value={photo} onChange={setPhoto} />
            </div>
          </div>
        </Step>
        <Step title="Look">
          <StepTitle title="How it looks" text="Try both; what you pick here is used on every device you sign in from." />
          <div className="grid gap-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div><p className="text-sm font-medium">Theme</p><p className="text-xs text-muted-foreground">Light for the ward, dark for the reporting room.</p></div>
              <ThemeToggle withLabel saveToProfile={false} />
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div><p className="text-sm font-medium">Text size</p><p className="text-xs text-muted-foreground">The whole page changes as you pick.</p></div>
              <TextSizeToggle saveToProfile={false} />
            </div>
            <div className="surface-inner p-4">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Preview</p>
              <p className="mt-1 font-bold">Lakshmi R., 58 F, UHID VXH/2026/000123</p>
              <p className="text-sm text-muted-foreground">Breast cancer, early as recorded. From Dr Rao, Breast Surgery. 2 left before the board.</p>
            </div>
          </div>
        </Step>
        <Step title="Start">
          <StepTitle title="Where you start and how to reach you" />
          <div className="grid gap-5">
            <div>
              <p className="mb-2 text-sm font-medium">Start page after sign-in</p>
              <RadioGroup value={start} onValueChange={(v) => setStart(v as typeof start)} className="grid gap-2 sm:grid-cols-3">
                {[["home", "Home", "Your Case File list"], ["last_case", "Last Case File", "Where you left off"], ["meetings", "Meetings", "The board calendar"]].map(([v, l, h]) => (
                  <Label key={v} htmlFor={`start-${v}`} className="surface-inner flex cursor-pointer items-start gap-2 p-3 has-[[data-state=checked]]:border-primary">
                    <RadioGroupItem id={`start-${v}`} value={v} className="mt-0.5" />
                    <span><span className="block text-sm font-medium">{l}</span><span className="block text-xs font-normal text-muted-foreground">{h}</span></span>
                  </Label>
                ))}
              </RadioGroup>
            </div>
            <Field id="phone" label="Mobile number" optional error={errors.phone} hint="Only signed-in members of this hospital can see it, and only if you allow it below.">
              <Input value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" autoComplete="tel" placeholder="+91 98765 43210" />
            </Field>
            <SwitchRow id="phone-visible" label="Show my number to signed-in hospital members" hint="So a colleague can call about a Case File. Off by default." checked={visible} onCheckedChange={setVisible} disabled={!phone.trim()} />
          </div>
        </Step>
        <Step title={canCreate ? "Gift" : "Done"}>
          {canCreate ? (
          <>
          <StepTitle title="Try it on one patient" text="Type one UHID. Vaidyx fetches the records from the hospital system and shows what is missing, in seconds. No profile needed first." />
          <div className="surface-inner flex flex-col items-center gap-4 p-5 text-center">
            <Illustration kind="gift" />
            <form className="flex w-full max-w-md flex-col gap-2 sm:flex-row" onSubmit={(e) => { e.preventDefault(); void finish(true); }}>
              <Input value={uhid} onChange={(e) => setUhid(e.target.value)} placeholder="UHID, IP No. or OP No." className="mono flex-1" aria-label="UHID" />
              <Button type="submit" disabled={!uhid.trim() || saving} aria-busy={saving}><Gift className="size-4" aria-hidden /> Fetch the records</Button>
            </form>
            <p className="flex items-center gap-1 text-xs text-muted-foreground"><Sparkles className="size-3.5" aria-hidden /> Or press Go to Home and come back to this any time with "+ New Case File".</p>
          </div>
          </>
          ) : (
            <>
              <StepTitle title="You are set" text="Your profile is saved. Everything here can be changed later in Settings." />
              <div className="surface-inner flex flex-col items-center gap-3 p-5 text-center">
                <Illustration kind="done" />
                <p className="max-w-md text-sm text-muted-foreground">
                  {(me?.roles.supporting || []).length
                    ? "Your home lists the requests to your department: the patient, the UHID, the accession number and what is missing, with a link to open it in your RIS or PACS."
                    : "Your home shows what your role needs. The bell at the top tells you when something waits for you."}
                </p>
              </div>
            </>
          )}
        </Step>
      </Stepper>
    </div>
  );
}
