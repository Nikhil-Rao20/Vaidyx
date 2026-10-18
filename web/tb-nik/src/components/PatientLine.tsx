import { cn } from "@/lib/utils";

/** Name, age/sex, UHID (mono), and the IP / OP number when given. One line, truncates from the right. */
export function PatientLine({ patient, extra, size = "md", className, strong = true }: {
  patient?: { name?: string; agesex?: string; uhid?: string; mrn?: string } | null;
  /** "IP/2026/00012" or "OP/2026/00987" */
  extra?: string | null;
  size?: "sm" | "md" | "lg";
  className?: string;
  strong?: boolean;
}) {
  if (!patient) return <span className={cn("text-muted-foreground", className)}>No patient</span>;
  const uhid = patient.uhid || patient.mrn;
  const text = size === "lg" ? "text-base" : size === "sm" ? "text-xs" : "text-sm";
  return (
    <span className={cn("inline-flex min-w-0 max-w-full flex-wrap items-baseline gap-x-2 gap-y-0.5", text, className)}>
      <span className={cn("truncate text-foreground", strong && "font-bold")}>{patient.name || "Unnamed"}</span>
      {patient.agesex ? <span className="text-muted-foreground">{patient.agesex}</span> : null}
      {uhid ? <span className="mono text-muted-foreground">UHID {uhid}</span> : null}
      {extra ? <span className="mono text-muted-foreground">{extra}</span> : null}
    </span>
  );
}
