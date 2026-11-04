// The meeting's Ask PubMed panel (docs/pubmed-ask/DESIGN.md section 8), beside Agents: general questions answered only from PubMed
// abstracts, every line quoted. Case File mode for the case on the floor (the team's PubMed threads of that Case File; the meeting
// READ window lets an admitted member ask), for the coordinator and the members. An outside expert, or a meeting with no case on the
// screen, asks from Home (their own history, no patient context). The agents keep answering from the records and guidelines only.
import { useSession } from "@/lib/session";
import { PubMedAsk } from "@/features/pubmed/PubMedAsk";
import { useCall } from "../context";

export function PubMedPanel() {
  const ctx = useCall();
  const { me } = useSession();
  const cid = ctx.cid && !ctx.expert ? ctx.cid : null;
  // Save to the Published list: the owner consultant of the Case File on the floor (as POST /cases/{id}/published).
  const owner = ctx.row?.owner_department ?? "";
  const placement = owner ? me?.roles?.departments?.[owner] : undefined;
  const canSave = !!cid && !!owner && (placement === "member" || placement === "head" || (me?.roles?.treating ?? []).includes(owner));
  const where = cid
    ? "Kept with the Case File on the screen; the whole team sees the answers."
    : ctx.expert
      ? "General questions only; the answers stay in your own PubMed history."
      : "No Case File on the screen: the answers stay in your own PubMed history.";
  return (
    <div data-testid="pubmed-panel-body" data-case={cid ?? ""}>
      <PubMedAsk key={cid ?? "home"} caseId={cid ?? undefined} variant="meeting" canSave={canSave} compact={ctx.phone} note={where} />
    </div>
  );
}
