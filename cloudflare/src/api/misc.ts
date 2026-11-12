/* error_log / errlog_view / stats / stats_view / line_push / cleanup / unzip の置き換え */
import {
  Ctx, CORS, JSON_CT, NO_STORE, json, resp, q, readJson, isObj, phpStr, dateC, ymd, his, sha256, htmlEsc,
  mbSub, mbLen,
} from '../lib';

const ymdAgo = (i: number) => ymd(Date.now() - i * 86400e3);
const nf = (n: number) => n.toLocaleString('en-US');

/* ============================== error_log.php ============================== */
const MAX_LINES_PER_DAY = 500;
export async function errorLog(c: Ctx): Promise<Response> {
  const { env, req } = c;
  const H = { 'Content-Type': 'application/json', 'Cache-Control': NO_STORE };
  const done = (ok: boolean) => resp(JSON.stringify({ ok }), 200, H);
  if (req.method !== 'POST') return done(false);
  const data = await readJson(req, 8192);
  if (!isObj(data) && !Array.isArray(data)) return done(false);
  const d = (isObj(data) ? data : {}) as Record<string, unknown>;
  const clip = (s: unknown, len: number) => {
    let v = typeof s === 'string' ? s : '';
    v = v.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g, '').replace(/\r\n|\r/g, '\n');
    return mbSub(v, len);
  };
  const entry = {
    t: dateC(), page: clip(d.page, 200), msg: clip(d.msg, 500), stack: clip(d.stack, 2000),
    ua: clip(req.headers.get('user-agent') ?? '', 200),
  };
  if (entry.page === '' || entry.msg === '') return done(false);
  const day = ymd();
  const n = await env.DB.prepare('SELECT COUNT(*) AS n FROM js_errors WHERE site=? AND day=?').bind(c.site, day).first<{ n: number }>();
  if ((n?.n ?? 0) >= MAX_LINES_PER_DAY) return done(false);
  await env.DB.prepare('INSERT INTO js_errors(site,day,body) VALUES(?,?,?)').bind(c.site, day, JSON.stringify(entry)).run();
  return done(true);
}

/* ============================== errlog_view.php ============================== */
export async function errlogView(c: Ctx): Promise<Response> {
  const { env, url } = c;
  const dq = q(url, 'days');
  const days = dq !== undefined ? Math.max(1, Math.min(30, parseInt(dq, 10) || 0)) : 7;
  const dayList = Array.from({ length: days }, (_, i) => ymdAgo(i));
  const rs = await env.DB.prepare(`SELECT day, body FROM js_errors WHERE site=? AND day IN (${dayList.map(() => '?').join(',')}) ORDER BY id`)
    .bind(c.site, ...dayList).all<{ day: string; body: string }>();
  // PHPは今日→過去の順に日ファイルを読む
  const byDay = new Map<string, string[]>();
  for (const r of rs.results) { if (!byDay.has(r.day)) byDay.set(r.day, []); byDay.get(r.day)!.push(r.body); }
  const byMsg = new Map<string, { n: number; pages: Set<string>; first: string; last: string; stack: string }>();
  let total = 0;
  for (const d of dayList) {
    for (const line of byDay.get(d) ?? []) {
      let e: Record<string, unknown>;
      try { e = JSON.parse(line); } catch { continue; }
      if (!isObj(e) || e.msg === undefined || e.msg === null) continue;
      total++;
      const key = phpStr(e.msg);
      if (!byMsg.has(key)) byMsg.set(key, { n: 0, pages: new Set(), first: phpStr(e.t ?? ''), last: phpStr(e.t ?? ''), stack: phpStr(e.stack ?? '') });
      const m = byMsg.get(key)!;
      m.n++; m.pages.add(phpStr(e.page ?? '')); m.last = e.t !== undefined && e.t !== null ? phpStr(e.t) : m.last;
    }
  }
  const list = [...byMsg].sort((a, b) => b[1].n - a[1].n);
  let html = `<!doctype html><meta charset="utf-8"><title>JSエラー — カジ競馬（運営用）</title>
<meta name="robots" content="noindex,nofollow">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{background:#0a0e16;color:#fff;font-family:"Noto Sans JP",sans-serif;
  font-size:15px;line-height:1.7;margin:0;padding:20px}
h1{font-size:24px}
.big{font-size:30px;font-weight:700;color:${total ? '#ff7171' : '#51b883'}}
.note{color:#b3b3b3}
.card{background:#12161f;border:1px solid #262b38;border-radius:10px;padding:14px 16px;margin:12px 0}
.card .msg{font-family:"Space Mono",monospace;font-size:14px;color:#ffd43d;word-break:break-all}
.card .meta{color:#b3b3b3;font-size:13px;margin-top:6px}
.card .pages{color:#7ec8f0;font-size:13px;margin-top:4px;word-break:break-all}
.card details{margin-top:8px}
.card pre{white-space:pre-wrap;word-break:break-all;font-size:12px;color:#b3b3b3;
  background:#0a0e16;padding:8px;border-radius:6px;max-height:200px;overflow-y:auto}
</style>
<h1>JSエラー（直近${days}日）</h1>
<p><span class="big">${nf(total)}</span> 件 / ${byMsg.size}種類</p>
<p class="note">error_log.phpが受け取ったクライアント側の例外。1日あたり最大500件まで記録（それ以上は捨てる）。<br>
Cookieなし・IP非保存。エラーメッセージの内容ごとにまとめて表示（多い順）。</p>

`;
  if (!list.length) html += '<p class="note">この期間、記録されたエラーはありません。</p>\n';
  for (const [msg, info] of list) {
    html += `<div class="card">
  <div class="msg">${htmlEsc(msg)}</div>
  <div class="meta">
    ${nf(info.n)}件 ／ 最初 ${htmlEsc(info.first)} ／ 最後 ${htmlEsc(info.last)}
  </div>
  <div class="pages">発生ページ: ${htmlEsc([...info.pages].join(' , '))}</div>
${info.stack ? `  <details><summary>スタックトレース（代表1件）</summary><pre>${htmlEsc(info.stack)}</pre></details>\n` : ''}</div>
`;
  }
  return resp(html, 200, { 'Content-Type': 'text/html; charset=UTF-8', 'Cache-Control': NO_STORE, Pragma: 'no-cache' });
}

