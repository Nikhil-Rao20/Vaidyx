/* Vaidyx-TB service worker: browser push only (no offline cache, no fetch handler).
   The server sends {title, body, kind, url}; the text never carries a UHID or a patient's name.
   A click focuses an open Vaidyx-TB tab, or opens one at the url given (same origin only). */

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = { body: event.data ? event.data.text() : "" };
  }
  const title = typeof data.title === "string" && data.title ? data.title : "Vaidyx-TB";
  const body = typeof data.body === "string" ? data.body : "You have something new.";
  const url = typeof data.url === "string" && data.url.startsWith("/") ? data.url : "/tb-nik/home";
  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon: "/static/tb-nik/favicon.svg",
      badge: "/static/tb-nik/favicon.svg",
      tag: typeof data.kind === "string" ? data.kind : "vaidyx-tb",
      renotify: true,
      data: { url },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL((event.notification.data && event.notification.data.url) || "/tb-nik/home", self.location.origin);
  if (target.origin !== self.location.origin) return;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      for (const c of list) {
        if (new URL(c.url).pathname.startsWith("/tb-nik") && "focus" in c) {
          if ("navigate" in c && target.pathname !== "/tb-nik") c.navigate(target.href).catch(() => {});
          return c.focus();
        }
      }
      return self.clients.openWindow(target.href);
    }),
  );
});
