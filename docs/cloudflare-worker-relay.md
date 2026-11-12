# netkeiba中継 Cloudflare Worker（セットアップ手順）

## なぜ必要か
サーバーのIPがnetkeibaにブロックされると、サイトの予想が全部止まる（2026-07-21に発生）。
CloudflareのIPからnetkeibaを取りに行く「中継」をWorkerで作れば、
proxy.php が 直接→Worker→キャッシュ の3段構えになり、ブロックされても死ななくなる。
実測で CloudflareのようなデータセンターIPはnetkeibaに届く（r.jina.ai が200）ことを確認済み。

## 手順（5分）
1. https://dash.cloudflare.com にログイン
2. 左メニュー「Workers & Pages」→「Create」→「Create Worker」
3. 名前は何でもよい（例: `nk-relay`）→「Deploy」
4. 「Edit code」を開き、下のコードを**全部貼り替えて**「Deploy」
5. 表示されるURL（例: `https://nk-relay.あなたのサブドメイン.workers.dev`）を教えてください
   → proxy.php にフォールバック配線します

## Workerコード（これを貼る）

```js
// netkeiba中継 Worker: proxy.php のフォールバック用
// 使い方: /?u=<Base64URL(対象URL)>&t=<TOKEN>
const TOKEN = "sw-relay-4e8b2d6a";   // proxy.php 側と合わせる（漏れたら両方変える）

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.searchParams.get("t") !== TOKEN) {
      return new Response("forbidden", { status: 403 });
    }
    // Base64URL → URL
    let target = "";
    try {
      const b = url.searchParams.get("u") || "";
      const std = b.replace(/-/g, "+").replace(/_/g, "/");
      target = atob(std + "=".repeat((4 - std.length % 4) % 4));
    } catch (_) {}
    // netkeiba系のみ許可（乱用防止）
    if (!/^https:\/\/[a-z0-9.-]*\.(netkeiba|keeeeeeba)\.com\//i.test(target)) {
      return new Response("bad url", { status: 400 });
    }
    const r = await fetch(target, {
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,*/*",
        "Accept-Language": "ja,en;q=0.8",
        "Referer": "https://nar.netkeiba.com/",
      },
    });
    const body = await r.arrayBuffer();
    return new Response(body, {
      status: r.status,
      headers: {
        "Content-Type": r.headers.get("content-type") || "text/html; charset=UTF-8",
        "Access-Control-Allow-Origin": "*",
        "X-Relay": "cf-worker",
      },
    });
  },
};
```

## 配線後の動き（proxy.php 側は私が実装）
```
proxy.php → ①netkeiba直（回復すれば最速）
          → ②このWorker経由（ブロック時の自動迂回）
          → ③サーバーキャッシュ（最後の砦・実装済み）
```
無料枠は10万リクエスト/日。サイトの通常利用なら余裕。
バックテスト等の大量取得には**使わない**（Workerまで弾かれたら本末転倒）。
