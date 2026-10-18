import { dueWords, formatDate, formatDateTime, formatDateWords, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

/** A date in DD/MM/YYYY (or words, or "3 h ago", or "due in 2 days"), the full date and time on hover. */
export function DateText({ value, mode = "date", fallback = "", className }: {
  value?: string | number | Date | null;
  mode?: "date" | "words" | "datetime" | "ago" | "due";
  fallback?: string;
  className?: string;
}) {
  if (!value) return fallback ? <span className={cn("text-muted-foreground", className)}>{fallback}</span> : null;
  const full = formatDateTime(value);
  let text = "";
  let tone = "";
  if (mode === "ago") text = timeAgo(value);
  else if (mode === "words") text = formatDateWords(value);
  else if (mode === "datetime") text = full;
  else if (mode === "due") {
    const d = dueWords(typeof value === "string" ? value : formatDate(value));
    text = d.text;
    tone = d.late ? "text-bad font-medium" : d.today ? "text-warn font-medium" : "";
  } else text = formatDate(value);
  const iso = value instanceof Date ? value.toISOString() : String(value);
  return (
    <time dateTime={iso} title={full} className={cn("tabular-nums", tone, className)}>
      {text}
    </time>
  );
}
