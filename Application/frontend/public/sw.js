/*
 * The service worker, for push notifications only.
 *
 * Phase 0 item 5. It shows the reminders the server pushes and opens the app
 * when one is tapped. It has no fetch handler on purpose: it caches nothing and
 * intercepts no request, so the app behaves exactly as it does without it. Read-
 * only offline is a separate item and would be added here deliberately.
 */

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { title: event.data ? event.data.text() : "" };
  }
  event.waitUntil(
    self.registration.showNotification(data.title || "Account", {
      body: data.body || "",
      tag: data.tag,
      data: { url: data.url || "/" },
      icon: "/icon-192.png",
      badge: "/icon-192.png",
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  // Only ever a page of this site, whatever the payload says.
  let target = new URL("/", self.location.origin);
  try {
    const asked = new URL(event.notification.data?.url || "/", self.location.origin);
    if (asked.origin === self.location.origin) target = asked;
  } catch {
    // fall back to the home page
  }
  // Marks the visit as one a notification caused. The app's own universe test
  // needs a room visited unprompted, and counting these would let the metric
  // manufacture itself (account-vision.md §13.2). The app strips it on arrival.
  target.searchParams.set("from", "push");
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      for (const client of windows) {
        if (client.url.startsWith(self.location.origin) && "focus" in client) {
          return client.navigate(target.href).then((c) => (c || client).focus());
        }
      }
      return self.clients.openWindow(target.href);
    })
  );
});