/* ============================== stats.php ============================== */
const GIF = Uint8Array.from(atob('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'), (ch) => ch.charCodeAt(0));
export async function stats(c: Ctx): Promise<Response> {
  const { env, req, url } = c;
  const out = resp(GIF, 200, { 'Content-Type': 'image/gif', 'Cache-Control': NO_STORE, Pragma: 'no-cache' });
  c.exec.waitUntil((async () => {
    let path = (q(url, 'p') ?? '').replace(/[^0-9a-zA-Z/_\-.?=&]/g, '');
    path = mbSub(path, 120);
    if (path === '' || path[0] !== '/') return;
    const ref = q(url, 'r') ?? '';
    let refHost = '';
    if (ref !== '') { try { refHost = new URL(ref).hostname.replace(/[^0-9a-zA-Z.\-]/g, ''); } catch { /* noop */ } }
    if (refHost === '') refHost = 'direct';
    // PHP版と同じ判定（labは lab_transform で 'seventh-well.com/lab' に置換されていた）
    const own = c.site === 'lab' ? 'seventh-well.com/lab' : 'kajikeiba.com';
    if (refHost.includes(own)) refHost = 'internal';
    const ua = req.headers.get('user-agent') ?? '';
    if (/bot|crawler|spider|slurp|bingpreview|facebookexternalhit/i.test(ua)) return;
    const device = /iPhone|Android|Mobile/i.test(ua) ? 'sp' : 'pc';
    const ip = req.headers.get('cf-connecting-ip') ?? '';
    const salt = ymd() + '|kajikeiba|' + c.site;
    const vid = (await sha256(salt + ip + device)).slice(0, 12);
    await env.DB.prepare('INSERT INTO pv(site,day,t,path,ref,dev,vid) VALUES(?,?,?,?,?,?,?)')
      .bind(c.site, ymd(), his(), path, refHost, device, vid).run();
  })().catch((e) => console.error('stats', e)));
  return out;
}

