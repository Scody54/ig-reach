// Minimal service worker: makes the site installable and shows a friendly offline page.
const CACHE = "igreach-v1";
const SHELL = ["/static/offline.html", "/static/icon-192.png"];
self.addEventListener("install", e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL))); self.skipWaiting(); });
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", e => {
  if (e.request.mode === "navigate") {
    e.respondWith(fetch(e.request).catch(() => caches.match("/static/offline.html")));
  }
});
