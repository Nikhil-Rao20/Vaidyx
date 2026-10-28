// The left column: "New message", the search over names, departments and words, the All / Unread / Open / Resolved filter,
// and the conversations (newest first) with the online dot, the last line, the time, unread counts, Resolved and muted marks.
import { motion } from "motion/react";
import { BellOff, SquarePen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DataList, DataRow } from "@/components/DataList";
import { DateText } from "@/components/DateText";
import { EmptyState } from "@/components/EmptyState";
import { SearchBox } from "@/components/SearchBox";
import { Pill } from "@/components/StatusPill";
import { spring } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { useConversations, useDebounced, useMessageSearch, useMessagesUnread } from "@/features/messages/hooks";
import { ConversationAvatar } from "@/features/messages/parts";
import { usePresence } from "@/features/messages/useMessagesLive";
import type { ConversationFilter, ConversationRow, SearchHit } from "@/features/messages/types";

export const FILTERS: Array<{ key: ConversationFilter; label: string }> = [
  { key: "all", label: "All" }, { key: "unread", label: "Unread" }, { key: "open", label: "Open" }, { key: "resolved", label: "Resolved" },
];

function FilterBar({ value, onChange }: { value: ConversationFilter; onChange: (f: ConversationFilter) => void }) {
  return (
    <div className="scroll-thin -mx-1 flex items-center gap-0.5 overflow-x-auto px-1 pb-1" role="tablist" aria-label="Show">
      {FILTERS.map((f) => {
        const active = f.key === value;
        return (
          <button key={f.key} type="button" role="tab" aria-selected={active} data-testid={`filter-${f.key}`} onClick={() => onChange(f.key)}
            className={cn("relative inline-flex h-8 shrink-0 items-center rounded-full px-3 text-[13px] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
              active ? "text-foreground" : "text-muted-foreground hover:text-foreground")}>
            {active ? <motion.span layoutId="messages-filter-pill" className="absolute inset-0 rounded-full bg-secondary" transition={spring} aria-hidden /> : null}
            <span className="relative">{f.label}</span>
          </button>
        );
      })}
    </div>
  );
}

function Row({ c, me, active }: { c: ConversationRow; me: string; active: boolean }) {
  const presence = usePresence(c.with?.user, c.with?.online ?? null);
  const unread = c.unread > 0;
  const from = c.last ? (c.last.by === me ? "You: " : c.kind !== "direct" ? `${c.last.by_name}: ` : "") : "";
  return (
    <div data-testid="conversation-row" data-id={c.id} data-active={active ? "true" : "false"} data-unread={unread ? "true" : "false"}>
      <DataRow to={`/messages/${encodeURIComponent(c.id)}`} arrow={false}
        className={cn("items-start", active && "border-primary/60 bg-primary/5")}>
        <div className="flex items-start gap-3" aria-current={active ? "page" : undefined}>
          <ConversationAvatar kind={c.kind} name={c.title} presence={c.kind === "direct" ? presence : undefined} />
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline gap-2">
              <span className={cn("min-w-0 flex-1 truncate text-sm", unread ? "font-bold text-foreground" : "font-medium text-foreground")}>{c.title}</span>
              {c.last ? <DateText value={c.last.ts} mode="ago" className={cn("shrink-0 text-[11px]", unread ? "font-semibold text-foreground" : "text-muted-foreground")} /> : null}
            </div>
            {c.kind !== "direct" && c.subtitle ? <p className="truncate text-xs text-muted-foreground">{c.subtitle}</p> : null}
            <div className="mt-0.5 flex items-center gap-2">
              <p className={cn("min-w-0 flex-1 truncate text-xs", unread ? "text-foreground" : "text-muted-foreground")}>
                {c.last ? (c.last.preview ? `${from}${c.last.preview}` : <span className="italic">This message was deleted</span>) : <span className="italic">No messages yet</span>}
              </p>
              {c.muted ? <BellOff className="size-3.5 shrink-0 text-muted-foreground" aria-label="Muted" /> : null}
              {c.resolved ? <Pill tone="ok" className="shrink-0">Resolved</Pill> : null}
              {unread ? (
                <span className="min-w-5 shrink-0 rounded-full bg-primary px-1.5 text-center text-[11px] font-bold leading-5 text-primary-foreground" aria-label={`${c.unread} unread`}>
                  {c.unread > 99 ? "99+" : c.unread}
                </span>
              ) : null}
            </div>
          </div>
        </div>
      </DataRow>
    </div>
  );
}

