// The discussion notes in the call (meetings-v2 5.2 / 5.3, owner decisions D12 and D13): after a case ends, the notes of what was said
// are written from the recorded text (Gemma-4-31B, non-medical). Every line keeps the exact spoken words behind its "said" chip (the
// speaker, the time and the quote copied word for word); the whole is labelled "AI draft, not reviewed" until the coordinator marks it
// reviewed. The coordinator may edit a line (shown as edited; the "said" stays) and mark the notes reviewed; the members read them.
// The notes summarise what people said; they never decide or advise.
// - NotesWrittenLine: the coordinator's line under the stage when a Case File's notes were written, with "Read the notes".
// - NotesPanel: the side panel's body (call/panels/SidePanel.tsx, kind "notes").
import { useContext, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, MessageSquareQuote, Pencil, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ErrorState, LoadingButton, SkeletonLines, StatusChip, errorText, fmtDate, modelLabel } from "@/features/casefile/components/common";
import { useCall } from "../call/context";
import { ShellContext } from "../call/useCallState";
import { editNoteLine, getMeetingNotes, reviewNotes, type CaseNotes, type MeetingNotes, type NoteLine } from "./api";
import { cn } from "@/lib/utils";

export const NOTES_DRAFT = "AI draft, not reviewed";
export const notesKey = (mid: string) => ["meeting-notes", mid] as const;
/** The longest line the coordinator may write (meeting_notes.MAX_LINE). */
export const MAX_NOTE_LINE = 300;

/** "Priya Venkatesan (SYNTHETIC)" out of the agenda's patient line. Pure. */
export function patientName(line?: string | null, fallback = ""): string {
  const s = (line ?? "").split(",")[0].trim();
  return s || fallback;
}

/** "16:42" out of the server's local ISO time ("2026-11-02T16:42:10"). Pure. */
export function clockOf(iso?: string | null): string {
  const m = /T(\d{2}):(\d{2})/.exec(iso ?? "");
  return m ? `${m[1]}:${m[2]}` : "";
}

/** The coordinator's line under the stage: the notes of a Case File were written. */
export function NotesWrittenLine({ caseId, lines, onClose }: { caseId: string; lines: number; onClose: () => void }) {
  const c = useCall();
  const x = useContext(ShellContext);
  const row = c.order.find((r) => r.case_id === caseId) ?? c.state.agenda.not_ready.find((r) => r.case_id === caseId);
  const name = patientName(row?.patient_line, caseId);
  return (
    <p className="flex items-center gap-2 rounded-lg border border-stage-line bg-stage-panel px-3 py-1.5 text-sm text-stage-fg" role="status" data-testid="notes-written" data-case={caseId}>
      <FileText className="size-4 shrink-0 text-stage-muted" aria-hidden />
      <span className="min-w-0 flex-1 truncate">Discussion notes written for {name} <span className="text-xs text-stage-muted">({lines} line{lines === 1 ? "" : "s"}, {NOTES_DRAFT})</span></span>
      <button type="button" className="shrink-0 rounded px-1 text-sm font-medium text-link underline underline-offset-2 outline-none focus-visible:ring-2 focus-visible:ring-primary" onClick={() => { x.openNotes(caseId); onClose(); }} data-testid="read-notes">Read the notes</button>
      <button type="button" className="shrink-0 rounded p-1 text-stage-muted hover:bg-stage-raised" onClick={onClose} aria-label="Dismiss"><X className="size-3.5" /></button>
    </p>
  );
}

