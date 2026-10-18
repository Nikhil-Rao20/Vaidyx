// One row of the Case File list (SPEC 3.3): urgency tag, patient line, cancer, "from Dr X, Dept Y", status word
// with icon, board date, last change. The whole row opens the Case File; it lifts and shows an arrow on hover.
import { Camera, CalendarDays, Clock } from "lucide-react";
import { DataRow } from "@/components/DataList";
import { UrgencyTag } from "@/components/UrgencyTag";
import { PatientLine } from "@/components/PatientLine";
import { StatusPill } from "@/components/StatusPill";
import { DateText } from "@/components/DateText";
import type { CaseListItem } from "@/lib/types";
import { drName } from "@/lib/format";

export function CaseRow({ c }: { c: CaseListItem }) {
  const cancer = c.protocol_label || c.cancer_name || "Cancer not set";
  const owner = c.owner?.doctor_name ? `from ${drName(c.owner.doctor_name)}${c.owner.department_label ? `, ${c.owner.department_label}` : ""}` : c.owner?.department_label ? `from ${c.owner.department_label}` : "";
  const left = typeof c.left_before_board === "number" ? c.left_before_board : null;
  return (
    <DataRow to={`/cases/${encodeURIComponent(c.case_id)}`} ariaLabel={`${c.patient?.name || "Unnamed"}, ${cancer}, ${c.status?.label || c.status?.key}`}>
      <div className="grid grid-cols-[2.75rem_1fr] items-center gap-x-3 gap-y-1 lg:grid-cols-[2.75rem_minmax(0,1.6fr)_minmax(0,1fr)_auto_7.5rem_6.5rem] lg:gap-x-4">
        <UrgencyTag level={c.urgency?.level ?? null} proposed={c.urgency?.proposed ?? null} setByName={c.urgency?.set_by_name} className="flex-col items-start" />
        <div className="min-w-0">
          <PatientLine patient={c.patient} />
          <p className="truncate text-sm text-muted-foreground">
            <span className="text-foreground">{cancer}</span>
            {c.setting ? <span>, {c.setting.replace(/_/g, " ")} as recorded</span> : null}
            {c.imaging_present ? <span className="ml-2 inline-flex items-center gap-0.5 align-middle text-xs"><Camera className="size-3" aria-hidden /> imaging</span> : null}
          </p>
        </div>
        <p className="col-start-2 truncate text-xs text-muted-foreground lg:col-start-auto lg:text-sm">{owner}</p>
        <div className="col-start-2 flex flex-wrap items-center gap-2 lg:col-start-auto lg:justify-end">
          <StatusPill status={c.status} />
          {left !== null && left > 0 && (c.status?.key === "needs_me" || c.status?.key === "waiting_department" || c.status?.key === "draft") ? (
            <span className="text-xs text-muted-foreground tabular-nums">{left} left</span>
          ) : null}
        </div>
        <p className="col-start-2 hidden items-center gap-1 text-xs text-muted-foreground lg:col-start-auto lg:flex" title="Board date">
          <CalendarDays className="size-3.5" aria-hidden /> <DateText value={c.board_date} fallback="no board date" />
        </p>
        <p className="col-start-2 hidden items-center gap-1 text-xs text-muted-foreground lg:col-start-auto lg:flex" title="Last change">
          <Clock className="size-3.5" aria-hidden /> <DateText value={c.last_change || c.created} mode="ago" />
        </p>
      </div>
    </DataRow>
  );
}
