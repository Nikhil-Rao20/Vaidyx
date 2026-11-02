// The live channel of Messages (contract section 9.5): one socket per signed-in person, shared by every component that mounts
// useMessagesLive() (the shell and the Messages page alike open it once). Events refresh the React Query caches; "typing" and
// "presence" live in a small store read only inside the Messages page. The list and the unread count also poll every 45 s,
// so a dead socket loses nothing.
import { useEffect, useSyncExternalStore } from "react";
import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { LiveClient, messagesWsUrl, type LiveEvent } from "@/lib/live";
import { useSession } from "@/lib/session";
import { msgKeys } from "@/features/messages/hooks";
import type { Presence } from "@/features/messages/types";

export interface Typing { by: string; by_name: string; at: number }

/** How long "<name> is typing" stays after the last typing event. */
export const TYPING_MS = 4000;
const TYPING_SEND_MS = 3000;
const ACTIVE_SEND_MS = 60_000;

// ---- the store (typing and presence) ------------------------------------------------------------------------------------
const typing = new Map<string, Typing>();
const presence = new Map<string, Presence>();
const listeners = new Set<() => void>();
const timers = new Map<string, number>();
function changed() { for (const l of listeners) l(); }
function subscribe(l: () => void) { listeners.add(l); return () => { listeners.delete(l); }; }

function setTyping(conv: string, t: Typing | null) {
  const old = timers.get(conv);
  if (old) window.clearTimeout(old);
  timers.delete(conv);
  if (t) {
    typing.set(conv, t);
    timers.set(conv, window.setTimeout(() => { typing.delete(conv); timers.delete(conv); changed(); }, TYPING_MS));
  } else typing.delete(conv);
  changed();
}

/** Who is typing in this conversation now (never me), or null. */
export function useTyping(conv: string | undefined): Typing | null {
  return useSyncExternalStore(subscribe, () => (conv ? typing.get(conv) ?? null : null), () => null);
}

/** The live presence of a person when the socket told one, else the value the list or the directory gave. */
export function usePresence(user: string | undefined, fallback?: Presence | boolean | null): Presence {
  const live = useSyncExternalStore(subscribe, () => (user ? presence.get(user) ?? null : null), () => null);
  if (live) return live;
  if (fallback === true) return "online";
  if (fallback === false || fallback == null) return "offline";
  return fallback;
}

// ---- the shared socket --------------------------------------------------------------------------------------------------
let client: LiveClient | null = null;
let users = 0;
let ctx: { qc: QueryClient; me: string } | null = null;
let lastActive = 0;
const lastTyping = new Map<string, number>();

function onEvent(ev: LiveEvent) {
  if (!ctx) return;
  const { qc, me } = ctx;
  const convId = String(ev.conversation_id ?? (ev.conversation as { id?: string } | undefined)?.id ?? "");
  switch (ev.type) {
    case "message": {
      const by = (ev.message as { by?: string } | undefined)?.by;
      if (convId && typing.get(convId)?.by === by) setTyping(convId, null);
      void qc.invalidateQueries({ queryKey: msgKeys.all });
      void qc.invalidateQueries({ queryKey: ["notifications"] });  // the bell item "New message from Dr X" shows at once, not at the next 45 s poll
      break;
    }
    case "edit": case "delete": case "react": case "resolve": case "read":
      if (convId) void qc.invalidateQueries({ queryKey: msgKeys.conversation(convId) });
      void qc.invalidateQueries({ queryKey: ["messages", "list"] });
      break;
    case "typing":
      if (convId && ev.by !== me) setTyping(convId, { by: String(ev.by ?? ""), by_name: String(ev.by_name ?? ev.by ?? "Someone"), at: Date.now() });
      break;
    case "presence":
      if (typeof ev.user === "string" && (ev.state === "online" || ev.state === "away" || ev.state === "offline")) { presence.set(ev.user, ev.state); changed(); }
      break;
    case "unread":
      if (typeof ev.total === "number") qc.setQueryData(msgKeys.unread, { unread_total: ev.total });
      break;
    default:
      break;
  }
}

function onActivity() {
  const now = Date.now();
  if (now - lastActive < ACTIVE_SEND_MS) return;
  if (client?.send({ type: "active" })) lastActive = now;
}

function acquire(qc: QueryClient, me: string) {
  ctx = { qc, me };
  users += 1;
  if (client) return;
  client = new LiveClient(messagesWsUrl(), {
    onEvent,
    // A fresh (re)connection: fetch again whatever was missed while the socket was down.
    onStatus: (s) => { if (s === "open" && ctx) void ctx.qc.invalidateQueries({ queryKey: msgKeys.all }); },
  });
  lastActive = Date.now();
  window.addEventListener("pointerdown", onActivity, { passive: true });
  window.addEventListener("keydown", onActivity, { passive: true });
  client.connect();
}

function release() {
  users = Math.max(0, users - 1);
  if (users || !client) return;
  client.close();
  client = null;
  ctx = null;
  window.removeEventListener("pointerdown", onActivity);
  window.removeEventListener("keydown", onActivity);
}

/** Tells the readers of this conversation that I am typing (at most once every 3 seconds). */
export function sendTyping(conv: string) {
  const now = Date.now();
  if (now - (lastTyping.get(conv) ?? 0) < TYPING_SEND_MS) return;
  if (client?.send({ type: "typing", conversation_id: conv })) lastTyping.set(conv, now);
}

/** Keeps the Messages socket open while the person is signed in and may use Messages. Safe to mount more than once. */
export function useMessagesLive(enabled = true) {
  const qc = useQueryClient();
  const { me } = useSession();
  const on = enabled && !!me?.messages;
  const user = me?.user ?? "";
  useEffect(() => {
    if (!on || !user) return;
    acquire(qc, user);
    return release;
  }, [on, user, qc]);
}
