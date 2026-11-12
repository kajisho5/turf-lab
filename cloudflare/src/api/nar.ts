/* nardata.php / nar_official.php の置き換え（keiba.go.jp 公式データ） */
import { unzipSync, strFromU8 } from 'fflate';
import { Ctx, Env, CORS, JSON_CT, json, resp, q, readJson, isObj, dateC, nowSec, md5, entityDecode, stripTags } from '../lib';

const TC: Record<string, string> = {
  門別: '30', 盛岡: '35', 水沢: '36', 浦和: '42', 船橋: '43', 大井: '44', 川崎: '45',
  金沢: '46', 笠松: '47', 名古屋: '48', 園田: '50', 姫路: '51', 高知: '54', 佐賀: '55',
};

/** str_getcsv 相当（ダブルクォート対応） */
export function parseCsvLine(ln: string): string[] {
  const out: string[] = []; let cur = ''; let inQ = false;
  for (let i = 0; i < ln.length; i++) {
    const ch = ln[i];
    if (inQ) {
      if (ch === '"') { if (ln[i + 1] === '"') { cur += '"'; i++; } else inQ = false; }
      else cur += ch;
    } else if (ch === '"' && cur === '') inQ = true;
    else if (ch === ',') { out.push(cur); cur = ''; }
    else cur += ch;
  }
  out.push(cur);
  return out;
}
const isDigits = (s: string | undefined) => !!s && /^\d+$/.test(s);

type Pay = { tan: Record<string, number>; fuku: Record<string, number>; wide: Record<string, number>; umaren: unknown; umatan: unknown; sanpuku: unknown; santan: unknown };
type Race = { ranks: Record<string, number>; top3: string[]; pay: Pay | null; raceName?: string; decided?: boolean };

