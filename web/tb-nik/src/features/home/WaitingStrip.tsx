// "Waiting for me" (GET /waiting): a resident's proposals to approve or return, join requests, reviews. A consultant
// acts inline; a resident sees its own proposals (GET /waiting "mine"): "waiting for Dr X" or "returned by Dr X: note".
import { useState } from "react";
import { Link } from "react-router-dom";
import { AnimatePresence, motion } from "motion/react";
import { Check, ChevronRight, Hourglass, PenLine, Undo2, UserPlus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ActionButton } from "@/components/ActionButton";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DateText } from "@/components/DateText";
import { notify } from "@/components/Toasts";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { useWaiting, useInvalidate, keys, notBuiltYet } from "@/hooks/useQueries";
import { api } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import type { Me } from "@/lib/session";
import type { WaitingItem } from "@/lib/types";
import { drName } from "@/lib/format";

/** The login of the person asking to join: `user` or `by`, else the tail of the id "<case>:join:<user>". */
function joinUser(item: WaitingItem): string {
  return item.user || item.by || item.id.split(":join:")[1] || item.id;
}

function Item({ item, consultant, onDone }: { item: WaitingItem; consultant: boolean; onDone: () => void }) {
  const [returning, setReturning] = useState(false);
  const approve = useAsyncAction(async () => {
    if (item.kind === "proposal") await api.post(EP.proposalApprove(item.case_id, item.id));
    else if (item.kind === "join") await api.post(EP.pendingApprove(item.case_id, joinUser(item)));
    notify.success(item.kind === "join" ? "Approved: they are on the Case File" : "Approved and done");
    onDone();
  }, { onError: (m) => notify.error("Could not approve", m) });
  const returned = item.status === "returned";
  const Icon = returned ? Undo2 : item.kind === "join" ? UserPlus : item.kind === "proposal" ? (consultant ? PenLine : Hourglass) : Hourglass;
  return (
    <motion.li layout initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, height: 0 }} className="surface-inner flex flex-wrap items-center gap-3 p-3">
      <span className={returned ? "grid size-8 shrink-0 place-items-center rounded-md status-warn" : "grid size-8 shrink-0 place-items-center rounded-md status-review"}><Icon className="size-4" aria-hidden /></span>
      <div className="min-w-0 flex-1 basis-[calc(100%-3rem)] sm:basis-0">
        <p className="truncate text-sm font-medium text-foreground">{item.title}</p>
        <p className="truncate text-xs text-muted-foreground">
          {item.patient_line}{consultant && item.by_name ? `, from ${drName(item.by_name)}` : ""}{item.note ? `: "${item.note}"` : ""} <DateText value={item.at} mode="ago" />
        </p>
      </div>
      <div className="ml-11 flex items-center gap-1.5 sm:ml-0">
        {consultant && item.kind !== "review" ? (
          <>
            <ActionButton type="button" size="sm" state={approve.state} doneText="Approved" onClick={() => void approve.run()} icon={<Check className="size-4" aria-hidden />}>Approve</ActionButton>
            <Button type="button" size="sm" variant="outline" onClick={() => setReturning(true)}>
              {item.kind === "join" ? <X className="size-4" aria-hidden /> : <Undo2 className="size-4" aria-hidden />} {item.kind === "join" ? "Reject" : "Return"}
            </Button>
          </>
        ) : null}
        <Button type="button" size="sm" variant="ghost" asChild aria-label="Open the Case File">
          <Link to={`/cases/${encodeURIComponent(item.case_id)}`}><ChevronRight className="size-4" aria-hidden /></Link>
        </Button>
      </div>
      <ConfirmDialog
        open={returning}
        onOpenChange={setReturning}
        title={item.kind === "join" ? "Reject this join request" : "Return this to the resident"}
        text={item.kind === "join" ? "The person is told and stays off the Case File." : "The resident gets your note and can propose again."}
        confirmText={item.kind === "join" ? "Reject" : "Return with note"}
        requireReason
        reasonLabel={item.kind === "join" ? "Reason (optional for them, kept in the record)" : "Note to the resident"}
        onConfirm={async (reason) => {
          if (item.kind === "join") await api.post(EP.pendingReject(item.case_id, joinUser(item)), { note: reason });
          else await api.post(EP.proposalReturn(item.case_id, item.id), { note: reason });
          notify.success(item.kind === "join" ? "Rejected" : "Returned with your note");
          onDone();
        }}
      />
    </motion.li>
  );
}

export function WaitingStrip({ me }: { me: Me }) {
  const waiting = useWaiting();
  const invalidate = useInvalidate();
  const consultant = (me.roles.treating || []).length > 0;
  const resident = Object.values(me.roles.departments || {}).includes("resident");
  const items = consultant ? waiting.data?.items ?? [] : resident ? waiting.data?.mine ?? [] : [];
  if (waiting.error && notBuiltYet(waiting.error)) return null;
  if (!waiting.isLoading && !items.length) return null;
  return (
    <section aria-label="Waiting for you" className="mb-5">
      <h2 className="mb-2 flex items-center gap-2 text-base">
        {consultant ? "Waiting for you" : "Your proposals"}
        {items.length ? <span className="rounded-full status-review px-2 text-xs font-bold">{items.length}</span> : null}
      </h2>
      {waiting.isLoading && !items.length ? (
        <div className="space-y-2" aria-busy="true">{[0, 1].map((i) => <div key={i} className="skeleton-line h-14" />)}</div>
      ) : (
        <ul className="space-y-2">
          <AnimatePresence initial={false}>
            {items.map((it) => <Item key={`${it.kind}:${it.id}`} item={it} consultant={consultant} onDone={() => void invalidate(keys.waiting, keys.caseLists, keys.notifications)} />)}
          </AnimatePresence>
        </ul>
      )}
    </section>
  );
}
