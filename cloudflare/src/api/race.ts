/* race.php（/race/{12桁}/ のサーバー側HTML）と sitemap.php の置き換え */
import { Ctx, Env, resp, htmlEsc, mbSub, nowSec, ymd } from '../lib';
import { directFetch, proxyGet } from './proxy';
import { pageCached } from './nar';
import { AV, JUSHO_KEYS, SITEMAP_URLS } from '../gen/meta';

const TTL_LIVE = 180;
const TTL_DONE = 86400;
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36';

/** 直接取得。失敗したら proxy.php と同じ中継（jina）を試す */
async function fetchPage(env: Env, url: string): Promise<string> {
  try {
    const r = await fetch(url, { headers: { 'User-Agent': UA, Accept: 'text/html,*/*', 'Accept-Language': 'ja,en;q=0.8' }, redirect: 'follow', signal: AbortSignal.timeout(20000) });
    const t = await r.text();
    if (r.ok && t.length > 200) return t;
  } catch { /* 下へ */ }
  try {
    const p = await proxyGet(env, url);
    if (p.status === 200) return await p.text();
  } catch { /* noop */ }
  return '';
}

const hasResultOf = (html: string) => html.includes('All_Result_Table') && /class="Result_Num"/.test(html);

function pick(html: string, cls: string): string {
  const re = new RegExp('class="[^"]*\\b' + cls.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\b[^"]*"[^>]*>([\\s\\S]*?)<', 'u');
  const m = html.match(re);
  return m ? strip(m[1]).replace(/\s+/gu, ' ').trim() : '';
}
const strip = (s: string) => s.replace(/<!--[\s\S]*?-->/g, '').replace(/<\/?[a-zA-Z!?][^>]*>/g, '');

/** "C2111213(C212)" → 「C2（十一）（十二）（十三）」。★core/race_app.js 等と同じ関数★ */
export function prettyRaceName(name: string): string {
  name = name.trim();
  const m = name.match(/^([A-D][1-3]|\d+歳)(\d{4,})(?:\([^)]*\))?$/u);
  if (!m) return name;
  if (m[2].length % 2) return name;
  const kdig = ['〇', '一', '二', '三', '四', '五', '六', '七', '八', '九'];
  const k = (n: number): string => {
    if (n < 10) return kdig[n];
    if (n < 20) return '十' + (n > 10 ? kdig[n - 10] : '');
    return kdig[Math.floor(n / 10)] + '十' + (n % 10 ? kdig[n % 10] : '');
  };
  let out = m[1];
  for (let i = 0; i < m[2].length; i += 2) {
    const gi = parseInt(m[2].slice(i, i + 2), 10);
    if (gi < 1 || gi > 25) return name;
    out += '（' + k(gi) + '）';
  }
  return out;
}

export async function racePage(c: Ctx, ridIn: string | null): Promise<Response> {
  const { env } = c;
  const rid = (ridIn ?? '').replace(/[^0-9]/g, '');
  if (rid.length !== 12) {
    return resp('<meta charset="utf-8"><title>レースが見つかりません — カジ競馬</title><p>レースが見つかりません。<a href="/">レース一覧へ</a></p>', 404,
      { 'Content-Type': 'text/html; charset=UTF-8' });
  }
  const jyo = parseInt(rid.slice(4, 6), 10);
  const isJra = jyo >= 1 && jyo <= 10;
  const host = isJra ? 'race.netkeiba.com' : 'nar.netkeiba.com';

  /* 結果ページ。確定済みのキャッシュは1日持つ（PHP版は意図に反して3分で取り直していた） */
  const resKey = `res_${rid}`;
  const old = await env.DB.prepare('SELECT body, at FROM page_cache WHERE k=?').bind(resKey).first<{ body: string; at: number }>();
  let result: string;
  if (old && old.body && hasResultOf(old.body) && nowSec() - old.at < TTL_DONE) result = old.body;
  else result = await pageCached(env, resKey, TTL_LIVE, () => fetchPage(env, `https://${host}/race/result.html?race_id=${rid}`));
  const hasResult = hasResultOf(result);
  const page = hasResult ? result
    : await pageCached(env, `card_${rid}`, TTL_LIVE, () => fetchPage(env, `https://${host}/race/shutuba.html?race_id=${rid}`));

  const raceName = prettyRaceName(pick(page, 'RaceName'));
  let raceNum = pick(page, 'RaceNum');
  if (raceNum === '') raceNum = parseInt(rid.slice(10, 12), 10) + 'R';
  const data01 = pick(page, 'RaceData01');
  const data02 = pick(page, 'RaceData02');

  type Row = { rank: string; waku: string; uma: string; name: string; jockey: string; time: string };
  const rows: Row[] = [];
  const rowRe = hasResult
    ? /<tr[^>]*>((?:(?!<\/tr>)[\s\S])*?class="Result_Num"[\s\S]*?)<\/tr>/gu
    : /<tr[^>]*class="[^"]*HorseList[^"]*"[^>]*>([\s\S]*?)<\/tr>/gu;
  for (const mm of page.matchAll(rowRe)) {
    const tr = mm[1];
    const hm = tr.match(/db\.netkeiba\.com\/horse\/\d+[^>]*>\s*(?:<[^>]+>)*\s*([^<]+)/u);
    if (!hm) continue;
    const name = hm[1].trim();
    if (name === '') continue;
    const tds = [...tr.matchAll(/<td[^>]*>([\s\S]*?)<\/td>/gu)].map((x) => x[1]);
    const cell = (i: number) => (tds[i] !== undefined ? strip(tds[i]).replace(/\s+/gu, ' ').trim() : '');
    rows.push(hasResult
      ? { rank: cell(0), waku: cell(1), uma: cell(2), name, jockey: pick(tr, 'Jockey'), time: cell(7) }
      : { rank: '', waku: cell(0), uma: cell(1), name, jockey: pick(tr, 'Jockey'), time: '' });
  }

  const pays: [string, string][] = [];
  if (hasResult) {
    const pm = page.match(/Payout_Detail_Table[\s\S]*?<\/table>/u);
    if (pm) {
      for (const pr of pm[0].matchAll(/<tr[^>]*>([\s\S]*?)<\/tr>/gu)) {
        const k = pr[1].match(/<th[^>]*>([\s\S]*?)<\/th>/u);
        if (!k) continue;
        const kind = strip(k[1]).trim();
        const p = pr[1].match(/class="Payout"[^>]*>([\s\S]*?)<\/td>/u);
        if (!p) continue;
        const yen = strip(p[1].replace(/<br\s*\/?>/gi, ' / ')).replace(/\s+/gu, ' ').trim();
        if (kind !== '' && yen !== '') pays.push([kind, yen]);
      }
    }
  }

  const e = htmlEsc;
  const title = ((raceNum ? `${raceNum} ` : '') + (raceName || 'レース')).trim();
  const where = `${data01} ${data02}`.trim();
  const kind = isJra ? '中央競馬' : '地方競馬';
  let desc = hasResult
    ? `${title}の結果と払戻。` + (rows.length ? `1着 ${rows[0].name}。` : '')
    : `${title}の出馬表。` + (rows.length ? `${rows.length}頭。` : '');
  desc += ` ${where}`;
  const av = (f: string) => { const h = (AV[c.site === 'lab' ? 'lab' : 'k'] as Record<string, string>)[f]; return h ? '?v=' + h : ''; };
  const jname = title.replace(/^\d+R\s*/u, '').trim();
  const jusho = jname !== '' && JUSHO_SET.has(jname);

  let h = `<!doctype html>
<html lang="ja">
<meta charset="utf-8">
<title>${e(title)}｜${e(kind)}の出馬表・結果 — カジ競馬</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="${e(mbSub(desc, 120))}">
<link rel="canonical" href="https://kajikeiba.com/race/${e(rid)}/">
<meta property="og:type" content="article">
<meta property="og:title" content="${e(title)}｜出馬表・結果">
<meta property="og:description" content="${e(mbSub(desc, 120))}">
<meta property="og:url" content="https://kajikeiba.com/race/${e(rid)}/">
<meta property="og:image" content="https://kajikeiba.com/data/ogp.png">
<meta name="twitter:card" content="summary_large_image">
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2591053009962162" crossorigin="anonymous"></script>
<link rel="stylesheet" href="/core/theme.css${av('theme.css')}">
<script src="/core/theme.js${av('theme.js')}"></script>
<script src="/core/table.js${av('table.js')}" defer></script>
<link rel="stylesheet" href="/core/race.css${av('race.css')}">
<header><div class="hbar">
  <a class="logo" href="/">カジ<span>競馬</span></a>
  <div style="flex:1"></div>
  <button class="themebtn" type="button" style="margin-right:10px">☾</button>
  <a href="/" style="text-decoration:none">← レース一覧</a>
</div></header>
<div class="wrap">
<div id="ssr">
  <h1>${e(title)}</h1>
  <p>${e(where)}</p>
`;
  if (jusho) {
    h += `    <p style="margin:4px 0 12px"><a href="/data/jusho/?r=${rawUrlEncode(jname)}"
       style="display:inline-block;border:1px solid var(--line);border-radius:8px;
       padding:6px 12px;text-decoration:none">📊 ${e(jname)}の過去データ（人気・枠・脚質）</a></p>
`;
  }
  if (rows.length) {
    h += `  <table>
    <tr>
      ${hasResult ? '<th>着順</th>' : ''}
      <th>枠</th><th>馬番</th><th>馬名</th><th>騎手</th>
      ${hasResult ? '<th>タイム</th>' : ''}
    </tr>
`;
    for (const r of rows) {
      h += `    <tr>
      ${hasResult ? `<td>${e(r.rank)}</td>` : ''}
      <td>${e(r.waku)}</td><td>${e(r.uma)}</td>
      <td>${e(r.name)}</td><td>${e(r.jockey)}</td>
      ${hasResult ? `<td>${e(r.time)}</td>` : ''}
    </tr>
`;
    }
    h += '  </table>\n';
  } else {
    h += '  <p>出馬表はまだ公開されていません。</p>\n';
  }
  if (pays.length) {
    h += '  <h2>払戻</h2>\n  <table>\n    <tr><th>券種</th><th>払戻</th></tr>\n';
    for (const p of pays) h += `    <tr><td>${e(p[0])}</td><td>${e(p[1])}</td></tr>\n`;
    h += '  </table>\n';
  }
  h += `  <p><a href="/">レース一覧へ</a></p>
</div>

<div class="vtabs" id="vtabs"></div>
<div class="rtabs" id="rtabs"></div>
<h1 id="title" style="display:none"></h1>
<p class="sub" id="sub"></p>
<div class="tabs" role="group" aria-label="表示の切替">
  <button id="tCard" aria-pressed="true">出馬表</button>
  <button id="tAi" aria-pressed="false">AI予想</button>
  <button id="tResult" aria-pressed="false">結果・払戻</button>
</div>
<div id="out"></div>
<footer>データ出典: netkeiba.com<br>
本ページは情報提供を目的としたもので、的中や利益を保証するものではありません。<br>
<a href="/privacy/">プライバシーポリシー・運営者情報</a></footer>
</div>
<script src="/core/scoring.js${av('scoring.js')}"></script>
<script src="/core/ltr_model.js${av('ltr_model.js')}"></script>
<script src="/core/personas.js${av('personas.js')}"></script>
<script src="/core/netkeiba_past.js${av('netkeiba_past.js')}"></script>
<script src="/core/montecarlo.js${av('montecarlo.js')}"></script>
<script src="/core/race_app.js${av('race_app.js')}"></script>
<script>
/* アクセス計測（Cookieなし・自前）。失敗しても本体に影響させない */
try{ new Image().src = '/stats.php?p=' + encodeURIComponent(location.pathname)
   + '&r=' + encodeURIComponent(document.referrer) + '&t=' + Date.now(); }catch(e){}
</script>

</html>`;
  return resp(h, 200, { 'Content-Type': 'text/html; charset=UTF-8', 'Cache-Control': 'public, max-age=120' });
}
const JUSHO_SET = new Set(JUSHO_KEYS);

/** rawurlencode（RFC3986） */
export function rawUrlEncode(s: string): string {
  return encodeURIComponent(s).replace(/[!'()*]/g, (ch) => '%' + ch.charCodeAt(0).toString(16).toUpperCase());
}

/* ============================== sitemap.php ============================== */
const SM_TTL = 43200;
const xmlEsc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
export async function sitemap(c: Ctx): Promise<Response> {
  const { env } = c;
  const H = { 'Content-Type': 'application/xml; charset=UTF-8' };
  const ck = 'sitemap_' + c.site;
  const row = await env.DB.prepare('SELECT v, at FROM kv WHERE k=?').bind(ck).first<{ v: string; at: number }>();
  if (row && nowSec() - row.at < SM_TTL) return resp(row.v, 200, H);
  const xml = await buildSitemap(env);
  await env.DB.prepare('INSERT OR REPLACE INTO kv(k,v,at) VALUES(?,?,?)').bind(ck, xml, nowSec()).run();
  return resp(xml, 200, H);
}
export async function buildSitemap(env: Env): Promise<string> {
  const urls: [string, string, string][] = SITEMAP_URLS.length ? [...SITEMAP_URLS] : [
    ['https://kajikeiba.com/', 'hourly', '1.0'], ['https://kajikeiba.com/ai/', 'weekly', '0.9'],
    ['https://kajikeiba.com/record/', 'daily', '0.9'], ['https://kajikeiba.com/articles/', 'weekly', '0.9'],
    ['https://kajikeiba.com/about/', 'monthly', '0.5'], ['https://kajikeiba.com/privacy/', 'yearly', '0.3'],
  ];
  for (const name of JUSHO_KEYS) urls.push(['https://kajikeiba.com/data/jusho/?r=' + rawUrlEncode(name), 'weekly', '0.7']);
  const today = ymd();
  const from = ymd(Date.now() - 29 * 86400e3);
  const rs = await env.DB.prepare('SELECT rid, day FROM race_index WHERE day>=? AND day<=? ORDER BY day DESC, rid').bind(from, today).all<{ rid: string; day: string }>();
  for (const r of rs.results) {
    const isToday = r.day === today;
    urls.push([`https://kajikeiba.com/race/${r.rid}/`, isToday ? 'hourly' : 'monthly', isToday ? '0.9' : '0.6']);
  }
  let xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n';
  for (const [loc, freq, pri] of urls) xml += `<url><loc>${xmlEsc(loc)}</loc><changefreq>${freq}</changefreq><priority>${pri}</priority></url>\n`;
  xml += '</urlset>\n';
  return xml;
}

/** cron: その日の netkeiba 一覧からレースIDを貯める（中央・地方の2本） */
export async function indexRaces(env: Env, day: string): Promise<number> {
  let n = 0;
  for (const host of ['race.netkeiba.com', 'nar.netkeiba.com']) {
    const url = `https://${host}/top/race_list_sub.html?kaisai_date=${day}`;
    let html = '';
    const d = await directFetch(url, 15000);
    if (d.ok && d.body) html = new TextDecoder().decode(d.body);
    else { try { const p = await proxyGet(env, url); if (p.status === 200) html = await p.text(); } catch { /* noop */ } }
    const ids = [...new Set([...html.matchAll(/race_id=(\d{12})/g)].map((m) => m[1]))];
    for (let i = 0; i < ids.length; i += 50) {
      const part = ids.slice(i, i + 50);
      await env.DB.batch(part.map((rid) => env.DB.prepare('INSERT OR IGNORE INTO race_index(rid,day) VALUES(?,?)').bind(rid, day)));
    }
    n += ids.length;
  }
  return n;
}
