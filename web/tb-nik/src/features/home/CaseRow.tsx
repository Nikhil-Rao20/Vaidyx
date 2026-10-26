// One row of the Case File list, read the way a treating doctor reads a ward list: the patient (name, age and sex, the UHID
// small), the cancer and its setting, then what the file is waiting for (the status word, how many records are left), the
// board date and the last change. The owner's name shows only on a file that is not the reader's own. Another department's
// Case File seen only through a link (night-v3 item 1.3) carries "Owned by <department>, read-only". The whole row opens the
// Case File; the search words are marked.
import { CalendarDays, Camera, Clock, Link2 } from "lucide-react";
import { DataRow } from "@/components/DataList";
import { UrgencyTag } from "@/components/UrgencyTag";
import { Pill, StatusPill } from "@/components/StatusPill";
import { DateText } from "@/components/DateText";
import { Highlight } from "@/components/Highlight";
import type { CaseListItem } from "@/lib/types";
import { drName } from "@/lib/format";

const SETTING: Record<string, string> = { early: "early", locally_advanced: "locally advanced", metastatic: "metastatic", recurrent: "recurrent" };

export function CaseRow({ c, q = "", showOwner = true }: { c: CaseListItem; q?: string; showOwner?: boolean }) {
  const cancer = c.protocol_label || c.cancer_name || "Cancer not set";
  const setting = c.setting ? SETTING[c.setting] || c.setting.replace(/_/g, " ") : "";
  const owner = c.owner?.doctor_name ? `${drName(c.owner.doctor_name)}${c.owner.department_label ? ` · ${c.owner.department_label}` : ""}` : c.owner?.department_label || "";
  const left = typeof c.left_before_board === "number" ? c.left_before_board : null;
  const showLeft = left !== null && left > 0 && (c.status?.key === "needs_me" || c.status?.key === "waiting_department" || c.status?.key === "draft");
  const uhid = c.patient?.uhid;
  const linkedOnly = Boolean(c.linked_only) || c.relation === "linked";
  const ownedBy = c.owned_by?.label || c.owner?.department_label || "another department";
  return (
    <DataRow to={`/cases/${encodeURIComponent(c.case_id)}`}>
      <div className="grid grid-cols-[2.25rem_1fr] items-center gap-x-3 gap-y-1 lg:grid-cols-[2.25rem_minmax(0,1.6fr)_minmax(0,1fr)_14rem_6.5rem_6rem] lg:gap-x-4">
        <UrgencyTag level={c.urgency?.level ?? null} proposed={c.urgency?.proposed ?? null} setByName={c.urgency?.set_by_name} size="sm" className="flex-col items-start" />
        <div className="min-w-0">
          <p className="flex min-w-0 items-baseline gap-x-2 truncate">
            <span className="truncate text-[15px] font-semibold text-foreground"><Highlight text={c.patient?.name || "Unnamed"} q={q} /></span>
            {c.patient?.agesex ? <span className="shrink-0 text-xs text-muted-foreground">{c.patient.agesex}</span> : null}
            {uhid ? <span className="id hidden shrink-0 text-xs text-muted-foreground/80 sm:inline"><Highlight text={uhid} q={q} id /></span> : null}
          </p>
          <p className="truncate text-sm text-body">
            <Highlight text={cancer} q={q} />
            {setting ? <span className="text-muted-foreground">, {setting}</span> : null}
            {c.imaging_present ? <Camera className="ml-1.5 inline size-3.5 align-[-2px] text-muted-foreground" aria-label="Imaging present" /> : null}
          </p>
          {linkedOnly ? <p className="mt-1"><Pill icon={Link2} title="Linked to a Case File of your department; you can read it, not change it">Owned by {ownedBy}, read-only</Pill></p> : null}
        </div>
        <p className="col-start-2 truncate text-xs text-muted-foreground lg:col-start-auto lg:text-sm">
          {showOwner && !c.mine && owner ? <Highlight text={owner} q={q} /> : c.residents_count ? `${c.residents_count} resident${c.residents_count === 1 ? "" : "s"} on it` : ""}
        </p>
        <div className="col-start-2 flex min-w-0 items-center gap-2 lg:col-start-auto">
          <StatusPill status={c.status} className="min-w-0" />
          {showLeft ? <span className="shrink-0 text-xs text-muted-foreground tabular-nums">{left} left</span> : null}
        </div>
        <p className="col-start-2 hidden items-center gap-1 text-xs text-muted-foreground lg:col-start-auto lg:flex" title="Board date">
          <CalendarDays className="size-3.5" aria-hidden /> <DateText value={c.board_date} fallback="no date" />
        </p>
        <p className="col-start-2 hidden items-center gap-1 text-xs text-muted-foreground lg:col-start-auto lg:flex" title="Last change">
          <Clock className="size-3.5" aria-hidden /> <DateText value={c.last_change || c.created} mode="ago" />
        </p>
      </div>
    </DataRow>
  );
}
