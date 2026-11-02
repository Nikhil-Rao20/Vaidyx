// The Decision panel of the call (night-v3 5.1, research/04 section 6.9): the coordinator's Decision tab as it was in the control
// view: the recorded banner, the decision form (compact), End case or Ask for the cards again, and the cards given so far (read every
// 15 s). Only for the coordinator or whoever may record; members see the live decision text on the strip only.
import { useQuery } from "@tanstack/react-query";
import { StopCircle } from "lucide-react";
import { LoadingButton } from "@/features/casefile/components/common";
import { getCards } from "../../api";
import { DecisionForm } from "../../components/DecisionForm";
import { usePanelAction } from "../../components/People";
import type { CardsResponse } from "../../types";
import { useCall } from "../context";

/** The cards line of a Case File: who agrees, who has a concern, how many are still to give one. */
export function cardsLine(c: CardsResponse["cards"][string] | undefined): string {
  if (!c) return "";
  const given = c.cards.length ? `Cards: ${c.cards.map((x) => `${x.name ?? x.user} ${x.agree ? "agrees" : "has a concern"}`).join("; ")}.` : "No cards yet.";
  const rest = c.missing.length ? ` Waiting for ${c.missing.length}.` : c.cards.length ? " Every head has given a card." : "";
  return given + rest;
}

export function DecisionPanel() {
  const ctx = useCall();
  const { mid, state, cid, row, canManage, canRecord } = ctx;
  const allowed = canManage || canRecord;
  const act = usePanelAction();
  const cards = useQuery({ queryKey: ["cards", mid], queryFn: () => getCards(mid), retry: false, refetchInterval: 15_000, enabled: allowed });
  if (!allowed) return <p className="text-sm text-muted-foreground">The MDT Coordinator records the decision; you see it as it is typed on the strip under the screen.</p>;
  const caseCards = cid ? cards.data?.cards?.[cid] : undefined;
  const ended = !!cid && (state.ended ?? []).includes(cid);
  const outcome = cid ? state.outcomes?.[cid] : undefined;
  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold text-foreground">Decision{row ? ` for ${row.patient_line}` : ""}</h3>
      {outcome ? <p className="rounded-md status-ok px-2 py-1 text-sm">Recorded: {outcome.label ?? outcome.outcome}. To change it, correct the record from the Case File's Board decisions panel.</p> : null}
      {/* once the outcome is recorded the form is gone: no more live text on the room screen, no Save that answers 409 (review finding 12) */}
      {cid && !outcome ? <DecisionForm mid={mid} caseId={cid} attendance={state.attendance} onSaved={() => ctx.refresh()} liveText={state.decision_live?.case_id && state.decision_live.case_id !== cid ? undefined : state.decision_live?.text} canRecord={state.can?.record !== false} compact /> : <p className="text-sm text-muted-foreground">Pick a case first.</p>}
      <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
        {canManage ? <LoadingButton size="sm" variant="outline" loading={act.pending === "end"} onClick={() => void act.run("end", async () => { await ctx.actions.endCase(); void cards.refetch(); })} disabled={!cid} title="Asks each board head for their card (Agree / Concern)" data-testid="end-case"><StopCircle className="size-4" />{ended ? "Ask for the cards again" : "End case, ask for cards"}</LoadingButton> : null}
        {caseCards ? <span className="text-xs text-muted-foreground" data-testid="cards-summary">{cardsLine(caseCards)}</span> : null}
      </div>
      {act.error ? <p role="alert" className="text-xs text-bad">{act.error}</p> : null}
    </div>
  );
}
