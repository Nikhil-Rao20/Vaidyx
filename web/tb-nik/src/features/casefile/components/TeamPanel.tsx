// Team: the owner, residents with end dates, consultants of other departments the owner let in ("Ask to join", night-v3
// item 1.1: they read the whole Case File, the owner's decisions stay with the owner), participating departments, the join
// code (copy, regenerate), pending joins to approve or reject (a resident or a consultant, with the department and the note),
// remove a resident or a member.
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Check, Copy, KeyRound, RefreshCw, Trash2, UserRoundCheck, UserRoundX, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { approveJoin, dropJoinCode, newJoinCode, rejectJoin, removeResident } from "../api";
import type { Team } from "../types";

/** The team as GET /cases/{id}/team gives it since night-v3 item 1.1: consultant members, and each pending entry's role and note. */
type Member = { user: string; name: string; role?: string; department?: string; department_label?: string; added_by?: string; added_at?: string };
type Pending = Team["pending"][number] & { role?: "resident" | "consultant" | string; note?: string };
import { EmptyState, LoadingButton, NotYetState, StatusChip, errorText, fmtDate, fmtDateTime, useAnnounce, useCopy } from "./common";

export function TeamPanel({ caseId, team, derived, isOwner, resident, onChanged, me }: { caseId: string; team: Team | null; derived: boolean; isOwner: boolean; resident: boolean; onChanged: () => Promise<void>; me: string }) {
  const [copied, copy] = useCopy();
  const [announce, liveNode] = useAnnounce();
  const [err, setErr] = useState<string | null>(null);
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null);
  const wrap = <T,>(fn: () => Promise<T>, said: string) => async () => { setErr(null); try { await fn(); announce(said); await onChanged(); } catch (e) { setErr(errorText(e)); } };
  const code = useMutation({ mutationFn: wrap(() => newJoinCode(caseId), "New join code ready.") });
  const drop = useMutation({ mutationFn: wrap(() => dropJoinCode(caseId), "Join code removed.") });
  const approve = useMutation({ mutationFn: (u: string) => wrap(() => approveJoin(caseId, u), "Approved.")() });
  const reject = useMutation({ mutationFn: (u: string) => wrap(() => rejectJoin(caseId, u), "Rejected.")() });
  const remove = useMutation({ mutationFn: (u: string) => wrap(() => removeResident(caseId, u), "Removed from the team.")(), onSettled: () => setConfirmRemove(null) });
  if (!team) return <EmptyState title="No team information" text="The server did not say who is on this Case File." />;
  const busy = code.isPending || drop.isPending || approve.isPending || reject.isPending || remove.isPending;
  const members: Member[] = (team as Team & { members?: Member[] }).members ?? [];
  const pending = team.pending as Pending[];
  return (
    <div className="space-y-4" data-testid="team-panel">
      {liveNode}
      {derived ? <NotYetState what="Teams with join codes" fallback="Showing the owner and participating departments from the Case File. Residents and join codes come with the team route." /> : null}
      <section>
        <h3 className="text-sm font-semibold text-foreground flex items-center gap-1.5"><Users className="size-4" aria-hidden />Owner</h3>
        <p className="text-sm mt-1">{(team.owner.department_label ?? team.owner.department ?? "").replace(/_/g, " ") || "No owner yet"}</p>
        <ul className="mt-1 space-y-0.5">
          {team.owner.doctors.map((d) => <li key={d.user} className="text-sm text-foreground">{d.name}{d.user === me ? " (you)" : ""}</li>)}
          {!team.owner.doctors.length ? <li className="text-xs text-muted-foreground">No consultant listed yet.</li> : null}
        </ul>
      </section>
      <section>
        <h3 className="text-sm font-semibold text-foreground">Residents</h3>
        {team.residents.length === 0 ? <p className="text-xs text-muted-foreground mt-1">No residents on this Case File.</p> : null}
        <ul className="mt-1 space-y-1">
          {team.residents.map((r) => (
            <li key={r.user} className="flex items-center gap-2 text-sm">
              <span className="flex-1 min-w-0 truncate">{r.name}{r.user === me ? " (you)" : ""}<span className="text-xs text-muted-foreground ml-1">{r.end_date ? `${r.expired ? "ended" : "until"} ${fmtDate(r.end_date)}` : "no end date"}</span>{r.expired ? <StatusChip kind="muted" className="ml-1">access ended</StatusChip> : null}</span>
              {(isOwner || r.user === me) && !derived ? (
                confirmRemove === r.user ? (
                  <span className="inline-flex gap-1">
                    <LoadingButton size="xs" variant="destructive" loading={remove.isPending} onClick={() => remove.mutate(r.user)}>Remove</LoadingButton>
                    <Button size="xs" variant="ghost" onClick={() => setConfirmRemove(null)}>Keep</Button>
                  </span>
                ) : <Button size="xs" variant="ghost" onClick={() => setConfirmRemove(r.user)} aria-label={`Remove ${r.name}`} disabled={busy}><Trash2 className="size-3" />{r.user === me ? "Leave" : "Remove"}</Button>
              ) : null}
            </li>
          ))}
        </ul>
      </section>
      {members.length ? (
        <section data-testid="team-members">
          <h3 className="text-sm font-semibold text-foreground">Consultants of other departments</h3>
          <p className="text-xs text-muted-foreground mt-0.5">They read the whole Case File; the owner's decisions stay with the owner.</p>
          <ul className="mt-1 space-y-1">
            {members.map((m) => (
              <li key={m.user} className="flex items-center gap-2 text-sm">
                <span className="flex-1 min-w-0 truncate">{m.name}{m.user === me ? " (you)" : ""}{m.department_label ? <span className="text-xs text-muted-foreground ml-1">{m.department_label}</span> : null}{m.added_at ? <span className="text-xs text-muted-foreground ml-1">since {fmtDate(m.added_at)}</span> : null}</span>
                {(isOwner || m.user === me) && !derived ? (
                  confirmRemove === m.user ? (
                    <span className="inline-flex gap-1">
                      <LoadingButton size="xs" variant="destructive" loading={remove.isPending} onClick={() => remove.mutate(m.user)}>Remove</LoadingButton>
                      <Button size="xs" variant="ghost" onClick={() => setConfirmRemove(null)}>Keep</Button>
                    </span>
                  ) : <Button size="xs" variant="ghost" onClick={() => setConfirmRemove(m.user)} aria-label={`Remove ${m.name}`} disabled={busy}><Trash2 className="size-3" />{m.user === me ? "Leave" : "Remove"}</Button>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <section>
        <h3 className="text-sm font-semibold text-foreground">Departments taking part</h3>
        {team.departments.length === 0 ? <p className="text-xs text-muted-foreground mt-1">Only the owner's department so far.</p> : null}
        <ul className="mt-1 flex flex-wrap gap-1">{team.departments.map((d) => <li key={d.id}><StatusChip kind="info">{(d.label ?? d.id).replace(/_/g, " ")}{d.since ? `, since ${fmtDate(d.since)}` : ""}</StatusChip></li>)}</ul>
      </section>
      {isOwner && !resident ? (
        <section className="rounded-md border border-border p-3">
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-1.5"><KeyRound className="size-4" aria-hidden />Join code</h3>
          <p className="text-xs text-muted-foreground mt-0.5">A resident types this 6-digit code on their home page to join. Residents of your department join at once; others wait for your approval.</p>
          {team.join_code && team.join_code.code ? (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className="mono text-2xl tracking-[0.3em] font-medium" data-testid="join-code">{team.join_code.code}</span>
              <Button size="sm" variant="outline" onClick={() => copy(team.join_code!.code)} aria-label="Copy the join code">{copied ? <Check className="size-4" /> : <Copy className="size-4" />}{copied ? "Copied" : "Copy"}</Button>
              <span className="text-xs text-muted-foreground">expires {fmtDateTime(team.join_code.expires_at)}{typeof team.join_code.uses === "number" ? `, used ${team.join_code.uses} times` : ""}</span>
            </div>
          ) : <p className="text-sm mt-2 text-muted-foreground">No active code.</p>}
          {!derived ? (
            <div className="mt-2 flex gap-1.5">
              <LoadingButton size="sm" loading={code.isPending} onClick={() => code.mutate()}><RefreshCw className="size-4" />{team.join_code ? "Regenerate" : "Create a code"}</LoadingButton>
              {team.join_code ? <LoadingButton size="sm" variant="ghost" loading={drop.isPending} onClick={() => drop.mutate()}>Remove code</LoadingButton> : null}
            </div>
          ) : null}
        </section>
      ) : null}
      {pending.length ? (
        <section data-testid="team-pending">
          <h3 className="text-sm font-semibold text-foreground">Waiting to join</h3>
          <ul className="mt-1 space-y-1">
            {pending.map((p) => (
              <li key={p.user} className="flex flex-wrap items-center gap-2 text-sm">
                <span className="flex-1 min-w-0">
                  {p.name}
                  <span className="text-xs text-muted-foreground"> ({[p.role === "consultant" ? "consultant" : "resident", p.department_label].filter(Boolean).join(", ")})</span>{" "}
                  <span className="text-xs text-muted-foreground">asked {fmtDateTime(p.requested_at)}</span>
                  {p.note ? <span className="block text-xs text-muted-foreground break-words">Note: {p.note}</span> : null}
                </span>
                {isOwner ? (
                  <>
                    <LoadingButton size="xs" loading={approve.isPending && approve.variables === p.user} onClick={() => approve.mutate(p.user)}><UserRoundCheck className="size-3" />Approve</LoadingButton>
                    <LoadingButton size="xs" variant="outline" loading={reject.isPending && reject.variables === p.user} onClick={() => reject.mutate(p.user)}><UserRoundX className="size-3" />Reject</LoadingButton>
                  </>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {err ? <p role="alert" className="text-xs text-bad">{err}</p> : null}
    </div>
  );
}
