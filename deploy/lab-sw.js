/* SW TURF LAB service worker — network-first（データ命のアプリなので常に最新優先・落ちたらキャッシュ） */
const C = "swturflab-v5";
self.addEventListener("install", e => { self.skipWaiting(); });
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== C).map(k => caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  const u = new URL(e.request.url);
  // API/プロキシ/オッズはキャッシュしない（常にネット）
  if (/predictions\.php|results\.php|kaiko\.php|proxy\.php|netkeiba|api_get_/.test(u.href)) return;
  e.respondWith(
    fetch(e.request).then(r => {
      if (r && r.ok && u.origin === location.origin) { const cp = r.clone(); caches.open(C).then(c => c.put(e.request, cp)); }
      return r;
    }).catch(() => caches.match(e.request))
  );
});
