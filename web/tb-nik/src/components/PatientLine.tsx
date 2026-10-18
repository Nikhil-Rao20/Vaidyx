import { cn } from "@/lib/utils";

/** Name, age and sex, the UHID (small, tabular) and the IP / OP number when given. One line, truncates from the right. */
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
  const text = size === "lg" ? "text-lg" : size === "sm" ? "text-xs" : "text-sm";
  const small = size === "lg" ? "text-sm" : size === "sm" ? "text-[11px]" : "text-xs";
  return (
    <span className={cn("inline-flex min-w-0 max-w-full flex-wrap items-baseline gap-x-2 gap-y-0.5", text, className)}>
      <span className={cn("truncate text-foreground", strong && "font-semibold")}>{patient.name || "Unnamed"}</span>
      {patient.agesex ? <span className={cn("text-muted-foreground", small)}>{patient.agesex}</span> : null}
      {uhid ? <span className={cn("id text-muted-foreground", small)}>{size === "lg" ? "UHID " : ""}{uhid}</span> : null}
      {extra ? <span className={cn("id text-muted-foreground", small)}>{extra}</span> : null}
    </span>
  );
}
