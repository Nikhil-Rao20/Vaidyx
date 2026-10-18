// Browser push: the service worker (public/sw.js, served at /static/tb-nik/sw.js) shows the text the server sends.
// The subscription goes to POST /push/subscribe with the VAPID key from GET /push/key. Everything here is same-origin.
import { api } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import type { PushKey } from "@/lib/types";

export const SW_URL = "/static/tb-nik/sw.js";

export type PushState = "unsupported" | "blocked" | "off" | "on";

export function pushSupported(): boolean {
  return typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

export function permissionState(): NotificationPermission | "unsupported" {
  if (!pushSupported()) return "unsupported";
  return Notification.permission;
}

function urlBase64ToUint8Array(base64: string): Uint8Array<ArrayBuffer> {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const b64 = (base64 + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(b64);
  const out = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

export async function registerServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (!pushSupported()) return null;
  try {
    const reg = await navigator.serviceWorker.register(SW_URL);
    return reg;
  } catch {
    return null;
  }
}

export async function currentSubscription(): Promise<PushSubscription | null> {
  if (!pushSupported()) return null;
  try {
    const reg = await navigator.serviceWorker.getRegistration(SW_URL);
    if (!reg) return null;
    return await reg.pushManager.getSubscription();
  } catch {
    return null;
  }
}

export async function pushState(): Promise<PushState> {
  if (!pushSupported()) return "unsupported";
  if (Notification.permission === "denied") return "blocked";
  const sub = await currentSubscription();
  return sub ? "on" : "off";
}

/** Ask the browser, subscribe, tell the server. Throws an Error with a plain message when a step fails. */
export async function subscribePush(): Promise<PushSubscription> {
  if (!pushSupported()) throw new Error("This browser cannot show push notifications.");
  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error("Notifications are blocked for this site. Allow them in the browser's site settings and try again.");
  const reg = (await registerServiceWorker()) ?? (await navigator.serviceWorker.ready);
  const key = await api.get<PushKey>(EP.pushKey);
  if (!key?.public_key) throw new Error("The server has no push key yet.");
  const existing = await reg.pushManager.getSubscription();
  const sub = existing ?? (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(key.public_key) }));
  await api.post(EP.pushSubscribe, { subscription: sub.toJSON() });
  return sub;
}

export async function unsubscribePush(): Promise<void> {
  const sub = await currentSubscription();
  if (!sub) return;
  try { await api.del(EP.pushSubscribe, { endpoint: sub.endpoint }); } catch { /* the server copy may already be gone */ }
  await sub.unsubscribe();
}
