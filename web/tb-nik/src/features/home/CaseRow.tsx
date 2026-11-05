// One row of the Case File list, read the way a treating doctor reads a ward list: the patient (name, age and sex, the UHID
// small), the cancer and its setting, the Case File's summary line (night-v3 3.4, full readers only), then what the file is
// waiting for (the status word, how many records are left), the board date and the last change. The owner's name shows only on a file that is not the reader's own. Another department's
// Case File seen only through a link (night-v3 item 1.3) carries "Owned by <department>, read-only". The whole row opens the
// Case File; the search words are marked. On a row the reader may act on (the owner's consultant, the MDT Coordinator) the
// "Scheduled <date>" pill is a chip with a small menu: Move to another meeting, Take off the agenda (night-v3 item 1.6); the list
// hosts the dialogs. Such a row is not one link (a button inside a link is invalid, review 9 C, I2): the patient block is the link,
// stretched over the row, and the chip sits above it as its own control.
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { CalendarDays, CalendarMinus, CalendarSync, Camera, ChevronDown, Clock, Link2, Lock } from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { DataRow, RowArrow, rowClass } from "@/components/DataList";
import { UrgencyTag } from "@/components/UrgencyTag";
import { Pill, StatusPill } from "@/components/StatusPill";
import { DateText } from "@/components/DateText";
import { Highlight } from "@/components/Highlight";
import type { CaseListItem } from "@/lib/types";
import { drName } from "@/lib/format";

const SETTING: Record<string, string> = { early: "early", locally_advanced: "locally advanced", metastatic: "metastatic", recurrent: "recurrent" };

export type MeetingAction = "move" | "withdraw";

/** The "Scheduled <date>" pill as a button with a menu: a sibling of the row's link, drawn above its stretched area. */
function MeetingChip({ c, onMeeting }: { c: CaseListItem; onMeeting: (a: MeetingAction) => void }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" data-testid="meeting-chip" title="Move to another meeting or take it off the agenda"
          className="relative z-10 inline-flex min-w-0 items-center gap-0.5 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <StatusPill status={c.status} className="min-w-0 cursor-pointer hover:brightness-95" />
          <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
          <span className="sr-only">, move or take off the agenda</span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-60" onClick={(e) => e.stopPropagation()}>
        <DropdownMenuItem onSelect={() => onMeeting("move")} data-testid="chip-move"><CalendarSync className="size-4" />Move to another meeting</DropdownMenuItem>
        <DropdownMenuItem onSelect={() => onMeeting("withdraw")} data-testid="chip-withdraw"><CalendarMinus className="size-4" />Take off the agenda</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function CaseRow({ c, q = "", showOwner = true, onMeeting }: { c: CaseListItem; q?: string; showOwner?: boolean; onMeeting?: (a: MeetingAction) => void }) {
  const cancer = c.protocol_label || c.cancer_name || "Cancer not set";
  const setting = c.setting ? SETTING[c.setting] || c.setting.replace(/_/g, " ") : "";
  const owner = c.owner?.doctor_name ? `${drName(c.owner.doctor_name)}${c.owner.department_label ? ` · ${c.owner.department_label}` : ""}` : c.owner?.department_label || "";
  const left = typeof c.left_before_board === "number" ? c.left_before_board : null;
  const showLeft = left !== null && left > 0 && (c.status?.key === "needs_me" || c.status?.key === "waiting_department" || c.status?.key === "draft");
  const uhid = c.patient?.uhid;
  const linkedOnly = Boolean(c.linked_only) || c.relation === "linked";
  const ownedBy = c.owned_by?.label || c.owner?.department_label || "another department";
  const to = `/cases/${encodeURIComponent(c.case_id)}`;
  const chip = !!onMeeting && c.status?.key === "scheduled" && c.status.detail !== "in session";
  const main = (
    <div className="min-w-0">
      <p className="flex min-w-0 items-baseline gap-x-2 truncate">
        <span className="truncate text-[15px] font-semibold text-foreground"><Highlight text={c.patient?.name || "Unnamed"} q={q} /></span>
        {c.patient?.agesex ? <span className="shrink-0 text-xs text-muted-foreground">{c.patient.agesex}</span> : null}
        {uhid ? <span className="id hidden shrink-0 text-xs text-muted-foreground sm:inline"><Highlight text={uhid} q={q} id /></span> : null}
      </p>
      <p className="truncate text-sm text-body">
        <Highlight text={cancer} q={q} />
        {setting ? <span className="text-muted-foreground">, {setting}</span> : null}
        {c.imaging_present ? <Camera className="ml-1.5 inline size-3.5 align-[-2px] text-muted-foreground" aria-label="Imaging present" /> : null}
      </p>
      {c.summary_line ? <p className="truncate text-xs text-muted-foreground" data-testid="row-summary-line"><Highlight text={c.summary_line} q={q} /></p> : null}
      {c.private ? <p className="mt-1"><Pill icon={Lock} title="Only the guest reviewer and the MDT Coordinator can see this Case File">Private</Pill></p> : null}
      {linkedOnly ? <p className="mt-1"><Pill icon={Link2} title="Linked to a Case File of your department; you can read it, not change it">Owned by {ownedBy}, read-only</Pill></p> : null}
    </div>
  );
  const grid = (patient: ReactNode) => (
    <div className="grid grid-cols-[2.25rem_1fr] items-center gap-x-3 gap-y-1 lg:grid-cols-[2.25rem_minmax(0,1.6fr)_minmax(0,1fr)_14rem_6.5rem_6rem] lg:gap-x-4">
      <UrgencyTag level={c.urgency?.level ?? null} proposed={c.urgency?.proposed ?? null} setByName={c.urgency?.set_by_name} size="sm" className="flex-col items-start" />
      {patient}
      <p className="col-start-2 truncate text-xs text-muted-foreground lg:col-start-auto lg:text-sm">
        {showOwner && !c.mine && owner ? <Highlight text={owner} q={q} /> : c.residents_count ? `${c.residents_count} resident${c.residents_count === 1 ? "" : "s"} on it` : ""}
      </p>
      <div className="col-start-2 flex min-w-0 items-center gap-2 lg:col-start-auto">
        {chip && onMeeting ? <MeetingChip c={c} onMeeting={onMeeting} /> : <StatusPill status={c.status} className="min-w-0" />}
        {showLeft ? <span className="shrink-0 text-xs text-muted-foreground tabular-nums">{left} left</span> : null}
      </div>
      <p className="col-start-2 hidden items-center gap-1 text-xs text-muted-foreground lg:col-start-auto lg:flex" title="Board date">
        <CalendarDays className="size-3.5" aria-hidden /> <DateText value={c.board_date} fallback="no date" />
      </p>
      <p className="col-start-2 hidden items-center gap-1 text-xs text-muted-foreground lg:col-start-auto lg:flex" title="Last change">
        <Clock className="size-3.5" aria-hidden /> <DateText value={c.last_change || c.created} mode="ago" />
      </p>
    </div>
  );
  if (!chip) return <DataRow to={to}>{grid(main)}</DataRow>;
  // The patient block is the link; its ::after covers the whole row, so a click anywhere but the chip opens the Case File.
  return (
    <div className={rowClass(true, "relative")} data-testid="case-row">
      <div className="min-w-0 flex-1">
        {grid(<Link to={to} className="block min-w-0 outline-none after:absolute after:inset-0 after:rounded-[inherit] focus-visible:after:ring-2 focus-visible:after:ring-ring">{main}</Link>)}
      </div>
      <RowArrow />
    </div>
  );
}
