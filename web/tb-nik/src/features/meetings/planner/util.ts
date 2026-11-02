// Small date helpers of the planner. Weekdays as the server counts them: 0 = Monday .. 6 = Sunday (meetings.WEEKDAY_NAMES).
import { formatDate, parseDate } from "@/lib/format";
import { todayIso } from "@/features/casefile/components/common";
import { useProtocols } from "@/hooks/useQueries";

export const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"] as const;
export const WEEKDAYS_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;

/** The server's weekday (0 = Monday) of a YYYY-MM-DD date; -1 when it is not one. */
export function weekdayIndex(iso?: string | null): number {
  const d = iso && /^\d{4}-\d{2}-\d{2}$/.test(iso) ? new Date(`${iso}T12:00:00`) : null;
  return d && !Number.isNaN(d.getTime()) ? (d.getDay() + 6) % 7 : -1;
}

/** "Friday 07/11/2026" */
export function dayAndDate(iso?: string | null): string {
  const i = weekdayIndex(iso);
  return i < 0 ? formatDate(iso ?? "") : `${WEEKDAYS[i]} ${formatDate(parseDate(`${iso}T12:00:00`))}`;
}

/** "Friday 07/11/2026 at 16:00" */
export function whenWords(iso?: string | null, time?: string | null): string {
  return `${dayAndDate(iso)}${time ? ` at ${time}` : ""}`;
}

/** "Every week on Friday" for a meeting of a weekly series (members cannot read the series itself; its weekday is the meeting's). */
export function everyWeekOn(iso?: string | null): string {
  const i = weekdayIndex(iso);
  return i < 0 ? "Every week" : `Every week on ${WEEKDAYS[i]}`;
}

/** The next `n` dates of a weekday from today, today only when the time has not passed (meetings._slot_dates). */
export function nextDates(weekday: number, time: string, n = 4, now = new Date()): string[] {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 12);
  const first = new Date(today);
  first.setDate(today.getDate() + ((weekday - (today.getDay() + 6) % 7 + 7) % 7));
  const hm = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
  if (first.getTime() === today.getTime() && time && time <= hm) first.setDate(first.getDate() + 7);
  return Array.from({ length: n }, (_, i) => {
    const d = new Date(first);
    d.setDate(first.getDate() + 7 * i);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  });
}

/** The meeting's day has come (today or a day that passed without a start). */
export function dayHasCome(iso?: string | null): boolean {
  return !!iso && iso <= todayIso();
}

/** The cancer of a row in words ("Breast cancer"), from the hospital's checklists; the id in words when it is not one of them. */
export function useCancerLabel(): (protocol?: string | null) => string {
  const q = useProtocols();
  const map = new Map((q.data?.protocols ?? []).map((p) => [p.id, p.label]));
  return (protocol) => (protocol ? map.get(protocol) ?? `${protocol.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase())}` : "");
}
