// The department inbox: open requests and the ones answered in the last 7 days (GET /inbox). The supporting doctor's
// home is this page; everyone with an inbox also has it at /requests.
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Inbox, Plus } from "lucide-react";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState } from "@/components/EmptyState";
import { DataList } from "@/components/DataList";
import { SearchBox } from "@/components/SearchBox";
import { RequestCard } from "@/features/requests/RequestCard";
import { MessageButton } from "@/components/MessageButton";
import { useInbox } from "@/hooks/useQueries";
import { useSession } from "@/lib/session";
import type { InboxRequest } from "@/lib/types";
import { cn } from "@/lib/utils";

type Tab = "open" | "done";

export default function RequestsPage({ embedded }: { embedded?: boolean }) {
  const { me } = useSession();
  const inbox = useInbox();
  const [params, setParams] = useSearchParams();
  const [tab, setTab] = useState<Tab>("open");
  const [q, setQ] = useState("");
  const caseFilter = params.get("case") || "";
  const departments = inbox.data?.departments ?? [];
  const [dept, setDept] = useState<string>("all");
  const all = useMemo<InboxRequest[]>(() => {
    const rows: InboxRequest[] = [];
    for (const d of departments) if (dept === "all" || d.id === dept) rows.push(...(d.requests || []));
    return rows;
  }, [departments, dept]);
  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return all
      .filter((r) => (tab === "done" ? r.status === "completed" || Boolean(r.done) : r.status !== "completed" && !r.done))
      .filter((r) => !caseFilter || r.case_id === caseFilter)
      .filter((r) => !needle || [r.patient?.name, r.uhid, r.patient?.mrn, r.label, r.what, r.accession, r.encounter?.ip_no, r.encounter?.op_no].filter(Boolean).join(" ").toLowerCase().includes(needle))
      .sort((a, b) => (tab === "open" ? Number(b.overdue) - Number(a.overdue) || String(a.due || "9").localeCompare(String(b.due || "9")) : String(b.completed || b.done?.at || "").localeCompare(String(a.completed || a.done?.at || ""))));
  }, [all, tab, q, caseFilter]);
  const openCount = all.filter((r) => r.status !== "completed" && !r.done).length;
  const overdue = all.filter((r) => r.overdue && r.status !== "completed").length;
  const canAnswer = Boolean(me && ((me.roles.supporting || []).length || Object.keys(me.roles.departments || {}).length));
  const title = embedded ? "Your department's requests" : "Requests";
  const subtitle = inbox.data ? `${openCount} open${overdue ? `, ${overdue} late` : ""}${departments.length > 1 ? `, across ${departments.length} departments` : departments[0] ? ` for ${departments[0].name}` : ""}` : undefined;

  return (
    <div>
      <PageHeader
        title={title}
        subtitle={subtitle}
        actions={(
          <span className="flex flex-wrap items-center gap-2">
            <MessageButton target={{ coordinator: true }} label="Message the MDT Coordinator" variant="outline" size="sm" />
            {departments.length > 1 ? (
              <select value={dept} onChange={(e) => setDept(e.target.value)} aria-label="Department" className="h-9 rounded-md border border-input bg-card px-2 text-sm">
                <option value="all">All my departments</option>
                {departments.map((d) => <option key={d.id} value={d.id}>{d.name} ({d.open})</option>)}
              </select>
            ) : null}
          </span>
        )}
      />
      {caseFilter ? (
        <p className="mb-3 flex items-center gap-2 text-sm text-muted-foreground">
          Showing requests for one Case File.
          <Button type="button" variant="link" size="sm" className="h-auto p-0" onClick={() => { params.delete("case"); setParams(params, { replace: true }); }}>Show all</Button>
        </p>
      ) : null}
      <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)}>
          <TabsList aria-label="Open or done">
            <TabsTrigger value="open">Open{openCount ? <span className={cn("ml-1.5 rounded-full px-1.5 text-[11px] font-bold", overdue ? "status-bad" : "bg-primary text-primary-foreground")}>{openCount}</span> : null}</TabsTrigger>
            <TabsTrigger value="done">Done</TabsTrigger>
          </TabsList>
        </Tabs>
        <SearchBox value={q} onChange={setQ} placeholder="Patient, UHID, accession" wrapperClassName="sm:w-72" />
      </div>
      <DataList<InboxRequest>
        items={shown}
        loading={inbox.isLoading}
        error={inbox.error}
        onRetry={() => void inbox.refetch()}
        retrying={inbox.isFetching}
        what="the department inbox"
        keyFor={(r) => `${r.case_id}:${r.action_id}`}
        renderRow={(r) => <RequestCard request={r} onChanged={() => void inbox.refetch()} canAnswer={canAnswer} />}
        skeletonRows={4}
        empty={
          tab === "open" ? (
            <EmptyState kind="inbox" title={q ? "No open request matches" : "No open requests"} text={q ? "Try another word, or clear the search." : "When a treating doctor asks your department for a record, the request appears here with the patient's identifiers."} action={q ? <Button type="button" variant="outline" size="sm" onClick={() => setQ("")}>Clear search</Button> : undefined} />
          ) : (
            <EmptyState kind="done" title="Nothing answered in the last 7 days" text="Requests you send done for stay here for a week." />
          )
        }
        footer={inbox.data && embedded && (me?.roles.treating || []).length ? (
          <p className="pt-2 text-center text-xs text-muted-foreground">
            <Inbox className="mr-1 inline size-3.5" aria-hidden /> Treating doctors send requests from a Case File. <Button type="button" variant="link" size="sm" className="h-auto p-0" asChild><Link to="/cases/new"><Plus className="size-3.5" aria-hidden /> New Case File</Link></Button>
          </p>
        ) : null}
      />
    </div>
  );
}
