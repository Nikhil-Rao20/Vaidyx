// /activity: everyone's own audited actions (GET /me/activity); the MDT Coordinator, the auditor and the root admin also
// read the full log (GET /activity, filtered by Case File and person; reading it is itself recorded).
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Building2, CalendarDays, Eye, FolderOpen, UserRound } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PageHeader } from "@/components/PageHeader";
import { SearchBox } from "@/components/SearchBox";
import { DataList } from "@/components/DataList";
import { EmptyState } from "@/components/EmptyState";
import { DateText } from "@/components/DateText";
import { useActivity, useMyActivity } from "@/hooks/useQueries";
import { useDebounce } from "@/hooks/useDebounce";
import { useSession } from "@/lib/session";
import type { ActivityEvent } from "@/lib/types";
import { parseDate } from "@/lib/format";

const SOURCE_ICON = { case: FolderOpen, organisation: Building2, session: CalendarDays } as const;

function dayLabel(ts: string, now = new Date()): string {
  const d = parseDate(ts);
  if (!d) return "Earlier";
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const t = d.getTime();
  if (t >= start) return "Today";
  if (t >= start - 86400000) return "Yesterday";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`;
}

function EventRow({ e, showBy, first }: { e: ActivityEvent; showBy?: boolean; first?: string | null }) {
  const Icon = SOURCE_ICON[(e.source as keyof typeof SOURCE_ICON) ?? "case"] ?? FolderOpen;
  return (
    <>
      {first ? <p className="pt-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">{first}</p> : null}
      <div className="surface-inner flex min-h-12 items-start gap-3 px-3 py-2.5">
        <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-md bg-muted text-muted-foreground"><Icon className="size-4" aria-hidden /></span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-foreground">{e.title}</p>
          {e.detail ? <p className="break-words text-xs text-muted-foreground">{e.detail}</p> : null}
          <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
            <DateText value={e.ts} mode="datetime" />
            {showBy && e.by ? <span className="inline-flex items-center gap-1"><UserRound className="size-3" aria-hidden /> {e.by_name || e.by}</span> : null}
            {e.case_id ? <Link to={`/cases/${encodeURIComponent(e.case_id)}`} className="mono text-link hover:underline">{e.case_id}</Link> : null}
          </p>
        </div>
      </div>
    </>
  );
}

function filterText(list: ActivityEvent[], q: string): ActivityEvent[] {
  const n = q.trim().toLowerCase();
  if (!n) return list;
  return list.filter((e) => [e.title, e.detail, e.case_id, e.by, e.kind].filter(Boolean).join(" ").toLowerCase().includes(n));
}

function grouped(list: ActivityEvent[]): Array<{ e: ActivityEvent; first: string | null }> {
  let last = "";
  return list.map((e) => {
    const label = dayLabel(e.ts);
    const first = label !== last ? label : null;
    last = label;
    return { e, first };
  });
}

function Mine() {
  const mine = useMyActivity();
  const [q, setQ] = useState("");
  const rows = useMemo(() => grouped(filterText(mine.data?.events ?? [], q)), [mine.data, q]);
  return (
    <div className="grid gap-3">
      <SearchBox value={q} onChange={setQ} placeholder="Search your actions" wrapperClassName="sm:max-w-sm" />
      <DataList
        items={rows}
        loading={mine.isLoading}
        error={mine.error}
        onRetry={() => void mine.refetch()}
        retrying={mine.isFetching}
        what="your activity"
        keyFor={(r, i) => `${r.e.ts}-${i}`}
        renderRow={(r) => <EventRow e={r.e} first={r.first} />}
        empty={<EmptyState kind={q ? "search" : "empty"} title={q ? "Nothing matches" : "No actions yet"} text={q ? "Try another word." : "Everything you do on a Case File, a meeting or a setting is recorded here under your name."} />}
        footer={mine.data?.total && mine.data.total > (mine.data.events?.length ?? 0) ? <p className="pt-2 text-center text-xs text-muted-foreground">The newest {mine.data.events.length} of {mine.data.total}.</p> : null}
      />
    </div>
  );
}

function FullLog() {
  const [caseId, setCaseId] = useState("");
  const [user, setUser] = useState("");
  const [limit, setLimit] = useState("200");
  const [q, setQ] = useState("");
  const dCase = useDebounce(caseId.trim(), 400);
  const dUser = useDebounce(user.trim().toLowerCase(), 400);
  const log = useActivity({ case_id: dCase, user: dUser, limit });
  const rows = useMemo(() => grouped(filterText(log.data?.events ?? [], q)), [log.data, q]);
  return (
    <div className="grid gap-3">
      <div className="grid gap-2 sm:grid-cols-[1fr_1fr_140px_1fr]">
        <Input value={caseId} onChange={(e) => setCaseId(e.target.value)} placeholder="Case File id" aria-label="Case File id" className="mono" />
        <Input value={user} onChange={(e) => setUser(e.target.value)} placeholder="Person (login)" aria-label="Person" />
        <Select value={limit} onValueChange={setLimit}>
          <SelectTrigger className="w-full" aria-label="How many"><SelectValue /></SelectTrigger>
          <SelectContent>{["100", "200", "500", "1000"].map((n) => <SelectItem key={n} value={n}>Newest {n}</SelectItem>)}</SelectContent>
        </Select>
        <SearchBox value={q} onChange={setQ} placeholder="Search the log" loading={log.isFetching && !log.isLoading} />
      </div>
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground"><Eye className="size-3.5" aria-hidden /> Reading the full log is itself recorded.</p>
      <DataList
        items={rows}
        loading={log.isLoading}
        error={log.error}
        onRetry={() => void log.refetch()}
        retrying={log.isFetching}
        what="the full activity log"
        keyFor={(r, i) => `${r.e.ts}-${i}`}
        renderRow={(r) => <EventRow e={r.e} first={r.first} showBy />}
        empty={<EmptyState kind="search" title="Nothing in the log for this" text="Clear a filter to see more." action={caseId || user || q ? <Button type="button" variant="outline" size="sm" onClick={() => { setCaseId(""); setUser(""); setQ(""); }}>Clear filters</Button> : undefined} />}
        footer={log.data?.total && log.data.total > (log.data.events?.length ?? 0) ? <p className="pt-2 text-center text-xs text-muted-foreground">The newest {log.data.events.length} of {log.data.total}.</p> : null}
      />
    </div>
  );
}

export default function ActivityPage() {
  const { me } = useSession();
  const full = Boolean(me && (me.roles.auditor || me.roles.coordinator || me.roles.root_admin));
  const [tab, setTab] = useState(full && me?.primary_role === "auditor" ? "all" : "mine");
  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader title="Activity" subtitle={full ? "Your own actions, and the full log of every action in the Tumour Board." : "Everything you did, newest first. Every action is recorded."} />
      {full ? (
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList aria-label="Whose actions">
            <TabsTrigger value="mine">My actions</TabsTrigger>
            <TabsTrigger value="all">Full log</TabsTrigger>
          </TabsList>
          <TabsContent value="mine" className="mt-4"><Mine /></TabsContent>
          <TabsContent value="all" className="mt-4"><FullLog /></TabsContent>
        </Tabs>
      ) : (
        <Mine />
      )}
    </div>
  );
}
