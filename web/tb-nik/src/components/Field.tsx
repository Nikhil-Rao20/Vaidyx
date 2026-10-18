import { cloneElement, isValidElement, type ReactElement, type ReactNode } from "react";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

/** Label, control, hint and error wired together (aria-describedby, aria-invalid). The control gets the id. */
export function Field({ id, label, hint, error, required, optional, children, className, trailing }: {
  id: string;
  label: ReactNode;
  hint?: ReactNode;
  error?: string | null;
  required?: boolean;
  optional?: boolean;
  children: ReactNode;
  className?: string;
  /** A small button inside the control on the right (show password); the control keeps the id and the label. */
  trailing?: ReactNode;
}) {
  const hintId = hint ? `${id}-hint` : undefined;
  const errId = error ? `${id}-error` : undefined;
  const described = [hintId, errId].filter(Boolean).join(" ") || undefined;
  const control = isValidElement(children)
    ? cloneElement(children as ReactElement<Record<string, unknown>>, { id, "aria-describedby": described, "aria-invalid": error ? true : undefined, "aria-required": required || undefined })
    : children;
  return (
    <div className={cn("grid gap-1.5", className)}>
      <Label htmlFor={id} className="flex items-baseline gap-2">
        <span>{label}</span>
        {required ? <span className="text-xs font-normal text-bad">required</span> : optional ? <span className="text-xs font-normal text-muted-foreground">optional</span> : null}
      </Label>
      {trailing ? <div className="relative">{control}{trailing}</div> : control}
      {hint ? <p id={hintId} className="text-xs text-muted-foreground">{hint}</p> : null}
      {error ? <p id={errId} role="alert" className="text-xs font-medium text-bad">{error}</p> : null}
    </div>
  );
}
