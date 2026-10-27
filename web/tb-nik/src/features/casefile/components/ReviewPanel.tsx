// Review in the side panel: the values that disagree, each with its quote and page, the factual differences between
// them, and Approve / Edit / Not needed. After a decision the panel moves to the next item that needs the doctor.
// Two reports differ (night-v3 item 1.7, design B5): both values with their report, and "Use this value for the board" on each; nothing
// is chosen for the doctor. The pick is a board_uses confirmation (a resident's goes to the consultant for sign-off); the difference stays
// shown with the pick and its Undo. A pick that no longer matches its report is said here ("... no longer matches the report: pick again").
// Voice (night-v3 item 4.4): a mic beside the reason box fills it as an editable edit; nothing is saved until the doctor clicks.
import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ArrowRight, Check, CheckCircle2, Clock, PenLine, Undo2, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DateInput } from "@/components/DateInput";
import { MicButton } from "@/components/MicButton";
import { postConfirmation, slotNotNeeded, undoConfirmation } from "../api";
import type { CaseFile, DiscordCitation, Slot } from "../types";
import type { SourceTarget } from "./SourceViewer";
import type { StalePick } from "../steps/types";
import { docStatusChip } from "./SourceViewer";
import { LoadingButton, StatusChip, errorText, fmtDate, indianDates, niceTitle, useAnnounce } from "./common";
import { cn } from "@/lib/utils";

interface Candidate { value: string; quote: string; doc_id: string; doc_title: string; page: number; date?: string | null; status?: string; verification?: string; current: boolean; superseded?: boolean }

function candidatesFor(cf: CaseFile, slot: Slot): { factId: string | null; list: Candidate[] } {
  const key = slot.confirmation?.key ?? "";
  const factId = slot.confirmation?.fact_id ?? slot.fact_id ?? slot.quote?.fact_id ?? (key.includes(":") ? key.split(":")[1] : null) ?? (cf.facts?.[slot.id] ? slot.id : null);
  const f = factId ? cf.facts?.[factId] : undefined;
  const list: Candidate[] = [];
  const titleOf = (id?: string) => cf.documents.find((d) => d.doc_id === id)?.classification?.title ?? cf.documents.find((d) => d.doc_id === id)?.filename ?? "record";
  if (f) {
    for (const h of f.history ?? []) {
      if (!h.value || !h.doc_id) continue;
      list.push({ value: h.value, quote: h.quote ?? "", doc_id: h.doc_id, doc_title: h.doc_title ?? titleOf(h.doc_id), page: (cf.documents.find((d) => d.doc_id === h.doc_id)?.facts?.[factId!]?.location?.page) ?? 0, date: h.date, status: h.doc_status, verification: h.verification, current: f.current?.doc_id === h.doc_id && f.current?.value === h.value, superseded: h.superseded });
    }
    if (slot.confirmation?.type === "confirm_value" && slot.confirmation.doc_id && !list.some((c) => c.doc_id === slot.confirmation!.doc_id)) {
      list.push({ value: slot.confirmation.value ?? slot.value ?? "", quote: slot.quote?.text ?? "", doc_id: slot.confirmation.doc_id, doc_title: titleOf(slot.confirmation.doc_id), page: slot.confirmation.page ?? slot.quote?.page ?? 0, current: true });
    }
  }
  if (!list.length && slot.quote) list.push({ value: slot.value ?? "", quote: slot.quote.text, doc_id: slot.quote.doc_id, doc_title: slot.quote.doc_title, page: slot.quote.page ?? 0, current: true });
  // newest first, current first among equals
  list.sort((a, b) => Number(b.current) - Number(a.current) || String(b.date ?? "").localeCompare(String(a.date ?? "")));
  return { factId, list };
}

