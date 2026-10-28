// One conversation: the header (who, presence, resolve, mute), the first-use notice, the messages by day (own on the right),
// reactions, the React / Edit / Delete menu, the Case File and meeting chips (as this reader may see them), "Seen", "is typing",
// and the composer. Marks read when the thread is open and visible and its last message changed (never on a timer).
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, Bell, BellOff, CalendarDays, CheckCircle2, FolderOpen, Info, Loader2, Lock, MoreHorizontal, Pencil, RotateCcw, Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Pill } from "@/components/StatusPill";
import { announce, notify } from "@/components/Toasts";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  deleteMessage, editMessage, getConversation, markNoticeSeen, markRead, messagesError, reactTo, sendMessage, setMuted, setResolved,
} from "@/features/messages/api";
import { msgKeys } from "@/features/messages/hooks";
import { Composer, type ComposerSend } from "@/features/messages/Composer";
import { ConversationAvatar, REACTIONS, TEXT_MAX, clock, groupDays, minutesLeft, presenceWord } from "@/features/messages/parts";
import { usePresence, useTyping } from "@/features/messages/useMessagesLive";
import type { Chip, ConversationRow, ConversationView, Message, PickedLink, Presence, ReactionKind } from "@/features/messages/types";

/** The first-use notice with the hospital's own retention setting (0 keeps every message until the hospital removes it). */
export function noticeText(days?: number | null): string {
  const kept = typeof days === "number" && days > 0
    ? `They are kept for ${days} days after the last message, then the text is removed.`
    : typeof days === "number" ? "They are kept until the hospital removes them." : "They are kept for a set time after the last message, then the text is removed.";
  return `Messages are for work between the staff of this hospital. ${kept} Only the people in a conversation can read it; the activity log records who messaged whom, never the text. Ask the MDT Coordinator to have a message removed.`;
}
export const NOTICE_TEXT = noticeText(365);

// ---- the frame (desktop: a card in the right column; phone: the whole screen above the Dock) -----------------------------
export function ThreadFrame({ phone, header, children, composer, testId = "thread", label }: {
  phone: boolean;
  header: ReactNode;
  children: ReactNode;
  composer: ReactNode;
  testId?: string;
  label: string;
}) {
  return (
    <section data-testid={testId} aria-label={label}
      className={cn("flex min-h-0 flex-col", phone ? "fixed inset-x-0 bottom-0 top-14 z-30 bg-background" : "surface h-full overflow-hidden")}>
      <div className="shrink-0 border-b border-border px-3 py-2.5 lg:px-4">{header}</div>
      {children}
      <div className={cn("shrink-0 border-t border-border bg-card px-3 pt-2 lg:px-4 lg:pb-3", phone && "pb-[calc(env(safe-area-inset-bottom)+4.5rem)]")}>{composer}</div>
    </section>
  );
}

/** The back arrow of the phone thread. */
export function BackToMessages() {
  return (
    <Link to="/messages" className="inline-flex min-h-9 items-center gap-1 rounded-md pr-2 text-sm font-medium text-link hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
      <ArrowLeft className="size-4" aria-hidden />Messages
    </Link>
  );
}

/** Who the conversation is with: avatar, name, the line under it, presence (direct only). */
export function ThreadTitle({ kind, title, subtitle, presence }: { kind: ConversationRow["kind"]; title: string; subtitle?: string; presence?: Presence }) {
  return (
    <div className="flex min-w-0 flex-1 items-center gap-3">
      <ConversationAvatar kind={kind} name={title} presence={kind === "direct" ? presence : undefined} />
      <div className="min-w-0">
        <h2 className="truncate text-base font-semibold leading-tight text-foreground">{title}</h2>
        <p className="truncate text-xs text-muted-foreground">
          {kind === "direct" && presence ? <span className={cn("font-medium", presence === "online" ? "text-ok" : presence === "away" ? "text-warn" : "")}>{presenceWord(presence)}</span> : null}
          {kind === "direct" && presence && subtitle ? ", " : null}
          {subtitle}
        </p>
      </div>
    </div>
  );
}

