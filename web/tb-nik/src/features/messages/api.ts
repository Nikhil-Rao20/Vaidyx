// The fetch functions of Messages (contract section 9.3 and 9.6). The client never sends the sender or a time.
import { api, ApiError, TB } from "@/lib/api";
import { errorCode } from "@/lib/live";
import type {
  ConversationFilter, ConversationList, ConversationRow, ConversationView, DirectoryResponse, LinkRef, LinksResponse, Message,
  MessageTarget, ReactionKind, SearchHit,
} from "@/features/messages/types";

const enc = encodeURIComponent;
export const MESSAGES = `${TB}/messages`;
const conv = (id: string) => `${MESSAGES}/conversations/${enc(id)}`;
const msg = (id: string, mid: string) => `${conv(id)}/messages/${enc(mid)}`;

function qs(params: Record<string, string | number | undefined | null>): string {
  const s = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "").map(([k, v]) => [k, String(v)])).toString();
  return s ? `?${s}` : "";
}

export const listConversations = (filter: ConversationFilter, q = "") => api.get<ConversationList>(`${MESSAGES}/conversations${qs({ filter, q })}`);
export const getConversation = (id: string, before?: number) => api.get<ConversationView>(`${conv(id)}${qs({ before })}`);
export const startConversation = (to: MessageTarget, text: string, link?: LinkRef | null, mentions?: string[]) =>
  api.post<{ conversation: ConversationRow; message: Message }>(`${MESSAGES}/conversations`, { to, text, ...(link ? { link } : {}), ...(mentions?.length ? { mentions } : {}) });
export const sendMessage = (id: string, text: string, link?: LinkRef | null, mentions?: string[]) =>
  api.post<{ message: Message }>(`${conv(id)}/messages`, { text, ...(link ? { link } : {}), ...(mentions?.length ? { mentions } : {}) });
export const editMessage = (id: string, mid: string, text: string) => api.patch<{ message: Message }>(msg(id, mid), { text });
export const deleteMessage = (id: string, mid: string) => api.del<{ message: Message }>(msg(id, mid));
export const reactTo = (id: string, mid: string, emoji: ReactionKind | null) => api.post<{ message: Message }>(`${msg(id, mid)}/react`, { emoji });
export const setResolved = (id: string, resolved: boolean) => api.post<{ conversation: ConversationRow }>(`${conv(id)}/resolve`, { resolved });
export const markRead = (id: string, seq: number) => api.post<{ unread_total: number }>(`${conv(id)}/read`, { seq });
export const setMuted = (id: string, muted: boolean) => api.post<{ conversation: ConversationRow }>(`${conv(id)}/mute`, { muted });
export const searchMessages = (q: string) => api.get<{ hits: SearchHit[] }>(`${MESSAGES}/search${qs({ q })}`);
export const getUnread = () => api.get<{ unread_total: number }>(`${MESSAGES}/unread`);
export const getLinks = (q = "") => api.get<LinksResponse>(`${MESSAGES}/links${qs({ q })}`);
export const markNoticeSeen = () => api.post<{ notice_seen: boolean }>(`${MESSAGES}/notice`, {});
export const getDirectory = (q = "", department = "") => api.get<DirectoryResponse>(`${TB}/directory${qs({ q, department })}`);

/** The server's words for the refusals of section 9.3 (used when an answer carries a code but no message of its own). */
const WORDS: Record<string, string> = {
  rate_limited: "Too many messages. Please wait a moment.",
  edit_window_over: "You can only edit a message for 10 minutes.",
  cannot_reach: "That person cannot be reached.",
  self_message: "You cannot message yourself.",
  link_not_allowed: "You can only attach a Case File you can open.",
  too_long: "A message can have at most 2000 characters.",
  empty: "Write a message first.",
  not_found: "No such conversation.",
  not_placed: "Messages are for placed hospital staff.",
  bad_reaction: "That reaction is not one of the five.",
};

/** The client's own words for a status when the server sent none (lib/api.ts messageFor); never shown when a code is known. */
const DEFAULTS = new Set([
  "The request was not understood.", "You do not have permission for this.", "Not found.", "This clashes with the current state.",
  "Too many attempts. Please wait a moment.", "Something went wrong.",
]);

/** The words to show for a failed Messages call: the server's own message first, then the contract's words for its code. */
export function messagesError(e: unknown, fallback = "Could not do that. Try again."): string {
  const code = errorCode(e);
  if (e instanceof ApiError) {
    if (e.message && !DEFAULTS.has(e.message)) return e.message;
    if (e.status === 429) return WORDS.rate_limited;
    return WORDS[code] ?? e.message ?? fallback;
  }
  return WORDS[code] ?? fallback;
}
