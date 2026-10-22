// A date typed and shown as DD/MM/YYYY whatever the browser's language, with our own calendar (components/Calendar) in a
// popover anchored to the field (the browser's picker opened at the top left of the screen on some set-ups, 18 Oct). The
// value in and out is ISO YYYY-MM-DD or "".
import { forwardRef, useEffect, useState, type ComponentProps } from "react";
import { CalendarDays } from "lucide-react";
import { Popover, PopoverAnchor, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Calendar } from "@/components/Calendar";
import { cn } from "@/lib/utils";

const pad = (n: number) => String(n).padStart(2, "0");

export function isoToDmy(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
  return m ? `${m[3]}/${m[2]}/${m[1]}` : "";
}

/** "21/10/2026", "21-10-2026", "21.10.2026" or "2026-10-21" to "2026-10-21"; null when it is not a real date. The year is always
 * typed in full: a two-digit year ("31") is ambiguous and was once read as 2031 for a rotation that ends in 2027. */
export function dmyToIso(text: string): string | null {
  const t = text.trim();
  if (!t) return "";
  let m = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(t);
  let y: number, mo: number, d: number;
  if (m) { y = +m[1]; mo = +m[2]; d = +m[3]; }
  else {
    m = /^(\d{1,2})[/.\-\s](\d{1,2})[/.\-\s](\d{4})$/.exec(t);
    if (!m) return null;
    d = +m[1]; mo = +m[2]; y = +m[3];
  }
  const dt = new Date(y, mo - 1, d);
  if (dt.getFullYear() !== y || dt.getMonth() !== mo - 1 || dt.getDate() !== d) return null;
  return `${y}-${pad(mo)}-${pad(d)}`;
}

export const DateInput = forwardRef<HTMLInputElement, Omit<ComponentProps<"input">, "value" | "onChange" | "type" | "min" | "max"> & {
  value: string;
  onChange: (iso: string) => void;
  min?: string;
  max?: string;
  wrapperClassName?: string;
}>(function DateInput({ value, onChange, min, max, className, wrapperClassName, disabled, onBlur, ...props }, ref) {
  const [text, setText] = useState(isoToDmy(value));
  const [bad, setBad] = useState(false);
  const [open, setOpen] = useState(false);
  useEffect(() => { if ((dmyToIso(text) ?? "") !== value) { setText(isoToDmy(value)); setBad(false); } }, [value]); // eslint-disable-line react-hooks/exhaustive-deps
  const commit = (t: string) => {
    const iso = dmyToIso(t);
    const outside = iso && ((min && iso < min) || (max && iso > max));
    setBad(iso === null || Boolean(outside));
    if (iso !== null && !outside) onChange(iso);
  };
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverAnchor asChild>
        <div className={cn("relative", wrapperClassName)}>
          <input
            ref={ref}
            type="text"
            inputMode="numeric"
            placeholder="DD/MM/YYYY"
            autoComplete="off"
            value={text}
            disabled={disabled}
            aria-invalid={bad || props["aria-invalid"] || undefined}
            title={bad ? "Type the date as DD/MM/YYYY, with the year in full" : undefined}
            onChange={(e) => { setText(e.target.value); if (/^\d{1,2}[/.\-\s]\d{1,2}[/.\-\s]\d{4}$/.test(e.target.value.trim()) || !e.target.value.trim()) commit(e.target.value); }}
            onBlur={(e) => { commit(text); onBlur?.(e); }}
            onKeyDown={(e) => { if (e.key === "ArrowDown" && e.altKey) { e.preventDefault(); setOpen(true); } }}
            className={cn(
              "h-9 w-full min-w-0 rounded-md border border-input bg-card px-3 py-1 pr-9 text-base tabular-nums transition-[color,box-shadow,border-color] outline-none placeholder:text-muted-foreground md:text-sm",
              "hover:border-border-strong focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/40 disabled:cursor-not-allowed disabled:opacity-50",
              bad && "border-bad ring-bad/20",
              className,
            )}
            {...props}
          />
          <PopoverTrigger asChild>
            <button
              type="button"
              tabIndex={-1}
              disabled={disabled}
              aria-label="Open the calendar"
              className={cn("absolute right-1 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-50", open && "bg-accent text-foreground")}
            >
              <CalendarDays className="size-4" aria-hidden />
            </button>
          </PopoverTrigger>
        </div>
      </PopoverAnchor>
      <PopoverContent align="end" sideOffset={6} className="w-auto p-3" onOpenAutoFocus={(e) => e.preventDefault()}>
        <Calendar value={value} min={min} max={max} autoFocus onChange={(iso) => { setText(isoToDmy(iso)); setBad(false); onChange(iso); setOpen(false); }} />
      </PopoverContent>
    </Popover>
  );
});
