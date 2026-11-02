// The guided Case File's header (B1, B9): who the patient is (name and UHID on every section, NISTIR two identifiers), the cancer as
// recorded, the owner, the board date and the urgency; on the right the one final action "Send to the board" and one "More" menu
// (Team, Board decisions, Print, Download, Move to another meeting, Take off the agenda, Archive). Nothing else: the work is in the sections.
// A draft checklist (version "x-draft", owner decision D6; night-v3 item 2.10) carries the chip "Checklist built (draft): needs a
// clinician's check" next to the cancer; the version comes from GET /protocols (cached).
// Under the patient the Case File's summary line (night-v3 3.4: built by Vaidyx from the Case summary, full readers only); the owner's
// consultant changes it in place (at most 160 characters) or goes back to the Vaidyx line.
import { useState } from "react";
import { Link } from "react-router-dom";
import { Archive, CalendarDays, CalendarMinus, CalendarSync, ChevronDown, ClipboardList, Download, MessageSquare, MoreHorizontal, Pencil, Presentation, Printer, Send, Users } from "lucide-react";
import { Input } from "@/components/ui/input";
import { consultantTitle, drName } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { UrgencyTag } from "@/components/UrgencyTag";
import { MessageButton, messageHref, useMayMessage } from "@/components/MessageButton";
import { BUILT_DRAFT_WORDS, DRAFT_CHECKLIST, NO_CHECKLIST_WORDS, genericRule, isDraftChecklist, isGeneric } from "@/lib/cancers";
import { useProtocols } from "@/hooks/useQueries";
import { ownerOf, setSummaryLine } from "../api";
import type { CaseFile, SummaryLine, Team } from "../types";
import { LoadingButton, StatusChip, errorText, fmtDate, useAnnounce } from "../components/common";
import type { Steps } from "./types";

export type MorePanel = "team" | "board";

const MAX_LINE = 160;

/** The summary line under the patient; a pencil for the owner's consultant opens an inline field. */
function SummaryLineRow({ caseId, line, canEdit }: { caseId: string; line: SummaryLine | null | undefined; canEdit: boolean }) {
  const [saved, setSaved] = useState<SummaryLine | null>(null);
  const cur = saved ?? line ?? null;
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState<"" | "save" | "vaidyx">("");
  const [err, setErr] = useState<string | null>(null);
  const [announce, liveNode] = useAnnounce();
  if (!cur?.text && !canEdit) return null;
  const send = async (t: string, which: "save" | "vaidyx") => {
    setBusy(which); setErr(null);
    try {
      const r = await setSummaryLine(caseId, t);
      setSaved(r.summary_line); setEditing(false);
      announce(which === "vaidyx" ? "The Vaidyx line is back." : "Summary line saved.");
    } catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };
  if (editing) {
    return (
      <div className="mt-1.5 max-w-3xl space-y-1.5 print:hidden" data-testid="summary-line-edit">
        {liveNode}
        <label htmlFor="summary-line-input" className="text-xs font-medium text-foreground">Summary line</label>
        <Input id="summary-line-input" value={text} onChange={(e) => setText(e.target.value)} maxLength={MAX_LINE} className="text-sm" aria-describedby="summary-line-note" aria-invalid={!!err || undefined} />
        <p id="summary-line-note" className="text-xs text-muted-foreground">At most {MAX_LINE} characters ({text.length} now). It shows here and in the Case File list, with your name.</p>
        {err ? <p role="alert" className="text-xs text-bad">{err}</p> : null}
        <div className="flex flex-wrap gap-2">
          <LoadingButton size="sm" loading={busy === "save"} disabled={!!busy || !text.trim()} onClick={() => void send(text, "save")} data-testid="summary-line-save">Save</LoadingButton>
          {cur?.edited ? <LoadingButton size="sm" variant="outline" loading={busy === "vaidyx"} disabled={!!busy} onClick={() => void send("", "vaidyx")} data-testid="summary-line-vaidyx">Use the Vaidyx line</LoadingButton> : null}
          <Button size="sm" variant="ghost" onClick={() => { setEditing(false); setErr(null); }}>Cancel</Button>
        </div>
      </div>
    );
  }
  return (
    <p className="mt-1 flex max-w-3xl items-start gap-1 text-sm text-muted-foreground" data-testid="summary-line">
      {liveNode}
      <span className="line-clamp-2 min-w-0">
        {cur?.text && !cur.edited ? <span className="mr-1.5 rounded bg-muted px-1 py-px text-xs" data-testid="summary-line-vaidyx-tag">Vaidyx line</span> : null}
        {cur?.text || <span className="italic">No summary line yet.</span>}
        {cur?.edited ? <span className="ml-1.5 text-xs" data-testid="summary-line-edited">edited by {drName(cur.by_name || cur.by)}</span> : null}
        {cur?.edited && cur.stale ? <span className="ml-1.5 text-xs text-warn" title={cur.vaidyx_text ? `Vaidyx would now write: ${cur.vaidyx_text}` : undefined}>(the Vaidyx line has changed since)</span> : null}
      </span>
      {canEdit ? (
        <button type="button" onClick={() => { setText(cur?.text ?? ""); setEditing(true); }} aria-label="Change the summary line" data-testid="summary-line-pencil"
          className="inline-flex size-6 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground print:hidden"><Pencil className="size-3.5" aria-hidden /></button>
      ) : null}
    </p>
  );
}

