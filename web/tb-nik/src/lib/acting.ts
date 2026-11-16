// The hospital a Vaidyx admin is working inside ("acting in", docs/admin-console/DESIGN.md D4). Kept for this tab only
// (sessionStorage key tbnik.actingHospital) and sent as the header X-TB-Hospital on every /api/tb request, but only while the
// signed-in person is a Vaidyx admin: the server ignores the header from anyone else, and this side does not send it either.
// Cleared on sign-out and when the session ends. No React here: lib/api.ts reads it on every request.
import { useSyncExternalStore } from "react";

export const ACTING_KEY = "tbnik.actingHospital";
export const ACTING_HEADER = "X-TB-Hospital";

export interface ActingHospital {
  id: string;
  name: string;
}

function read(): ActingHospital | null {
  try {
    const raw = sessionStorage.getItem(ACTING_KEY);
    if (!raw) return null;
    const v = JSON.parse(raw) as Partial<ActingHospital>;
    return typeof v?.id === "string" && v.id ? { id: v.id, name: typeof v.name === "string" ? v.name : v.id } : null;
  } catch {
    return null;
  }
}

let current: ActingHospital | null = typeof window === "undefined" ? null : read();
// Until GET /me answers, a stored choice counts as made by a Vaidyx admin (only a Vaidyx admin can make one, in this tab);
// the session sets the real value as soon as it knows who is signed in.
let vaidyxAdmin = current !== null;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((f) => f());
}

export function actingHospital(): ActingHospital | null {
  return current;
}

/** The header for an /api/tb request: only for a Vaidyx admin with a hospital chosen. */
export function actingHeaders(): Record<string, string> {
  return vaidyxAdmin && current ? { [ACTING_HEADER]: current.id } : {};
}

/** Called by the session once GET /me answers. Anyone else never keeps a choice. */
export function setVaidyxAdmin(v: boolean) {
  vaidyxAdmin = v;
  if (!v && current) clearActing();
}

export function setActing(h: ActingHospital | null) {
  current = h ? { id: h.id, name: h.name || h.id } : null;
  try {
    if (current) sessionStorage.setItem(ACTING_KEY, JSON.stringify(current));
    else sessionStorage.removeItem(ACTING_KEY);
  } catch { /* storage blocked: the choice lives for this page only */ }
  if (current) vaidyxAdmin = true;
  emit();
}

export function clearActing() {
  setActing(null);
}

function subscribe(fn: () => void) {
  listeners.add(fn);
  return () => { listeners.delete(fn); };
}

/** The hospital being acted in, re-rendering when it changes. */
export function useActingHospital(): ActingHospital | null {
  return useSyncExternalStore(subscribe, actingHospital, () => null);
}