/* ============================== stats_view.php ============================== */
export async function statsView(c: Ctx): Promise<Response> {
  const { env, url } = c;
  const dq = q(url, 'days');
  const days = dq !== undefined ? Math.max(1, Math.min(90, parseInt(dq, 10) || 0)) : 14;
  const dayList = Array.from({ length: days }, (_, i) => ymdAgo(i));
  const byDay = new Map<string, [number, number]>();
  for (const d of dayList) byDay.set(d, [0, 0]);
  const byPath = new Map<string, number>(); const byRef = new Map<string, number>(); const byDev = new Map<string, number>();
  const inc = (m: Map<string, number>, k: string, n: number) => m.set(k, (m.get(k) ?? 0) + n);
  const oldest = dayList[dayList.length - 1];
  const a = await env.DB.prepare('SELECT day, COUNT(*) AS pv, COUNT(DISTINCT vid) AS u FROM pv WHERE site=? AND day>=? GROUP BY day').bind(c.site, oldest).all<{ day: string; pv: number; u: number }>();
  for (const r of a.results) if (byDay.has(r.day)) byDay.set(r.day, [r.pv, r.u]);
  for (const [col, m] of [['path', byPath], ['ref', byRef], ['dev', byDev]] as const) {
    const rs = await env.DB.prepare(`SELECT ${col} AS k, COUNT(*) AS n FROM pv WHERE site=? AND day>=? GROUP BY ${col}`).bind(c.site, oldest).all<{ k: string; n: number }>();
    for (const r of rs.results) inc(m, r.k, r.n);
  }
  const sortDesc = (m: Map<string, number>) => [...m].sort((x, y) => y[1] - x[1]);
  const totPv = [...byDay.values()].reduce((s, v) => s + v[0], 0);
  let search = 0;
  for (const [h, n] of byRef) if (/google|yahoo|bing|duckduckgo/i.test(h)) search += n;
  const ext = totPv - (byRef.get('internal') ?? 0);
  const e = htmlEsc;
  let html = `<!doctype html><meta charset="utf-8"><title>アクセス — カジ競馬（運営用）</title>
<meta name="robots" content="noindex,nofollow">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{background:#0a0e16;color:#fff;font-family:"Noto Sans JP",sans-serif;
  font-size:16px;line-height:1.7;margin:0;padding:20px}
h1{font-size:24px}h2{font-size:19px;margin-top:32px;border-left:4px solid #ffd43d;padding-left:10px}
table{border-collapse:collapse;width:100%;max-width:720px;margin:10px 0}
th,td{border-bottom:1px solid #333;padding:7px 8px;text-align:left}
th{color:#b3b3b3}td.n{text-align:right;font-variant-numeric:tabular-nums}
.big{font-size:30px;font-weight:700;color:#ffd43d}
.note{color:#b3b3b3}
</style>
<h1>アクセス（直近${days}日）</h1>
<p><span class="big">${nf(totPv)}</span> PV</p>
<p class="note">Cookieなし・IP非保存・クローラ除外。訪問者数は日ごとの概数。</p>

<h2>判断指標（docs/BUSINESS.md）</h2>
<table>
<tr><th>指標</th><th class="n">現在</th><th class="n">3か月後の目安</th></tr>
<tr><td>月間PV（直近${days}日から換算）</td>
    <td class="n">${nf(Math.round(totPv / days * 30))}</td><td class="n">30,000</td></tr>
<tr><td>検索流入の比率</td>
    <td class="n">${ext ? Math.round(100 * search / ext) : 0}%</td><td class="n">40%</td></tr>
</table>

<h2>日別</h2>
<table><tr><th>日付</th><th class="n">PV</th><th class="n">訪問者</th></tr>
`;
  for (const [d, [pv, u]] of byDay) html += `<tr><td>${e(d.slice(0, 4) + '-' + d.slice(4, 6) + '-' + d.slice(6, 8))}</td>\n<td class="n">${nf(pv)}</td><td class="n">${nf(u)}</td></tr>\n`;
  html += '</table>\n\n<h2>よく見られたページ</h2>\n<table><tr><th>パス</th><th class="n">PV</th></tr>\n';
  for (const [p, n] of sortDesc(byPath).slice(0, 25)) html += `<tr><td>${e(p)}</td><td class="n">${nf(n)}</td></tr>\n`;
  html += '</table>\n\n<h2>流入元</h2>\n<table><tr><th>参照元</th><th class="n">PV</th></tr>\n';
  for (const [p, n] of sortDesc(byRef).slice(0, 20)) html += `<tr><td>${e(p)}</td><td class="n">${nf(n)}</td></tr>\n`;
  html += '</table>\n\n<h2>端末</h2>\n<table><tr><th>端末</th><th class="n">PV</th></tr>\n';
  for (const [p, n] of sortDesc(byDev)) html += `<tr><td>${e(p === 'sp' ? 'スマホ' : 'PC')}</td><td class="n">${nf(n)}</td></tr>\n`;
  html += '</table>';
  return resp(html, 200, { 'Content-Type': 'text/html; charset=UTF-8' });
}