/** 当日ZIPを取って {rid:{ranks,top3,pay,decided}} を作る（PHP nar_fetch_daily と同じ） */
export async function narFetchDaily(): Promise<{ error: string } | { generated: string; races: Record<string, Race> }> {
  let zip: Uint8Array;
  try {
    const r = await fetch('https://www.keiba.go.jp/KeibaWeb/DataDownload/RaceDataDownload?type=daily', { headers: { 'User-Agent': 'Mozilla/5.0' }, signal: AbortSignal.timeout(25000) });
    zip = new Uint8Array(await r.arrayBuffer());
  } catch { return { error: 'fetch failed' }; }
  if (zip.length < 1000) return { error: 'fetch failed' };
  let files: Record<string, Uint8Array>;
  try { files = unzipSync(zip, { filter: (f) => f.name.includes('horselist') || f.name.includes('payback') }); }
  catch { return { error: 'zip open failed' }; }
  const out: Record<string, Race> = {};
  for (const [nm, data] of Object.entries(files)) {
    const isHorse = nm.includes('horselist');
    const isPay = nm.includes('payback');
    for (const ln of strFromU8(data).split(/\r?\n/)) {
      if (ln === '') continue;
      const c = parseCsvLine(ln);
      if (c[0] === undefined || c[0] === '競馬場' || !(c[0] in TC)) continue;
      const ymd = (c[1] ?? '').replace(/\//g, '');
      if (ymd.length !== 8) continue;
      const rid = ymd.slice(0, 4) + TC[c[0]] + ymd.slice(4, 8) + (c[2] ?? '').padStart(2, '0');
      if (!out[rid]) out[rid] = { ranks: {}, top3: [], pay: null };
      if (isHorse && c.length >= 36) {
        if (c[31] !== '' && isDigits(c[31])) {
          out[rid].ranks[c[5]] = parseInt(c[31], 10);
          if (parseInt(c[31], 10) <= 3) out[rid].top3.push(c[5]);
        }
      } else if (isPay && c.length >= 54) {
        const p: Pay = { tan: {}, fuku: {}, wide: {}, umaren: null, umatan: null, sanpuku: null, santan: null };
        if (c[4] !== '' && isDigits(c[5])) p.tan[c[4]] = parseInt(c[5], 10);
        for (const [a, b] of [[7, 8], [10, 11], [13, 14]]) if (c[a] !== '' && isDigits(c[b])) p.fuku[c[a]] = parseInt(c[b], 10);
        for (const [a, b, y] of [[32, 33, 34], [36, 37, 38], [40, 41, 42]]) if (c[a] !== '' && isDigits(c[y])) p.wide[c[a] + '-' + c[b]] = parseInt(c[y], 10);
        if (c[24] !== '' && isDigits(c[26])) p.umaren = { c: [c[24], c[25]], y: parseInt(c[26], 10) };
        if (c[28] !== '' && isDigits(c[30])) p.umatan = { c: [c[28], c[29]], y: parseInt(c[30], 10) };
        if (c[44] !== '' && isDigits(c[47])) p.sanpuku = { c: [c[44], c[45], c[46]], y: parseInt(c[47], 10) };
        if (c[49] !== '' && isDigits(c[52])) p.santan = { c: [c[49], c[50], c[51]], y: parseInt(c[52], 10) };
        out[rid].pay = p;
        out[rid].raceName = c[3] ?? '';
      }
    }
  }
  for (const r of Object.values(out)) r.decided = Object.keys(r.ranks).length > 0 && r.pay !== null;
  return { generated: dateC(), races: out };
}

/** PHPの空連想配列は [] で出る。JSON化の直前に合わせる */
function phpShape(v: unknown): unknown {
  if (Array.isArray(v)) return v.map(phpShape);
  if (isObj(v)) {
    const ks = Object.keys(v);
    if (ks.length === 0) return [];
    const o: Record<string, unknown> = {};
    for (const k of ks) o[k] = phpShape(v[k]);
    return o;
  }
  return v;
}

/** collect（cron からも呼ぶ）: 確定レースを日付別にマージ保存 */
export async function narCollect(env: Env): Promise<{ status: number; body: unknown }> {
  const res = await narFetchDaily();
  if ('error' in res) return { status: 502, body: res };
  const byDate: Record<string, Record<string, Race>> = {};
  for (const [rid, r] of Object.entries(res.races)) {
    if (!r.decided) continue;
    const day = rid.slice(0, 4) + rid.slice(6, 10);
    (byDate[day] ??= {})[rid] = r;
  }
  let added = 0; let total = 0; const dates: string[] = [];
  for (const [day, races] of Object.entries(byDate)) {
    const row = await env.DB.prepare('SELECT body FROM official_results WHERE day=?').bind(day).first<{ body: string }>();
    let cur: Record<string, unknown> = {};
    if (row) { try { const j = JSON.parse(row.body); if (isObj(j)) cur = j; } catch { /* noop */ } }
    for (const [rid, r] of Object.entries(races)) { if (!(rid in cur)) added++; cur[rid] = r; }
    await env.DB.prepare('INSERT OR REPLACE INTO official_results(day,body) VALUES(?,?)').bind(day, JSON.stringify(phpShape(cur))).run();
    total += Object.keys(cur).length; dates.push(day);
  }
  return { status: 200, body: { ok: true, generated: res.generated, dates, newly_decided: added, stored: total } };
}

export async function nardata(c: Ctx): Promise<Response> {
  const { env, req, url } = c;
  const H = { ...CORS, 'Content-Type': JSON_CT };
  if (req.method === 'OPTIONS') return resp(null, 204, H);
  const action = q(url, 'action') ?? '';

  if (action === 'daily') {
    const row = await env.DB.prepare("SELECT v, at FROM kv WHERE k='nar_daily'").first<{ v: string; at: number }>();
    if (row && nowSec() - row.at < 300) return resp(row.v, 200, H);
    const res = await narFetchDaily();
    const s = JSON.stringify(phpShape(res));
    if (!('error' in res)) await env.DB.prepare("INSERT OR REPLACE INTO kv(k,v,at) VALUES('nar_daily',?,?)").bind(s, nowSec()).run();
    return resp(s, 200, H);
  }
  if (action === 'collect') {
    const r = await narCollect(env);
    return resp(JSON.stringify(r.body), r.status, H);
  }
  const hist = async (names: string[]) => {
    const m = new Map<string, string>();
    for (let i = 0; i < names.length; i += 90) {
      const part = names.slice(i, i + 90);
      const rs = await env.DB.prepare(`SELECT name, hist FROM nar_hist WHERE name IN (${part.map(() => '?').join(',')})`).bind(...part).all<{ name: string; hist: string }>();
      for (const r of rs.results) m.set(r.name, r.hist);
    }
    return m;
  };
  if (action === 'get') {
    const name = q(url, 'name') ?? '';
    if (name === '') return resp(JSON.stringify({ error: 'no name' }), 200, H);
    const m = await hist([name]);
    return resp(`{"name":${JSON.stringify(name)},"hist":${m.get(name) ?? '[]'}}`, 200, H);
  }
  if (action === 'batch') {
    let names = q(url, 'names') !== undefined ? q(url, 'names')!.split(',') : [];
    if ((names.length === 0) && req.method === 'POST') {
      const b = await readJson(req);
      if (isObj(b) && Array.isArray(b.names)) names = b.names.map(String);
    }
    names = names.map((n) => n.trim()).filter((n) => n !== '');
    const m = await hist([...new Set(names)]);
    const parts: string[] = []; const seen = new Set<string>();
    for (const n of names) { if (seen.has(n)) continue; seen.add(n); parts.push(JSON.stringify(n) + ':' + (m.get(n) ?? '[]')); }
    return resp(parts.length ? '{"records":{' + parts.join(',') + '}}' : '{"records":[]}', 200, H);
  }
  if (action === 'info') {
    const r = await env.DB.prepare('SELECT COUNT(*) AS n FROM nar_hist').first<{ n: number }>();
    const n = r?.n ?? 0;
    let buckets = 0;
    if (n) { const all = await env.DB.prepare('SELECT name FROM nar_hist').all<{ name: string }>(); const s = new Set<string>(); for (const x of all.results) s.add((await md5(x.name)).slice(0, 2)); buckets = s.size; }
    return resp(JSON.stringify({ buckets, horses: n, source: 'keiba.go.jp official' }), 200, H);
  }
  return resp(JSON.stringify({ error: 'unknown action', actions: ['get', 'batch', 'info'] }), 200, H);
}

/* ============================== nar_official.php ============================== */
const NO_TTL_LIVE = 120;
async function fetchText(url: string): Promise<string> {
  try {
    const r = await fetch(url, { headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' }, redirect: 'follow', signal: AbortSignal.timeout(25000) });
    return await r.text();
  } catch { return ''; }
}
/** cached()：TTL内ならキャッシュ、取れなければ古くても返す */
export async function pageCached(env: Env, key: string, ttl: number, fn: () => Promise<string>): Promise<string> {
  const row = await env.DB.prepare('SELECT body, at FROM page_cache WHERE k=?').bind(key).first<{ body: string; at: number }>();
  if (row && nowSec() - row.at < ttl && row.body !== '') return row.body;
  const v = await fn();
  if (v !== '') { await env.DB.prepare('INSERT OR REPLACE INTO page_cache(k,body,at) VALUES(?,?,?)').bind(key, v, nowSec()).run(); return v; }
  return row ? row.body : '';
}
function cellsOf(tr: string): string[] {
  const out: string[] = [];
  for (const m of tr.matchAll(/<t[dh][^>]*>([\s\S]*?)<\/t[dh]>/gu)) {
    let v = entityDecode(stripTags(m[1]));
    v = v.replace(/ /g, ' ').replace(/　/g, ' ');
    out.push(v.replace(/\s+/gu, ' ').trim());
  }
  return out;
}
export async function narOfficial(c: Ctx): Promise<Response> {
  const { env, url } = c;
  const H = { 'Content-Type': 'application/json; charset=UTF-8', 'Cache-Control': 'public, max-age=60' };
  const date = (q(url, 'date') ?? '').replace(/[^0-9]/g, '');
  const baba = (q(url, 'baba') ?? '').replace(/[^0-9]/g, '');
  const race = (q(url, 'race') ?? '').replace(/[^0-9]/g, '');
  if (date.length !== 8) return resp(JSON.stringify({ error: 'date は YYYYMMDD' }), 400, H);
  const d = `${date.slice(0, 4)}%2f${date.slice(4, 6)}%2f${date.slice(6, 8)}`;
  if (baba === '') {
    const html = await pageCached(env, `nar_list_${date}`, NO_TTL_LIVE, () => fetchText(`https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/RaceList?k_raceDate=${d}`));
    const list: string[] = [];
    for (const m of html.matchAll(/k_babaCode=(\d+)/g)) if (!list.includes(m[1])) list.push(m[1]);
    return resp(JSON.stringify({ date, baba: list }), 200, H);
  }
  const html = await pageCached(env, `nar_mark_${date}_${baba}_${race}`, NO_TTL_LIVE, () => fetchText(
    `https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/RaceMarkTable?k_raceDate=${d}&k_raceNo=${race}&k_babaCode=${baba}`));
  const hasResult = html.includes('着順');
  const horses: Record<string, unknown>[] = [];
  for (const mm of html.matchAll(/<tr[^>]*>([\s\S]*?)<\/tr>/gu)) {
    const c2 = cellsOf(mm[1]);
    if (c2.length < 10) continue;
    if (!/^\d+$/.test(c2[0])) continue;
    const jk = c2[7] ?? '';
    const jkName = jk.replace(/（.*?）/gu, '').trim();
    const jm = jk.match(/（(.*?)）/u);
    const wm = (c2[9] ?? '').match(/(\d{3})\s*\(([-+]?\d+)\)/);
    horses.push(hasResult ? {
      rank: parseInt(c2[0], 10), waku: parseInt(c2[1], 10) || 0, num: parseInt(c2[2], 10) || 0,
      name: c2[3], belong: c2[4], sexAge: c2[5], kg: c2[6], jockey: jkName, jockeyBelong: jm ? jm[1] : '',
      trainer: c2[8] ?? '', weight: wm ? wm[1] : null, diff: wm ? wm[2] : null,
      time: c2[10] ?? '', margin: c2[11] ?? '', last3f: c2[12] ?? '', corner: c2[13] ?? '', pop: c2[14] ?? '', odds: c2[15] ?? '',
    } : {
      waku: parseInt(c2[0], 10), num: parseInt(c2[1], 10) || 0, name: c2[2], belong: c2[3] ?? '', sexAge: c2[4] ?? '', kg: c2[5] ?? '',
      jockey: jkName, trainer: c2[7] ?? '',
    });
  }
  let title = '';
  const tm = html.match(/<h[12][^>]*>([\s\S]*?)<\/h[12]>/u);
  if (tm) title = entityDecode(stripTags(tm[1])).replace(/\s+/gu, ' ').trim();
  return resp(JSON.stringify({ date, baba, race: parseInt(race || '0', 10), title, hasResult, horses, source: '地方競馬全国協会（keiba.go.jp）' }), 200, H);
}

export { json };
