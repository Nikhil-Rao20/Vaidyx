// Board decisions (night-v3 3.2): every board round of the Case File, newest first, each with the fields the MDT Coordinator recorded
// in the meeting (labels, choices and step order from decision_fields.json), the actions it raised, who recorded it and, when it was
// corrected later, who corrected it, why, and each earlier version. The owning department's consultants (and the MDT Coordinator on
// the meeting day) may correct a record: the same six steps of the meeting form, only the changed fields sent as a new version.
// Read-only for everyone else. The decision is the board's, in its own words.
import { useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { ClipboardList, PencilLine } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DECISION_SPEC, DecisionForm, choicesOf, fieldOf, recordOutcome } from "@/features/meetings/components/DecisionForm";
import type { BoardRecord, BoardRecordVersion, CaseFile } from "../types";
import { EmptyState, StatusChip, fmtDate, fmtDateTime, useAnnounce, type ChipKind } from "./common";

const OUTCOME = new Map(DECISION_SPEC.outcomes.map((o) => [String(o.id), o.label]));
export const outcomeLabel = (id: string) => OUTCOME.get(id) ?? id.replace(/_/g, " ");
const outcomeChip = (id: string): ChipKind => (id === "decision" ? "ok" : id === "deferred" ? "warn" : id === "not_discussed" ? "muted" : "info");
const ACTION_KIND: Record<string, string> = { investigation: "Investigation", referral: "Referral" };

const s = (v: unknown) => (typeof v === "string" ? v.trim() : typeof v === "number" ? String(v) : "");
const choiceText = (k: string, v: string) => choicesOf(k).find((c) => c.id === v)?.label ?? v.replace(/_/g, " ");
const rowObj = (x: unknown) => (x && typeof x === "object" ? (x as Record<string, unknown>) : null);

/** One field's value as lines of text; [] when empty. Old string-shaped records (participants, concerns as a sentence) still show. */
export function valueLines(key: string, v: unknown): string[] {
  const fd = fieldOf(key);
  if (v == null || v === "") return [];
  if (typeof v === "string" && !["choice", "yn", "date"].includes(fd.kind)) return v.trim() ? [v.trim()] : [];
  switch (fd.kind) {
    case "choice": case "yn": return s(v) ? [choiceText(key, s(v))] : [];
    case "date": return s(v) ? [fmtDate(s(v))] : [];
    case "multi": return Array.isArray(v) && v.length ? [v.map((x) => choiceText(key, s(x))).filter(Boolean).join(", ")] : [];
    case "people": return Array.isArray(v) ? [v.map((x) => s(x) || s(rowObj(x)?.name)).filter(Boolean).join(", ")].filter(Boolean) : [];
    case "concerns": return Array.isArray(v) ? v.map(rowObj).filter(Boolean).map((c) => (s(c!.by) ? `${s(c!.by)}: ${s(c!.text)}` : s(c!.text))).filter(Boolean) : [];
    case "investigations": return Array.isArray(v) ? v.map(rowObj).filter(Boolean).filter((r) => s(r!.item)).map((r) => {
      const parts = [s(r!.department), s(r!.due) ? `due ${fmtDate(s(r!.due))}` : ""].filter(Boolean);
      return parts.length ? `${s(r!.item)} (${parts.join(", ")})` : s(r!.item);
    }) : [];
    case "referrals": return Array.isArray(v) ? v.map(rowObj).filter(Boolean).filter((r) => s(r!.kind)).map((r) => `${choiceText(key, s(r!.kind))}${s(r!.department) ? ` (${s(r!.department)})` : ""}${s(r!.note) ? `: ${s(r!.note)}` : ""}`) : [];
    default: return s(v) ? [s(v)] : [];
  }
}

/** The value shown for a field of a record, with the fallbacks of the records saved before the decision record v2. */
function recordValue(rec: BoardRecord, key: string): unknown {
  const r = rec as unknown as Record<string, unknown>;
  if (key === "intent") return rec.intent || rec.intent_as_recorded;
  if (key === "awaited") return rec.awaited || (recordOutcome(rec) === "deferred" ? rec.deferred_reason : "");
  if (key === "members_present") return Array.isArray(rec.members_present) && rec.members_present.length ? rec.members_present : rec.participants;
  return r[key];
}

