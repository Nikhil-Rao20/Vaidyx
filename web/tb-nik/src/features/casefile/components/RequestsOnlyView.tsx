// The Case File as a supporting department sees it (access scope "requests"): the patient line, what the department was
// asked for, and the department's own records. No summary, chats, team, helpers or board decisions (they are not theirs).
import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, CalendarDays, Inbox } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useProtocols } from "@/hooks/useQueries";
import type { CaseFile } from "../types";
import { ReportsPanel } from "./ReportsPanel";
import { SidePanel } from "./SidePanel";
import { SourceViewer, type SourceTarget } from "./SourceViewer";
import { StatusChip, fmtDate, screenNote } from "./common";

const STATUS: Record<string, { kind: "ok" | "warn" | "bad" | "muted"; word: string }> = {
  completed: { kind: "ok", word: "done" },
  pending: { kind: "warn", word: "open" },
  overdue: { kind: "bad", word: "late" },
  suggested: { kind: "muted", word: "not sent yet" },
};

export function RequestsOnlyView({ id, cf }: { id: string; cf: CaseFile }) {
  const [source, setSource] = useState<SourceTarget | null>(null);
  const protocols = useProtocols();
  const c = cf.case;
  const p = c.patient ?? { name: "", mrn: "", agesex: "" };
  const protocolId = c.protocol ?? "";
  const cancer = (protocols.data?.protocols ?? []).find((x) => x.id === protocolId)?.label || (protocolId ? `${protocolId.charAt(0).toUpperCase()}${protocolId.slice(1).replace(/_/g, " ")} cancer` : "");
  const owner = typeof cf.access?.owner === "object" && cf.access?.owner ? cf.access.owner.name ?? cf.access.owner.id : "";
  const actions = cf.state?.actions ?? [];
  return (
    <div className="space-y-3 pb-24 lg:pb-8" data-testid="casefile-page" data-scope="requests">
      <header className="surface p-3 sm:p-4" data-testid="header-strip">
        <h1 className="text-xl sm:text-2xl leading-tight break-words">{p.name || "Unnamed patient"} <span className="text-base font-normal text-muted-foreground whitespace-nowrap">{p.agesex}</span></h1>
        <p className="text-sm text-muted-foreground">UHID <span className="mono text-foreground">{p.mrn}</span></p>
        <p className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-sm">
          {cancer ? <span className="font-medium text-foreground">{cancer}</span> : null}
          {owner ? <span className="text-muted-foreground">Responsible Department: {owner}</span> : null}
          <span className="inline-flex items-center gap-1 text-muted-foreground"><CalendarDays className="size-3.5" aria-hidden />{c.board_date ? `Board ${fmtDate(c.board_date)}` : "Board date not set"}</span>
        </p>
      </header>

      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-12">
        <section className="surface min-w-0 p-4 lg:col-span-5" aria-labelledby="h-asked">
          <h2 id="h-asked" className="flex items-center gap-2 text-base"><Inbox className="size-4 text-brand" aria-hidden />What your department was asked for</h2>
          <p className="mt-1 text-sm text-muted-foreground">You see this Case File because your department was asked for a record. Only those requests and your department's records are shown.</p>
          {actions.length ? (
            <ul className="mt-3 divide-y divide-border">
              {actions.map((a) => {
                const st = STATUS[a.status] ?? STATUS.pending;
                return (
                  <li key={a.id} className="py-2.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium text-foreground">{a.label}</span>
                      <StatusChip kind={st.kind}>{st.word}</StatusChip>
                    </div>
                    {a.what && a.what !== a.label ? <p className="mt-0.5 text-xs text-muted-foreground">{screenNote(a.what)}</p> : null}
                    <p className="mt-0.5 flex flex-wrap gap-x-3 text-xs text-muted-foreground">
                      {a.accession ? <span>Accession <span className="mono text-foreground">{a.accession}</span></span> : null}
                      {a.due ? <span>Needed by {fmtDate(a.due)}</span> : null}
                    </p>
                  </li>
                );
              })}
            </ul>
          ) : <p className="mt-3 text-sm text-muted-foreground">No request from this Case File is open for your department.</p>}
          <Button asChild size="sm" className="mt-3"><Link to={`/requests?case=${encodeURIComponent(id)}`}>Answer in Requests<ArrowRight className="size-4" aria-hidden /></Link></Button>
        </section>
        <div className="min-w-0 lg:col-span-7">
          <ReportsPanel caseId={id} cf={cf} onOpenSource={setSource} onChanged={async () => {}} />
        </div>
      </div>

      <SidePanel open={!!source} onClose={() => setSource(null)} title={source?.title ?? "Source"} subtitle="Quotes are shown as printed; nothing is interpreted." width="wide">
        {source ? <SourceViewer caseId={id} target={source} doc={cf.documents.find((d) => d.doc_id === source.docId)} /> : null}
      </SidePanel>
    </div>
  );
}
