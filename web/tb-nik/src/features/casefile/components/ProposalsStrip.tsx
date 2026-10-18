// The consultant's strip: pending proposals from residents, each with Approve / Return (with a note).
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { Check, Undo2, UserRoundCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { approveProposal, returnProposal } from "../api";
import type { Proposal } from "../types";
import { LoadingButton, errorText, fmtDateTime, useAnnounce } from "./common";

const ACTION_WORDS: Record<string, string> = { waive: "mark not needed", not_needed: "mark not needed", confirm: "confirm a value", mark_ready: "mark ready", send_request: "send a request", urgency: "change the urgency", refer: "refer the Case File", typed_value: "enter a value", published_case: "add a published case" };

function describe(p: Proposal, labelOf?: (slotId: string) => string | undefined): string {
  const pl = p.payload ?? {};
  const bits = [ACTION_WORDS[p.action] ?? p.action];
  const slot = typeof pl.slot === "string" ? pl.slot : typeof pl.key === "string" && !String(pl.key).includes(":") ? pl.key : null;
  if (slot) bits.push(`(${labelOf?.(slot) ?? labelOf?.(`record:${slot}`) ?? slot.replace(/^(fact|record):/, "").replace(/_/g, " ")})`);
  if (typeof pl.label === "string") bits.push(`(${pl.label})`);
  const res = pl.result as { title?: string } | undefined;
  if (res && typeof res.title === "string") bits.push(`: ${res.title}`);
  if (typeof pl.value === "string") bits.push(`: ${pl.value}`);
  const fields = pl.fields as Record<string, unknown> | undefined;
  if (fields && typeof fields.value === "string") bits.push(`: ${fields.value}`);
  if (typeof pl.level === "number") bits.push(`to ${pl.level}`);
  if (typeof pl.reason === "string" && pl.reason) bits.push(`, reason: ${pl.reason}`);
  return bits.join(" ");
}

export function ProposalsStrip({ caseId, proposals, onChanged, labelOf }: { caseId: string; proposals: Proposal[]; onChanged: () => Promise<void>; labelOf?: (slotId: string) => string | undefined }) {
  const [returning, setReturning] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [announce, liveNode] = useAnnounce();
  const approve = useMutation({ mutationFn: (pid: string) => approveProposal(caseId, pid), onSuccess: async () => { announce("Approved and done."); setErr(null); await onChanged(); }, onError: (e) => setErr(errorText(e)) });
  const ret = useMutation({ mutationFn: ({ pid, n }: { pid: string; n: string }) => returnProposal(caseId, pid, n), onSuccess: async () => { announce("Returned with your note."); setReturning(null); setNote(""); setErr(null); await onChanged(); }, onError: (e) => setErr(errorText(e)) });
  const pending = proposals.filter((p) => p.status === "pending");
  if (!pending.length) return null;
  return (
    <section className="surface border-review/40 p-3 print:hidden" aria-labelledby="h-proposals" data-testid="proposals-strip">
      {liveNode}
      <h2 id="h-proposals" className="text-sm font-semibold flex items-center gap-1.5"><UserRoundCheck className="size-4 text-review" aria-hidden />{pending.length === 1 ? "A resident asks you to sign off" : `${pending.length} residents' proposals wait for you`}</h2>
      <ul className="mt-2 space-y-2">
        <AnimatePresence initial={false}>
          {pending.map((p) => (
            <motion.li key={p.id} layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, height: 0 }} className="rounded-md border border-border p-2 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="flex-1 min-w-0"><span className="font-medium">{p.by_name ?? p.by}</span> asks to {describe(p, labelOf)}<span className="text-xs text-muted-foreground"> {fmtDateTime(p.at)}</span>{p.note ? <span className="block text-xs text-muted-foreground">"{p.note}"</span> : null}</span>
                <LoadingButton size="xs" loading={approve.isPending && approve.variables === p.id} onClick={() => approve.mutate(p.id)} disabled={ret.isPending}><Check className="size-3" />Approve</LoadingButton>
                <Button size="xs" variant="outline" onClick={() => { setReturning(returning === p.id ? null : p.id); setNote(""); }} aria-expanded={returning === p.id}><Undo2 className="size-3" />Return</Button>
              </div>
              {returning === p.id ? (
                <form className="mt-2 flex flex-wrap gap-1.5" onSubmit={(e) => { e.preventDefault(); if (note.trim().length >= 3) ret.mutate({ pid: p.id, n: note.trim() }); }}>
                  <label htmlFor={`ret-${p.id}`} className="sr-only">Note to the resident</label>
                  <Input id={`ret-${p.id}`} autoFocus value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why it goes back (the resident sees this)" className="h-8 flex-1 min-w-48 text-sm" maxLength={300} />
                  <LoadingButton size="xs" type="submit" variant="secondary" loading={ret.isPending} disabled={note.trim().length < 3}>Return with note</LoadingButton>
                </form>
              ) : null}
            </motion.li>
          ))}
        </AnimatePresence>
      </ul>
      {err ? <p role="alert" className="text-xs text-bad mt-1">{err}</p> : null}
    </section>
  );
}
