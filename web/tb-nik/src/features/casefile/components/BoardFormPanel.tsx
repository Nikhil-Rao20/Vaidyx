// Board form: the ten fields the coordinator records during the meeting. Read-only here for everyone; the coordinator
// fills it on the meeting control view.
import { Link } from "react-router-dom";
import { ClipboardList } from "lucide-react";
import type { BoardRecord, CaseFile } from "../types";
import { EmptyState, StatusChip, fmtDate, fmtDateTime } from "./common";

const OUTCOME: Record<string, string> = { decision: "Decision", deferred: "Deferred", referred: "Referred", not_discussed: "Not discussed", noted: "Noted" };

/** A list the old board records keep as a string and the new ones as an array. */
function listText(v: unknown): string | undefined {
  if (Array.isArray(v)) return v.map((x) => (typeof x === "string" ? x : x && typeof x === "object" && "name" in x ? String((x as { name: unknown }).name) : "")).filter(Boolean).join(", ") || undefined;
  return typeof v === "string" && v.trim() ? v : undefined;
}

export function latestBoardRecord(cf: CaseFile): BoardRecord | null {
  if (cf.case?.board_record) return cf.case.board_record;
  const recs = cf.state?.board_records ?? [];
  return recs.length ? recs[recs.length - 1] : null;
}

export function BoardFormPanel({ cf, coordinator }: { cf: CaseFile; coordinator: boolean }) {
  const rec = latestBoardRecord(cf);
  const outcome = rec?.meeting_outcome ?? rec?.outcome ?? rec?.outcome_type;
  const rows: Array<[string, string | undefined]> = rec ? [
    ["Outcome", outcome ? OUTCOME[outcome] ?? outcome.replace(/_/g, " ") : undefined],
    ["Decision as recorded", rec.decision_text],
    ["Rationale as discussed", rec.rationale],
    ["Treatment intent as stated by the board", rec.intent_as_stated ?? rec.intent_as_recorded],
    ["Responsible doctor", rec.responsible_doctor],
    ["Next step and date", [rec.next_step, rec.next_step_date ? fmtDate(rec.next_step_date) : ""].filter(Boolean).join(", ") || undefined],
    ["Awaited, from whom", [rec.awaited ?? rec.deferred_reason, rec.awaited_from].filter(Boolean).join(", from ") || undefined],
    ["Referred to", rec.referred_to],
    ["Members present", listText(rec.members_present ?? rec.participants)],
    ["Concerns", Array.isArray(rec.concerns) ? rec.concerns.map((c) => (c.by ? `${c.by}: ${c.text}` : c.text)).join("; ") || undefined : listText(rec.concerns as unknown)],
  ] : [];
  return (
    <div className="space-y-3" data-testid="board-form">
      <p className="text-sm text-muted-foreground flex items-start gap-1.5"><ClipboardList className="size-4 mt-0.5 shrink-0" aria-hidden />Recorded by the MDT Coordinator during the meeting; read-only here. The decision is the board's, in its own words.</p>
      {!rec ? (
        <EmptyState kind="wait" title="No board decision recorded yet" text={cf.case?.meeting_id ? "The form is filled during the meeting." : "The Case File is not on a meeting agenda yet."} action={coordinator && cf.case?.meeting_id ? <Link className="text-link underline" to={`/meetings/${cf.case.meeting_id}`}>Open the meeting</Link> : undefined} />
      ) : (
        <dl className="divide-y divide-border rounded-md border border-border">
          {rows.map(([k, v]) => (
            <div key={k} className="grid grid-cols-[9rem_1fr] gap-2 px-3 py-2 text-sm">
              <dt className="text-muted-foreground">{k}</dt>
              <dd className="text-foreground">{v || <span className="text-muted-foreground">not recorded</span>}</dd>
            </div>
          ))}
          <div className="px-3 py-2 text-xs text-muted-foreground flex flex-wrap gap-2">
            {rec.recorded_at ? <span>recorded {fmtDateTime(rec.recorded_at)}</span> : null}
            {rec.recorded_by ? <span>by {rec.recorded_by}</span> : null}
            {outcome ? <StatusChip kind={outcome === "decision" ? "ok" : outcome === "deferred" ? "warn" : "info"}>{OUTCOME[outcome] ?? outcome}</StatusChip> : null}
          </div>
        </dl>
      )}
    </div>
  );
}
