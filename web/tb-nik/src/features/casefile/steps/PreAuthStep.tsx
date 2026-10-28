// Pre-Authorization (B6): what the board still needs for this cancer and setting, grouped by the department that will really receive the
// request. Each group: one click "Send request to <department>" (a ready-written request with a due date, Undo for 10 s, "Change the
// message" beside it); each item: Fill it in myself (values a doctor may type), Upload outside report, Not needed for this patient (with a
// reason). After sending: "Request sent to <department>, date · reply due"; overdue rows offer Send reminder and Call the department.
// Voice (night-v3 item 4.4): a mic beside "Why is it not needed?" fills it as an editable edit; values filled in are typed.
import { useRef, useState, type ReactNode } from "react";
import { ArrowRight, ChevronDown, Hourglass, PenLine, Phone, Send, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MicButton } from "@/components/MicButton";
import { cn } from "@/lib/utils";
import { consultantTitle } from "@/lib/format";
import { LoadingButton, errorText, fmtDate, niceTitle, plural, screenNote } from "../components/common";
import { Card } from "./Overview";
import type { MissingItem, Steps } from "./types";

export interface PreAuthHandlers {
  sendGroup: (items: MissingItem[], key: string) => void;
  changeMessage: (item: MissingItem) => void;
  notNeeded: (item: MissingItem, reason: string) => Promise<void>;
  fillIn: (item: MissingItem, value: string) => Promise<void>;
  upload: () => void;
  remind: (item: MissingItem) => Promise<void>;
  /** The Undo bar while a request waits its 10 s. */
  pendingBar: (key: string) => ReactNode;
  isPending: (key: string) => boolean;
}

function why(it: MissingItem): string {
  if (it.draft?.doc_title) return `${niceTitle(it.draft.doc_title)} is only ${String(it.draft.status || "not final").toLowerCase()}: a final, signed report is needed`;
  if (it.pending) return screenNote(it.note) || "Pending in the report";
  const n = screenNote(it.note);
  return n && !/^No .* in the Case File$/i.test(n) ? n : "Not found in the reports";
}

function ItemRow({ it, h, canAct, resident, caseId }: { it: MissingItem; h: PreAuthHandlers; canAct: boolean; resident: boolean; caseId: string }) {
  const [mode, setMode] = useState<"idle" | "fill" | "not_needed">("idle");
  const [text, setText] = useState("");
  const boxRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const run = async (fn: () => Promise<void>) => { setBusy(true); setErr(null); try { await fn(); setMode("idle"); setText(""); } catch (e) { setErr(errorText(e)); } finally { setBusy(false); } };
  return (
    <li className="py-2.5" data-testid="missing-item">
      <p className="text-sm font-medium text-foreground">{it.label}</p>
      <p className="text-xs text-muted-foreground">{why(it)}</p>
      {canAct && mode === "idle" ? (
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {it.typable ? <Button size="xs" variant="outline" onClick={() => setMode("fill")}><PenLine className="size-3" />Fill it in myself</Button> : null}
          <Button size="xs" variant="outline" onClick={h.upload}><Upload className="size-3" />Upload outside report</Button>
          {it.can_not_needed ? <Button size="xs" variant="ghost" onClick={() => setMode("not_needed")}>Not needed for this patient</Button> : null}
        </div>
      ) : null}
      {mode !== "idle" ? (
        <form className="mt-1.5 flex flex-wrap items-center gap-1.5" onSubmit={(e) => { e.preventDefault(); void run(() => (mode === "fill" ? h.fillIn(it, text.trim()) : h.notNeeded(it, text.trim()))); }}>
          <Input ref={boxRef} autoFocus value={text} onChange={(e) => setText(e.target.value)} className="h-8 max-w-sm text-sm" maxLength={200}
            placeholder={mode === "fill" ? `${it.label}, as you know it` : "Why is it not needed? (recorded with your name)"} aria-label={mode === "fill" ? it.label : "Why it is not needed"} />
          {mode === "not_needed" ? <MicButton target={boxRef} screen="preauth-why" context="reason" caseId={caseId} size="icon-xs" label="Dictate the reason"
            onInsert={(next) => { if (next.length > 200) setText(next.slice(0, 200)); }} /> : null}
          <LoadingButton size="xs" type="submit" loading={busy} disabled={mode === "fill" ? !text.trim() : text.trim().length < 3}>{resident ? "Send for sign-off" : mode === "fill" ? "Save" : "Mark not needed"}</LoadingButton>
          <Button size="xs" variant="ghost" type="button" onClick={() => { setMode("idle"); setErr(null); }}>Cancel</Button>
        </form>
      ) : null}
      {mode === "fill" ? <p className="mt-1 text-xs text-muted-foreground">Shown as "entered by you, no report".</p> : null}
      {err ? <p role="alert" className="mt-1 text-xs text-bad">{err}</p> : null}
    </li>
  );
}

