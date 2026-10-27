// The people of a meeting as a list (the People panel): admitted members with their department, where they are, their role
// badges, a hand with its order number, the microphone and camera when the call knows them, and for the coordinator the waiting
// room with Admit buttons. Also the small pieces the call's side panels share (a section heading, an action runner).
import { useCallback, useState, type ReactNode } from "react";
import { Camera, CameraOff, Hand, Mic, MicOff, UserRoundCheck } from "lucide-react";
import type { Attendee, MeetingState } from "@/lib/live";
import { BADGE_WORD, type RoleBadge } from "../call/types";
import { LoadingButton, errorText, initials } from "@/features/casefile/components/common";
import { cn } from "@/lib/utils";

const COLOURS = ["#2f6f8f", "#3e5cad", "#5b3fc4", "#1d6a44", "#8a5200", "#9c3d5e", "#2a7a74", "#6b4e2e"];
function colourOf(key: string): string {
  let h = 0;
  for (const ch of key) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return COLOURS[h % COLOURS.length];
}

/** The order of the raised hands: 1 for the first raised. Kept in the server's order unless every hand carries its time. */
export function handOrder(hands: MeetingState["hands"] | undefined): Map<string, number> {
  const rows = (hands ?? []).map((h, i) => (typeof h === "string" ? { user: h, at: undefined as string | undefined, i } : { user: h.user, at: h.at, i }));
  if (rows.length && rows.every((r) => !!r.at)) rows.sort((a, b) => (a.at! < b.at! ? -1 : a.at! > b.at! ? 1 : a.i - b.i));
  const out = new Map<string, number>();
  for (const r of rows) if (r.user && !out.has(r.user)) out.set(r.user, out.size + 1);
  return out;
}

/** Where a person is, in words. */
export function whereWord(a: Attendee): string {
  if (a.status === "waiting") return "waiting to be admitted";
  if (a.status === "present" || (a.status === "remote" && a.mode === "room")) return "in the room";
  if (a.status === "remote") return "remote";
  if (a.status === "absent") return "not here";
  return a.status;
}

export function PersonRow({ a, hand, me, action, badges, handNo, mic, cam, menu }: {
  a: Attendee; hand?: boolean; me?: boolean; action?: ReactNode;
  /** The role badges (head, coordinator, presenter, outside expert); without them the plain "head" mark of the attendance shows. */
  badges?: RoleBadge[];
  /** The hand's place in the queue ("hand 2"). */
  handNo?: number;
  /** The microphone and camera when the call knows them (null: not in the call). */
  mic?: boolean | null; cam?: boolean | null;
  menu?: ReactNode;
}) {
  const raised = !!(hand || a.hand || handNo);
  const marks = badges ?? (a.head ? (["head"] as RoleBadge[]) : []);
  const media = [mic === true ? "microphone on" : mic === false ? "microphone off" : "", cam === true ? "camera on" : cam === false ? "camera off" : ""].filter(Boolean);
  return (
    <li className={cn("flex items-center gap-2.5 rounded-lg px-2 py-1.5", a.status === "waiting" && "bg-warn/10")} data-testid="person-row" data-user={a.user}>
      <span className="grid size-8 shrink-0 place-items-center rounded-full text-xs font-semibold text-white" style={{ background: colourOf(a.name) }} aria-hidden>{initials(a.name)}</span>
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-1.5 text-sm font-medium text-stage-fg">
          <span className="truncate">{a.name}{me ? " (you)" : ""}</span>
          {marks.map((b) => <span key={b} className="rounded bg-stage-raised px-1 text-[10px] font-medium text-stage-muted">{BADGE_WORD[b].toLowerCase()}</span>)}
          {raised ? <span className="inline-flex items-center gap-0.5 text-[11px] text-warn"><Hand className="size-3.5" aria-hidden />{handNo ? `hand ${handNo}` : "hand raised"}</span> : null}
        </span>
        <span className="flex items-center gap-1.5 text-xs text-stage-muted">
          <span className="min-w-0 truncate">{[a.department_name ?? a.department, whereWord(a), a.online === false ? "offline" : ""].filter(Boolean).join(" · ")}</span>
          {mic === true ? <Mic className="size-3 shrink-0" aria-hidden /> : mic === false ? <MicOff className="size-3 shrink-0" aria-hidden /> : null}
          {cam === true ? <Camera className="size-3 shrink-0" aria-hidden /> : cam === false ? <CameraOff className="size-3 shrink-0" aria-hidden /> : null}
          {media.length ? <span className="sr-only">{media.join(", ")}</span> : null}
        </span>
      </span>
      {action}
      {menu}
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

// ---- pieces the call's side panels share ----------------------------------------------------------------------------------
/** A section of a side panel: a small heading (with an optional count and a control on the right) over its body. */
export function PanelSection({ title, count, tone, right, children, className, id }: { title: string; count?: number; tone?: "warn"; right?: ReactNode; children: ReactNode; className?: string; id?: string }) {
  return (
    <section className={className} aria-labelledby={id}>
      <div className="mb-1 flex items-center gap-2">
        <h3 id={id} className={cn("min-w-0 flex-1 text-[11px] font-semibold uppercase tracking-wide", tone === "warn" ? "text-warn" : "text-stage-muted")}>{title}{count !== undefined ? ` · ${count}` : ""}</h3>
        {right}
      </div>
      {children}
    </section>
  );
}

/** Runs one panel action at a time: which one is pending (by a key) and the server's message when it failed. */
export function usePanelAction() {
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(async (key: string, fn: () => Promise<unknown>): Promise<boolean> => {
    setPending(key); setError(null);
    try { await fn(); return true; } catch (e) { setError(errorText(e)); return false; } finally { setPending(null); }
  }, []);
  return { pending, error, run, clear: () => setError(null) };
}
