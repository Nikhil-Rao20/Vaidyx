// A month calendar (weeks start on Monday, as on an Indian ward board): previous / next month, Today, a 7 x 6 grid with the
// arrow keys moving the focus, Enter choosing. Values in and out are ISO YYYY-MM-DD. The month slides when it changes.
import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];
const pad = (n: number) => String(n).padStart(2, "0");
export const toIso = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
function fromIso(iso?: string | null): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
  return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null;
}

function monthGrid(year: number, month: number): Date[] {
  const first = new Date(year, month, 1);
  const lead = (first.getDay() + 6) % 7; // Monday = 0
  const start = new Date(year, month, 1 - lead);
  return Array.from({ length: 42 }, (_, i) => new Date(start.getFullYear(), start.getMonth(), start.getDate() + i));
}

export function Calendar({ value, onChange, min, max, className, autoFocus }: {
  value: string;
  onChange: (iso: string) => void;
  min?: string;
  max?: string;
  className?: string;
  autoFocus?: boolean;
}) {
  const selected = fromIso(value);
  const today = new Date();
  const [view, setView] = useState(() => { const d = selected ?? today; return { y: d.getFullYear(), m: d.getMonth() }; });
  const [dir, setDir] = useState(0);
  const [focusIso, setFocusIso] = useState(() => toIso(selected ?? today));
  const reduce = useReducedMotion();
  const gridRef = useRef<HTMLDivElement>(null);
  const days = useMemo(() => monthGrid(view.y, view.m), [view]);
  useEffect(() => { const d = fromIso(value); if (d) { setView({ y: d.getFullYear(), m: d.getMonth() }); setFocusIso(toIso(d)); } }, [value]);
  useEffect(() => { if (autoFocus) gridRef.current?.querySelector<HTMLButtonElement>('[tabindex="0"]')?.focus(); }, [autoFocus]);

  const move = (delta: number) => {
    setDir(delta);
    setView((v) => { const d = new Date(v.y, v.m + delta, 1); return { y: d.getFullYear(), m: d.getMonth() }; });
  };
  const allowed = (iso: string) => !(min && iso < min) && !(max && iso > max);
  const onKey = (e: React.KeyboardEvent, d: Date) => {
    const step: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };
    if (e.key in step) {
      e.preventDefault();
      const n = new Date(d.getFullYear(), d.getMonth(), d.getDate() + step[e.key]);
      if (n.getMonth() !== view.m || n.getFullYear() !== view.y) { setDir(n > d ? 1 : -1); setView({ y: n.getFullYear(), m: n.getMonth() }); }
      setFocusIso(toIso(n));
      window.setTimeout(() => gridRef.current?.querySelector<HTMLButtonElement>(`[data-iso="${toIso(n)}"]`)?.focus(), 0);
    } else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); const iso = toIso(d); if (allowed(iso)) onChange(iso); }
  };

  return (
    <div className={cn("w-[18.5rem] select-none", className)} role="group" aria-label="Calendar">
      <div className="mb-2 flex items-center justify-between">
        <Button type="button" variant="ghost" size="icon-sm" onClick={() => move(-1)} aria-label="Previous month"><ChevronLeft className="size-4" /></Button>
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-foreground" aria-live="polite">{MONTHS[view.m]} {view.y}</span>
          <Button type="button" variant="ghost" size="xs" onClick={() => { const t = toIso(today); setDir(0); setView({ y: today.getFullYear(), m: today.getMonth() }); setFocusIso(t); if (allowed(t)) onChange(t); }}>Today</Button>
        </div>
        <Button type="button" variant="ghost" size="icon-sm" onClick={() => move(1)} aria-label="Next month"><ChevronRight className="size-4" /></Button>
      </div>
      <div className="grid grid-cols-7 text-center text-[11px] font-medium text-muted-foreground" aria-hidden>
        {DAYS.map((d) => <span key={d} className="py-1">{d}</span>)}
      </div>
      <div className="relative overflow-hidden" ref={gridRef}>
        <AnimatePresence initial={false} mode="popLayout" custom={dir}>
          <motion.div
            key={`${view.y}-${view.m}`}
            custom={dir}
            initial={reduce || !dir ? { opacity: 0 } : { opacity: 0, x: dir * 24 }}
            animate={{ opacity: 1, x: 0 }}
            exit={reduce || !dir ? { opacity: 0 } : { opacity: 0, x: dir * -24 }}
            transition={{ duration: 0.18 }}
            className="grid grid-cols-7 gap-y-0.5"
            role="grid"
          >
            {days.map((d) => {
              const iso = toIso(d);
              const inMonth = d.getMonth() === view.m;
              const isSel = selected ? toIso(selected) === iso : false;
              const isToday = toIso(today) === iso;
              const ok = allowed(iso);
              return (
                <button
                  key={iso}
                  type="button"
                  role="gridcell"
                  data-iso={iso}
                  tabIndex={iso === focusIso ? 0 : -1}
                  aria-selected={isSel}
                  aria-label={d.toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" })}
                  disabled={!ok}
                  onClick={() => onChange(iso)}
                  onKeyDown={(e) => onKey(e, d)}
                  onFocus={() => setFocusIso(iso)}
                  className={cn(
                    "mx-auto grid size-9 place-items-center rounded-full text-sm tabular-nums outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
                    isSel ? "bg-primary font-semibold text-primary-foreground" : ok ? "hover:bg-accent" : "text-muted-foreground/50",
                    !inMonth && !isSel && "text-muted-foreground/60",
                    isToday && !isSel && "ring-1 ring-inset ring-primary/60 font-semibold text-foreground",
                  )}
                >
                  {d.getDate()}
                </button>
              );
            })}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
