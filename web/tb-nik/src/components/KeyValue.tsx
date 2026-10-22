import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Label on the left, value on the right; stacks on narrow screens. */
export function KeyValueList({ children, className, columns = 1 }: { children: ReactNode; className?: string; columns?: 1 | 2 }) {
  return <dl className={cn("grid gap-x-6 gap-y-2", columns === 2 ? "sm:grid-cols-2" : "", className)}>{children}</dl>;
}

export function KeyValue({ label, value, mono, hint, className, fallback = "not given" }: {
  label: ReactNode;
  value?: ReactNode;
  mono?: boolean;
  hint?: ReactNode;
  className?: string;
  fallback?: string;
}) {
  const empty = value === undefined || value === null || value === "";
  return (
    <div className={cn("grid grid-cols-[minmax(7rem,30%)_1fr] items-baseline gap-x-3 gap-y-0.5", className)}>
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className={cn("min-w-0 break-words text-sm text-foreground", mono && "mono", empty && "text-muted-foreground italic")}>
        {empty ? fallback : value}
        {hint ? <span className="ml-2 text-xs text-muted-foreground not-italic">{hint}</span> : null}
      </dd>
    </div>
  );
}
