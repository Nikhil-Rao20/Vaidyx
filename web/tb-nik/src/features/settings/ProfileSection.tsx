// Settings: the profile (name, title, registration number, photo, mobile number and who may see it). PUT /me/profile.
import { useEffect, useState, type FormEvent } from "react";
import { Save, UserRound } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Field } from "@/components/Field";
import { ActionButton } from "@/components/ActionButton";
import { AvatarPicker } from "@/components/AvatarPicker";
import { SwitchRow } from "@/components/FilterChips";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { useProfile } from "@/hooks/useProfile";
import { isDoctor, roleWords } from "@/lib/nav";
import { SettingsCard } from "@/features/settings/SettingsCard";

const TITLES = ["Dr", "Prof", "Mr", "Ms", "Mrs"];

export function ProfileSection() {
  const { me, update } = useProfile();
  const [name, setName] = useState(me?.display_name && me.display_name !== me.user ? me.display_name : "");
  const [title, setTitle] = useState(me?.profile?.title || "Dr");
  const [reg, setReg] = useState(me?.profile?.registration_no || "");
  const [photo, setPhoto] = useState(me?.profile?.photo || "");
  const [phone, setPhone] = useState(me?.profile?.phone || "");
  const [visible, setVisible] = useState(Boolean(me?.profile?.phone_visible));
  const [errors, setErrors] = useState<{ name?: string; reg?: string; phone?: string }>({});
  const doctor = me ? isDoctor(me) : false;
  const dirty = Boolean(me) && (
    name !== (me?.display_name && me.display_name !== me.user ? me.display_name : "") || title !== (me?.profile?.title || "Dr") || reg !== (me?.profile?.registration_no || "") ||
    photo !== (me?.profile?.photo || "") || phone !== (me?.profile?.phone || "") || visible !== Boolean(me?.profile?.phone_visible)
  );
  useEffect(() => { if (!phone.trim() && visible) setVisible(false); }, [phone, visible]);
  const save = useAsyncAction(async () => {
    await update({ display_name: name.trim(), title, registration_no: reg.trim(), photo, phone: phone.trim(), phone_visible: visible && Boolean(phone.trim()) });
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const er: typeof errors = {};
    if (name.trim().length < 2) er.name = "Type your name as colleagues know it.";
    if (doctor && !reg.trim()) er.reg = "Your medical council registration number is needed for doctors.";
    else if (reg.trim() && !/^[A-Za-z0-9 /.-]{2,40}$/.test(reg.trim())) er.reg = "Letters, digits, spaces, slashes, dots and hyphens only.";
    if (phone.trim() && !/^\+?[0-9][0-9 -]{6,19}$/.test(phone.trim())) er.phone = "Digits, spaces and hyphens, with an optional + at the start.";
    setErrors(er);
    if (!Object.keys(er).length) void save.run();
  };
  if (!me) return null;
  return (
    <SettingsCard id="profile" icon={UserRound} title="Profile" text="How colleagues see you on Case Files, meetings and records.">
      <form className="grid gap-4" onSubmit={submit} noValidate>
        <div className="grid gap-4 sm:grid-cols-[120px_1fr]">
          <Field id="s-title" label="Title">
            <Select value={title} onValueChange={setTitle}>
              <SelectTrigger className="w-full" id="s-title" aria-label="Title"><SelectValue /></SelectTrigger>
              <SelectContent>{TITLES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
            </Select>
          </Field>
          <Field id="s-name" label="Name" required error={errors.name}>
            <Input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" maxLength={80} />
          </Field>
        </div>
        <Field id="s-reg" label="Registration number" required={doctor} optional={!doctor} error={errors.reg} hint="State or National Medical Council; printed on the board record.">
          <Input value={reg} onChange={(e) => setReg(e.target.value)} className="mono" maxLength={40} />
        </Field>
        <div>
          <p className="mb-2 text-sm font-medium">Picture</p>
          <AvatarPicker name={name.trim()} value={photo} onChange={setPhoto} />
        </div>
        <Field id="s-phone" label="Mobile number" optional error={errors.phone} hint="Only signed-in members of this hospital can see it, and only when you allow it below.">
          <Input value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" autoComplete="tel" placeholder="+91 98765 43210" maxLength={20} />
        </Field>
        <SwitchRow id="s-phone-visible" label="Show my number to signed-in hospital members" hint="Off by default." checked={visible} onCheckedChange={setVisible} disabled={!phone.trim()} />
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
          <p className="text-xs text-muted-foreground">Login <span className="mono">{me.user}</span>. Roles: {roleWords(me).join(", ")} (set by your admin).</p>
          <ActionButton type="submit" state={save.state} doneText="Saved" loadingText="Saving" disabled={!dirty && save.state !== "done"} icon={<Save className="size-4" aria-hidden />}>Save profile</ActionButton>
        </div>
        {save.error ? <p role="alert" className="rounded-md status-bad px-3 py-2 text-sm">{save.error}</p> : null}
      </form>
    </SettingsCard>
  );
}