const changeText = (key: string, v: unknown) => valueLines(key, v).join("; ") || "empty";

function Versions({ versions, current }: { versions: BoardRecordVersion[]; current?: number }) {
  const list = [...versions].sort((a, b) => b.version - a.version);
  return (
    <details className="text-xs text-muted-foreground" data-testid="earlier-versions">
      <summary className="cursor-pointer hover:text-foreground">Earlier versions ({versions.length})</summary>
      <ol className="mt-1 space-y-1.5 pl-3">
        {list.map((v) => (
          <li key={v.version}>
            <span className="font-medium text-foreground">Version {v.version}{v.version === current ? " (current)" : ""}</span>
            {v.at ? `, ${fmtDateTime(v.at)}` : ""}{v.by_name || v.by ? `, by ${v.by_name || v.by}` : ""}{v.reason ? `: ${v.reason}` : ""}
            {v.changed?.length ? (
              <ul className="mt-0.5 list-disc space-y-0.5 pl-4">
                {v.changed.map((c) => <li key={c.key}>{fieldOf(c.key).label}: was {changeText(c.key, c.old)}, now {changeText(c.key, c.new)}</li>)}
              </ul>
            ) : null}
          </li>
        ))}
      </ol>
    </details>
  );
}

function RoundCard({ rec, n, latest, canCorrect, onCorrect }: { rec: BoardRecord; n: number; latest: boolean; canCorrect: boolean; onCorrect: () => void }) {
  const outcome = recordOutcome(rec);
  const date = rec.board_date || rec.recorded_at;
  const rows = DECISION_SPEC.fields.filter((fd) => fd.key !== "outcome").map((fd) => ({ fd, lines: valueLines(fd.key, recordValue(rec, fd.key)) })).filter((x) => x.lines.length);
  const actions = (rec.actions ?? []).filter((a) => a && s(a.task));
  const titleId = `board-round-${n}-title`;
  return (
    <article className="rounded-md border border-border" aria-labelledby={titleId} data-testid={`board-round-${n}`}>
      <header className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2">
        <h3 id={titleId} className="text-sm font-semibold text-foreground">Round {n}{date ? `, ${fmtDate(date)}` : ""}</h3>
        <StatusChip kind={outcomeChip(outcome)}>{outcomeLabel(outcome)}</StatusChip>
        {latest ? <span className="text-xs text-muted-foreground">Latest</span> : null}
        {canCorrect ? <Button size="xs" variant="outline" className="ml-auto" onClick={onCorrect} data-testid="correct-record" aria-label={`Correct the record of round ${n}`}><PencilLine className="size-3" />Correct this record</Button> : null}
      </header>
      {rows.length ? (
        <dl className="divide-y divide-border">
          {rows.map(({ fd, lines }) => (
            <div key={fd.key} className="grid grid-cols-1 gap-0.5 px-3 py-2 text-sm sm:grid-cols-[10rem_1fr] sm:gap-2" data-field={fd.key}>
              <dt className="text-muted-foreground">{fd.label}</dt>
              <dd className="min-w-0 break-words text-foreground">{lines.length > 1 ? <ul className="list-disc space-y-0.5 pl-4">{lines.map((l, i) => <li key={i}>{l}</li>)}</ul> : <span className="whitespace-pre-wrap">{lines[0]}</span>}</dd>
            </div>
          ))}
        </dl>
      ) : <p className="px-3 py-2 text-sm text-muted-foreground">Nothing was recorded beyond the outcome.</p>}
      {actions.length ? (
        <div className="border-t border-border px-3 py-2 text-sm">
          <p className="text-muted-foreground">Actions raised</p>
          <ul className="mt-0.5 list-disc space-y-0.5 pl-4" data-testid="round-actions">
            {actions.map((a, i) => {
              const kind = ACTION_KIND[a.kind ?? ""] ?? "Action";
              const parts = [s(a.department), s(a.due) ? `due ${fmtDate(s(a.due))}` : ""].filter(Boolean);
              return <li key={i}>{a.task.startsWith(kind) ? "" : `${kind}: `}{a.task}{parts.length ? ` (${parts.join(", ")})` : ""}</li>;
            })}
          </ul>
        </div>
      ) : null}
      <div className="space-y-1 border-t border-border px-3 py-2 text-xs text-muted-foreground">
        {rec.recorded_at || rec.recorded_by || rec.entered_by ? <p>recorded{rec.recorded_at ? ` ${fmtDateTime(rec.recorded_at)}` : ""}{rec.recorded_by || rec.entered_by ? ` by ${rec.recorded_by || rec.entered_by}` : ""}</p> : null}
        {rec.corrected ? <p className="text-foreground" data-testid="corrected-line">Corrected by {rec.corrected.by_name || rec.corrected.by} on {fmtDate(rec.corrected.at)} (version {rec.corrected.version}){rec.corrected.reason ? `: ${rec.corrected.reason}` : ""}</p> : null}
        {rec.corrected && rec.versions?.length ? <Versions versions={rec.versions} current={rec.version} /> : null}
      </div>
    </article>
  );
}

