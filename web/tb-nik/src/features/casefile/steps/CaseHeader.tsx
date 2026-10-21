// The guided Case File's header (B1, B9): who the patient is (name and UHID on every section, NISTIR two identifiers), the cancer as
// recorded, the owner, the board date and the urgency; on the right the one final action "Send to the board" and one "More" menu
// (Team, Board form, Print, Download, Archive). Nothing else: the work is in the sections.
import { Link } from "react-router-dom";
import { Archive, CalendarDays, ChevronDown, ClipboardList, Download, MoreHorizontal, Presentation, Printer, Send, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { UrgencyTag } from "@/components/UrgencyTag";
import { GENERIC_RULE, NO_CHECKLIST_WORDS, isGeneric } from "@/lib/cancers";
import { ownerOf } from "../api";
import type { CaseFile, Team } from "../types";
import { StatusChip, fmtDate } from "../components/common";
import type { Steps } from "./types";

export type MorePanel = "team" | "board";

export function CaseHeader({ cf, team, steps, onSend, onPanel, onPrint, deckHref, exportHref, exportAllowed, onArchive, resident, consultantName }: {
  cf: CaseFile; team: Team | null; steps: Steps | null; onSend: () => void; onPanel: (p: MorePanel) => void; onPrint: () => void;
  deckHref: string; exportHref: string; exportAllowed: boolean; onArchive?: () => void; resident: boolean; consultantName: string;
}) {
  const c = cf.case;
  const p = c.patient ?? { name: "", mrn: "", agesex: "" };
  const generic = isGeneric(c.protocol);
  const cancerName = ((c as { cancer_name?: string }).cancer_name ?? "").trim();
  const cancer = generic ? `${cancerName || "Other cancer"} (${NO_CHECKLIST_WORDS})` : steps?.protocol_label || c.protocol_label || (c.protocol ? c.protocol.replace(/_/g, " ") : "Cancer not chosen yet");
  const ids = (p.ids ?? []).filter((x) => x.kind === "ip_no" || x.kind === "op_no").map((x) => x.value);
  const ownerDept = team?.owner?.department_label || ownerOf(cf).name;
  const ownerName = team?.owner?.doctors?.[0]?.name ?? cf.access?.owner_name ?? "";
  const sent = !!c.board_ready;
  const prepare = steps?.mode === "prepare";
  const urgency = team?.urgency !== undefined ? team?.urgency : c.urgency;
  return (
    <header className="surface px-4 py-3 print:shadow-none print:border-0 print:p-0" data-testid="case-header">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="min-w-0 flex-1">
          <h1 className="flex flex-wrap items-baseline gap-x-2 text-xl leading-tight sm:text-[1.4rem]">
            <span className="break-words">{p.name || "Unnamed patient"}</span>
            <span className="text-base font-normal text-muted-foreground whitespace-nowrap">{p.agesex}</span>
          </h1>
          <p className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5 text-sm text-muted-foreground">
            <span>UHID <span className="id text-foreground">{p.mrn}</span></span>
            {ids.map((v) => <span key={v} className="id">{v}</span>)}
          </p>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <span className="font-medium text-foreground" data-testid="header-cancer">{cancer}{!generic && c.setting ? <span className="font-normal text-muted-foreground">, {c.setting.replace(/_/g, " ")}</span> : null}</span>
            {generic ? <span className="text-muted-foreground">{GENERIC_RULE}</span> : null}
            <span className="text-muted-foreground">{ownerName ? `${ownerName}, ` : ""}{ownerDept || "no owner yet"}</span>
            <span className="inline-flex items-center gap-1 text-muted-foreground"><CalendarDays className="size-3.5" aria-hidden />
              {c.board_date ? <>Board {fmtDate(c.board_date)}</> : "Board date not set"}
              {c.meeting_id ? <Link className="ml-1 text-link underline underline-offset-2" to={`/meetings/${c.meeting_id}`}>meeting</Link> : null}
            </span>
            <span className="inline-flex items-center gap-1.5 text-muted-foreground">Urgency<UrgencyTag level={urgency?.level ?? null} proposed={urgency?.proposed?.level ?? null} setByName={urgency?.set_by_name} size="sm" /></span>
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2 print:hidden">
          {sent ? <StatusChip kind="ok" icon={Send}>Sent to the board{c.board_ready?.at ? `, ${fmtDate(c.board_ready.at)}` : ""}</StatusChip> : null}
          {prepare && !sent ? (
            <Button onClick={onSend} data-testid="send-to-board" title={steps?.left ? `${steps.left} still open: you will be asked why the board should discuss it anyway` : "Send this Case File to the board"}>
              <Send className="size-4" />{resident ? `Send to Dr ${consultantName} for sign-off` : "Send to the board"}
            </Button>
          ) : null}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" data-testid="more-menu"><MoreHorizontal className="size-4" />More<ChevronDown className="size-3 opacity-70" /></Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-64">
              <DropdownMenuItem onSelect={() => onPanel("team")}><Users className="size-4" />Team</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => onPanel("board")}><ClipboardList className="size-4" />Board form</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={onPrint}><Printer className="size-4" />Print</DropdownMenuItem>
              <DropdownMenuItem asChild><a href={deckHref} download><Presentation className="size-4" />Download the slides (.pptx)</a></DropdownMenuItem>
              {exportAllowed ? <DropdownMenuItem asChild><a href={exportHref} download><Download className="size-4" />NCG VTB template (.pptx)</a></DropdownMenuItem>
                : <DropdownMenuItem disabled><Download className="size-4" />NCG VTB template<span className="ml-auto text-xs">after you read the summary</span></DropdownMenuItem>}
              {onArchive ? <><DropdownMenuSeparator /><DropdownMenuItem onSelect={onArchive}><Archive className="size-4" />Archive</DropdownMenuItem></> : null}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </header>
  );
}
