// Messages (night-v3 item 8.4, contract docs/night-v3/research/06_messages.md section 9.7): /messages, /messages/:id and
// /messages/new?to=<login>|dept=<id>|coordinator=1[&case=<id>]. Desktop: the conversations on the left, the thread on the right.
// Phone: the list full width; a conversation opens full screen with a back arrow and the composer above the Dock.
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useMatch, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { MessageSquarePlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { RowSkeleton } from "@/components/DataList";
import { notify } from "@/components/Toasts";
import { useIsDesktop } from "@/hooks/useMediaQuery";
import { ApiError } from "@/lib/api";
import { useSession } from "@/lib/session";
import { cn } from "@/lib/utils";
import { messagesError, startConversation } from "@/features/messages/api";
import { msgKeys, useConversation, useConversations, useDirectory, useLinks } from "@/features/messages/hooks";
import { ConversationList } from "@/features/messages/ConversationList";
import { DirectoryPicker, existingConversation, pickPath, type Pick } from "@/features/messages/DirectoryPicker";
import { Composer, type ComposerSend } from "@/features/messages/Composer";
import { BackToMessages, Thread, ThreadFrame, ThreadTitle } from "@/features/messages/Thread";
import { NOT_PLACED } from "@/features/messages/parts";
import { useMessagesLive } from "@/features/messages/useMessagesLive";
import type { ConversationFilter, ConversationKind, MessageTarget, PickedLink } from "@/features/messages/types";

// The filter and the search words survive moving between conversations (the shell remounts the page on every path).
const kept: { filter: ConversationFilter; q: string } = { filter: "all", q: "" };

/** The Case File (or meeting) to put in the composer from ?case=, only when GET /messages/links lists it for me. */
function useInitialLink(caseId: string): PickedLink | null {
  const links = useLinks(caseId, !!caseId);
  return useMemo(() => {
    const hit = links.data?.cases.find((c) => c.id === caseId);
    return hit ? { type: "case", id: hit.id, label: hit.label } : null;
  }, [links.data, caseId]);
}

function Loading({ phone }: { phone: boolean }) {
  return (
    <div data-testid="thread-loading" aria-busy="true" aria-label="Loading"
      className={cn("space-y-2 p-4", phone ? "fixed inset-x-0 bottom-0 top-14 z-30 bg-background" : "surface h-full")}>
      <RowSkeleton /><RowSkeleton /><RowSkeleton />
    </div>
  );
}

function Missing({ phone, error }: { phone: boolean; error: unknown }) {
  const gone = error instanceof ApiError && error.status === 404;
  return (
    <div className={cn("grid place-items-center p-4", phone ? "fixed inset-x-0 bottom-0 top-14 z-30 bg-background pb-24" : "surface h-full")}>
      {gone ? (
        <EmptyState kind="notfound" title="No such conversation" text="It does not exist, or you are not in it."
          action={<Button asChild variant="outline"><Link to="/messages">Back to Messages</Link></Button>} />
      ) : <ErrorState error={error} what="this conversation" />}
    </div>
  );
}

/** The composer against a person, a department or the MDT Coordinator before the first message (/messages/new). */
function NewConversation({ phone, me, onFind }: { phone: boolean; me: string; onFind: () => void }) {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const to = params.get("to") ?? "";
  const dept = params.get("dept") ?? "";
  const coord = params.get("coordinator") === "1";
  const caseId = params.get("case") ?? "";
  const pick: Pick | null = to ? { to } : dept ? { dept } : coord ? { coordinator: true } : null;
  const target: MessageTarget | null = to ? { user: to } : dept ? { department: dept } : coord ? { role: "coordinator" } : null;
  const dir = useDirectory("", !!pick);
  const list = useConversations("all", "", !!pick);
  const initialLink = useInitialLink(caseId);
  const sending = useRef(false);

  // There is a conversation with this target already: open it (with the Case File, when one was asked for).
  const found = pick ? existingConversation(list.data?.conversations, me, pick) : undefined;
  useEffect(() => {
    if (pick && found && !sending.current) navigate(pickPath(list.data?.conversations, me, pick, caseId || undefined), { replace: true });
  }, [found?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!pick || !target) {
    return (
      <div className={cn("grid place-items-center p-4", phone ? "fixed inset-x-0 bottom-0 top-14 z-30 bg-background pb-24" : "surface h-full")}>
        <EmptyState kind="people" title="Who is it for?" text="Choose a colleague, a department or the MDT Coordinator."
          action={<Button type="button" onClick={onFind}>Find a person to message</Button>} />
      </div>
    );
  }
  if (to && to === me) {
    return (
      <div className={cn("grid place-items-center p-4", phone ? "fixed inset-x-0 bottom-0 top-14 z-30 bg-background pb-24" : "surface h-full")}>
        <EmptyState kind="people" title="You cannot message yourself." action={<Button type="button" onClick={onFind}>Find a person to message</Button>} />
      </div>
    );
  }

  let kind: ConversationKind = "direct";
  let title = to;
  let subtitle = "";
  if (to) {
    const p = dir.data?.people.find((x) => x.user === to) ?? dir.data?.coordinators.find((x) => x.user === to);
    if (p) {
      title = p.display_name;
      subtitle = [p.title, p.departments.map((d) => d.name).join(", ")].filter(Boolean).join(", ");
    } else if (dir.isLoading) title = "";
  } else if (dept) {
    kind = "department";
    const d = dir.data?.departments.find((x) => x.id === dept);
    title = d?.name ?? (dir.isLoading ? "" : dept);
    subtitle = d ? `Reaches ${d.members} ${d.members === 1 ? "person" : "people"}` : "";
  } else {
    kind = "coordinator";
    title = "MDT Coordinator";
    const n = dir.data?.coordinators.length ?? 0;
    subtitle = n ? `Reaches ${n} ${n === 1 ? "coordinator" : "coordinators"}` : "";
  }

  const send = async ({ text, link, mentions }: ComposerSend) => {
    sending.current = true;
    try {
      const r = await startConversation(target, text, link, mentions);
      void qc.invalidateQueries({ queryKey: msgKeys.all });
      navigate(`/messages/${encodeURIComponent(r.conversation.id)}`, { replace: true });
      return true;
    } catch (e) {
      sending.current = false;
      notify.error(messagesError(e, "Could not send. Try again."));
      return false;
    }
  };

  const titleEl = <ThreadTitle kind={kind} title={title || "Loading"} subtitle={subtitle} />;
  return (
    <ThreadFrame phone={phone} label={`New message to ${title || "a colleague"}`}
      header={phone ? <div className="flex flex-col gap-1.5"><BackToMessages />{titleEl}</div> : titleEl}
      composer={<Composer key={`${to}|${dept}|${coord}`} me={me} initialLink={initialLink} onSend={send} autoFocus={!phone} />}>
      <div className="grid min-h-0 flex-1 place-items-center overflow-y-auto p-4">
        <p className="max-w-sm text-center text-sm text-muted-foreground" data-testid="new-hint">
          {kind === "department" ? `A new conversation with ${title || "the department"}. Everyone placed there can read and answer it.`
            : kind === "coordinator" ? "A new conversation with the MDT Coordinator. Every coordinator can read and answer it."
            : `A new conversation with ${title || "this colleague"}. Only the two of you can read it.`}
        </p>
      </div>
    </ThreadFrame>
  );
}

function OpenThread({ id, phone, me }: { id: string; phone: boolean; me: string }) {
  const [params] = useSearchParams();
  const view = useConversation(id);
  const initialLink = useInitialLink(params.get("case") ?? "");
  if (view.isLoading) return <Loading phone={phone} />;
  if (view.error || !view.data) return <Missing phone={phone} error={view.error} />;
  return <Thread view={view.data} me={me} phone={phone} initialLink={initialLink} />;
}

export default function MessagesPage() {
  const { me } = useSession();
  const desktop = useIsDesktop();
  const { id } = useParams();
  const isNew = !!useMatch("/messages/new");
  const [filter, setFilterState] = useState<ConversationFilter>(kept.filter);
  const [q, setQState] = useState(kept.q);
  const [finding, setFinding] = useState(false);
  const allowed = !!me?.messages;
  useMessagesLive(allowed);

  if (!me) return null;
  if (!allowed) {
    return (
      <div data-testid="messages-page" className="py-10">
        <EmptyState kind="lock" title={NOT_PLACED} text="Ask your department admin to place you in a department, or write to the MDT Coordinator another way." />
      </div>
    );
  }

  const setFilter = (f: ConversationFilter) => { kept.filter = f; setFilterState(f); };
  const setQ = (v: string) => { kept.q = v; setQState(v); };
  const user = me.user;
  const openId = !isNew && id ? id : undefined;
  const list = (
    <ConversationList me={user} activeId={openId} filter={filter} onFilter={setFilter} q={q} onQ={setQ} onNew={() => setFinding(true)}
      className={desktop ? "surface h-full p-3" : undefined} />
  );
  const right = isNew ? <NewConversation phone={!desktop} me={user} onFind={() => setFinding(true)} />
    : openId ? <OpenThread key={openId} id={openId} phone={!desktop} me={user} />
    : desktop ? (
      <div className="surface grid h-full place-items-center p-6" data-testid="no-conversation">
        <EmptyState kind="inbox" title="Choose a conversation" text="Or start one with New message."
          action={<Button type="button" variant="outline" onClick={() => setFinding(true)}><MessageSquarePlus className="size-4" aria-hidden />New message</Button>} />
      </div>
    ) : null;

  return (
    <div data-testid="messages-page"
      className={cn(desktop && "grid h-[calc(100dvh-7.5rem)] min-h-[30rem] grid-cols-[360px_minmax(0,1fr)] gap-4")}>
      {/* The same two slots on every width, so turning a tablet or resizing the window keeps the draft in the composer. */}
      {desktop || !(openId || isNew) ? list : null}
      {desktop || openId || isNew ? <div className="min-h-0 min-w-0">{right}</div> : null}
      <DirectoryPicker open={finding} onOpenChange={setFinding} />
    </div>
  );
}
