// Edit a drafted request before it goes: the address, the subject, the body and the due date, then Send.
import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Send } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { getRequestDraft, sendRequest } from "../api";
import type { Slot, SlotAction } from "../types";
import { ErrorState, LoadingButton, SkeletonLines, errorText, fmtDate, todayIso } from "./common";

export function RequestEditPanel({ caseId, slot, action, onSent }: { caseId: string; slot: Slot; action: SlotAction; onSent: () => Promise<void> }) {
  const q = useQuery({ queryKey: ["draft", caseId, action.action_id], queryFn: () => getRequestDraft(caseId, action.action_id!), enabled: !!action.action_id, retry: false });
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [due, setDue] = useState("");
  useEffect(() => { if (q.data) { setSubject(q.data.subject ?? ""); setBody(q.data.body ?? ""); setDue((q.data.due ?? "").slice(0, 10)); } }, [q.data]);
  const send = useMutation({ mutationFn: () => sendRequest(caseId, action.action_id!, { message: body, due: due || undefined, subject }), onSuccess: () => void onSent() });
  if (!action.action_id) return <p className="text-sm text-muted-foreground">This line has no drafted request to edit yet.</p>;
  if (q.isLoading) return <SkeletonLines n={5} />;
  if (q.isError) return <ErrorState error={q.error} retry={() => void q.refetch()} compact />;
  const d = q.data!;
  const today = todayIso();
  const dueBad = due && due < today ? "The due date is in the past." : null;
  return (
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (!dueBad) send.mutate(); }} data-testid="request-edit">
      <p className="text-sm text-muted-foreground">For the line <span className="font-medium text-foreground">{slot.label}</span>. Sent in-app to {d.to}{d.accession ? `, accession ${d.accession}` : ""}.</p>
      <div>
        <label htmlFor="req-subject" className="text-sm font-medium">Subject</label>
        <Input id="req-subject" value={subject} onChange={(e) => setSubject(e.target.value)} className="mt-1 h-9 text-sm" maxLength={200} />
      </div>
      <div>
        <label htmlFor="req-body" className="text-sm font-medium">Message</label>
        <Textarea id="req-body" value={body} onChange={(e) => setBody(e.target.value)} className="mt-1 min-h-40 text-sm" maxLength={4000} />
      </div>
      <div>
        <label htmlFor="req-due" className="text-sm font-medium">Needed by</label>
        <Input id="req-due" type="date" value={due} min={today} onChange={(e) => setDue(e.target.value)} className="mt-1 h-9 text-sm w-48" aria-invalid={!!dueBad} aria-describedby="req-due-help" />
        <p id="req-due-help" className={`text-xs mt-0.5 ${dueBad ? "text-bad" : "text-muted-foreground"}`}>{dueBad ?? (d.due ? `Suggested: ${fmtDate(d.due)}` : "Suggested: 3 working days")}</p>
      </div>
      {send.isError ? <p role="alert" className="text-xs text-bad">{errorText(send.error)}</p> : null}
      <div className="flex gap-2 justify-end">
        {d.mailto ? <a className="text-xs text-link underline self-center" href={d.mailto}>Open in my mail instead</a> : null}
        <LoadingButton type="submit" loading={send.isPending} loadingText="Sending" disabled={!!dueBad || body.trim().length < 5}><Send className="size-4" />Send to {d.to}</LoadingButton>
      </div>
    </form>
  );
}