function Hits({ hits }: { hits: SearchHit[] }) {
  if (!hits.length) return null;
  return (
    <section aria-label="Found in messages" className="space-y-1.5" data-testid="search-hits">
      <h2 className="px-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Found in messages</h2>
      {hits.slice(0, 20).map((h) => (
        <DataRow key={`${h.conversation_id}:${h.message.id}`} to={`/messages/${encodeURIComponent(h.conversation_id)}`} arrow={false}>
          <div className="flex items-baseline gap-2">
            <span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">{h.title}</span>
            <DateText value={h.message.ts} mode="ago" className="shrink-0 text-[11px] text-muted-foreground" />
          </div>
          <p className="truncate text-xs text-muted-foreground">{h.message.by_name}: {h.message.text}</p>
        </DataRow>
      ))}
    </section>
  );
}

export function ConversationList({ me, activeId, filter, onFilter, q, onQ, onNew, className }: {
  me: string;
  activeId?: string;
  filter: ConversationFilter;
  onFilter: (f: ConversationFilter) => void;
  q: string;
  onQ: (q: string) => void;
  onNew: () => void;
  className?: string;
}) {
  const dq = useDebounced(q.trim());
  const list = useConversations(filter, dq.length >= 2 ? dq : "");
  const search = useMessageSearch(dq);
  const unread = useMessagesUnread();
  const total = unread.data?.unread_total ?? list.data?.unread_total ?? 0;
  const searching = dq.length >= 2;
  const hits = searching ? search.data?.hits ?? [] : [];

  const empty = searching ? (
    hits.length ? null : <EmptyState kind="search" compact title="Nothing found" text="No conversation or message matches these words." />
  ) : filter === "unread" ? <EmptyState kind="done" compact title="Nothing unread" />
    : filter === "resolved" ? <EmptyState kind="done" compact title="Nothing resolved yet" />
    : filter === "open" ? <EmptyState kind="done" compact title="Nothing open" text="Every conversation is resolved." />
    : <EmptyState kind="inbox" compact title="No messages yet" action={<Button type="button" onClick={onNew}>Find a person to message</Button>} />;

  return (
    <div data-testid="conversation-list" className={cn("flex min-h-0 flex-col gap-3", className)}>
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="truncate text-xl font-semibold">Messages</h1>
          <p className="text-xs text-muted-foreground" aria-live="polite">{total ? `${total} unread` : "Nothing unread"}</p>
        </div>
        <Button type="button" onClick={onNew} data-testid="new-message" className="shrink-0">
          <SquarePen className="size-4" aria-hidden />New message
        </Button>
      </div>
      <SearchBox value={q} onChange={onQ} label="Find a person, a department or a word" placeholder="Find a person, a department or a word"
        loading={searching && (list.isFetching || search.isFetching)} />
      <FilterBar value={filter} onChange={onFilter} />
      <div className="scroll-thin -mx-1 min-h-0 flex-1 space-y-4 overflow-y-auto px-1 pb-2">
        <DataList items={list.data?.conversations} loading={list.isLoading} error={list.error} onRetry={() => list.refetch()} retrying={list.isFetching}
          what="your messages" skeletonRows={5} keyFor={(c) => c.id} empty={empty}
          renderRow={(c) => <Row c={c} me={me} active={c.id === activeId} />} />
        <Hits hits={hits} />
      </div>
    </div>
  );
}
