// /meetings/join: the 6-digit code from the coordinator, then the waiting room until admitted. Meetings-v2 5.2: while the meeting is
// recorded as text, the waiting room says "This meeting is being recorded as text. No audio is kept." (the join answer's summary row
// first, then the live state).
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { ArrowLeft, KeyRound } from "lucide-react";
import { ApiError } from "@/lib/api";
import { useSession } from "@/lib/session";
import { errorCode, useMeetingLive } from "@/lib/live";
import { joinMeeting, notBuiltYet } from "./api";
import { EmptyState, LoadingButton, NotYetState, errorText, fmtDate } from "@/features/casefile/components/common";
import { cn } from "@/lib/utils";
import { useLightForMeeting } from "@/lib/appearance";
import { RecordingNotice } from "./recorder/notice";

function WaitingRoom({ mid, label, recording }: { mid: string; label?: string; recording?: string | null }) {
  const nav = useNavigate();
  const { me } = useSession();
  const live = useMeetingLive(mid, { onEvent: (ev) => { if (ev.type === "admit" && ev.user === me?.user) nav(`/meetings/${mid}/member`, { replace: true }); } });
  useEffect(() => {
    const st = live.state?.me?.status;
    if (st === "present" || st === "remote") nav(`/meetings/${mid}/member`, { replace: true });
  }, [live.state, mid, nav]);
  return (
    <div className="surface p-6" data-testid="waiting-room">
      <EmptyState kind="wait" title="You are in the waiting room" text={`${label ? `${label}. ` : ""}The coordinator admits people from the control view. Keep this page open; it moves on by itself.`} />
      <RecordingNotice state={live.state ? live.state.recording?.state : recording} className="mb-3" />
      <p className="text-center text-xs text-muted-foreground" role="status">{live.status === "open" ? "Connected, waiting" : "Checking every 10 seconds"}</p>
    </div>
  );
}

export default function JoinPage() {
  useLightForMeeting();  // the meeting is always light (owner, 2 Nov 2026)
  const nav = useNavigate();
  const [code, setCode] = useState("");
  const [waitingFor, setWaitingFor] = useState<{ id: string; label?: string; recording?: string | null } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const join = useMutation({
    mutationFn: (c: string) => joinMeeting(c),
    onSuccess: (r) => {
      if (r.status === "admitted") nav(`/meetings/${r.meeting_id}/member`, { replace: true });
      else setWaitingFor({ id: r.meeting_id, label: r.meeting ? `Tumour Board, ${fmtDate(r.meeting.date)}${r.meeting.time ? ` at ${r.meeting.time}` : ""}` : undefined, recording: r.meeting?.recording ?? null });
    },
  });
  useEffect(() => { inputRef.current?.focus(); }, []);
  const digits = code.replace(/\D/g, "").slice(0, 6);
  const e = join.error;
  const code_ = errorCode(e);
  const err = e
    ? notBuiltYet(e) ? null
      : e instanceof ApiError && e.status === 404 ? "No meeting has this code. Check the digits with the MDT Coordinator."
      : e instanceof ApiError && (e.status === 410 || code_ === "code_expired") ? "This code has expired. Ask the MDT Coordinator for the new one."
      : e instanceof ApiError && e.status === 429 ? "Too many tries. Wait 15 minutes, then try again."
      : errorText(e)
    : null;
  if (waitingFor) return <div className="max-w-md mx-auto"><WaitingRoom mid={waitingFor.id} label={waitingFor.label} recording={waitingFor.recording} /></div>;
  return (
    <div className="max-w-md mx-auto space-y-3" data-testid="join-page">
      <p className="text-xs text-muted-foreground"><Link to="/meetings" className="hover:underline inline-flex items-center gap-1"><ArrowLeft className="size-3" aria-hidden />Meetings</Link></p>
      {notBuiltYet(e) ? <NotYetState what="Joining a meeting with a code" fallback="Ask the MDT Coordinator to add you to the old board session in /tb." /> : null}
      <form className="surface p-6 space-y-4" onSubmit={(ev) => { ev.preventDefault(); if (digits.length === 6) join.mutate(digits); }}>
        <div className="flex items-center gap-2"><KeyRound className="size-5 text-brand" aria-hidden /><h1>Join a meeting</h1></div>
        <p className="text-sm text-muted-foreground">Type the 6-digit code the MDT Coordinator shared. Hospital members only; you wait in the waiting room until admitted.</p>
        <label htmlFor="join-code" className="text-sm font-medium">Meeting code</label>
        <div className="relative" onClick={() => inputRef.current?.focus()}>
          <input ref={inputRef} id="join-code" value={digits} onChange={(ev) => setCode(ev.target.value)} inputMode="numeric" pattern="[0-9]*" autoComplete="one-time-code" maxLength={6} className="absolute inset-0 h-full w-full opacity-0 cursor-text" aria-describedby={err ? "join-error" : "join-help"} aria-invalid={!!err} />
          <div className="flex justify-between gap-2" aria-hidden>
            {Array.from({ length: 6 }).map((_, i) => (
              <span key={i} className={cn("grid h-14 flex-1 place-items-center rounded-md border-2 text-2xl font-mono bg-card transition-colors", err ? "border-bad/60" : i === digits.length ? "border-primary" : digits[i] ? "border-border-strong" : "border-border")}>{digits[i] ?? ""}</span>
            ))}
          </div>
        </div>
        {err ? <p id="join-error" role="alert" className="rounded-md status-bad px-3 py-2 text-sm">{err}</p> : <p id="join-help" className="text-xs text-muted-foreground">{digits.length < 6 ? `${6 - digits.length} more digit${6 - digits.length === 1 ? "" : "s"}` : "Ready to join"}</p>}
        <LoadingButton type="submit" className="w-full" loading={join.isPending} loadingText="Joining" disabled={digits.length !== 6} data-testid="join-submit">Join</LoadingButton>
      </form>
    </div>
  );
}
