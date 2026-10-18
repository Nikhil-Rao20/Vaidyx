import { Flame, TriangleAlert } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * The urgency tag 1 to 5 set by the owner's consultant (5 most urgent). Colour only on 4 and 5, always with an icon.
 * `proposed` shows a resident's proposal waiting for the consultant.
 */
export function UrgencyTag({ level, proposed, setByName, size = "md", className }: {
  level: number | null | undefined;
  proposed?: number | null;
  setByName?: string;
  size?: "sm" | "md";
  className?: string;
}) {
  const n = typeof level === "number" && level >= 1 && level <= 5 ? level : null;
  const dim = size === "sm" ? "h-6 min-w-6 px-1.5 text-xs" : "h-7 min-w-7 px-2 text-sm";
  const tone = n === 5 ? "status-bad" : n === 4 ? "status-warn" : n ? "bg-muted text-muted-foreground" : "border border-dashed border-border-strong text-muted-foreground";
  const Icon = n === 5 ? Flame : n === 4 ? TriangleAlert : null;
  const words = n ? `Urgency ${n} of 5${n === 5 ? ", most urgent" : n === 4 ? ", urgent" : ""}` : "Urgency not set";
  const title = setByName && n ? `${words}, set by ${setByName}` : words;
  return (
    <span className={cn("inline-flex items-center gap-1", className)}>
      <span className={cn("inline-flex items-center justify-center gap-0.5 rounded-md font-bold tabular-nums", dim, tone)} title={title} aria-label={title} role="img">
        {Icon ? <Icon className={size === "sm" ? "size-3" : "size-3.5"} aria-hidden /> : null}
        {n ?? <span aria-hidden className="text-[10px] font-normal leading-none whitespace-nowrap">not set</span>}
      </span>
      {typeof proposed === "number" ? (
        <span className="rounded-md status-review px-1.5 py-0.5 text-[11px] font-medium" title={`A resident proposes urgency ${proposed}`}>
          proposed {proposed}
        </span>
      ) : null}
    </span>
  );
}
