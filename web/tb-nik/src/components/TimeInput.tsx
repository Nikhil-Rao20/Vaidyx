// A time typed as HH:MM (24-hour clock) with a list of quarter-hour slots in a popover anchored to the field. The value in and
// out is "HH:MM" or "".
import { forwardRef, useEffect, useRef, useState, type ComponentProps } from "react";
import { Clock } from "lucide-react";
import { Popover, PopoverAnchor, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

const pad = (n: number) => String(n).padStart(2, "0");
export function cleanTime(text: string): string | null {
  const t = text.trim();
  if (!t) return "";
  const m = /^(\d{1,2})[:.\s]?(\d{2})$/.exec(t);
  if (!m) return null;
  const h = +m[1], mi = +m[2];
  if (h > 23 || mi > 59) return null;
  return `${pad(h)}:${pad(mi)}`;
}
const SLOTS = Array.from({ length: 4 * 24 }, (_, i) => `${pad(Math.floor(i / 4))}:${pad((i % 4) * 15)}`);

export const TimeInput = forwardRef<HTMLInputElement, Omit<ComponentProps<"input">, "value" | "onChange" | "type"> & {
  value: string;
  onChange: (hhmm: string) => void;
  wrapperClassName?: string;
  /** The first slot shown when the field is empty (a board usually meets in working hours). */
  startAt?: string;
}>(function TimeInput({ value, onChange, className, wrapperClassName, disabled, onBlur, startAt = "08:00", ...props }, ref) {
  const [text, setText] = useState(value);
  const [bad, setBad] = useState(false);
  const [open, setOpen] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  useEffect(() => { if ((cleanTime(text) ?? "") !== value) { setText(value); setBad(false); } }, [value]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!open) return;
    const want = value || startAt;
    window.setTimeout(() => listRef.current?.querySelector<HTMLButtonElement>(`[data-slot-time="${want}"]`)?.scrollIntoView({ block: "center" }), 0);
  }, [open, value, startAt]);
  const commit = (t: string) => {
    const v = cleanTime(t);
    setBad(v === null);
    if (v !== null) { setText(v); onChange(v); }
  };
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverAnchor asChild>
        <div className={cn("relative", wrapperClassName)}>
          <input
            ref={ref}
            type="text"
            inputMode="numeric"
            placeholder="HH:MM"
            autoComplete="off"
            value={text}
            disabled={disabled}
            aria-invalid={bad || props["aria-invalid"] || undefined}
            title={bad ? "Type the time as HH:MM, 24-hour clock" : undefined}
            onChange={(e) => setText(e.target.value)}
            onBlur={(e) => { commit(text); onBlur?.(e); }}
            className={cn(
              "h-9 w-full min-w-0 rounded-md border border-input bg-card px-3 py-1 pr-9 text-base tabular-nums transition-[color,box-shadow,border-color] outline-none placeholder:text-muted-foreground md:text-sm",
              "hover:border-border-strong focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/40 disabled:cursor-not-allowed disabled:opacity-50",
              bad && "border-bad ring-bad/20",
              className,
            )}
            {...props}
          />
          <PopoverTrigger asChild>
            <button type="button" tabIndex={-1} disabled={disabled} aria-label="Pick a time" className={cn("absolute right-1 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-50", open && "bg-accent text-foreground")}>
              <Clock className="size-4" aria-hidden />
            </button>
          </PopoverTrigger>
        </div>
      </PopoverAnchor>
      <PopoverContent align="end" sideOffset={6} className="w-36 p-1" onOpenAutoFocus={(e) => e.preventDefault()}>
        <div ref={listRef} className="scroll-thin max-h-60 overflow-y-auto" role="listbox" aria-label="Times">
          {SLOTS.map((t) => (
            <button
              key={t}
              type="button"
              role="option"
              aria-selected={t === value}
              data-slot-time={t}
              onClick={() => { setText(t); setBad(false); onChange(t); setOpen(false); }}
              className={cn("block w-full rounded-md px-3 py-1.5 text-left text-sm tabular-nums hover:bg-accent", t === value && "bg-secondary font-semibold text-secondary-foreground", t.endsWith(":00") && "mt-0.5")}
            >
              {t}
            </button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
});
