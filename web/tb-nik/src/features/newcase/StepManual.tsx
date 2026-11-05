// Step 1 for a guest reviewer (real, anonymized files; 5 Nov 2026): no hospital system. A label the reviewer recognises, age and
// sex; never a name or a hospital number. The Case File is private: only this login sees it. The files are added in Records.
import { Lock } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Field } from "@/components/Field";
import type { NewCaseForm } from "@/features/newcase/form";

export function manualDone(form: NewCaseForm): boolean {
  const age = Number(form.manualAge);
  return form.manualLabel.trim().length > 0 && /^\d{1,3}$/.test(form.manualAge.trim()) && age >= 0 && age <= 120 && Boolean(form.manualSex);
}

export function StepManual({ form, onChange }: { form: NewCaseForm; onChange: (patch: Partial<NewCaseForm>) => void }) {
  const ageBad = form.manualAge.trim() !== "" && !/^\d{1,3}$/.test(form.manualAge.trim());
  return (
    <div className="grid gap-5">
      <div className="flex items-start gap-3 rounded-md bg-muted p-4 text-sm">
        <Lock className="mt-0.5 size-4 shrink-0" aria-hidden />
        <p><span className="font-medium">Private: only you and the MDT Coordinator can see this Case File (and the people in its meeting, once you send it to the board).</span> It is not fetched from a hospital system: you add the anonymized files yourself in Records, after Create.</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-[2fr_1fr]">
        <Field id="manual-label" label="Case label" hint="Something you recognise, such as Case A. Never the patient's name or a hospital number.">
          <Input id="manual-label" value={form.manualLabel} maxLength={40} autoFocus autoComplete="off" placeholder="Case A"
                 onChange={(e) => onChange({ manualLabel: e.target.value })} />
        </Field>
        <Field id="manual-age" label="Age" error={ageBad ? "Years, as a number" : undefined}>
          <Input id="manual-age" value={form.manualAge} inputMode="numeric" maxLength={3} autoComplete="off" placeholder="52"
                 onChange={(e) => onChange({ manualAge: e.target.value.replace(/[^\d]/g, "") })} />
        </Field>
      </div>
      <div>
        <p className="mb-2 text-sm font-medium">Sex</p>
        <RadioGroup value={form.manualSex} onValueChange={(v) => onChange({ manualSex: v })} className="grid gap-2 sm:grid-cols-3">
          {[["F", "Female"], ["M", "Male"], ["O", "Other"]].map(([v, l]) => (
            <Label key={v} htmlFor={`sex-${v}`} className="surface-inner flex cursor-pointer items-center gap-2 p-3 has-[[data-state=checked]]:border-primary">
              <RadioGroupItem id={`sex-${v}`} value={v} />
              <span className="text-sm font-medium">{l}</span>
            </Label>
          ))}
        </RadioGroup>
      </div>
    </div>
  );
}
