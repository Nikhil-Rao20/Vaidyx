// The side of the planner (meetings-v2 3.3, owner D9 and D10): the join code (made by itself, valid through the meeting; New code makes
// another), the members (made by themselves: the board heads and the teams of the Case Files listed), the meeting PDF (the agenda before,
// the record after), and More: minutes per case, video, the room screen for a separate projector computer, Cancel this meeting (with a
// reason; it says where its Case Files go).
import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Check, ChevronDown, Copy, Download, KeyRound, MonitorPlay, Users, Video, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { plural } from "@/lib/format";
import { cn } from "@/lib/utils";
import { LoadingButton, errorText, fmtDateTime, useCopy } from "@/features/casefile/components/common";
import { MembersStrip } from "../components/shared";
import { listOpenMeetings, meetingPdfUrl } from "../api";
import type { PlanMeeting, PlanState } from "./types";
import { whenWords } from "./util";

export function JoinCodeCard({ code, onNew, busy, error }: { code: PlanState["code"]; onNew: () => void; busy: boolean; error?: string | null }) {
  const [copied, copy] = useCopy();
  return (
    <section className="surface p-3 sm:p-4" aria-labelledby="code-title" data-testid="join-code-card">
      <h2 id="code-title" className="flex items-center gap-1.5 text-sm font-semibold"><KeyRound className="size-4 text-brand" aria-hidden />Join code</h2>
      {code ? (
        <>
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <span className="mono text-3xl tracking-[0.3em] text-foreground" data-testid="meeting-code">{code.value}</span>
            <Button size="sm" variant="outline" onClick={() => void copy(code.value)} aria-label="Copy the join code">{copied ? <Check className="size-4" /> : <Copy className="size-4" />}{copied ? "Copied" : "Copy"}</Button>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">Members type it in Meetings, Join with a code. It works until {fmtDateTime(code.expires_at)}.</p>
        </>
      ) : (
        <p className="mt-1 text-sm text-muted-foreground" aria-busy={busy}>{busy ? "Making the code" : "No code yet."}</p>
      )}
      {error ? <p role="alert" className="mt-1 text-xs text-bad">{error}</p> : null}
      <LoadingButton size="sm" variant="ghost" className="-ml-2 mt-1" loading={busy && !!code} loadingText="Making a new code" onClick={onNew} disabled={busy} data-testid="new-code">
        <KeyRound className="size-3.5" aria-hidden />{code ? "New code (the old one stops working)" : "Make the code"}
      </LoadingButton>
    </section>
  );
}

function headName(h: NonNullable<PlanState["heads"]>[number]): string {
  return typeof h === "string" ? h.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase()) : h.name || h.id;
}

/** The members, made by themselves from the board heads and the case teams of the agenda (the departments the agenda goes to). */
export function MembersCard({ state }: { state: PlanState }) {
  const heads = (state.heads ?? []).map(headName);
  const teams = new Map<string, number>();
  for (const r of [...state.agenda.discussion, ...state.agenda.noting]) {
    const d = r.owner_department_name || r.owner_department;
    if (d) teams.set(d, (teams.get(d) ?? 0) + 1);
  }
  const joined = state.attendance.filter((a) => a.status === "present" || a.status === "remote" || a.status === "waiting");
  const chip = "inline-flex items-center rounded-full border border-border bg-card px-2 py-0.5 text-xs text-foreground";
  return (
    <section className="surface p-3 sm:p-4" aria-labelledby="members-title" data-testid="plan-members">
      <h2 id="members-title" className="flex items-center gap-1.5 text-sm font-semibold"><Users className="size-4 text-brand" aria-hidden />Members</h2>
      <p className="mt-0.5 text-xs text-muted-foreground">Made by Vaidyx from the board heads and the teams of the Case Files listed. The agenda goes to all of them.</p>
      <p className="mt-2 text-xs font-medium text-muted-foreground">Board heads</p>
      <div className="mt-1 flex flex-wrap gap-1" data-testid="members-heads">
        {heads.length ? heads.map((h) => <span key={h} className={chip}>{h}</span>) : <span className="text-xs text-muted-foreground">None set by the hospital.</span>}
      </div>
      <p className="mt-2 text-xs font-medium text-muted-foreground">Case teams</p>
      <div className="mt-1 flex flex-wrap gap-1" data-testid="members-teams">
        {teams.size ? [...teams].map(([d, n]) => <span key={d} className={chip}>{d}<span className="ml-1 text-muted-foreground">{n}</span></span>) : <span className="text-xs text-muted-foreground">They come with the Case Files.</span>}
      </div>
      {joined.length ? <div className="mt-3 border-t border-border pt-2"><p className="mb-1 text-xs font-medium text-muted-foreground">Joined</p><MembersStrip attendance={state.attendance} hands={state.hands} /></div> : null}
    </section>
  );
}

export function PdfCard({ mid, after }: { mid: string; after: boolean }) {
  return (
    <section className="surface p-3 sm:p-4" aria-label="The meeting PDF" data-testid="pdf-card">
      <Button asChild variant="outline" className="w-full justify-start">
        <a href={meetingPdfUrl(mid)} download data-testid="meeting-pdf"><Download className="size-4" />{after ? "Download the meeting record (PDF)" : "Download the agenda (PDF)"}</a>
      </Button>
      <p className="mt-1.5 text-xs text-muted-foreground">{after ? "The cases, the board's questions, the decisions and the minutes." : "The cases and their questions for the board. After the meeting it also carries the decisions and the minutes."}</p>
    </section>
  );
}

