// The people of a meeting as a list (the People panel): admitted members with their department, where they are, a hand, and
// for the coordinator the waiting room with Admit buttons.
import { Hand, UserRoundCheck } from "lucide-react";
import type { Attendee } from "@/lib/live";
import { LoadingButton, initials } from "@/features/casefile/components/common";
import { cn } from "@/lib/utils";

const COLOURS = ["#2f6f8f", "#3e5cad", "#5b3fc4", "#1d6a44", "#8a5200", "#9c3d5e", "#2a7a74", "#6b4e2e"];
function colourOf(key: string): string {
  let h = 0;
  for (const ch of key) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return COLOURS[h % COLOURS.length];
}

export function PersonRow({ a, hand, me, action }: { a: Attendee; hand?: boolean; me?: boolean; action?: React.ReactNode }) {
  const where = a.status === "waiting" ? "waiting to be admitted" : a.status === "remote" ? "remote" : a.status === "present" ? "in the room" : a.status;
  return (
    <li className={cn("flex items-center gap-2.5 rounded-lg px-2 py-1.5", a.status === "waiting" && "bg-warn/10")} data-testid="person-row" data-user={a.user}>
      <span className="grid size-8 shrink-0 place-items-center rounded-full text-xs font-semibold text-white" style={{ background: colourOf(a.name) }} aria-hidden>{initials(a.name)}</span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5 text-sm font-medium text-stage-fg"><span className="truncate">{a.name}{me ? " (you)" : ""}</span>{a.head ? <span className="rounded bg-stage-raised px-1 text-[10px] text-stage-muted">head</span> : null}{hand || a.hand ? <Hand className="size-3.5 text-warn" aria-label="hand raised" /> : null}</span>
        <span className="block truncate text-xs text-stage-muted">{[a.department_name ?? a.department, where, a.online === false ? "offline" : ""].filter(Boolean).join(" · ")}</span>
      </span>
      {action}
    </li>
  );
}

export function PeopleList({ attendance, hands, me, canAdmit, onAdmit, admitting }: { attendance: Attendee[]; hands: Set<string>; me?: string | null; canAdmit?: boolean; onAdmit?: (user: string) => void; admitting?: string | null }) {
  const waiting = attendance.filter((a) => a.status === "waiting");
  const admitted = attendance.filter((a) => a.status === "present" || a.status === "remote");
  const absent = attendance.filter((a) => a.status === "absent");
  return (
    <div className="space-y-3">
      {waiting.length ? (
        <section>
          <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-warn">Waiting · {waiting.length}</h3>
          <ul className="space-y-0.5" data-testid="waiting-list">
            {waiting.map((a) => <PersonRow key={a.user} a={a} me={a.user === me} action={canAdmit && onAdmit ? <LoadingButton size="xs" loading={admitting === a.user} onClick={() => onAdmit(a.user)}><UserRoundCheck className="size-3" />Admit</LoadingButton> : undefined} />)}
          </ul>
        </section>
      ) : null}
      <section>
        <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-stage-muted">In the meeting · {admitted.length}</h3>
        {admitted.length ? <ul className="space-y-0.5">{admitted.map((a) => <PersonRow key={a.user} a={a} hand={hands.has(a.user)} me={a.user === me} />)}</ul> : <p className="text-sm text-stage-muted">No one has joined yet.</p>}
      </section>
      {absent.length ? (
        <section>
          <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-stage-muted">Expected, not here · {absent.length}</h3>
          <ul className="space-y-0.5 opacity-70">{absent.map((a) => <PersonRow key={a.user} a={a} />)}</ul>
        </section>
      ) : null}
    </div>
  );
}
