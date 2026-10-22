// A labelled switch row (label, a hint under it, the switch on the right), used by the set-up, the profile and the notification
// settings.
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";

export function SwitchRow({ id, label, hint, checked, onCheckedChange, disabled }: { id: string; label: string; hint?: string; checked: boolean; onCheckedChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5">
      <div className="min-w-0">
        <Label htmlFor={id} className="cursor-pointer">{label}</Label>
        {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
      </div>
      <Switch id={id} checked={checked} onCheckedChange={onCheckedChange} disabled={disabled} />
    </div>
  );
}