/** One note line: its text, "edited" when the coordinator changed it, and the "said" chip that shows the exact words. */
function Line({ mid, caseId, line, canEdit }: { mid: string; caseId: string; line: NoteLine; canEdit: boolean }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(line.text);
  const save = useMutation({
    mutationFn: () => editNoteLine(mid, caseId, line.id, text.trim()),
    onSuccess: () => { setEditing(false); void qc.invalidateQueries({ queryKey: notesKey(mid) }); },
  });
  const said = line.said;
  const who = said.speaker_name || (said.speaker === "room" ? "Board room" : said.speaker);
  const at = clockOf(said.at);
  const quoteId = `said-${line.id}`;
  return (
    <li className="space-y-1 rounded-lg border border-border bg-card p-2.5" data-testid="note-line" data-line={line.id}>
      {editing ? (
        <form className="space-y-1.5" onSubmit={(e) => { e.preventDefault(); if (text.trim()) save.mutate(); }}>
          <label htmlFor={`edit-${line.id}`} className="sr-only">The note line</label>
          <Textarea id={`edit-${line.id}`} value={text} onChange={(e) => setText(e.target.value.slice(0, MAX_NOTE_LINE))} rows={3} className="text-sm" data-testid="note-edit-text" />
          <p className="text-xs text-muted-foreground">The spoken words behind it stay as they were. {MAX_NOTE_LINE - text.length} characters left.</p>
          {save.isError ? <p role="alert" className="text-xs text-bad">{errorText(save.error)}</p> : null}
          <div className="flex gap-2">
            <LoadingButton size="sm" type="submit" loading={save.isPending} loadingText="Saving" disabled={!text.trim() || text.trim() === line.text} data-testid="note-edit-save">Save the line</LoadingButton>
            <Button size="sm" type="button" variant="ghost" onClick={() => { setEditing(false); setText(line.text); }}>Cancel</Button>
          </div>
        </form>
      ) : (
        <p className="text-sm leading-snug" data-testid="note-text">{line.text}</p>
      )}
      <div className="flex flex-wrap items-center gap-1.5">
        <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-controls={quoteId}
          className="inline-flex items-center gap-1 rounded-full bg-secondary px-2 py-0.5 text-xs text-secondary-foreground outline-none hover:bg-secondary/80 focus-visible:ring-2 focus-visible:ring-primary"
          title="The exact words that were said" data-testid="said-chip">
          <MessageSquareQuote className="size-3.5" aria-hidden />said · {who}{at ? ` · ${at}` : ""}
        </button>
        {line.edited ? <span className="text-xs text-muted-foreground" data-testid="note-edited">Edited by {line.edited.by_name || line.edited.by}{line.edited.checked === false ? "; check it against the words said" : ""}</span> : null}
        {canEdit && !editing ? <Button size="xs" variant="ghost" className="ml-auto h-7" onClick={() => { setText(line.text); setEditing(true); }} data-testid="note-edit"><Pencil className="size-3.5" />Edit</Button> : null}
      </div>
      {open ? (
        <blockquote id={quoteId} className="border-l-2 border-primary/60 pl-2 text-sm" data-testid="said-quote">
          <p className="text-xs text-muted-foreground">{who}{at ? `, ${at}` : ""}, said:</p>
          <p className="italic">“{said.quote}”</p>
        </blockquote>
      ) : null}
    </li>
  );
}

