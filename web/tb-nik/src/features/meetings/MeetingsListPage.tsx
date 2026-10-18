// Meetings: the list, newest first. The coordinator creates one by hand (date, time, room, video, minutes per case).
// When meetings.py is not on the server, the old board sessions show read-only with a note.
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarPlus, ChevronRight, KeyRound, Video } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { DateInput } from "@/components/DateInput";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useSession } from "@/lib/session";
import { createMeeting, listMeetings, listOldSessions, notBuiltYet } from "./api";
import type { MeetingRow, NewMeeting } from "./types";
import { EmptyState, ErrorState, LoadingButton, NotYetState, SkeletonLines, errorText, fmtDate, fmtDateTime, todayIso } from "@/features/casefile/components/common";
import { MeetingStatusChip } from "./components/shared";

function NewMeetingDialog({ open, onOpenChange, videoAvailable, onCreated }: { open: boolean; onOpenChange: (o: boolean) => void; videoAvailable: boolean; onCreated: (id: string) => void }) {
  const today = todayIso();
  const [form, setForm] = useState<NewMeeting>({ date: today, time: "14:00", room: "", video: videoAvailable, minutes_per_case: 10 });
  const [touched, setTouched] = useState(false);
  const create = useMutation({ mutationFn: () => createMeeting({ ...form, room: form.room?.trim() || undefined }), onSuccess: (m) => { onOpenChange(false); onCreated(m.id); } });
  const dateBad = !form.date ? "Choose a date." : form.date < today ? "The date is in the past." : null;
  const timeBad = !/^\d{2}:\d{2}$/.test(form.time) ? "Choose a time." : null;
  const minsBad = !form.minutes_per_case || form.minutes_per_case < 1 || form.minutes_per_case > 60 ? "1 to 60 minutes." : null;
  const bad = dateBad || timeBad || minsBad;
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!create.isPending) onOpenChange(o); }}>
      <DialogContent aria-describedby="nm-desc" data-testid="new-meeting-dialog">
        <form onSubmit={(e) => { e.preventDefault(); setTouched(true); if (!bad) create.mutate(); }} className="space-y-4">
          <DialogHeader>
            <DialogTitle>New meeting</DialogTitle>
            <DialogDescription id="nm-desc">The agenda is built afterwards from the Case Files marked ready. No cut-off: late additions are flagged to members.</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div><Label htmlFor="nm-date">Date</Label><DateInput id="nm-date" value={form.date} min={today} onChange={(v) => setForm({ ...form, date: v })} wrapperClassName="mt-1" aria-invalid={touched && !!dateBad} />{touched && dateBad ? <p className="text-xs text-bad mt-0.5">{dateBad}</p> : null}</div>
            <div><Label htmlFor="nm-time">Time</Label><Input id="nm-time" type="time" value={form.time} onChange={(e) => setForm({ ...form, time: e.target.value })} className="mt-1" aria-invalid={touched && !!timeBad} />{touched && timeBad ? <p className="text-xs text-bad mt-0.5">{timeBad}</p> : null}</div>
            <div className="col-span-2"><Label htmlFor="nm-room">Room</Label><Input id="nm-room" value={form.room} onChange={(e) => setForm({ ...form, room: e.target.value })} placeholder="for example: Oncology seminar room, 2nd floor" className="mt-1" maxLength={120} /></div>
            <div><Label htmlFor="nm-mins">Minutes per case</Label><Input id="nm-mins" type="number" min={1} max={60} value={form.minutes_per_case ?? ""} onChange={(e) => setForm({ ...form, minutes_per_case: Number(e.target.value) })} className="mt-1 w-28" aria-invalid={touched && !!minsBad} />{touched && minsBad ? <p className="text-xs text-bad mt-0.5">{minsBad}</p> : null}</div>
            <div className="flex items-end gap-2 pb-1">
              <Switch id="nm-video" checked={form.video} onCheckedChange={(v) => setForm({ ...form, video: v })} disabled={!videoAvailable} />
              <Label htmlFor="nm-video" className="inline-flex items-center gap-1"><Video className="size-4" aria-hidden />Video for remote members{!videoAvailable ? <span className="text-xs text-muted-foreground">(not set up)</span> : null}</Label>
            </div>
          </div>
          {create.isError ? <p role="alert" className="text-sm text-bad">{errorText(create.error)}</p> : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={create.isPending}>Cancel</Button>
            <LoadingButton type="submit" loading={create.isPending} loadingText="Creating"><CalendarPlus className="size-4" />Create meeting</LoadingButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** "Thursday, " for a YYYY-MM-DD date (busy people plan by the day of the week). */
function weekday(iso?: string): string {
  if (!iso || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return "";
  const d = new Date(`${iso}T12:00:00`);
  return Number.isNaN(d.getTime()) ? "" : `${d.toLocaleDateString("en-IN", { weekday: "long" })}, `;
}

function OldSessions() {
  const q = useQuery({ queryKey: ["old-sessions"], queryFn: listOldSessions });
  if (q.isLoading) return <SkeletonLines n={3} />;
  if (q.isError) return <ErrorState error={q.error} retry={() => void q.refetch()} compact />;
  const rows = q.data?.sessions ?? [];
  return (
    <div className="space-y-3">
      <NotYetState what="The new meeting rooms (agenda lists, join by code, live screen)" fallback="Showing the board sessions the old interface keeps, read-only. Open /tb to run one." />
      {rows.length === 0 ? <EmptyState kind="wait" title="No board sessions yet" /> : null}
      <ul className="surface divide-y divide-border">
        {rows.map((s) => (
          <li key={s.id} className="flex items-center gap-3 px-4 py-3 text-sm">
            <div className="flex-1 min-w-0">
              <p className="font-medium text-foreground">{fmtDate(s.date)}{s.title ? `, ${s.title}` : ""}</p>
              <p className="text-xs text-muted-foreground">{s.cases ?? 0} Case File{s.cases === 1 ? "" : "s"}{s.created_by ? `, created by ${s.created_by}` : ""}</p>
            </div>
            <MeetingStatusChip status={s.status} />
            <a className="text-link text-xs underline" href={`/tb#session=${encodeURIComponent(s.id)}`}>open in /tb</a>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function MeetingsListPage() {
  const { me } = useSession();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const q = useQuery({ queryKey: ["meetings"], queryFn: listMeetings, retry: false, refetchInterval: 30_000 });
  const notBuilt = q.isError && notBuiltYet(q.error);
  const canManage = q.data?.can_manage ?? !!me?.roles?.coordinator;
  const rows = q.data?.meetings ?? [];
  const key = (m: MeetingRow) => `${m.date} ${m.time ?? ""}`;
  // In session first, then the planned ones by date and time.
  const rank = (m: MeetingRow) => (m.status === "in_session" ? 0 : 1);
  const upcoming = rows.filter((m) => m.status === "planned" || m.status === "in_session").sort((a, b) => rank(a) - rank(b) || key(a).localeCompare(key(b)));
  const today = todayIso();
  const past = rows.filter((m) => m.status !== "planned" && m.status !== "in_session").sort((a, b) => key(b).localeCompare(key(a)));
  return (
    <div className="space-y-4 max-w-5xl mx-auto" data-testid="meetings-page">
      <header className="flex flex-wrap items-center gap-2">
        <h1>Meetings</h1>
        <span className="flex-1" />
        <Button asChild variant="outline" size="sm"><Link to="/meetings/join"><KeyRound className="size-4" />Join with a code</Link></Button>
        {canManage && !notBuilt ? <Button size="sm" onClick={() => setOpen(true)} data-testid="new-meeting"><CalendarPlus className="size-4" />New meeting</Button> : null}
      </header>
      {q.isLoading ? <div className="surface p-4"><SkeletonLines n={4} /></div> : null}
      {q.isError && !notBuilt ? <ErrorState error={q.error} retry={() => void q.refetch()} /> : null}
      {notBuilt ? <OldSessions /> : null}
      {q.data ? (
        rows.length === 0 ? (
          <EmptyState kind="wait" title="No meetings yet" text={canManage ? "Create the next Tumour Board meeting; the agenda is built from the Case Files marked ready." : "The MDT Coordinator has not planned a meeting yet."} action={canManage ? <Button onClick={() => setOpen(true)}><CalendarPlus className="size-4" />New meeting</Button> : undefined} />
        ) : (
          <div className="space-y-4">
          {([["Upcoming", upcoming], ["Past", past]] as const).map(([title, list]) => list.length ? (
          <section key={title} aria-label={title}>
          <h2 className="text-sm font-semibold text-muted-foreground mb-1.5">{title}</h2>
          <ul className="surface divide-y divide-border" data-testid={title === "Upcoming" ? "meetings-list" : "meetings-past"}>
            {list.map((m) => (
              <li key={m.id}>
                <Link to={`/meetings/${m.id}`} className="row-lift group flex items-center gap-3 px-4 py-3 text-sm rounded-md">
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-foreground truncate">{m.title || m.room || "Tumour Board"}</p>
                    <p className="text-sm text-body">
                      {weekday(m.date)}{fmtDate(m.date)}{m.time ? `, ${m.time}` : ""}{m.room && m.title ? `, ${m.room}` : ""}
                      {m.status === "planned" && m.date && m.date < today ? <span className="ml-2 rounded-md status-warn px-1.5 py-0.5 text-xs font-medium">date passed, not started</span> : null}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {m.counts ? `${m.counts.discussion} for discussion, ${m.counts.noting} for noting${m.counts.not_ready ? `, ${m.counts.not_ready} not ready` : ""}` : ""}
                      <span className="block">{m.agenda_sent_at ? `Agenda sent ${fmtDateTime(m.agenda_sent_at)}` : "Agenda not sent"}{m.video ? ", video on" : ""}</span>
                    </p>
                  </div>
                  {m.video ? <Video className="size-4 text-muted-foreground" aria-label="video on" /> : null}
                  <MeetingStatusChip status={m.status} />
                  <ChevronRight className="size-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition" aria-hidden />
                </Link>
              </li>
            ))}
          </ul>
          </section>
          ) : null)}
          </div>
        )
      ) : null}
      <NewMeetingDialog open={open} onOpenChange={setOpen} videoAvailable={!!me?.features?.video} onCreated={(id) => { void qc.invalidateQueries({ queryKey: ["meetings"] }); nav(`/meetings/${id}`); }} />
    </div>
  );
}
