// Home for the treating doctor, the resident and the coordinator: greeting, "+ New Case File", the waiting strip,
// the coordinator's next meeting card, the gift box when there is nothing yet, and the list.
import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/PageHeader";
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
  const onCount = useCallback((n: ListCounts) => setCounts(n), []);
  const treating = (me.roles.treating || []).length > 0;
  const coordinator = Boolean(me.roles.coordinator);
  const resident = !treating && Object.values(me.roles.departments || {}).includes("resident");
  const canCreate = treating || coordinator;
  const title = me.profile?.title?.trim();
  const name = me.display_name && me.display_name !== me.user ? (title ? `${title} ${me.display_name.replace(new RegExp(`^${title}\\.?\\s+`, "i"), "")}` : me.display_name) : "";
  const subtitle = coordinator && !treating
    ? "The Case Files of every department, the ready list and the next meeting."
    : resident
      ? "The Case Files you are on. Steps that need a consultant's sign-off go to them from here."
      : me.hospital?.name ? `${me.hospital.name}. Your department's Case Files, newest first.` : "Your department's Case Files, newest first.";
  return (
    <div>
      <PageHeader
        title={`${greeting()}${name ? `, ${name}` : ""}`}
        subtitle={subtitle}
        actions={canCreate ? (
          <ClickSpark sparkColor="var(--primary)" sparkCount={8} sparkRadius={18} duration={420}>
            <Button type="button" className="hover:bg-primary-hover active:scale-[0.97]" asChild>
              <Link to="/cases/new"><Plus className="size-4" aria-hidden /> New Case File</Link>
            </Button>
          </ClickSpark>
        ) : undefined}
      />
      <WaitingStrip me={me} />
      {coordinator ? <NextMeetingCard readyCount={counts?.ready ?? 0} waitingCount={counts?.waiting ?? 0} /> : null}
      {canCreate && counts && counts.all === 0 ? <GiftBox className="mb-5" /> : null}
      {canCreate && counts && counts.all > 0 && counts.all < 3 ? <GiftBox compact className="mb-5" /> : null}
      <CaseFileList me={me} canCreate={canCreate} onCount={onCount} />
    </div>
  );
}