// ---- the chips -------------------------------------------------------------------------------------------------------------
function ChipView({ chip, mine }: { chip: Chip; mine: boolean }) {
  const enc = encodeURIComponent(chip.id);
  const base = "mt-1.5 inline-flex max-w-full items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium";
  if (chip.can_open && chip.label) {
    const Icon = chip.type === "case" ? FolderOpen : CalendarDays;
    return (
      <Link to={chip.type === "case" ? `/cases/${enc}` : `/meetings/${enc}`} data-testid="chip" data-open="true"
        className={cn(base, "border-primary/40 bg-card text-link hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring", mine && "bg-card/80")}>
        <Icon className="size-3.5 shrink-0" aria-hidden />
        <span className="truncate">{chip.type === "case" ? "Case File" : "Meeting"}: {chip.label}</span>
      </Link>
    );
  }
  return (
    <span data-testid="chip" data-open="false" className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
      <span className={cn(base, "mt-0 border-border bg-muted text-muted-foreground")}>
        <Lock className="size-3.5 shrink-0" aria-hidden />
        {chip.type === "case" ? "A Case File you cannot open" : "A meeting you cannot open"}
      </span>
      {chip.type === "case" && chip.offer ? (
        <Link to={`/cases/${enc}`} className="text-xs font-medium text-link hover:underline" data-testid="chip-offer">Open with a reason</Link>
      ) : null}
    </span>
  );
}

