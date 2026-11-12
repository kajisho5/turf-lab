/* 無人運転の通し試験用ローカルサーバー
 *
 * ★なぜ要るか★
 *   デプロイ前の tweet.html（?auto=line 対応版）を通しで試したい。
 *   file:// では同一オリジンのPHP（proxy.php等）が呼べないので、
 *   ローカルで配信しつつ *.php だけ本番へ転送する。
 *
 *   静的: deploy/ と core/ をそのまま配る（＝ローカルの最新版が動く）
 *   PHP : https://seventh-well.com/odds/ へフォワード（本物のデータ・本物のdry保存）
 *
 * 使い方: node tools/line-runner/dev_proxy.js  → http://localhost:7877/tweet.html
 */
const http = require('http');
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..', '..');
const PORT = 7877;
const REMOTE = 'https://seventh-well.com/odds';
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
               '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8' };

http.createServer(async (req, res) => {
  const u = new URL(req.url, 'http://x');
  const p = decodeURIComponent(u.pathname);
  if (p.endsWith('.php')) {
    // 本番へフォワード（メソッド・ボディ・クエリ維持）
    try {
      const body = req.method === 'POST'
        ? await new Promise((ok) => { const c = []; req.on('data', (d) => c.push(d));
                                      req.on('end', () => ok(Buffer.concat(c))); })
        : undefined;
      const r = await fetch(REMOTE + p + u.search, {
        method: req.method,
        headers: { 'Content-Type': req.headers['content-type'] || 'application/json' },
        body,
      });
      const buf = Buffer.from(await r.arrayBuffer());
      res.writeHead(r.status, { 'Content-Type': r.headers.get('content-type') || 'text/plain' });
      res.end(buf);
    } catch (e) {
      res.writeHead(502); res.end('proxy error: ' + e.message);
    }
    return;
  }
  // 静的: /core/* はリポジトリの core/、それ以外は deploy/
  const base = p.startsWith('/core/') ? ROOT : path.join(ROOT, 'deploy');
  let f = path.normalize(path.join(base, p === '/' ? 'tweet.html' : p));
  if (!f.startsWith(path.normalize(ROOT))) { res.writeHead(403); return res.end(); }
  fs.readFile(f, (e, b) => {
    if (e) { res.writeHead(404); return res.end('404 ' + p); }
    res.writeHead(200, { 'Content-Type': MIME[path.extname(f)] || 'application/octet-stream',
                         'Cache-Control': 'no-store' });
    res.end(b);
  });
}).listen(PORT, () => console.log('dev proxy: http://localhost:' + PORT + '/tweet.html'));
