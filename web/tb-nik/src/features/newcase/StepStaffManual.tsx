// Step 1 for a hospital doctor whose patient is not in the hospital system, or when the hospital system cannot be reached
// (docs/new-case/DESIGN.md N5): the patient's name, the hospital number if known, age and sex. The hospital system lookup stays the
// main way; this is the backup. The Case File is not linked to the hospital system: the reports are added in Records after Create.
// The one-Case-File-per-patient-and-cancer check still runs on the hospital number when one is given.
import { ArrowLeft, FileText } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Field } from "@/components/Field";
import type { NewCaseForm } from "@/features/newcase/form";

/** Step 1 by hand is complete with a name (2+ letters), an age in years (0 to 120) and the sex; the hospital number is optional. */
export function staffManualDone(form: NewCaseForm): boolean {
  const age = Number(form.manualAge);
  return form.manualName.trim().replace(/[^\p{L}]/gu, "").length >= 2 && /^\d{1,3}$/.test(form.manualAge.trim()) && age >= 0 && age <= 120 && Boolean(form.manualSex);
}

export function StepStaffManual({ form, onChange, onBack }: { form: NewCaseForm; onChange: (patch: Partial<NewCaseForm>) => void; onBack: () => void }) {
  const ageBad = form.manualAge.trim() !== "" && (!/^\d{1,3}$/.test(form.manualAge.trim()) || Number(form.manualAge) > 120);
  return (
    <div className="grid gap-5">
      <div className="flex items-start gap-3 rounded-md bg-muted p-4 text-sm" data-testid="manual-note">
        <FileText className="mt-0.5 size-4 shrink-0" aria-hidden />
        <p><span className="font-medium">Not linked to the hospital system: add the reports in Records after Create.</span></p>
      </div>
      <div className="grid gap-4 sm:grid-cols-[2fr_1fr]">
        <Field id="manual-name" label="Patient's name" required hint="As on the hospital record.">
          <Input value={form.manualName} maxLength={80} autoFocus autoComplete="off" placeholder="e.g. Lakshmi Narayanan"
                 onChange={(e) => onChange({ manualName: e.target.value })} />
        </Field>
        <Field id="manual-uhid" label="Hospital number" optional hint="The UHID if you know it. It finds an existing Case File of this patient.">
          <Input value={form.manualUhid} maxLength={40} autoComplete="off" className="mono" placeholder="e.g. VXH/2026/000123"
                 onChange={(e) => onChange({ manualUhid: e.target.value })} />
        </Field>
      </div>
      <div className="grid gap-4 sm:grid-cols-[1fr_2fr] sm:items-start">
        <Field id="manual-age" label="Age" required error={ageBad ? "Years, as a number up to 120" : undefined}>
          <Input value={form.manualAge} inputMode="numeric" maxLength={3} autoComplete="off" placeholder="52"
                 onChange={(e) => onChange({ manualAge: e.target.value.replace(/[^\d]/g, "") })} />
        </Field>
        <div>
          <p className="mb-2 text-sm font-medium" id="manual-sex-label">Sex <span className="text-xs font-normal text-bad">required</span></p>
          <RadioGroup aria-labelledby="manual-sex-label" value={form.manualSex} onValueChange={(v) => onChange({ manualSex: v })} className="grid grid-cols-3 gap-2">
            {[["F", "Female"], ["M", "Male"], ["O", "Other"]].map(([v, l]) => (
              <Label key={v} htmlFor={`staff-sex-${v}`} className="surface-inner flex cursor-pointer items-center gap-2 p-3 has-[[data-state=checked]]:border-primary">
                <RadioGroupItem id={`staff-sex-${v}`} value={v} />
                <span className="text-sm font-medium">{l}</span>
              </Label>
            ))}
          </RadioGroup>
        </div>
      </div>
      <div>
        <Button type="button" variant="link" className="h-auto px-0 text-sm" onClick={onBack}>
          <ArrowLeft className="size-4" aria-hidden /> Back to the hospital system lookup
        </Button>
      </div>
    </div>
  );
}
