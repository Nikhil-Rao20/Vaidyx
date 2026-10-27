// One past Case File in the Similar Case Files list (night-v3 item 7.3, docs/night-v3/research/07_similar_cases.md 4.7 and 8.4): the
// label "Past Case File, not advice for this patient" first, the cancer, the stage with where it was written, the key values with their
// quotes, the board decisions as written by the board, the outcome so far, and the quoted "why similar" and "how it differs" lines.
// No number, rank, percent, bar or stars: the order of the list is the only order.
import { FolderOpen } from "lucide-react";
import type { SimilarLine, SimilarResult } from "../types";
import { LoadingButton, StatusChip } from "./common";

export const SIMILAR_LABEL = "Past Case File, not advice for this patient";

const words = (s?: string) => (s ?? "").replace(/_/g, " ").trim();
/** A quote that only repeats the value shown is not drawn twice. */
const same = (a?: string, b?: string) => (a ?? "").replace(/\s+/g, " ").trim().toLowerCase() === (b ?? "").replace(/\s+/g, " ").trim().toLowerCase();

function Part({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <h4 className="text-xs font-semibold text-muted-foreground">{title}</h4>
      {children}
    </div>
  );
}

/** A quote in the published-case style: the words as written, then where they sit. */
function Quoted({ text, where }: { text: string; where?: string }) {
  return <span className="block border-l-2 border-border pl-2 text-sm"><span className="text-foreground">{text}</span>{where ? <> <span className="text-xs text-muted-foreground">({where})</span></> : null}</span>;
}

function Lines({ lines, testId }: { lines: SimilarLine[]; testId: string }) {
  return (
    <ul className="space-y-1.5" data-testid={testId}>
      {lines.map((l, i) => (
        <li key={i} className="space-y-0.5 text-sm">
          {l.about ? <StatusChip kind="muted" className="whitespace-normal">{words(l.about)}</StatusChip> : null}
          <span className="block text-foreground">This file, {l.this.where}: &quot;{l.this.text}&quot;.</span>
          <span className="block text-foreground">Past file, {l.past.where}: &quot;{l.past.text}&quot;.</span>
        </li>
      ))}
    </ul>
  );
}

export function SimilarResultCard({ r, onOpen, opening, message }: { r: SimilarResult; onOpen: () => void; opening: boolean; message?: string | null }) {
  const label = r.label || SIMILAR_LABEL;
  const kinds = Array.from(new Set(r.stage.map((s) => s.label).filter(Boolean)));
  const ageSex = [r.age_band, r.sex].filter(Boolean).join(", ");
  const values = [...r.values].sort((a, b) => Number(!!b.shared) - Number(!!a.shared));
  const outcome = r.outcome_so_far ?? { sentences: [] };
  return (
    <li className="min-w-0 space-y-2 rounded-md border border-border p-3 break-words" data-testid="similar-item" data-case={r.case_id}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <p className="text-sm font-semibold text-foreground">Past Case File {r.case_id}</p>
        <StatusChip kind="muted" className="whitespace-normal">{label}</StatusChip>
        {kinds.map((k) => <StatusChip key={k} kind="info" className="whitespace-normal">{k}</StatusChip>)}
      </div>
      <p className="text-sm text-foreground">
        {[r.cancer, words(r.setting)].filter(Boolean).join(", ")}
        {ageSex ? <span className="text-muted-foreground"> · {ageSex}</span> : null}
      </p>

      <Part title="Stage">
        {r.stage.length ? (
          <ul className="space-y-1">
            {r.stage.map((s, i) => (
              <li key={i} className="text-sm">
                <span className="font-medium text-foreground">{s.text}</span>{" "}
                <span className="text-xs text-muted-foreground">({[s.label, s.where].filter(Boolean).join(", ")})</span>
                {s.quote && !same(s.quote, s.text) ? <Quoted text={s.quote} /> : null}
              </li>
            ))}
          </ul>
        ) : <p className="text-sm text-muted-foreground">No stage recorded; none confirmed</p>}
      </Part>

      {values.length ? (
        <Part title="Key values">
          <ul className="space-y-1">
            {values.map((v, i) => (
              <li key={`${v.fact}-${i}`} className="text-sm">
                <span className="text-muted-foreground">{v.label}:</span> <span className="text-foreground">{v.value}</span>
                {v.shared ? <> <StatusChip kind="muted">also on this file</StatusChip></> : null}
                {v.quote && !same(v.quote, v.value) ? <Quoted text={v.quote} where={v.where} /> : v.where ? <> <span className="text-xs text-muted-foreground">({v.where})</span></> : null}
              </li>
            ))}
          </ul>
        </Part>
      ) : null}

      <Part title="Board decisions">
        {r.decisions.length ? (
          <ul className="space-y-2">
            {r.decisions.map((d) => (
              <li key={d.record_id} className="space-y-1" data-testid="similar-decision">
                <p className="text-sm text-foreground">
                  <span className="font-medium">Board, {d.when}:</span> {[d.outcome_label || words(d.outcome), d.intent_label || d.intent ? `intent ${d.intent_label || words(d.intent)}` : ""].filter(Boolean).join(", ")}
                </p>
                {d.text ? (
                  <figure className="border-l-2 border-border pl-2">
                    <blockquote className="text-sm text-foreground">{d.text}</blockquote>
                    <figcaption className="text-xs text-muted-foreground">as written by the board</figcaption>
                  </figure>
                ) : null}
                {(d.modalities ?? []).length ? <div className="flex flex-wrap gap-1">{d.modalities!.map((m) => <StatusChip key={m} kind="muted">{words(m)}</StatusChip>)}</div> : null}
                {d.stage_as_agreed ? <p className="text-xs text-muted-foreground">Stage as agreed by the board: {d.stage_as_agreed}</p> : null}
              </li>
            ))}
          </ul>
        ) : <p className="text-sm text-muted-foreground">No board decision shown.</p>}
      </Part>

      <Part title="Outcome so far">
        {outcome.sentences.length || outcome.later_records ? (
          <>
            {outcome.sentences.length ? <ul className="space-y-1">{outcome.sentences.map((s, i) => <li key={i}><Quoted text={s.text} where={s.where} /></li>)}</ul> : null}
            {outcome.later_records ? <p className="text-xs text-muted-foreground">{outcome.later_records}</p> : null}
          </>
        ) : <p className="text-sm text-muted-foreground">No records after the board decision yet</p>}
      </Part>

      <Part title="Why similar">
        {r.similar.length ? <Lines lines={r.similar.slice(0, 3)} testId="similar-why" /> : null}
        {r.no_reasons || !r.similar.length ? (
          <div className="space-y-1">
            <StatusChip kind="muted">No quoted reasons found</StatusChip>
            {(r.matched_by ?? []).length ? <p className="text-sm text-muted-foreground">Matched by recorded fields: {r.matched_by!.join(", ")}</p> : null}
          </div>
        ) : null}
      </Part>

      {r.differs.length ? <Part title="How it differs"><Lines lines={r.differs.slice(0, 2)} testId="similar-differs" /></Part> : null}

      <div className="flex flex-wrap items-center gap-2 border-t border-border pt-2">
        <span className="min-w-0 flex-1 text-xs text-muted-foreground">{label}</span>
        <LoadingButton size="sm" variant="outline" loading={opening} loadingText="Opening" onClick={onOpen} data-testid="similar-open"><FolderOpen className="size-4" aria-hidden />Open Past Case File</LoadingButton>
      </div>
      {message ? <p role="status" className="text-xs text-muted-foreground" data-testid="similar-open-message">{message}</p> : null}
    </li>
  );
}