export function BoardDecisionsPanel({ cf, coordinator, onChanged }: { cf: CaseFile; coordinator: boolean; onChanged?: () => void | Promise<void> }) {
  const qc = useQueryClient();
  const [announce, liveNode] = useAnnounce();
  // A saved correction shows at once, before the Case File is read again.
  const [fresh, setFresh] = useState<Record<string, BoardRecord>>({});
  const [editing, setEditing] = useState<BoardRecord | null>(null);
  const saved = cf.state?.board_records?.length ? cf.state.board_records : cf.case?.board_record ? [cf.case.board_record] : [];
  const rounds = saved.map((r, i) => ({ rec: (r.id && fresh[r.id]) || r, n: i + 1 }));
  const allowed = cf.permissions?.correct_board_record ?? {};
  const caseId = cf.case.case_id;

  const done = async (result: unknown) => {
    const rec = (result && typeof result === "object" ? (result as { record?: BoardRecord }).record : undefined) ?? null;
    if (rec?.id) setFresh((x) => ({ ...x, [rec.id!]: rec }));
    setEditing(null);
    announce(`Correction saved as version ${rec?.version ?? rec?.corrected?.version ?? ""}.`.replace(" .", "."));
    await qc.invalidateQueries({ queryKey: ["case", caseId] });
    await onChanged?.();
  };

  return (
    <div className="space-y-3" data-testid="board-form">
      {liveNode}
      <p className="text-sm text-muted-foreground flex items-start gap-1.5"><ClipboardList className="size-4 mt-0.5 shrink-0" aria-hidden />Recorded by the MDT Coordinator during the meeting; read-only here. The decision is the board's, in its own words.</p>
      {!rounds.length ? (
        <EmptyState kind="wait" title="No board decision recorded yet" text={cf.case?.meeting_id ? "The form is filled during the meeting." : "The Case File is not on a meeting agenda yet."} action={coordinator && cf.case?.meeting_id ? <Link className="text-link underline" to={`/meetings/${cf.case.meeting_id}`}>Open the meeting</Link> : undefined} />
      ) : (
        <div className="space-y-3">
          {[...rounds].reverse().map(({ rec, n }) => (
            <RoundCard key={rec.id ?? n} rec={rec} n={n} latest={n === rounds.length} canCorrect={!!(rec.id && allowed[rec.id])} onCorrect={() => setEditing(rec)} />
          ))}
        </div>
      )}
      <Dialog open={!!editing} onOpenChange={(o) => { if (!o) setEditing(null); }}>
        <DialogContent aria-describedby="correct-desc" data-testid="correct-dialog" className="max-h-[calc(100dvh-2rem)] overflow-y-auto overflow-x-hidden p-4 sm:max-w-2xl sm:p-6">
          <DialogHeader>
            <DialogTitle className="pr-6">Correct this record{editing ? `: round ${rounds.find((x) => x.rec === editing)?.n ?? ""}` : ""}</DialogTitle>
            <DialogDescription id="correct-desc">
              For a slip in what was recorded. Change only what the board said differently; the record as first saved and every version stay kept, with your name and the reason.
            </DialogDescription>
          </DialogHeader>
          {editing ? <DecisionForm mode="correct" initial={editing} mid="" caseId={caseId} attendance={[]} onSaved={done} compact /> : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}
