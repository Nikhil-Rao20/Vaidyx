// The Case Files page (the home of every clinical role): the title with a greeting under it, "+ New Case File" and "Join with
// a code", the waiting strip, the coordinator's next meeting card, the gift box when there is nothing yet, and the list.
import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { CalendarPlus, ChevronDown, KeyRound, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { PageHeader } from "@/components/PageHeader";
import { JoinDialog, type JoinKind } from "@/components/JoinDialog";
import ClickSpark from "@/components/vendor/ClickSpark";
import { WaitingStrip } from "@/features/home/WaitingStrip";
import { NextMeetingCard } from "@/features/home/NextMeetingCard";
import { GiftBox } from "@/features/home/GiftBox";
import { CaseFileList, type ListCounts } from "@/features/home/CaseFileList";
import type { Me } from "@/lib/session";

function greeting(): string {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
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
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button type="button" variant="outline"><KeyRound className="size-4" aria-hidden /> Join with a code <ChevronDown className="size-3.5 opacity-70" aria-hidden /></Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onSelect={() => setJoin("case")}><KeyRound className="size-4" aria-hidden /> A Case File (6-digit code from the consultant)</DropdownMenuItem>
                <DropdownMenuItem onSelect={() => setJoin("meeting")}><CalendarPlus className="size-4" aria-hidden /> A meeting (6-digit code from the coordinator)</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
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
      {canCreate && counts && counts.all === 0 ? <GiftBox className="mb-5" /> : null}
      {canCreate && counts && counts.all > 0 && counts.all < 3 ? <GiftBox compact className="mb-5" /> : null}
      <CaseFileList me={me} canCreate={canCreate} onCount={onCount} />
      <JoinDialog kind={join ?? "case"} open={join !== null} onOpenChange={(o) => { if (!o) setJoin(null); }} />
    </div>
  );
}