/** Where the Case Files of a cancelled meeting go: the next open meeting after it (meetings._rehome_plan), else they wait. */
function cancelText(m: PlanMeeting, total: number, next: PlanMeeting | null | undefined, loading: boolean): string {
  const series = m.series_id ? " The weekly series goes on; only this date is skipped." : "";
  if (total === 0) return `It has no Case File. The member departments are told.${series}`;
  const what = plural(total, "Case File");
  const where = loading ? `Its ${what} go to the next planned meeting.`
    : next ? `Its ${what} go to the next planned meeting, ${whenWords(next.date, next.time)}, in the same lists.`
    : `No later meeting is planned: its ${what} wait and join the next meeting you plan.`;
  return `${where} The member departments and each treating team are told.${series}`;
}

export function MoreCard({ m, total, videoAvailable, onSave, onCancel }: {
  m: PlanMeeting; total: number; videoAvailable: boolean;
  onSave: (fields: { minutes_per_case?: number; video?: boolean }) => Promise<unknown>;
  onCancel: (reason: string) => Promise<unknown>;
}) {
  const [open, setOpen] = useState(false);
  const [mins, setMins] = useState(String(m.minutes_per_case ?? 10));
  const [busy, setBusy] = useState<"mins" | "video" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [cancelOpen, setCancelOpen] = useState(false);
  const openQ = useQuery({ queryKey: ["meetings", "open"], queryFn: listOpenMeetings, enabled: cancelOpen, staleTime: 15_000 });
  const key = (x: PlanMeeting) => `${x.date} ${x.time ?? ""}`;
  const next = openQ.data ? ((openQ.data.meetings ?? []) as PlanMeeting[]).filter((x) => x.id !== m.id && key(x) > key(m)).sort((a, b) => key(a).localeCompare(key(b)))[0] ?? null : undefined;
  const minsN = Number(mins);
  const minsBad = !Number.isInteger(minsN) || minsN < 1 || minsN > 60;
  const save = async (what: "mins" | "video", f: { minutes_per_case?: number; video?: boolean }) => {
    setBusy(what); setErr(null);
    try { await onSave(f); } catch (e) { setErr(errorText(e)); } finally { setBusy(null); }
  };
  return (
    <section className="surface" data-testid="plan-more">
      <Collapsible open={open} onOpenChange={setOpen}>
        <CollapsibleTrigger asChild>
          <button type="button" className="flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-sm font-semibold hover:bg-muted sm:px-4" aria-expanded={open} data-testid="plan-more-toggle">
            More<span className="font-normal text-muted-foreground">minutes per case, video, cancel</span><span className="flex-1" /><ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} aria-hidden />
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="space-y-3 border-t border-border px-3 py-3 sm:px-4">
            <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); if (!minsBad) void save("mins", { minutes_per_case: minsN }); }}>
              <div><Label htmlFor="plan-mins">Minutes per case</Label><Input id="plan-mins" type="number" inputMode="numeric" min={1} max={60} value={mins} onChange={(e) => setMins(e.target.value)} className="mt-1 w-24" aria-invalid={minsBad} /></div>
              <LoadingButton type="submit" size="sm" variant="outline" loading={busy === "mins"} disabled={minsBad || minsN === m.minutes_per_case} data-testid="save-minutes">Save</LoadingButton>
            </form>
            {minsBad ? <p className="-mt-2 text-xs text-bad">1 to 60 minutes.</p> : null}
            <div className="flex items-center gap-2">
              <Switch id="plan-video" checked={!!m.video} disabled={!videoAvailable || busy === "video"} onCheckedChange={(v) => void save("video", { video: v })} />
              <Label htmlFor="plan-video" className="inline-flex items-center gap-1"><Video className="size-4" aria-hidden />Video for remote members{!videoAvailable ? <span className="text-xs text-muted-foreground">(not set up)</span> : null}</Label>
            </div>
            {err ? <p role="alert" className="text-xs text-bad">{err}</p> : null}
            <Button asChild size="sm" variant="ghost" className="-ml-2">
              <Link to={`/meetings/${m.id}/room`} target="_blank" rel="noopener" title="For a hospital that drives the projector from another computer"><MonitorPlay className="size-4" />Open the room screen on another computer</Link>
            </Button>
            <div className="border-t border-border pt-3">
              <Button size="sm" variant="outline" className="border-bad/40 text-bad hover:bg-bad-soft hover:text-bad" onClick={() => setCancelOpen(true)} data-testid="cancel-meeting"><XCircle className="size-4" />Cancel this meeting</Button>
            </div>
          </div>
        </CollapsibleContent>
      </Collapsible>
      <ConfirmDialog open={cancelOpen} onOpenChange={setCancelOpen} destructive requireReason reasonLabel="Reason (shown to the members)" title="Cancel this meeting?"
        confirmText="Cancel the meeting" cancelText="Keep the meeting" doneText="Cancelled"
        text={<span data-testid="cancel-where">{cancelText(m, total, next, openQ.isLoading)}</span>}
        onConfirm={(reason) => onCancel(reason)} />
    </section>
  );
}