// ---- one message -------------------------------------------------------------------------------------------------------
function MessageItem({ m, me, kind, names, seen, onReact, onEdit, onDelete }: {
  m: Message;
  me: string;
  kind: ConversationRow["kind"];
  names: Map<string, string>;
  seen: boolean;
  onReact: (m: Message, k: ReactionKind) => void;
  onEdit: (m: Message, text: string) => Promise<boolean>;
  onDelete: (m: Message) => void;
}) {
  const mine = m.by === me;
  const [menu, setMenu] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(m.text);
  const [saving, setSaving] = useState(false);
  const press = useRef<number | null>(null);
  const gone = m.deleted || m.removed;
  const left = minutesLeft(m.can_edit_until);
  const reacted = REACTIONS.filter((r) => (m.reactions[r.kind]?.length ?? 0) > 0);

  const save = async () => {
    const t = draft.trim();
    if (!t || t.length > TEXT_MAX) return;
    if (t === m.text) { setEditing(false); return; }
    setSaving(true);
    try { if (await onEdit(m, t)) setEditing(false); } finally { setSaving(false); }
  };
  // A long press on a phone opens the same menu as the hover button.
  const startPress = (e: React.PointerEvent) => {
    if (e.pointerType !== "touch" || gone) return;
    press.current = window.setTimeout(() => setMenu(true), 500);
  };
  const endPress = () => { if (press.current) { window.clearTimeout(press.current); press.current = null; } };

  return (
    <li data-testid="message" data-mine={mine ? "true" : "false"} data-id={m.id} className={cn("group flex items-start gap-1", mine ? "flex-row-reverse" : "flex-row")}>
      <div className={cn("flex min-w-0 max-w-[85%] flex-col lg:max-w-[70%]", mine ? "items-end" : "items-start")}>
        <div onPointerDown={startPress} onPointerUp={endPress} onPointerLeave={endPress} onPointerCancel={endPress}
          className={cn("min-w-0 max-w-full rounded-2xl border px-3 py-2", mine ? "rounded-br-md border-primary/30 bg-primary/10" : "rounded-bl-md border-border bg-card", gone && "bg-muted")}>
          <p className={cn("flex flex-wrap items-baseline gap-x-1.5 text-xs", mine && "justify-end")}>
            {!mine && kind !== "direct" ? <span className="font-semibold text-foreground">{m.by_name || m.by}</span> : null}
            <time dateTime={m.ts} title={formatDateTime(m.ts)} className="tabular-nums text-muted-foreground">{clock(m.ts)}</time>
            {m.edited && !gone ? <span className="text-muted-foreground" title={m.edited_ts ? `Edited ${formatDateTime(m.edited_ts)}` : undefined}>edited</span> : null}
          </p>
          {editing ? (
            <div className="mt-1 flex min-w-[min(18rem,70vw)] flex-col gap-1.5">
              <label htmlFor={`edit-${m.id}`} className="sr-only">Edit the message</label>
              <Textarea id={`edit-${m.id}`} value={draft} onChange={(e) => setDraft(e.target.value)} autoFocus data-testid="edit-input"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void save(); }
                  if (e.key === "Escape") { e.preventDefault(); setEditing(false); setDraft(m.text); }
                }}
                className="max-h-40 min-h-11 text-base md:text-base" />
              <div className="flex justify-end gap-2">
                <Button type="button" size="sm" variant="ghost" onClick={() => { setEditing(false); setDraft(m.text); }}>Cancel</Button>
                <Button type="button" size="sm" onClick={() => void save()} disabled={saving || !draft.trim() || draft.length > TEXT_MAX} data-testid="edit-save">
                  {saving ? <Loader2 className="size-4 animate-spin" aria-hidden /> : null}Save
                </Button>
              </div>
            </div>
          ) : m.deleted ? (
            <p className="text-sm italic text-muted-foreground">This message was deleted</p>
          ) : m.removed ? (
            <p className="text-sm italic text-muted-foreground">The text was removed after the set keeping time</p>
          ) : (
            <p className="whitespace-pre-wrap break-words text-sm text-foreground [overflow-wrap:anywhere]">{m.text}</p>
          )}
          {m.link && !gone ? <ChipView chip={m.link} mine={mine} /> : null}
        </div>
        {reacted.length && !gone ? (
          <ul className={cn("mt-1 flex flex-wrap gap-1", mine && "justify-end")} aria-label="Reactions" data-testid="reactions">
            {reacted.map((r) => {
              const who = m.reactions[r.kind] ?? [];
              const minePick = who.includes(me);
              const Icon = r.icon;
              const list = who.map((u) => (u === me ? "you" : names.get(u) ?? u)).join(", ");
              return (
                <li key={r.kind}>
                  <button type="button" onClick={() => onReact(m, r.kind)} title={`${r.label}: ${list}`} aria-pressed={minePick}
                    aria-label={`${r.label}, ${who.length}${minePick ? ", including you" : ""}`}
                    className={cn("inline-flex h-6 items-center gap-1 rounded-full border px-2 text-[11px] font-medium tabular-nums focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      minePick ? "border-primary/50 bg-primary/10 text-foreground" : "border-border bg-card text-muted-foreground hover:text-foreground")}>
                    <Icon className="size-3" aria-hidden />{r.word ? <span>{r.label}</span> : null}<span>{who.length}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        ) : null}
        {seen ? <p className="mt-0.5 text-[11px] text-muted-foreground" data-testid="seen">Seen</p> : null}
      </div>
      {!gone && !editing ? (
        <DropdownMenu open={menu} onOpenChange={setMenu}>
          <DropdownMenuTrigger asChild>
            <Button type="button" variant="ghost" size="icon-xs" aria-label="Message actions" data-testid="message-menu"
              className="mt-1 shrink-0 text-muted-foreground opacity-50 focus-visible:opacity-100 data-[state=open]:opacity-100 lg:opacity-0 lg:group-hover:opacity-100">
              <MoreHorizontal className="size-4" aria-hidden />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align={mine ? "end" : "start"} className="w-60">
            <DropdownMenuLabel className="text-xs text-muted-foreground">React</DropdownMenuLabel>
            {REACTIONS.map((r) => {
              const Icon = r.icon;
              const on = m.reactions[r.kind]?.includes(me);
              return (
                <DropdownMenuItem key={r.kind} onSelect={() => onReact(m, r.kind)} data-testid={`react-${r.kind}`}>
                  <Icon className="size-4" aria-hidden />{r.label}{on ? <span className="ml-auto text-xs text-muted-foreground">yours</span> : null}
                </DropdownMenuItem>
              );
            })}
            {mine && left > 0 ? (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">You can edit for {left} more {left === 1 ? "minute" : "minutes"}</DropdownMenuLabel>
                <DropdownMenuItem onSelect={() => { setDraft(m.text); setEditing(true); }} data-testid="edit-message"><Pencil className="size-4" aria-hidden />Edit</DropdownMenuItem>
                <DropdownMenuItem onSelect={() => onDelete(m)} variant="destructive" data-testid="delete-message"><Trash2 className="size-4" aria-hidden />Delete</DropdownMenuItem>
              </>
            ) : null}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : <span className="w-6 shrink-0" aria-hidden />}
    </li>
  );
}

// ---- the first-use notice -------------------------------------------------------------------------------------------------
function Notice({ days }: { days?: number | null }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const gotIt = async () => {
    setBusy(true);
    try {
      await markNoticeSeen();
      qc.setQueriesData<ConversationView>({ queryKey: ["messages", "c"] }, (old) => (old ? { ...old, notice_seen: true } : old));
    } catch (e) {
      notify.error(messagesError(e));
    } finally { setBusy(false); }
  };
  return (
    <div data-testid="notice" role="note" className="surface-inner mx-auto flex max-w-2xl flex-col gap-2 border-primary/30 p-3 text-sm sm:flex-row sm:items-start">
      <Info className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
      <p className="min-w-0 flex-1 text-foreground">{noticeText(days)}</p>
      <Button type="button" size="sm" onClick={() => void gotIt()} disabled={busy} className="self-end sm:self-start">Got it</Button>
    </div>
  );
}

// ---- the thread ---------------------------------------------------------------------------------------------------------
export function Thread({ view, me, phone, initialLink }: { view: ConversationView; me: string; phone: boolean; initialLink?: PickedLink | null }) {
  const qc = useQueryClient();
  const c = view.conversation;
  const id = c.id;
  const key = msgKeys.conversation(id);
  const presence = usePresence(c.with?.user, c.with?.online ?? null);
  const typing = useTyping(id);
  const [older, setOlder] = useState<Message[]>([]);
  const [moreBusy, setMoreBusy] = useState(false);
  const [hasMore, setHasMore] = useState(view.has_more);
  const [toDelete, setToDelete] = useState<Message | null>(null);
  const [busy, setBusy] = useState<"" | "resolve" | "mute">("");
  const listRef = useRef<HTMLDivElement>(null);
  const atBottom = useRef(true);
  const lastId = useRef<string | null>(null);

  const messages = [...older.filter((o) => !view.messages.some((m) => m.id === o.id)), ...view.messages];
  const names = new Map(view.readers.map((r) => [r.user, r.display_name]));
  for (const m of messages) if (!names.has(m.by)) names.set(m.by, m.by_name);
  const lastSeq = messages.reduce((a, m) => Math.max(a, m.seq), 0);
  const newest = messages[messages.length - 1];
  const lastMine = [...messages].reverse().find((m) => m.by === me && !m.deleted);
  const seenId = c.kind === "direct" && lastMine && view.seen_seq != null && view.seen_seq >= lastMine.seq ? lastMine.id : null;

  useEffect(() => { setHasMore(view.has_more); }, [view.has_more]);

  // Follow the newest message when at the bottom (or when it is mine).
  useLayoutEffect(() => {
    const nid = newest?.id ?? null;
    if (nid === lastId.current) return;
    const first = lastId.current === null;
    lastId.current = nid;
    const el = listRef.current;
    if (el && (first || atBottom.current || newest?.by === me)) el.scrollTop = el.scrollHeight;
  }, [newest?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Read up to the last message while the thread is open and visible (and when the tab becomes visible again).
  const posted = useRef(0);
  useEffect(() => {
    const go = () => {
      if (document.visibilityState !== "visible" || !lastSeq || posted.current >= lastSeq) return;
      posted.current = lastSeq;
      markRead(id, lastSeq)
        .then((r) => {
          if (typeof r?.unread_total === "number") qc.setQueryData(msgKeys.unread, { unread_total: r.unread_total });
          void qc.invalidateQueries({ queryKey: ["messages", "list"] });
        })
        .catch(() => { posted.current = 0; });
    };
    go();
    document.addEventListener("visibilitychange", go);
    return () => document.removeEventListener("visibilitychange", go);
  }, [id, lastSeq, qc]);

  const putMessage = (m: Message) => {
    qc.setQueryData<ConversationView>(key, (old) => {
      if (!old) return old;
      const has = old.messages.some((x) => x.id === m.id);
      return { ...old, messages: has ? old.messages.map((x) => (x.id === m.id ? m : x)) : [...old.messages, m] };
    });
    setOlder((o) => o.map((x) => (x.id === m.id ? m : x)));
  };
  const putConversation = (row: ConversationRow) => {
    qc.setQueryData<ConversationView>(key, (old) => (old ? { ...old, conversation: row } : old));
    void qc.invalidateQueries({ queryKey: ["messages", "list"] });
  };

  const send = async ({ text, link, mentions }: ComposerSend) => {
    try {
      const r = await sendMessage(id, text, link, mentions);
      atBottom.current = true;
      putMessage(r.message);
      void qc.invalidateQueries({ queryKey: ["messages", "list"] });
      return true;
    } catch (e) {
      notify.error(messagesError(e, "Could not send. Try again."));
      return false;
    }
  };
  const react = async (m: Message, kind: ReactionKind) => {
    const mineKinds = REACTIONS.map((r) => r.kind).filter((k) => m.reactions[k]?.includes(me));
    try {
      if (mineKinds.includes(kind)) {
        // The server removes all of my reactions on a message at once (emoji null); the others I had are put back.
        let r = await reactTo(id, m.id, null);
        for (const k of mineKinds) if (k !== kind) r = await reactTo(id, m.id, k);
        putMessage(r.message);
      } else {
        putMessage((await reactTo(id, m.id, kind)).message);
      }
    } catch (e) { notify.error(messagesError(e)); }
  };
  const edit = async (m: Message, text: string) => {
    try { putMessage((await editMessage(id, m.id, text)).message); return true; } catch (e) { notify.error(messagesError(e)); return false; }
  };
  const remove = async (m: Message) => {
    try { putMessage((await deleteMessage(id, m.id)).message); void qc.invalidateQueries({ queryKey: ["messages", "list"] }); }
    catch (e) { notify.error(messagesError(e)); throw e; }
  };
  const toggleResolved = async () => {
    setBusy("resolve");
    try { putConversation((await setResolved(id, !c.resolved)).conversation); announce(c.resolved ? "Reopened" : "Marked as resolved"); }
    catch (e) { notify.error(messagesError(e)); } finally { setBusy(""); }
  };
  const toggleMuted = async () => {
    setBusy("mute");
    try { putConversation((await setMuted(id, !c.muted)).conversation); announce(c.muted ? "Unmuted" : "Muted: no bell or phone alert for this conversation"); }
    catch (e) { notify.error(messagesError(e)); } finally { setBusy(""); }
  };
  const loadOlder = async () => {
    const first = messages[0];
    if (!first) return;
    setMoreBusy(true);
    try {
      const r = await getConversation(id, first.seq);
      setOlder((o) => [...r.messages.filter((x) => !o.some((y) => y.id === x.id)), ...o]);
      setHasMore(r.has_more);
    } catch (e) { notify.error(messagesError(e, "Could not load the earlier messages.")); } finally { setMoreBusy(false); }
  };

  const actions = (
    <div className="flex shrink-0 items-center gap-1">
      <Button type="button" variant={c.resolved ? "outline" : "ghost"} size={phone ? "icon-sm" : "sm"} onClick={() => void toggleResolved()} disabled={busy === "resolve"}
        data-testid="resolve" aria-label={c.resolved ? "Reopen" : "Mark as resolved"} title={c.resolved ? "Reopen" : "Mark as resolved"}>
        {c.resolved ? <RotateCcw className="size-4" aria-hidden /> : <CheckCircle2 className="size-4" aria-hidden />}
        {phone ? null : c.resolved ? "Reopen" : "Mark as resolved"}
      </Button>
      <Button type="button" variant="ghost" size={phone ? "icon-sm" : "sm"} onClick={() => void toggleMuted()} disabled={busy === "mute"}
        data-testid="mute" aria-label={c.muted ? "Unmute" : "Mute"} title={c.muted ? "Unmute" : "Mute"}>
        {c.muted ? <Bell className="size-4" aria-hidden /> : <BellOff className="size-4" aria-hidden />}
        {phone ? null : c.muted ? "Unmute" : "Mute"}
      </Button>
    </div>
  );

  const title = <ThreadTitle kind={c.kind} title={c.title} subtitle={c.subtitle} presence={c.kind === "direct" ? presence : undefined} />;
  const header = phone ? (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between gap-2"><BackToMessages />{actions}</div>
      {title}
    </div>
  ) : <div className="flex items-center gap-3">{title}{actions}</div>;

  return (
    <ThreadFrame phone={phone} label={`Conversation with ${c.title}`} header={header}
      composer={
        <>
          {typing ? <p data-testid="typing" className="pb-1 text-xs italic text-muted-foreground" aria-live="polite">{typing.by_name} is typing</p> : null}
          {c.resolved ? (
            <p className="flex flex-wrap items-center gap-1.5 pb-1.5 text-xs text-muted-foreground">
              <Pill tone="ok">Resolved</Pill>
              <span>by {c.resolved.by === me ? "you" : c.resolved.by_name}. A new message reopens it.</span>
            </p>
          ) : null}
          <Composer key={id} conversationId={id} readers={view.readers} me={me} initialLink={initialLink} onSend={send} />
        </>
      }>
      {!view.notice_seen ? <div className="shrink-0 px-3 pt-3 lg:px-4"><Notice days={view.retention_days} /></div> : null}
      <div ref={listRef} role="log" aria-label="Messages" data-testid="message-list"
        onScroll={() => { const el = listRef.current; if (el) atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 32; }}
        className="scroll-thin min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 py-3 lg:px-4">
        {hasMore ? (
          <div className="mb-2 flex justify-center">
            <Button type="button" variant="ghost" size="sm" onClick={() => void loadOlder()} disabled={moreBusy}>
              {moreBusy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : null}Show earlier messages
            </Button>
          </div>
        ) : null}
        {!messages.length ? <p className="py-6 text-center text-sm text-muted-foreground">No messages yet.</p> : groupDays(messages).map((day) => (
          <section key={day.key} aria-label={day.label} className="pb-2">
            <h3 className="sticky top-0 z-[1] mx-auto mb-3 mt-2 w-fit rounded-full border border-border bg-card px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">{day.label}</h3>
            <ol className="space-y-2">
              {day.items.map((m) => (
                <MessageItem key={m.id} m={m} me={me} kind={c.kind} names={names} seen={m.id === seenId}
                  onReact={(mm, k) => void react(mm, k)} onEdit={edit} onDelete={setToDelete} />
              ))}
            </ol>
          </section>
        ))}
      </div>
      <ConfirmDialog open={!!toDelete} onOpenChange={(o) => { if (!o) setToDelete(null); }} title="Delete this message?" destructive confirmText="Delete" doneText="Deleted"
        text={'Everyone in the conversation will see "This message was deleted". The activity log keeps that you deleted it.'}
        onConfirm={async () => { if (toDelete) await remove(toDelete); }} />
    </ThreadFrame>
  );
}