function WaitRow({ it, h, canAct }: { it: MissingItem; h: PreAuthHandlers; canAct: boolean }) {
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const r = it.request;
  const overdue = !!r?.overdue;
  return (
    <li className="flex flex-wrap items-center gap-3 py-2.5" data-testid="waiting-item">
      <Hourglass className={cn("size-4 shrink-0", overdue ? "text-bad" : "text-warn")} aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-foreground">{it.label}</p>
        <p className={cn("text-xs", overdue ? "font-medium text-bad" : "text-muted-foreground")}>
          {overdue ? "Overdue. " : ""}Request sent to {it.department?.label ?? "the department"}{r?.sent_at ? `, ${fmtDate(r.sent_at)}` : ""}{r?.due ? ` · reply due ${fmtDate(r.due)}` : ""}{r?.reminders ? ` · ${plural(r.reminders, "reminder")} sent` : ""}
        </p>
      </div>
      {overdue && it.department?.phone ? <Button asChild size="sm" variant="outline"><a href={`tel:${it.department.phone}`}><Phone className="size-4" />Call the department</a></Button> : null}
      {canAct && r?.action_id ? (done ? <span className="text-xs text-ok">Reminder sent</span> : (
        <LoadingButton size="sm" variant="outline" loading={busy} onClick={async () => { setBusy(true); setErr(null); try { await h.remind(it); setDone(true); } catch (e) { setErr(errorText(e)); } finally { setBusy(false); } }}>Send reminder</LoadingButton>
      )) : null}
      {err ? <p role="alert" className="basis-full text-xs text-bad">{err}</p> : null}
    </li>
  );
}

export function PreAuthStep({ steps, h, canAct, resident, consultantName, onNext }: { steps: Steps; h: PreAuthHandlers; canAct: boolean; resident: boolean; consultantName: string; onNext: () => void }) {
  const { groups, waiting, optional } = steps.pre_authorization;
  const [showOptional, setShowOptional] = useState(false);
  const setting = steps.protocol_label ? `${steps.protocol_label}` : "this cancer";
  return (
    <div className="space-y-4" data-testid="section-pre-authorization">
      <div>
        <h2 className="text-lg">Pre-Authorization check</h2>
        <p className="text-sm text-muted-foreground">What the board still needs for {setting}. Vaidyx checked every report; what is not there is listed here with the department it belongs to.</p>
      </div>
      {!groups.length && !waiting.length ? <div className="surface flex items-center gap-2 px-4 py-4 text-sm status-ok">Everything the board needs is in the reports, or settled.</div> : null}
      {groups.map((g) => {
        const key = `group:${g.department.label}`;
        const pending = h.isPending(key);
        return (
          <Card key={key} title={g.department.label} count={g.items.length} testId="missing-group">
            <ul className="divide-y divide-border">{g.items.map((it) => <ItemRow key={it.slot_id} it={it} h={h} canAct={canAct && !pending} resident={resident} caseId={steps.case_id} />)}</ul>
            {canAct ? (
              <div className="flex flex-wrap items-center gap-2 border-t border-border py-2.5">
                <Button onClick={() => h.sendGroup(g.items, key)} disabled={pending || !g.department.name} data-testid="send-request">
                  <Send className="size-4" />{resident ? `Send to ${consultantTitle(consultantName)} for sign-off` : `Send request to ${g.department.label}`}
                </Button>
                {!resident && g.items[0]?.department?.action_id ? <button type="button" className="text-sm text-link hover:underline" onClick={() => h.changeMessage(g.items[0])} disabled={pending}>Change the message</button> : null}
              </div>
            ) : null}
            {h.pendingBar(key)}
          </Card>
        );
      })}
      {waiting.length ? (
        <Card title="Waiting on other departments" count={waiting.length} testId="waiting-group">
          <ul className="divide-y divide-border">{waiting.map((it) => <WaitRow key={it.slot_id} it={it} h={h} canAct={canAct} />)}</ul>
        </Card>
      ) : null}
      {optional.length ? (
        <section className="surface">
          <button type="button" onClick={() => setShowOptional((v) => !v)} aria-expanded={showOptional} className="flex w-full items-center gap-2 px-4 py-3 text-left">
            <ChevronDown className={cn("size-4 text-muted-foreground transition-transform", !showOptional && "-rotate-90")} aria-hidden />
            <span className="text-[15px] font-semibold">The board may also ask for</span><span className="text-sm text-muted-foreground">({optional.length})</span>
          </button>
          {showOptional ? <ul className="divide-y divide-border border-t border-border px-4">{optional.map((it) => <ItemRow key={it.slot_id} it={it} h={h} canAct={canAct} resident={resident} caseId={steps.case_id} />)}</ul> : null}
        </section>
      ) : null}
      <div className="flex justify-end"><Button variant="outline" onClick={onNext}>Next: Summary<ArrowRight className="size-4" /></Button></div>
    </div>
  );
}
