/* ODDS ANOMALY — Service Worker
   方針:
   - アプリ本体(シェル)はキャッシュしてオフラインでも起動できるように
   - オッズ/出馬表/結果(netkeiba・プロキシ)と学習ログPHPは常に最新を取りに行く（キャッシュしない）
*/
// 2026-07-26: v425(単純カウンタ)からセマンティックバージョニングへ切替。
// 起点4.3.0は節目（初期MVP→GBM/人格導入→⭐フォメ/kochi独立→中央DB拡充、の4区切り目の途中）の目安。
// 以後はdeploy.pyが自動でパッチ番号だけ+1する。
const CACHE = "odds-anomaly-v4.3.66";
const SHELL = [
  "./",
  "./index.html",
  "./help.html",
  "./changelog.html",
  "./tweet.html",
  "./kochi.html",
  "./jusho.html",
  "./kaiko.html",
  "./news.html",
  "./manifest.json",
  "./icon-192.png",
  "./icon-512.png",
  "./apple-touch-icon.png"
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener("message", (e) => {
  if (e.data === "skipWaiting") self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  // 動的データ（プロキシ/netkeiba/各種PHP/外部API）は常にネットワーク優先・キャッシュしない。
  // ※ proxy.php を明示的に含めること。Base64化(?u=...)でURLから "netkeiba.com" の文字列が
  //    消えたため、これが無いとレース結果HTMLがキャッシュされ、発走前に取得した「結果なし」が
  //    確定後も返り続けて答え合わせが永久に「結果待ち」になる。
  const dynamic =
    /proxy\.php/.test(url.pathname) ||
    /netkeiba\.com/.test(url.href) ||
    /codetabs\.com|allorigins|corsproxy|thingproxy|workers\.dev/.test(url.href) ||
    /(oddslog|bias|predictions|results|kaiko|horse|jockey)\.php/.test(url.pathname) ||
    url.search.includes("action=");
  if (dynamic) {
    e.respondWith(fetch(req).catch(() => new Response("{}", { headers: { "Content-Type": "application/json" } })));
    return;
  }

  // 同一オリジン
  if (url.origin === self.location.origin) {
    const isShell = /\.(html?|js)$/.test(url.pathname) || url.pathname.endsWith("/") || url.pathname === "";
    if (isShell) {
      // HTML/JS は「ネットワーク優先」: 常に最新を取りに行き、成功したらキャッシュ更新。
      // オフライン時のみキャッシュにフォールバック。→ アップロードが即反映される。
      e.respondWith(
        fetch(req).then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
          return res;
        }).catch(() => caches.match(req).then((hit) => hit || caches.match("./index.html")))
      );
      return;
    }
    // 画像・アイコン等の静的アセットはキャッシュ優先（変わらないので高速化）
    e.respondWith(
      caches.match(req).then((hit) =>
        hit ||
        fetch(req).then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
          return res;
        })
      )
    );
    return;
  }

  // それ以外（フォント等）はネット優先、失敗時キャッシュ
  e.respondWith(fetch(req).catch(() => caches.match(req)));
});