export function CaseHeader({ cf, team, steps, onSend, onPanel, onPrint, deckHref, exportHref, exportAllowed, onArchive, onMove, onWithdraw, resident, consultantName }: {
  cf: CaseFile; team: Team | null; steps: Steps | null; onSend: () => void; onPanel: (p: MorePanel) => void; onPrint: () => void;
  deckHref: string; exportHref: string; exportAllowed: boolean; onArchive?: () => void; resident: boolean; consultantName: string;
  /** Move to another meeting / Take off the agenda (night-v3 item 1.6): given only when the viewer may act (owner's consultant or coordinator). */
  onMove?: () => void; onWithdraw?: () => void;
}) {
  const c = cf.case;
  const p = c.patient ?? { name: "", mrn: "", agesex: "" };
  const generic = isGeneric(c.protocol);
  const protocols = useProtocols();
  const draft = !generic && isDraftChecklist(protocols.data?.protocols.find((x) => x.id === c.protocol));
  const cancerName = ((c as { cancer_name?: string }).cancer_name ?? "").trim();
  const cancer = generic ? `${cancerName || "Other cancer"} (${NO_CHECKLIST_WORDS})` : steps?.protocol_label || c.protocol_label || (c.protocol ? c.protocol.replace(/_/g, " ") : "Cancer not chosen yet");
  const ids = (p.ids ?? []).filter((x) => x.kind === "ip_no" || x.kind === "op_no").map((x) => x.value);
  const ownerDept = team?.owner?.department_label || ownerOf(cf).name;
  const ownerName = team?.owner?.doctors?.[0]?.name ?? cf.access?.owner_name ?? "";
  const ownerUser = team && !(team as { derived?: boolean }).derived ? team.owner?.doctors?.[0]?.user ?? "" : "";  // a login only from the real team (a derived team carries the name)
  const mayMessageCoordinator = useMayMessage();
  const withdrawn = !!c.board_send?.withdrawn;
  const sent = !!c.board_ready && !withdrawn;  // taken off the agenda: the ready mark stays, Send to the board picks a meeting again
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
          {(cf.access?.scope ?? "").toLowerCase() !== "requests" ? <SummaryLineRow caseId={c.case_id} line={c.summary_line} canEdit={!!steps?.summary?.case_summary?.can?.edit} /> : null}
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <span className="font-medium text-foreground" data-testid="header-cancer">{cancer}{!generic && c.setting ? <span className="font-normal text-muted-foreground">, {c.setting.replace(/_/g, " ")}</span> : null}</span>
            {generic ? <span className="text-muted-foreground">{genericRule(c.protocol)}</span> : null}
            {draft ? <StatusChip kind="warn" icon={ClipboardList} title={DRAFT_CHECKLIST} className="whitespace-normal">{BUILT_DRAFT_WORDS}</StatusChip> : null}
            <span className="text-muted-foreground">{ownerName ? `${ownerName}, ` : ""}{ownerDept || "no owner yet"}</span>
            {ownerUser ? <MessageButton target={{ to: ownerUser }} caseId={c.case_id} iconOnly label={`Message ${ownerName || "the owner"}`} className="print:hidden" /> : null}
            <span className="inline-flex items-center gap-1 text-muted-foreground"><CalendarDays className="size-3.5" aria-hidden />
              {c.board_date ? <>Board {fmtDate(c.board_date)}</> : "Board date not set"}
              {c.meeting_id ? <Link className="ml-1 text-link underline underline-offset-2" to={`/meetings/${c.meeting_id}`}>meeting</Link> : null}
            </span>
            <span className="inline-flex items-center gap-1.5 text-muted-foreground">Urgency<UrgencyTag level={urgency?.level ?? null} proposed={urgency?.proposed?.level ?? null} setByName={urgency?.set_by_name} size="sm" /></span>
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2 print:hidden">
          {sent ? <StatusChip kind="ok" icon={Send}>Sent to the board{c.board_ready?.at ? `, ${fmtDate(c.board_ready.at)}` : ""}</StatusChip> : null}
          {withdrawn ? <StatusChip kind="warn" icon={CalendarMinus} title={c.board_send?.withdrawn?.reason ? `Reason: ${c.board_send.withdrawn.reason}` : undefined}>Taken off the agenda{c.board_send?.withdrawn?.at ? `, ${fmtDate(c.board_send.withdrawn.at)}` : ""}</StatusChip> : null}
          {prepare && !sent ? (
            <Button onClick={onSend} data-testid="send-to-board" title={steps?.left ? `${steps.left} still open: you will be asked why the board should discuss it anyway` : "Send this Case File to the board"}>
              <Send className="size-4" />{resident ? `Send to ${consultantTitle(consultantName)} for sign-off` : "Send to the board"}
            </Button>
          ) : null}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" data-testid="more-menu"><MoreHorizontal className="size-4" />More<ChevronDown className="size-3 opacity-70" /></Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-64">
              <DropdownMenuItem onSelect={() => onPanel("team")}><Users className="size-4" />Team</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => onPanel("board")}><ClipboardList className="size-4" />Board decisions</DropdownMenuItem>
              {mayMessageCoordinator ? <DropdownMenuItem asChild><Link to={messageHref({ coordinator: true }, c.case_id)} data-testid="more-message-coordinator"><MessageSquare className="size-4" />Message the MDT Coordinator</Link></DropdownMenuItem> : null}
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={onPrint}><Printer className="size-4" />Print</DropdownMenuItem>
              <DropdownMenuItem asChild><a href={deckHref} download><Presentation className="size-4" />Download the slides (.pptx)</a></DropdownMenuItem>
              {exportAllowed ? <DropdownMenuItem asChild><a href={exportHref} download><Download className="size-4" />NCG VTB template (.pptx)</a></DropdownMenuItem>
                : <DropdownMenuItem disabled><Download className="size-4" />NCG VTB template<span className="ml-auto text-xs">after you read the summary</span></DropdownMenuItem>}
              {sent && (onMove || onWithdraw) ? <DropdownMenuSeparator /> : null}
              {sent && onMove ? <DropdownMenuItem onSelect={onMove} data-testid="more-move"><CalendarSync className="size-4" />Move to another meeting</DropdownMenuItem> : null}
              {sent && onWithdraw && c.meeting_id ? <DropdownMenuItem onSelect={onWithdraw} data-testid="more-withdraw"><CalendarMinus className="size-4" />Take off the agenda</DropdownMenuItem> : null}
              {onArchive ? <><DropdownMenuSeparator /><DropdownMenuItem onSelect={onArchive}><Archive className="size-4" />Archive</DropdownMenuItem></> : null}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </header>
  );
}