/* ============================== line_push.php ============================== */
export async function linePush(c: Ctx): Promise<Response> {
  const { env, req } = c;
  const H = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'POST, OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type', 'Content-Type': JSON_CT };
  if (req.method === 'OPTIONS') return resp(null, 204, H);
  const j = (await readJson(req)) as Record<string, unknown> | null;
  const rid = phpStr(isObj(j) ? j.race_id ?? '' : '').replace(/[^0-9]/g, '');
  let text = phpStr(isObj(j) ? j.text ?? '' : '');
  if (rid === '' || text === '') return json({ ok: false, error: 'bad payload' }, 400, H);
  if (mbLen(text) > 1800) text = mbSub(text, 1800);
  const put = (name: string) => env.DB.prepare('INSERT OR REPLACE INTO line_outbox(name,text,at) VALUES(?,?,?)').bind(name, text, Math.floor(Date.now() / 1000)).run();

  // ★ドライラン★ 送らず outbox に残すだけ（送信済み印も付けない）
  if (isObj(j) && j.dry !== undefined && j.dry !== null && j.dry !== false && j.dry !== 0 && j.dry !== '' && j.dry !== '0') {
    await put(rid + '.dry.txt');
    return json({ ok: true, dry: true }, 200, H);
  }
  // 二重送信ガード
  const sent = await env.DB.prepare('SELECT 1 AS x FROM line_sent WHERE rid=?').bind(rid).first();
  if (sent) return json({ ok: true, dup: true }, 200, H);
  await put(rid + '.txt');
  const token = env.LINE_CHANNEL_TOKEN;
  if (!token) return json({ ok: false, reason: 'no_token', note: 'line_config.php 未設置。メッセージは line_outbox/ に保存した（ドライラン）' }, 200, H);
  let code = 0; let res = '';
  try {
    const r = await fetch('https://api.line.me/v2/bot/message/broadcast', {
      method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token },
      body: JSON.stringify({ messages: [{ type: 'text', text }] }), signal: AbortSignal.timeout(15000),
    });
    code = r.status; res = await r.text();
  } catch { code = 0; }
  if (code >= 200 && code < 300) {
    await env.DB.prepare('INSERT OR REPLACE INTO line_sent(rid,at) VALUES(?,?)').bind(rid, dateC()).run();
    return json({ ok: true }, 200, H);
  }
  return json({ ok: false, error: 'line api ' + code, body: res.slice(0, 300) }, 200, H);
}

/* ============================== cleanup.php ============================== */
/* 全部残す方針（36500日）。使用量の報告だけ D1 の実量で出す */
export async function cleanup(c: Ctx): Promise<Response> {
  const { env, url } = c;
  const run = url.searchParams.has('run');
  const T: [string, string, string][] = [
    ['odds_data', 'odds_snaps', 'body'], ['horse_data', 'horses', 'body'], ['jockey_data', 'jockeys', 'body'],
    ['result_data', 'results', 'body'], ['pred_data', 'predictions', "COALESCE(LENGTH(CAST(body AS BLOB)),LENGTH(body_gz))"], ['lock_data', 'locks', 'body'],
  ];
  const out: Record<string, unknown> = { run, dirs: {}, freedBytes: 0, deleted: 0 };
  let sizeAfter = 0;
  for (const [dir, table, col] of T) {
    const expr = col === 'body' ? 'LENGTH(CAST(body AS BLOB))' : col;
    const r = await env.DB.prepare(`SELECT COUNT(*) AS n, COALESCE(SUM(${expr}),0) AS b FROM ${table}`).first<{ n: number; b: number }>();
    let zero = 0;
    if (table === 'predictions') {
      const z = await env.DB.prepare("SELECT COUNT(*) AS n FROM predictions WHERE (body IS NULL OR body='') AND body_gz IS NULL").first<{ n: number }>();
      zero = z?.n ?? 0;
      if (run && zero) {
        const d = await env.DB.prepare("DELETE FROM predictions WHERE (body IS NULL OR body='') AND body_gz IS NULL").run();
        (out.deleted as number) += d.meta.changes ?? 0;
        (out as { deleted: number }).deleted = (out.deleted as number);
      }
    }
    (out.dirs as Record<string, unknown>)[dir] = {
      files: r?.n ?? 0, mb: Math.round(((r?.b ?? 0) / 1048576) * 10) / 10, deletable: zero, deletableMb: 0, zeroByte: zero,
    };
  }
  const meta = await env.DB.prepare('SELECT 1').run();
  sizeAfter = (meta.meta as { size_after?: number }).size_after ?? 0;
  const limitMb = 10240; // Workers Paid の D1 1つ上限（無料は500MB）
  out.diskFreeMb = Math.round((limitMb - sizeAfter / 1048576) * 10) / 10;
  return resp(JSON.stringify(out), 200, { 'Access-Control-Allow-Origin': '*', 'Content-Type': JSON_CT });
}

/* ============================== unzip.php / unzip_horse.php ============================== */
export async function unzipGone(): Promise<Response> {
  return resp('Cloudflare版では不要です（データはD1に直接入ります）。\n', 200, { 'Content-Type': 'text/plain; charset=utf-8' });
}

export { CORS };