function differences(a: Candidate, b: Candidate): string[] {
  const out: string[] = [];
  if (a.value !== b.value) out.push(`Value: "${a.value}" against "${b.value}"`);
  if ((a.date ?? "") !== (b.date ?? "")) out.push(`Report date: ${fmtDate(a.date) || "not stated"} against ${fmtDate(b.date) || "not stated"}`);
  if ((a.status ?? "") !== (b.status ?? "")) out.push(`Report status: ${(a.status ?? "not stated").toLowerCase()} against ${(b.status ?? "not stated").toLowerCase()}`);
  if ((a.verification ?? "") !== (b.verification ?? "")) out.push(`Quote check: ${a.verification ?? "unknown"} against ${b.verification ?? "unknown"}`);
  if (a.doc_id === b.doc_id) out.push("Both values come from the same report");
  return out;
}

export function ReviewPanel({ caseId, cf, slot, queue, derived, resident, consultantName, onOpenSource, onNext, onDone, onPropose }: {
  caseId: string; cf: CaseFile; slot: Slot; queue: Slot[]; derived: boolean; resident: boolean; consultantName: string;
  onOpenSource: (t: SourceTarget) => void; onNext: (next: Slot | null) => void; onDone: () => Promise<void>;
  onPropose: (action: string, payload: Record<string, unknown>, label: string) => Promise<void>;
}) {
  const { factId, list } = useMemo(() => candidatesFor(cf, slot), [cf, slot]);
  const [picked, setPicked] = useState(0);
  const [mode, setMode] = useState<"pick" | "edit" | "not_needed">("pick");
  const [edited, setEdited] = useState("");
  const [reason, setReason] = useState("");
  const reasonRef = useRef<HTMLInputElement>(null);
  /** Dictated words go in at the cursor; the box keeps its 200 characters. */
  const reasonMic = <MicButton target={reasonRef} screen="reason" context="reason" caseId={caseId} size="icon-xs" label="Dictate the reason" onInsert={(next) => { if (next.length > 200) setReason(next.slice(0, 200)); }} />;
  const [announce, liveNode] = useAnnounce();
  const ctype = slot.confirmation?.type ?? "confirm_value";
  const doc = cf.documents.find((d) => d.doc_id === (slot.confirmation?.doc_id ?? list[picked]?.doc_id ?? slot.quote?.doc_id ?? slot.confirmation?.key.split(":")[0]));
  const c = doc?.classification ?? {};
  const [reportDate, setReportDate] = useState(c.report_date_iso ?? "");
  const [eventDate, setEventDate] = useState(c.event_date_iso ?? "");
  const [docType, setDocType] = useState(c.doc_type ?? "");
  useEffect(() => { setPicked(0); setMode("pick"); setEdited(""); setReason(""); setReportDate(c.report_date_iso ?? ""); setEventDate(c.event_date_iso ?? ""); setDocType(c.doc_type ?? ""); }, [slot.id, c.report_date_iso, c.event_date_iso, c.doc_type]);

  const nextItem = queue.find((s) => s.id !== slot.id) ?? null;
  const advance = async () => { await onDone(); announce(nextItem ? `Done. Next: ${nextItem.label}` : "Done. Nothing else needs your confirmation."); onNext(nextItem); };

  const act = useMutation({
    mutationFn: async (what: "approve" | "edit" | "not_needed") => {
      const cand = list[picked];
      if (what === "not_needed") {
        if (reason.trim().length < 3) throw new Error("Give a short reason: it is recorded with your name.");
        if (resident) return onPropose("not_needed", derived ? { key: slot.id, reason: reason.trim() } : { slot: slot.id, reason: reason.trim() }, `Not needed: ${slot.label}`);
        if (!derived) { await slotNotNeeded(caseId, slot.id, reason.trim()); return; }
        await postConfirmation(caseId, { type: "waive", key: slot.id, reason: reason.trim() });
        return;
      }
      let body: { type: string; key: string; fields: Record<string, unknown>; reason: string };
      if (ctype === "note_discordance") body = { type: "note_discordance", key: slot.confirmation?.key ?? "", fields: {}, reason: reason.trim() };
      else if (ctype === "confirm_dates" && doc) body = { type: "confirm_dates", key: doc.doc_id, fields: { report_date: reportDate, event_date: eventDate }, reason: reason.trim() };
      else if (ctype === "confirm_doc_type" && doc) body = { type: "confirm_doc_type", key: doc.doc_id, fields: { doc_type: docType }, reason: reason.trim() };
      else if (ctype === "confirm_match" && doc) body = { type: "confirm_match", key: doc.doc_id, fields: { case_id: what === "edit" ? "" : caseId }, reason: reason.trim() };
      else if (ctype === "attest_final" && doc) body = { type: "attest_final", key: doc.doc_id, fields: {}, reason: reason.trim() };
      else {
        if (!cand || !factId) throw new Error("There is no value to confirm on this line.");
        const value = what === "edit" ? edited.trim() : cand.value;
        if (!value) throw new Error("Enter the value as printed in the report.");
        body = { type: "confirm_value", key: `${cand.doc_id}:${factId}`, fields: { value }, reason: reason.trim() };
      }
      if (resident) return onPropose("confirm", body, `Confirm ${slot.label}`);
      await postConfirmation(caseId, body);
    },
    onSuccess: advance,
  });

  // Two reports differ: pick the value the board uses (night-v3 item 1.7)
  const cites: DiscordCitation[] = slot.confirmation?.citations ?? [];
  const boardPick = slot.confirmation?.picked ?? slot.picked ?? null;
  const [sentPick, setSentPick] = useState<string | null>(null);
  useEffect(() => { setSentPick(null); }, [slot.id]);
  const pick = useMutation({
    mutationFn: async (c: DiscordCitation) => {
      if (!factId || !c.value) throw new Error("There is no value to pick on this line.");
      const body = { type: "board_uses", key: factId, fields: { doc_id: c.doc_id, value: c.value }, reason: reason.trim() };
      if (resident) { await onPropose("confirm", body, `Pick the value for the board: ${slot.label}, ${c.value}`); setSentPick(c.doc_id); return; }
      await postConfirmation(caseId, body);
      await onDone();
      announce(`The board uses ${c.value} from ${niceTitle(c.doc_title) || "the report"}.`);
    },
  });
  const unpick = useMutation({
    mutationFn: async () => {
      if (!boardPick) return;
      await undoConfirmation(caseId, boardPick.confirmation);
      await onDone();
      announce("Pick undone. Both values are open again.");
    },
  });
  const otherSide = boardPick ? cites.find((x) => x.doc_id !== boardPick.doc_id) : undefined;
  const stale = (slot as Slot & { pick_stale?: StalePick | null }).pick_stale ?? null;
  const staleLine = stale ? `Your pick of ${stale.value} from ${niceTitle(stale.doc_title) || "the report"} no longer matches the report: pick again` : "";

  const diffs = list.length >= 2 ? differences(list[0], list[1]) : [];
  const signLabel = resident ? `Ask Dr ${consultantName} to sign off` : ctype === "note_discordance" ? "Noted, I read the difference" : "Approve";

  return (
    <div className="space-y-3" data-testid="review-panel">
      {liveNode}
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span>{queue.length} {queue.length === 1 ? "item needs" : "items need"} your confirmation</span>
        {nextItem ? <span className="ml-auto inline-flex items-center gap-1">next: {nextItem.label} <ArrowRight className="size-3" aria-hidden /></span> : null}
      </div>
      <div>
        <h3 className="text-base">{slot.label}</h3>
        {slot.note && !stale ? <p className="text-sm text-muted-foreground">{slot.note}</p> : null}
      </div>
      {stale ? (
        <p className="rounded-md border border-warn/50 bg-warn-soft p-2.5 text-sm text-foreground" role="status" data-testid="review-pick-stale">
          {staleLine}{stale.by_name ? ` (picked by ${stale.by_name}${stale.at ? `, ${fmtDate(stale.at)}` : ""})` : ""}.
        </p>
      ) : null}

      {ctype === "note_discordance" ? (
        <div className="space-y-2 text-sm" data-testid="review-discordance">
          <p className="text-foreground">{slot.confirmation?.kind_label ? <span className="font-medium">{slot.confirmation.kind_label}: </span> : null}{indianDates(slot.confirmation?.why || slot.note)}</p>
          {boardPick ? (
            <div className="rounded-md border border-primary/50 bg-secondary/40 p-2.5" role="status" data-testid="review-picked">
              <p className="text-foreground">
                The board uses <span className="font-semibold">{boardPick.value}</span> from {niceTitle(boardPick.doc_title) || "the report"} ({boardPick.by_name || boardPick.by || "a doctor"}{boardPick.at ? `, ${fmtDate(boardPick.at)}` : ""}).
                {otherSide?.value ? <> The other report says <span className="font-semibold">{otherSide.value}</span>.</> : null}
              </p>
              {!resident ? (
                <LoadingButton size="xs" variant="ghost" className="mt-1" loading={unpick.isPending} onClick={() => unpick.mutate()} data-testid="pick-undo"><Undo2 className="size-3" />Undo</LoadingButton>
              ) : null}
              {unpick.isError ? <p role="alert" className="text-xs text-bad">{errorText(unpick.error)}</p> : null}
            </div>
          ) : null}
          <ul className="space-y-2" aria-label="The two values">
            {cites.map((c, i) => {
              const uses = !!boardPick && boardPick.doc_id === c.doc_id;
              return (
                <li key={`${c.doc_id}-${i}`} className={cn("rounded-md border p-2.5", uses ? "border-primary bg-secondary/40" : "border-border")} data-testid="pick-card">
                  {c.value ? <p className="text-[1.05rem] font-semibold text-foreground">{c.value}</p> : null}
                  <p className="flex flex-wrap gap-x-2 text-xs text-muted-foreground">
                    <span>{niceTitle(c.doc_title) || "record"}</span>
                    {c.date ? <span>{fmtDate(c.date)}</span> : null}
                    {c.status ? <span>{c.final === false ? `${c.status.toLowerCase()}, not final` : c.status.toLowerCase()}</span> : null}
                  </p>
                  {c.quote ? <blockquote className="mt-1 border-l-2 border-primary/60 pl-2 text-foreground">{c.quote}</blockquote>
                    : c.confirmed_by ? <p className="mt-1 text-xs text-muted-foreground">confirmed by {c.confirmed_by} against the report, no quote</p> : null}
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    <button type="button" className="quote-chip hover:brightness-95" onClick={() => onOpenSource({ docId: c.doc_id, page: c.page ?? 0, quote: c.quote, title: c.doc_title })}>{niceTitle(c.doc_title) || "record"} p. {(c.page ?? 0) + 1}</button>
                    {uses ? <StatusChip kind="ok" icon={CheckCircle2}>The board uses this value</StatusChip> : null}
                    {!boardPick && c.value && sentPick !== c.doc_id ? (
                      <LoadingButton size="xs" variant="outline" loading={pick.isPending && pick.variables?.doc_id === c.doc_id} disabled={pick.isPending || act.isPending || !!sentPick}
                        onClick={() => pick.mutate(c)} data-testid="pick-value">
                        <Check className="size-3.5" />Use this value for the board
                      </LoadingButton>
                    ) : null}
                    {sentPick === c.doc_id ? <span className="inline-flex items-center gap-1 text-xs text-muted-foreground" data-testid="pick-sent"><Clock className="size-3.5" aria-hidden />Sent to Dr {consultantName} for sign-off</span> : null}
                  </div>
                </li>
              );
            })}
          </ul>
          {pick.isError ? <p role="alert" className="text-xs text-bad">{errorText(pick.error)}</p> : null}
          {!boardPick ? (
            <p className="text-xs text-muted-foreground">
              Nothing is chosen for you. Pick the value the board should use{resident ? ` (Dr ${consultantName} signs it off)` : ""}, or record that you read the difference. Either way both reports stay on file and the difference stays listed.
            </p>
          ) : null}
        </div>
      ) : null}

      {ctype !== "note_discordance" && (ctype === "confirm_value" || !doc) ? (
        <>
          {list.length === 0 ? <p className="text-sm text-muted-foreground">No quoted value is on file for this line. Mark it not needed, or ask the department for the report.</p> : null}
          <ul className="space-y-2" role="radiogroup" aria-label="Values found">
            {list.map((cand, i) => (
              <li key={`${cand.doc_id}-${i}`}>
                <label className={cn("block rounded-md border p-3 cursor-pointer transition", picked === i ? "border-primary bg-secondary/40" : "border-border hover:bg-muted")}>
                  <div className="flex items-start gap-2">
                    <input type="radio" name="candidate" className="mt-1 accent-[var(--primary)]" checked={picked === i} onChange={() => setPicked(i)} aria-label={`${cand.value} from ${cand.doc_title}`} />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-foreground">{cand.value}</p>
                      <p className="text-xs text-muted-foreground flex flex-wrap gap-x-2">{cand.doc_title}{cand.date ? <span>{fmtDate(cand.date)}</span> : null}{cand.status ? <span>{cand.status.toLowerCase()}</span> : null}</p>
                      {cand.quote ? <blockquote className="mt-1 text-sm border-l-2 border-primary/60 pl-2 text-foreground">{cand.quote}</blockquote> : <p className="mt-1 text-xs text-warn">no verbatim quote: the value cannot be shown as fact</p>}
                      <div className="mt-1 flex flex-wrap gap-1">
                        {docStatusChip(cf.documents.find((d) => d.doc_id === cand.doc_id))}
                        {cand.current ? <StatusChip kind="info">current pick</StatusChip> : null}
                        {cand.superseded ? <StatusChip kind="muted">earlier version</StatusChip> : null}
                        {cand.verification && cand.verification !== "verified" ? <StatusChip kind="review">quote {cand.verification}</StatusChip> : null}
                        <button type="button" className="quote-chip hover:brightness-95" onClick={(e) => { e.preventDefault(); onOpenSource({ docId: cand.doc_id, page: cand.page, quote: cand.quote, factId: factId ?? undefined, title: cand.doc_title }); }}>open page {cand.page + 1}</button>
                      </div>
                    </div>
                  </div>
                </label>
              </li>
            ))}
          </ul>
          {diffs.length ? (
            <div className="rounded-md bg-muted p-2 text-sm">
              <p className="font-medium text-foreground">What differs</p>
              <ul className="list-disc pl-5 text-muted-foreground">{diffs.map((d, i) => <li key={i}>{d}</li>)}</ul>
            </div>
          ) : null}
        </>
      ) : null}

      {ctype === "confirm_dates" && doc ? (
        <div className="space-y-2 text-sm">
          <p className="text-muted-foreground">The dates printed on <span className="font-medium text-foreground">{c.title ?? doc.filename}</span> were not clear. Confirm them as printed.</p>
          <div className="grid grid-cols-2 gap-2">
            <label className="text-xs">Report date<DateInput value={reportDate} onChange={setReportDate} wrapperClassName="mt-1" className="h-8 text-sm" aria-label="Report date" /></label>
            <label className="text-xs">Event (sample, scan) date<DateInput value={eventDate} onChange={setEventDate} wrapperClassName="mt-1" className="h-8 text-sm" aria-label="Event (sample, scan) date" /></label>
          </div>
          <button type="button" className="quote-chip hover:brightness-95" onClick={() => onOpenSource({ docId: doc.doc_id, page: 0, title: c.title })}>open the report</button>
        </div>
      ) : null}
      {ctype === "confirm_doc_type" && doc ? (
        <div className="space-y-2 text-sm">
          <p className="text-muted-foreground">What kind of report is <span className="font-medium text-foreground">{c.title ?? doc.filename}</span>? {c.doc_type_disagreement?.note ?? ""}</p>
          <select value={docType} onChange={(e) => setDocType(e.target.value)} className="h-8 rounded-md border border-input bg-card px-2 text-sm" aria-label="Document type">
            {[c.doc_type, c.doc_type_disagreement?.keyword_type].filter((x, i, a): x is string => !!x && a.indexOf(x) === i).map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
          </select>
          <button type="button" className="quote-chip hover:brightness-95" onClick={() => onOpenSource({ docId: doc.doc_id, page: 0, title: c.title })}>open the report</button>
        </div>
      ) : null}
      {ctype === "confirm_match" && doc ? (
        <div className="space-y-2 text-sm">
          <p className="text-muted-foreground"><span className="font-medium text-foreground">{c.title ?? doc.filename}</span> was matched by name only. Check the patient on the report.</p>
          <button type="button" className="quote-chip hover:brightness-95" onClick={() => onOpenSource({ docId: doc.doc_id, page: 0, title: c.title })}>open the report</button>
        </div>
      ) : null}
      {ctype === "attest_final" && doc ? <p className="text-sm text-muted-foreground"><span className="font-medium text-foreground">{c.title ?? doc.filename}</span> does not state whether it is final. Attest it final only if the signed report says so.</p> : null}

      {mode === "edit" ? (
        <div>
          <label htmlFor="review-edit" className="text-sm font-medium">Value as printed in the report</label>
          <Input id="review-edit" autoFocus value={edited} onChange={(e) => setEdited(e.target.value)} className="mt-1 h-9 text-sm" maxLength={200} />
        </div>
      ) : null}
      {boardPick ? null : mode === "not_needed" ? (
        <div>
          <label htmlFor="review-reason" className="text-sm font-medium">Why is it not needed?</label>
          <div className="mt-1 flex items-start gap-1">
            <Input ref={reasonRef} id="review-reason" autoFocus value={reason} onChange={(e) => setReason(e.target.value)} className="h-9 min-w-0 flex-1 text-sm" maxLength={200} placeholder="Recorded with your name" />
            {reasonMic}
          </div>
        </div>
      ) : (
        <div>
          <label htmlFor="review-reason" className="text-xs text-muted-foreground">Reason (optional, recorded)</label>
          <div className="mt-1 flex items-start gap-1">
            <Input ref={reasonRef} id="review-reason" value={reason} onChange={(e) => setReason(e.target.value)} className="h-8 min-w-0 flex-1 text-sm" maxLength={200} />
            {reasonMic}
          </div>
        </div>
      )}
      {act.isError ? <p role="alert" className="text-xs text-bad">{errorText(act.error)}</p> : null}

      <div className="flex flex-wrap gap-1.5 pt-1">
        {boardPick ? null : mode === "pick" ? (
          <>
            <LoadingButton loading={act.isPending && act.variables === "approve"} onClick={() => act.mutate("approve")} disabled={act.isPending || (ctype === "confirm_value" && !list.length)} data-testid="review-approve"><Check className="size-4" />{signLabel}</LoadingButton>
            {ctype === "confirm_value" ? <Button variant="outline" onClick={() => { setMode("edit"); setEdited(list[picked]?.value ?? ""); }} disabled={act.isPending}><PenLine className="size-4" />Edit</Button> : null}
            {ctype === "confirm_match" ? <Button variant="outline" onClick={() => act.mutate("edit")} disabled={act.isPending}><XCircle className="size-4" />Not this patient</Button> : null}
            <Button variant="ghost" onClick={() => setMode("not_needed")} disabled={act.isPending}>Not needed</Button>
          </>
        ) : mode === "edit" ? (
          <>
            <LoadingButton loading={act.isPending} onClick={() => act.mutate("edit")} disabled={!edited.trim()}><Check className="size-4" />{resident ? signLabel : "Save the edited value"}</LoadingButton>
            <Button variant="ghost" onClick={() => setMode("pick")}>Back</Button>
          </>
        ) : (
          <>
            <LoadingButton loading={act.isPending} onClick={() => act.mutate("not_needed")} disabled={reason.trim().length < 3}>{resident ? signLabel : "Mark not needed"}</LoadingButton>
            <Button variant="ghost" onClick={() => setMode("pick")}>Back</Button>
          </>
        )}
        {nextItem ? <Button variant="ghost" className="ml-auto" onClick={() => onNext(nextItem)}>Skip<ArrowRight className="size-4" /></Button> : null}
      </div>
    </div>
  );
}
