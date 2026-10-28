// The React Query keys and queries of Messages. Every key starts with "messages" (or "directory"), so invalidating
// ["messages"] refreshes the list, the open conversation, the unread count and the search together.
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "@/lib/api";
import {
  getConversation, getDirectory, getLinks, getUnread, listConversations, searchMessages,
} from "@/features/messages/api";
import type { ConversationFilter } from "@/features/messages/types";

export const msgKeys = {
  all: ["messages"] as const,
  list: (filter: ConversationFilter, q = "") => ["messages", "list", filter, q] as const,
  conversation: (id: string) => ["messages", "c", id] as const,
  unread: ["messages", "unread"] as const,
  search: (q: string) => ["messages", "search", q] as const,
  links: (q: string) => ["messages", "links", q] as const,
  directory: (q: string) => ["directory", q] as const,
};

/** The fallback poll when the live socket is down (the bell polls at the same pace). */
export const POLL_MS = 45_000;

/** No retry on a refusal (400, 401, 403, 404): it would only be refused again. */
function retry(count: number, err: unknown): boolean {
  if (err instanceof ApiError && [400, 401, 403, 404, 429].includes(err.status)) return false;
  return count < 1;
}

export function useConversations(filter: ConversationFilter = "all", q = "", enabled = true) {
  return useQuery({ queryKey: msgKeys.list(filter, q), queryFn: () => listConversations(filter, q), retry, refetchInterval: POLL_MS, enabled });
}

export function useConversation(id: string | undefined) {
  return useQuery({ queryKey: msgKeys.conversation(id ?? ""), queryFn: () => getConversation(id ?? ""), retry, enabled: !!id });
}

export function useMessagesUnread(enabled = true) {
  return useQuery({ queryKey: msgKeys.unread, queryFn: getUnread, retry, refetchInterval: POLL_MS, enabled });
}

export function useMessageSearch(q: string) {
  const t = q.trim();
  return useQuery({ queryKey: msgKeys.search(t), queryFn: () => searchMessages(t), retry, enabled: t.length >= 2, staleTime: 10_000 });
}

export function useLinks(q: string, enabled = true) {
  return useQuery({ queryKey: msgKeys.links(q.trim()), queryFn: () => getLinks(q.trim()), retry, enabled, staleTime: 30_000 });
}

export function useDirectory(q: string, enabled = true) {
  return useQuery({ queryKey: msgKeys.directory(q.trim()), queryFn: () => getDirectory(q.trim()), retry, enabled, staleTime: 30_000 });
}

/** The value after it stopped changing for `ms` (search boxes). */
export function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(t);
  }, [value, ms]);
  return v;
}
