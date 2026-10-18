// The coordinator's control view during a meeting: which case is on the screen, Next / Previous, the slide picker,
// the timer, admitting people, opening a record or images on the shared screen, the decision form, End case, End meeting.
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, DoorOpen, Images, MonitorOff, MonitorUp, Pause, Play, RotateCcw, StopCircle, UserRoundCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import type { MeetingState } from "@/lib/live";
import { admit, endCase, endMeeting, getCards, getSlides, openOnScreen, setCurrent, timer as timerCall } from "../api";
import { getCase } from "@/features/casefile/api";
import { DecisionForm } from "./DecisionForm";
import { AgentTile, MembersStrip, QuestionsList, TimerBadge } from "./shared";
import { LoadingButton, StatusChip, errorText, fmtDateTime, useAnnounce } from "@/features/casefile/components/common";
import { docStatusChip } from "@/features/casefile/components/SourceViewer";
import { cn } from "@/lib/utils";

export function ControlView({ mid, state, onChanged }: { mid: string; state: MeetingState; onChanged: () => void }) {
  const order = useMemo(() => [...state.agenda.discussion, ...state.agenda.noting], [state.agenda]);
  const cid = state.current?.case_id ?? null;
  const idx = order.findIndex((r) => r.case_id === cid);
  const row = idx >= 0 ? order[idx] : null;
  const [minutes, setMinutes] = useState<number>(row?.minutes ?? state.meeting.minutes_per_case ?? 10);
  useEffect(() => { setMinutes(row?.minutes ?? state.meeting.minutes_per_case ?? 10); }, [cid]); // eslint-disable-line react-hooks/exhaustive-deps
  const [endOpen, setEndOpen] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [announce, liveNode] = useAnnounce();
  const wrap = <T,>(fn: () => Promise<T>) => async () => { setErr(null); try { const r = await fn(); onChanged(); return r; } catch (e) { setErr(errorText(e)); throw e; } };

  const go = useMutation({ mutationFn: (c: { case_id: string; slide?: number }) => wrap(() => setCurrent(mid, c.case_id, c.slide))(), onSuccess: (_r, c) => announce(c.slide !== undefined ? `Slide ${c.slide + 1} on the screen.` : "Next case on the screen.") });
  const tm = useMutation({ mutationFn: (a: "start" | "stop" | "reset") => wrap(() => timerCall(mid, a, a === "start" || a === "reset" ? minutes : undefined))() });
  const adm = useMutation({ mutationFn: (u: string) => wrap(() => admit(mid, u))(), onSuccess: () => announce("Admitted.") });
  const open = useMutation({ mutationFn: (o: { kind: "record" | "images" | "none"; doc_id?: string }) => wrap(() => openOnScreen(mid, o.kind, o.doc_id))(), onSuccess: (_r, o) => announce(o.kind === "none" ? "The shared screen shows the slide again." : o.kind === "images" ? "Images open on the shared screen." : "Record open on the shared screen.") });
  const end = useMutation({ mutationFn: () => wrap(() => endCase(mid, cid!))(), onSuccess: (r) => announce(r?.cards_requested?.length ? `Cards asked of ${r.cards_requested.length} board heads.` : "Discussion ended.") });
  const finish = useMutation({ mutationFn: () => wrap(() => endMeeting(mid))(), onSuccess: () => setEndOpen(false) });

  const slides = useQuery({ queryKey: ["slides", mid, cid], queryFn: () => getSlides(mid, cid!), enabled: !!cid, retry: false, staleTime: 60_000 });
  const cf = useQuery({ queryKey: ["case", cid], queryFn: () => getCase(cid!), enabled: !!cid, retry: false, staleTime: 60_000 });
  const cards = useQuery({ queryKey: ["cards", mid], queryFn: () => getCards(mid), retry: false, refetchInterval: 15_000 });
  const waiting = state.attendance.filter((a) => a.status === "waiting");
  const docs = (cf.data?.documents ?? []).filter((d) => d.state === "ready" && !d.superseded);
  const opened = state.current?.opened;
  const caseCards = cid ? cards.data?.cards?.[cid] : undefined;
  const ended = !!cid && (state.ended ?? []).includes(cid);
  const outcome = cid ? state.outcomes?.[cid] : undefined;

  return (
    <div className="grid gap-4 lg:grid-cols-12 items-start" data-testid="control-view">
      {liveNode}
      <div className="lg:col-span-7 space-y-4">
        <section className="surface p-4 space-y-3" aria-label="On the screen">
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="outline" onClick={() => idx > 0 && go.mutate({ case_id: order[idx - 1].case_id })} disabled={idx <= 0 || go.isPending} aria-label="Previous case"><ChevronLeft className="size-4" />Previous</Button>
            <div className="flex-1 min-w-0 text-center">
              {row ? <><p className="font-medium text-foreground truncate">{row.patient_line}</p><p className="text-xs text-muted-foreground">{idx + 1} of {order.length}{row.presenter_name ? `, presenter ${row.presenter_name}` : ""}{row.owner_name ? `, owner ${row.owner_name}` : ""}</p></> : <p className="text-sm text-muted-foreground">No case on the screen yet. Press Next to start with the first.</p>}
            </div>
            <LoadingButton size="sm" loading={go.isPending && go.variables?.slide === undefined} onClick={() => go.mutate({ case_id: order[Math.min(order.length - 1, idx + 1)].case_id })} disabled={order.length === 0 || idx >= order.length - 1 || go.isPending} aria-label="Next case" data-testid="next-case">Next<ChevronRight className="size-4" /></LoadingButton>
          </div>
          {row?.board_question ? <p className="text-sm rounded-md bg-muted px-2 py-1.5"><span className="text-muted-foreground">Board question: </span>{row.board_question}</p> : row ? <p className="text-xs text-warn">The board question is not written on this Case File.</p> : null}
          <div className="flex flex-wrap items-center gap-2">
            <TimerBadge timer={state.current?.timer} />
            <label className="inline-flex items-center gap-1 text-xs text-muted-foreground">minutes <Input type="number" min={1} max={60} value={minutes} onChange={(e) => setMinutes(Math.max(1, Math.min(60, Number(e.target.value) || 1)))} className="h-7 w-16 text-sm" aria-label="Minutes for this case" /></label>
            {state.current?.timer?.running ? <Button size="xs" variant="outline" onClick={() => tm.mutate("stop")} disabled={tm.isPending}><Pause className="size-3" />Stop</Button> : <Button size="xs" variant="outline" onClick={() => tm.mutate("start")} disabled={tm.isPending || !cid} data-testid="timer-start"><Play className="size-3" />Start</Button>}
            <Button size="xs" variant="ghost" onClick={() => tm.mutate("reset")} disabled={tm.isPending || !cid}><RotateCcw className="size-3" />Reset</Button>
          </div>
          <div>
            <p className="text-xs font-medium text-muted-foreground mb-1">Slide on the screen</p>
            {slides.isLoading ? <div className="skeleton-line h-7 w-64" /> : null}
            {slides.isError ? <p className="text-xs text-warn">Slides are not available for this case: {errorText(slides.error)}</p> : null}
            <div className="flex flex-wrap gap-1" role="group" aria-label="Slide picker">
              {(slides.data?.slides ?? []).map((s, i) => (
                <button key={s.id} type="button" aria-pressed={(state.current?.slide ?? 0) === i} onClick={() => go.mutate({ case_id: cid!, slide: i })} disabled={go.isPending} className={cn("rounded-md border px-2 py-1 text-xs transition active:scale-95 disabled:opacity-60", (state.current?.slide ?? 0) === i ? "border-primary bg-secondary text-secondary-foreground font-medium" : "border-border hover:bg-muted")}>{i + 1}. {s.title}</button>
              ))}
            </div>
          </div>
          <div>
            <p className="text-xs font-medium text-muted-foreground mb-1">On the shared screen</p>
            <div className="flex flex-wrap items-center gap-1.5">
              {opened && opened.kind !== "none" ? <StatusChip kind="info">{opened.kind === "images" ? "images" : "record"}: {opened.title ?? "open"}</StatusChip> : <StatusChip kind="muted">slide only</StatusChip>}
              {opened && opened.kind !== "none" ? <Button size="xs" variant="outline" onClick={() => open.mutate({ kind: "none" })} disabled={open.isPending}><MonitorOff className="size-3" />Back to the slide</Button> : null}
            </div>
            <ul className="mt-1.5 max-h-48 overflow-y-auto divide-y divide-border rounded-md border border-border" aria-label="Records of this Case File">
              {cf.isLoading ? <li className="p-2"><div className="skeleton-line h-4 w-3/4" /></li> : null}
              {cf.isError ? <li className="p-2 text-xs text-warn">The records could not be listed: {errorText(cf.error)}</li> : null}
              {!cf.isLoading && !cf.isError && docs.length === 0 ? <li className="p-2 text-xs text-muted-foreground">No records to open{cid ? "" : ": pick a case first"}.</li> : null}
              {docs.map((d) => {
                const title = d.classification?.title ?? d.filename;
                return (
                  <li key={d.doc_id} className="flex items-center gap-2 px-2 py-1 text-xs">
                    <span className="flex-1 min-w-0 truncate">{title}</span>
                    {docStatusChip(d)}
                    <Button size="xs" variant={opened?.doc_id === d.doc_id && opened.kind === "record" ? "secondary" : "ghost"} onClick={() => open.mutate({ kind: "record", doc_id: d.doc_id })} disabled={open.isPending} aria-label={`Show ${title} on the screen`}><MonitorUp className="size-3" />Show</Button>
                    {d.his?.imaging_study_ref ? <Button size="xs" variant={opened?.doc_id === d.doc_id && opened.kind === "images" ? "secondary" : "ghost"} onClick={() => open.mutate({ kind: "images", doc_id: d.doc_id })} disabled={open.isPending} aria-label={`Show the images of ${title} on the screen`} title="Opens the study in the hospital viewer on the shared screen; people view the images, no model reads them"><Images className="size-3" />Images</Button> : null}
                  </li>
                );
              })}
            </ul>
          </div>
          {err ? <p role="alert" className="text-xs text-bad">{err}</p> : null}
        </section>

        <section className="surface p-4" aria-label="Decision">
          <h2 className="text-base mb-2">Decision{row ? ` for ${row.patient_line}` : ""}</h2>
          {outcome ? <p className="mb-2 text-sm status-ok rounded-md px-2 py-1">Recorded: {outcome.label ?? outcome.outcome}{outcome.at ? `, ${fmtDateTime(outcome.at)}` : ""}. Saving again records a correction.</p> : null}
          {cid ? <DecisionForm mid={mid} caseId={cid} attendance={state.attendance} onSaved={onChanged} liveText={state.decision_live?.case_id && state.decision_live.case_id !== cid ? undefined : state.decision_live?.text} canRecord={state.can?.record !== false} /> : <p className="text-sm text-muted-foreground">Pick a case first.</p>}
          <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border pt-3">
            <LoadingButton size="sm" variant="outline" loading={end.isPending} onClick={() => end.mutate()} disabled={!cid} title="Asks each board head for their card (Agree / Concern)" data-testid="end-case"><StopCircle className="size-4" />{ended ? "Ask for the cards again" : "End case, ask for cards"}</LoadingButton>
            {caseCards ? (
              <span className="text-xs text-muted-foreground" data-testid="cards-summary">
                {caseCards.cards.length ? `Cards: ${caseCards.cards.map((c) => `${c.name ?? c.user} ${c.agree ? "agrees" : "has a concern"}`).join("; ")}.` : "No cards yet."}
                {caseCards.missing.length ? ` Waiting for ${caseCards.missing.length}.` : caseCards.cards.length ? " Every head has given a card." : ""}
              </span>
            ) : null}
            <span className="flex-1" />
            <Button size="sm" variant="destructive" onClick={() => setEndOpen(true)} data-testid="end-meeting"><DoorOpen className="size-4" />End meeting</Button>
          </div>
        </section>
      </div>

      <div className="lg:col-span-5 space-y-4">
        <section className="surface p-3 space-y-2" aria-label="People">
          <h2 className="text-sm font-semibold">People</h2>
          <MembersStrip attendance={state.attendance} hands={state.hands} />
          {waiting.length ? (
            <ul className="space-y-1" data-testid="waiting-list">
              {waiting.map((a) => (
                <li key={a.user} className="flex items-center gap-2 text-sm rounded-md bg-warn-soft px-2 py-1">
                  <span className="flex-1">{a.name}{a.department_name || a.department ? <span className="text-xs text-muted-foreground"> ({a.department_name ?? a.department})</span> : null} is waiting{a.outside_expert ? <span className="text-xs text-muted-foreground"> (outside expert)</span> : null}</span>
                  <LoadingButton size="xs" loading={adm.isPending && adm.variables === a.user} onClick={() => adm.mutate(a.user)}><UserRoundCheck className="size-3" />Admit</LoadingButton>
                </li>
              ))}
            </ul>
          ) : <p className="text-xs text-muted-foreground">No one is waiting to be admitted.</p>}
          <AgentTile agent={state.agent} />
        </section>
        <section className="surface p-3" aria-label="Questions from members">
          <h2 className="text-sm font-semibold mb-1">Questions from members</h2>
          <QuestionsList questions={state.questions ?? []} caseId={cid} emptyText="No questions on this case yet." />
        </section>
        <section className="surface p-3" aria-label="Agenda">
          <h2 className="text-sm font-semibold mb-1">Agenda</h2>
          <ol className="space-y-1 text-sm">
            {order.map((r, i) => (
              <li key={r.case_id} className={cn("flex items-center gap-2 rounded-md px-2 py-1", r.case_id === cid ? "bg-secondary" : "")}>
                <span className="text-xs text-muted-foreground w-5 tabular-nums">{i + 1}.</span>
                <button type="button" className="flex-1 text-left truncate hover:underline underline-offset-2 disabled:opacity-60" onClick={() => go.mutate({ case_id: r.case_id })} disabled={go.isPending || r.case_id === cid} title={r.case_id === cid ? "On the screen now" : "Put this case on the screen"}>{r.patient_line || r.case_id}</button>
                {r.decided || r.outcome ? <StatusChip kind="ok">{r.outcome_label ?? r.outcome?.replace(/_/g, " ") ?? "decided"}</StatusChip> : null}
                <Link to={`/cases/${r.case_id}`} className="text-xs text-link underline">file</Link>
              </li>
            ))}
          </ol>
          {state.meeting.started_at ? <p className="text-xs text-muted-foreground mt-2">Started {fmtDateTime(state.meeting.started_at)}</p> : null}
        </section>
      </div>

      <Dialog open={endOpen} onOpenChange={(o) => { if (!finish.isPending) setEndOpen(o); }}>
        <DialogContent aria-describedby="end-desc">
          <DialogHeader><DialogTitle>End the meeting?</DialogTitle><DialogDescription id="end-desc">The outcomes already saved go to the owners. Case Files without a saved outcome keep their place; mark them Not discussed first to move them to the next meeting.</DialogDescription></DialogHeader>
          <p className="text-sm">{order.filter((r) => r.decided || r.outcome).length} of {order.length} Case Files have a saved outcome.</p>
          {finish.isError ? <p role="alert" className="text-sm text-bad">{errorText(finish.error)}</p> : null}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEndOpen(false)} disabled={finish.isPending}>Keep going</Button>
            <LoadingButton variant="destructive" loading={finish.isPending} loadingText="Ending" onClick={() => finish.mutate()}>End meeting</LoadingButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
