/* Radar Fundamentalista B3 — Service Worker v1.0 */

const CACHE = "radar-b3-v1";
const STATIC_ASSETS = [
  "/dashboard.html",
  "/manifest.json",
  "/icons/icon.svg",
];

/* Install: cache core assets */
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

/* Activate: clean old caches */
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

/* Fetch: stale-while-revalidate for HTML, cache-first for assets */
self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  /* Skip non-GET and cross-origin */
  if (request.method !== "GET" || url.origin !== location.origin) return;

  /* Cache-first for static assets (icons, manifest) */
  if (STATIC_ASSETS.includes(url.pathname)) {
    event.respondWith(
      caches.open(CACHE).then((cache) =>
        cache.match(request).then((cached) => cached || fetchAndCache(request, cache))
      )
    );
    return;
  }

  /* Network-first for dashboard (always try fresh data) */
  if (url.pathname.endsWith("dashboard.html")) {
    event.respondWith(
      fetch(request)
        .then((res) => {
          const clone = res.clone();
          caches.open(CACHE).then((cache) => cache.put(request, clone));
          return res;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  /* Stale-while-revalidate for everything else (exports, etc.) */
  event.respondWith(
    caches.open(CACHE).then((cache) =>
      cache.match(request).then((cached) => {
        const fetchPromise = fetch(request)
          .then((res) => {
            cache.put(request, res.clone());
            return res;
          })
          .catch(() => cached);
        return cached || fetchPromise;
      })
    )
  );
});

function fetchAndCache(request, cache) {
  return fetch(request).then((res) => {
    cache.put(request, res.clone());
    return res;
  });
}