function CaseNotesView({ mid, notes, canManage, name }: { mid: string; notes: CaseNotes; canManage: boolean; name: string }) {
  const qc = useQueryClient();
  const reviewed = notes.review?.status === "reviewed";
  const review = useMutation({
    mutationFn: (status: "reviewed" | "draft") => reviewNotes(mid, notes.case_id, status),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: notesKey(mid) }); },
  });
  if (notes.withheld) return <p className="text-sm text-muted-foreground" data-testid="notes-withheld">{notes.note || "Withheld."}</p>;
  const model = notes.model_line || (notes.model ? `Written by ${modelLabel(notes.model)}` : "");
  return (
    <section className="space-y-2" aria-label={`Discussion notes, ${name}`} data-testid="case-notes" data-case={notes.case_id}>
      <div className="flex flex-wrap items-center gap-1.5">
        <StatusChip kind={reviewed ? "ok" : "review"} className="whitespace-normal" title={reviewed ? undefined : "Written by an AI model from the recorded text; a person has not checked it yet"}><span data-testid="notes-label">{notes.label || (reviewed ? "Reviewed" : NOTES_DRAFT)}</span></StatusChip>
      </div>
      <p className="text-xs text-muted-foreground">{[model, notes.generated_at ? `${fmtDate(notes.generated_at)} ${clockOf(notes.generated_at)}` : ""].filter(Boolean).join(" · ")}. What people said, in their words; the notes never decide or advise.</p>
      {notes.lines.length ? (
        <ol className="space-y-1.5" aria-label="Note lines">{notes.lines.map((l) => <Line key={l.id} mid={mid} caseId={notes.case_id} line={l} canEdit={canManage} />)}</ol>
      ) : <p className="text-sm text-muted-foreground">No line could be written from what was said about this Case File.</p>}
      {notes.dropped ? <p className="text-xs text-muted-foreground" data-testid="notes-dropped">{notes.dropped} line{notes.dropped === 1 ? " was" : "s were"} left out: the words were not found exactly in what was said.</p> : null}
      {canManage ? (
        <div className="flex flex-wrap items-center gap-2 border-t border-border pt-2">
          {reviewed
            ? <LoadingButton size="sm" variant="ghost" loading={review.isPending} onClick={() => review.mutate("draft")} data-testid="notes-unreview">Back to draft</LoadingButton>
            : <LoadingButton size="sm" variant="outline" loading={review.isPending} loadingText="Saving" onClick={() => review.mutate("reviewed")} disabled={!notes.lines.length} data-testid="notes-review">Mark reviewed</LoadingButton>}
          {review.isError ? <p role="alert" className="text-xs text-bad">{errorText(review.error)}</p> : null}
        </div>
      ) : null}
    </section>
  );
}

/** The notes panel: one Case File's notes (the one asked for, else the case on the floor, else the first with notes), a chip row to
 *  switch between the Case Files that have notes. */
export function NotesPanel() {
  const c = useCall();
  const x = useContext(ShellContext);
  const q = useQuery<MeetingNotes, Error>({ queryKey: notesKey(c.mid), queryFn: () => getMeetingNotes(c.mid), retry: false, staleTime: 5_000 });
  const [pick, setPick] = useState<string | null>(null);
  const cases = useMemo(() => q.data?.cases ?? [], [q.data]);
  const nameOf = (cid: string) => patientName((c.order.find((r) => r.case_id === cid) ?? c.state.agenda.not_ready.find((r) => r.case_id === cid))?.patient_line, cid);
  const want = pick ?? x.notesCase ?? c.cid;
  // a Case File asked for by name shows its own notes or none; the case on the floor without notes gives way to the first with notes
  const shown = cases.find((n) => n.case_id === want) ?? (pick || x.notesCase ? null : cases[0] ?? null);
  const focus = shown?.case_id ?? want ?? null;
  const building = (q.data?.building ?? []).includes(focus ?? "");

  if (q.isLoading) return <SkeletonLines n={4} />;
  if (q.isError) return <ErrorState error={q.error} retry={() => void q.refetch()} compact />;
  return (
    <div className="space-y-3" data-testid="notes-body">
      <p className="text-xs text-muted-foreground">Written from the recorded text of the meeting (no audio is kept). Each line has the exact words said behind its “said” chip.</p>
      {cases.length > 1 ? (
        <div className="flex flex-wrap gap-1" role="group" aria-label="Case Files with notes">
          {cases.map((n) => (
            <button key={n.case_id} type="button" onClick={() => setPick(n.case_id)} aria-pressed={n.case_id === focus}
              className={cn("rounded-full border px-2.5 py-1 text-xs outline-none focus-visible:ring-2 focus-visible:ring-primary", n.case_id === focus ? "border-primary bg-primary/10 font-medium" : "border-border hover:bg-muted")}>{nameOf(n.case_id)}</button>
          ))}
        </div>
      ) : null}
      {focus ? <h3 className="text-sm font-semibold" data-testid="notes-patient">{nameOf(focus)}</h3> : null}
      {building ? <p className="text-xs text-muted-foreground" role="status">The notes of this Case File are being written now.</p> : null}
      {shown ? <CaseNotesView mid={c.mid} notes={shown} canManage={c.canManage} name={nameOf(shown.case_id)} />
        : <p className="text-sm text-muted-foreground" data-testid="notes-none">No discussion notes for this Case File yet. They are written from the recorded text when its discussion ends.</p>}
    </div>
  );
}
