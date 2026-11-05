// The Case Files page (the home of every clinical role): the title with a greeting under it, "Join a Case File" and "Join a
// meeting" (each opens the 6-digit code dialog; the owner, 18 Oct), "+ New Case File" for those who may create, the waiting
// strip, the coordinator's next meeting card, the gift box when there is nothing yet, the Ask PubMed card (3 Nov 2026) and the list.
import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { KeyRound, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/PageHeader";
import { JoinDialog, type JoinKind } from "@/components/JoinDialog";
import ClickSpark from "@/components/vendor/ClickSpark";
import { WaitingStrip } from "@/features/home/WaitingStrip";
import { NextMeetingCard } from "@/features/home/NextMeetingCard";
import { GiftBox } from "@/features/home/GiftBox";
import { CaseFileList, type ListCounts } from "@/features/home/CaseFileList";
import { AskPubMedCard } from "@/features/pubmed/AskPubMedCard";
import type { Me } from "@/lib/session";

function greeting(): string {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

/** One of the two join buttons: the name in plain words and, under it, where the code comes from. */
function JoinButton({ label, hint, onClick }: { label: string; hint: string; onClick: () => void }) {
  return (
    <Button type="button" variant="outline" onClick={onClick} className="h-auto min-h-10 min-w-0 flex-1 basis-0 flex-col items-start gap-0 whitespace-normal py-1.5 text-left sm:flex-none sm:basis-auto">
      <span className="inline-flex items-center gap-1.5"><KeyRound className="size-4 text-muted-foreground" aria-hidden />{label}</span>
      <span className="text-[11px] font-normal leading-tight text-muted-foreground">{hint}</span>
    </Button>
  );
}

export function CaseFileHome({ me }: { me: Me }) {
  const [counts, setCounts] = useState<ListCounts | null>(null);
  const [join, setJoin] = useState<JoinKind | null>(null);
  const onCount = useCallback((n: ListCounts) => setCounts(n), []);
  const treating = (me.roles.treating || []).length > 0;
  const coordinator = Boolean(me.roles.coordinator);
  const resident = !treating && Object.values(me.roles.departments || {}).includes("resident");
  const canCreate = treating || coordinator;
  const title = me.profile?.title?.trim();
  const name = me.display_name && me.display_name !== me.user ? (title ? `${title} ${me.display_name.replace(new RegExp(`^${title}\\.?\\s+`, "i"), "")}` : me.display_name) : "";
  const where = coordinator && !treating
    ? "every department's Case Files, the ready list and the next meeting"
    : resident
      ? "the Case Files you are on; steps that need a consultant's sign-off go to them from here"
      : me.hospital?.name ? `your department's Case Files at ${me.hospital.name}` : "your department's Case Files";
  return (
    <div>
      <PageHeader
        title="Case Files"
        subtitle={`${greeting()}${name ? `, ${name}` : ""}. Here are ${where}.`}
        actions={
          <>
            {me.real_data ? null : <JoinButton label="Join a Case File" hint="6-digit code from the consultant" onClick={() => setJoin("case")} />}
            <JoinButton label="Join a meeting" hint="6-digit code from the coordinator" onClick={() => setJoin("meeting")} />
            {canCreate ? (
              <ClickSpark sparkColor="var(--primary)" sparkCount={8} sparkRadius={18} duration={420}>
                <Button type="button" className="hover:bg-primary-hover active:scale-[0.97]" asChild>
                  <Link to="/cases/new"><Plus className="size-4" aria-hidden /> New Case File</Link>
                </Button>
              </ClickSpark>
            ) : null}
          </>
        }
      />
      <WaitingStrip me={me} />
      {coordinator ? <NextMeetingCard readyCount={counts?.ready ?? 0} waitingCount={counts?.waiting ?? 0} /> : null}
      {/* a guest reviewer (real_data) has no hospital system to fetch from: no UHID box (5 Nov 2026) */}
      {canCreate && !me.real_data && counts && counts.all === 0 ? <GiftBox className="mb-5" /> : null}
      {canCreate && !me.real_data && counts && counts.all > 0 && counts.all < 3 ? <GiftBox compact className="mb-5" /> : null}
      <AskPubMedCard className="mb-5" />
      <CaseFileList me={me} canCreate={canCreate} onCount={onCount} />
      <JoinDialog kind={join ?? "case"} open={join !== null} onOpenChange={(o) => { if (!o) setJoin(null); }} />
    </div>
  );
}
