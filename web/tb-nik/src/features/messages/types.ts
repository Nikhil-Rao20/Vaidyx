// The shapes of the Messages routes (night-v3 Phase 8, contract docs/night-v3/research/06_messages.md section 9.2, 9.3 and 9.6).
// Every text here is the sender's own words, shown as text (never as HTML).

export type ConversationKind = "direct" | "department" | "coordinator";
export type ConversationFilter = "all" | "unread" | "open" | "resolved";
export type ReactionKind = "thumbs_up" | "seen" | "thanks" | "will_do" | "tick";
export type Presence = "online" | "away" | "offline";

/** A Case File or meeting attached to a message, as this reader may see it (computed per reader at read time). */
export interface Chip {
  type: "case" | "meeting";
  id: string;
  /** "TB-2026-0042, Breast cancer" when the reader may open it, else null. */
  label: string | null;
  can_open: boolean;
  /** The reader may open it with a reason (break-glass) through the normal Case File route. */
  offer: boolean;
}

/** What the sender attaches: the id only. */
export interface LinkRef { type: "case" | "meeting"; id: string }

export interface Message {
  id: string;
  seq: number;
  ts: string;
  by: string;
  by_name: string;
  text: string;
  link: Chip | null;
  mentions: string[];
  edited: boolean;
  edited_ts: string | null;
  deleted: boolean;
  removed: boolean;
  reactions: Partial<Record<ReactionKind, string[]>>;
  /** Own message, within the 10 minutes: until when it may be edited or deleted; else null. */
  can_edit_until: string | null;
}

export interface ConversationRow {
  id: string;
  kind: ConversationKind;
  /** The other person's name, the department's name or "MDT Coordinator". */
  title: string;
  /** Person: title and departments; department: "Reaches N people" or "From Dr X"; coordinator: "Reaches N coordinators". */
  subtitle: string;
  /** `online` is true only when online; `presence` is the word ("online", "away", "offline", review 9 C, I4). */
  with: { user: string; display_name: string; title?: string; departments: string[]; online: boolean | Presence; presence?: Presence } | null;
  department: { id: string; name: string; members: number } | null;
  created_by: string;
  last: { seq: number; ts: string; by: string; by_name: string; preview: string } | null;
  unread: number;
  resolved: { by: string; by_name: string; ts: string } | null;
  muted: boolean;
}

export interface ConversationList { conversations: ConversationRow[]; unread_total: number }

export interface ConversationView {
  conversation: ConversationRow;
  messages: Message[];
  has_more: boolean;
  readers: Array<{ user: string; display_name: string }>;
  /** Direct only: the partner's last read seq ("Seen"). */
  seen_seq: number | null;
  notice_seen: boolean;
  /** The hospital's retention setting in days (0 keeps every message), for the first-use notice. */
  retention_days?: number;
}

export interface SearchHit { conversation_id: string; title: string; message: Message }

export interface DirectoryPerson {
  user: string;
  display_name: string;
  title: string;
  departments: Array<{ id: string; name: string; role: "Head" | "Consultant" | "Resident" | string }>;
  coordinator: boolean;
  online: Presence | boolean;
  photo: string | null;
  phone: string | null;
}

export interface DirectoryDepartment { id: string; name: string; group: string; members: number }

export interface DirectoryResponse {
  people: DirectoryPerson[];
  departments: DirectoryDepartment[];
  coordinators: DirectoryPerson[];
  me: string;
}

export interface LinkOption { id: string; label: string }
export interface LinksResponse { cases: LinkOption[]; meetings: LinkOption[] }

/** Who a new conversation goes to (POST /messages/conversations). */
export type MessageTarget = { user: string } | { department: string } | { role: "coordinator" };

/** A chosen attachment in the composer (the id is sent; the label is only for the chip on screen). */
export interface PickedLink { type: "case" | "meeting"; id: string; label: string }
