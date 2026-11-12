/* oddslog.php（オッズ時系列）と odds-log.php（旧・異常検知の学習ログ）の置き換え */
import {
  Ctx, CORS, JSON_CT, NO_STORE, json, resp, q, readJson, isObj, isset, empty, phpStr, phpInt, isNumeric,
  Env, streamJson,
} from '../lib';

/* ============================== oddslog.php ============================== */
export async function oddslog(c: Ctx): Promise<Response> {
  const { env, req, url } = c;
  const H = { 'Access-Control-Allow-Origin': '*', 'Content-Type': JSON_CT, 'Access-Control-Allow-Methods': 'GET, POST, OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type', 'Cache-Control': NO_STORE };
  if (req.method === 'OPTIONS') return resp('', 200, H);
  const action = q(url, 'action') ?? '';
  const db = env.DB;
  const digits = (v: unknown) => phpStr(v).replace(/[^0-9]/g, '');

  if (action === 'save') {
    const d = await readJson(req);
    if (!isObj(d) || empty(d) || empty(d.rid) || empty(d.odds)) return json({ error: 'bad payload' }, 400, H);
    const rid = digits(d.rid);
    const date = digits(isset(d.date) ? d.date : '');
    if (rid === '' || date.length !== 8) return json({ error: 'bad rid/date' }, 400, H);
    const row = await db.prepare('SELECT body FROM odds_snaps WHERE date=? AND rid=?').bind(date, rid).first<{ body: string }>();
    let arr: unknown[] = [];
    if (row) { try { const j = JSON.parse(row.body); if (Array.isArray(j)) arr = j; else if (isObj(j)) arr = Object.values(j); } catch { /* 壊れていたら作り直す */ } }
    // ★post（発走時刻）と mtp（残り分数）も保存する★ 白リスト方式
    const snap = {
      ts: isset(d.ts) ? phpInt(d.ts) : Math.floor(Date.now() / 1000) * 1000,
      mode: isset(d.mode) ? d.mode : '',
      post: isset(d.post) ? phpStr(d.post).replace(/[^0-9:]/g, '') : null,
      mtp: isset(d.mtp) && isNumeric(d.mtp) ? phpInt(d.mtp) : null,
      odds: d.odds,
    };
    // 同一分内の重複は上書き
    const minute = Math.floor(snap.ts / 60000);
    let replaced = false;
    for (let i = 0; i < arr.length; i++) {
      const old = arr[i];
      if (isObj(old) && isset(old.ts) && Math.floor(Number(old.ts) / 60000) === minute) { arr[i] = snap; replaced = true; break; }
    }
    if (!replaced) arr.push(snap);
    await db.prepare('INSERT OR REPLACE INTO odds_snaps(date,rid,n,body) VALUES(?,?,?,?)').bind(date, rid, arr.length, JSON.stringify(arr)).run();
    return json({ ok: true, rid, snapshots: arr.length }, 200, H);
  }
  if (action === 'get') {
    const rid = digits(q(url, 'rid') ?? '');
    const date = digits(q(url, 'date') ?? '');
    if (rid === '') return json({ error: 'no rid' }, 400, H);
    const row = date.length === 8
      ? await db.prepare('SELECT body FROM odds_snaps WHERE date=? AND rid=?').bind(date, rid).first<{ body: string }>()
      : await db.prepare('SELECT body FROM odds_snaps WHERE rid=? ORDER BY date LIMIT 1').bind(rid).first<{ body: string }>();
    if (row) return resp(row.body, 200, H);
    return resp('[]', 200, H);
  }
  if (action === 'dates') {
    const rs = await db.prepare('SELECT date, COUNT(*) AS races FROM odds_snaps GROUP BY date ORDER BY date DESC').all<{ date: string; races: number }>();
    return json({ dates: rs.results }, 200, H);
  }
  if (action === 'list') {
    const date = digits(q(url, 'date') ?? '');
    if (date.length !== 8) return json({ error: 'bad date' }, 400, H);
    const rs = await db.prepare('SELECT rid, n AS snapshots FROM odds_snaps WHERE date=? ORDER BY rid').bind(date).all<{ rid: string; snapshots: number }>();
    return json({ date, races: rs.results }, 200, H);
  }
  return json({ error: 'unknown action' }, 400, H);
}

/* ============================== odds-log.php（旧） ============================== */
export const OLD_MAX = 5000;

/** id一致で上書き（resultは既存を保持）、無ければ末尾。trim=true なら5000件を超えた古い分を捨てて件数を返す */
export async function oldUpsert(env: Env, mode: string, recs: Record<string, unknown>[], trim = true): Promise<number> {
  const db = env.DB;
  for (const rec of recs) {
    if (!isset(rec.id)) continue;
    const ids = phpStr(rec.id);
    if (empty(rec.result)) {
      const ex = await db.prepare('SELECT body FROM oddslog_old WHERE mode=? AND id=?').bind(mode, ids).first<{ body: string }>();
      if (ex) { try { const r = JSON.parse(ex.body); if (isObj(r) && !empty(r.result)) rec.result = r.result; } catch { /* noop */ } }
    }
    await db.prepare(`INSERT INTO oddslog_old(mode,id,seq,body) VALUES(?1,?2,(SELECT COALESCE(MAX(seq),0)+1 FROM oddslog_old WHERE mode=?1),?3)
        ON CONFLICT(mode,id) DO UPDATE SET body=excluded.body`).bind(mode, ids, JSON.stringify(rec)).run();
  }
  if (!trim) return -1;
  const cnt = await db.prepare('SELECT COUNT(*) AS n FROM oddslog_old WHERE mode=?').bind(mode).first<{ n: number }>();
  let n = cnt?.n ?? 0;
  if (n > OLD_MAX) {
    await db.prepare(`DELETE FROM oddslog_old WHERE mode=?1 AND seq IN (SELECT seq FROM oddslog_old WHERE mode=?1 ORDER BY seq LIMIT ?2)`).bind(mode, n - OLD_MAX).run();
    n = OLD_MAX;
  }
  return n;
}

/* EUC-JP への変換表（Workers の TextEncoder は UTF-8 しか作れないので、デコーダから逆引きを作る） */
let EUC_MAP: Map<string, number[]> | null = null;
function eucEncode(s: string): Uint8Array {
  if (!EUC_MAP) {
    EUC_MAP = new Map();
    const dec = new TextDecoder('euc-jp');
    for (let a = 0xa1; a <= 0xfe; a++) for (let b = 0xa1; b <= 0xfe; b++) {
      const ch = dec.decode(new Uint8Array([a, b]));
      if (ch.length === 1 && ch !== '�' && !EUC_MAP.has(ch)) EUC_MAP.set(ch, [a, b]);
    }
    for (let b = 0xa1; b <= 0xdf; b++) EUC_MAP.set(dec.decode(new Uint8Array([0x8e, b])), [0x8e, b]);
  }
  const out: number[] = [];
  for (const ch of s) {
    const cp = ch.codePointAt(0)!;
    if (cp < 0x80) { out.push(cp); continue; }
    const e = EUC_MAP.get(ch);
    if (e) out.push(...e); else out.push(0x3f);
  }
  return new Uint8Array(out);
}
function rawUrlEncodeBytes(b: Uint8Array): string {
  let s = '';
  for (const x of b) {
    const ch = String.fromCharCode(x);
    s += /[A-Za-z0-9\-_.~]/.test(ch) ? ch : '%' + x.toString(16).toUpperCase().padStart(2, '0');
  }
  return s;
}
async function fetchEucHtml(u: string): Promise<string> {
  try {
    const r = await fetch(u, { headers: { 'User-Agent': 'Mozilla/5.0' }, signal: AbortSignal.timeout(25000) });
    if (!r.ok) return '';
    return new TextDecoder('euc-jp').decode(await r.arrayBuffer());
  } catch { return ''; }
}

export async function oddsLogOld(c: Ctx): Promise<Response> {
  const { env, req, url } = c;
  const H = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'GET,POST,OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type', 'Content-Type': JSON_CT };
  if (req.method === 'OPTIONS') return resp(null, 204, H);
  const mode = q(url, 'mode') === 'nar' ? 'nar' : 'jra';
  const action = q(url, 'action') ?? 'list';
  const db = env.DB;
  try {
    if (action === 'list') {
      return streamJson(H, async (write) => {
        await write('{"records":[');
        let first = true; let last = -1;
        for (;;) {
          const rs = await db.prepare('SELECT seq, body FROM oddslog_old WHERE mode=? AND seq>? ORDER BY seq LIMIT 1000').bind(mode, last).all<{ seq: number; body: string }>();
          for (const r of rs.results) { await write((first ? '' : ',') + r.body); first = false; last = r.seq; }
          if (rs.results.length < 1000) break;
        }
        await write(']}');
      });
    }
    if (action === 'stats') {
      const rs = await db.prepare('SELECT body FROM oddslog_old WHERE mode=?').bind(mode).all<{ body: string }>();
      let settled = 0;
      for (const r of rs.results) { try { const j = JSON.parse(r.body); if (isObj(j) && isObj(j.result) && !empty(j.result.win)) settled++; } catch { /* noop */ } }
      return json({ count: rs.results.length, settled }, 200, H);
    }
    if (action === 'jusho_list') {
      const name = q(url, 'name') ?? '';
      if (name === '') return json({ editions: [] }, 200, H);
      const inner = 'https://db.netkeiba.com/?pid=race_list&word=' + rawUrlEncodeBytes(eucEncode(name)) + '&front=1';
      const html = await fetchEucHtml('https://api.codetabs.com/v1/proxy/?quest=' + encodeURIComponent(inner).replace(/[!'()*]/g, (ch) => '%' + ch.charCodeAt(0).toString(16).toUpperCase()));
      const editions: { rid: string; year: string; label: string }[] = [];
      const seen = new Set<string>();
      for (const m of html.matchAll(/\/race\/(\d{12})\/?"[^>]*>([^<]*)/g)) {
        const rid = m[1]; const label = m[2].trim();
        if (seen.has(rid)) continue; seen.add(rid);
        if (!/G[I123]|\(G\d\)|重賞/u.test(label)) continue;
        editions.push({ rid, year: rid.slice(0, 4), label });
      }
      return json({ editions }, 200, H);
    }
    if (action === 'jusho_result') {
      const rid = (q(url, 'rid') ?? '').replace(/[^0-9]/g, '');
      if (rid === '') return json({ html: '' }, 200, H);
      const html = await fetchEucHtml('https://api.codetabs.com/v1/proxy/?quest=' + encodeURIComponent(`https://db.netkeiba.com/race/${rid}/`));
      return json({ html }, 200, H);
    }
    if (action === 'board') {
      const row = await db.prepare("SELECT v FROM kv WHERE k='odds_snaps'").first<{ v: string }>();
      let snaps: Record<string, unknown> = {};
      try { const j = row ? JSON.parse(row.v) : {}; if (isObj(j)) snaps = j; } catch { /* noop */ }
      const want = q(url, 'mode') ?? '';
      const rows = [];
      for (const [rid, s] of Object.entries(snaps)) {
        if (!isObj(s) || empty(s.series) || !Array.isArray(s.series)) continue;
        if (want && isset(s.mode) && s.mode !== want) continue;
        const series = s.series as { win?: Record<string, number> }[];
        const curWin = series[series.length - 1]?.win ?? {};
        const first = series[0]?.win ?? {};
        let maxDrop = 0; let dropNum: string | null = null; let minOdds: number | null = null; let minNum: string | null = null;
        for (const [num, od0] of Object.entries(curWin)) {
          const od = Number(od0); if (!(od > 0)) continue;
          if (minOdds === null || od < minOdds) { minOdds = od; minNum = num; }
          const f = Number(first[num]);
          if (f > 0) { const chg = (od - f) / f * 100; if (chg < maxDrop) { maxDrop = chg; dropNum = num; } }
        }
        rows.push({
          rid, mode: isset(s.mode) ? s.mode : '', track: isset(s.track) ? s.track : '', no: isset(s.no) ? phpInt(s.no) : 0,
          postMin: isset(s.postMin) ? phpInt(s.postMin) : null, horses: Object.keys(curWin).length, snaps: series.length,
          minOdds, minNum, maxDrop: Math.round(maxDrop * 10) / 10, dropNum,
        });
      }
      rows.sort((a, b) => a.maxDrop - b.maxDrop);
      return json({ board: rows, count: rows.length }, 200, H);
    }
    if (action === 'put') {
      const body = await readJson(req);
      if (!isObj(body) || !isset(body.id)) return json({ error: 'invalid record' }, 400, H);
      const n = await oldUpsert(env, mode, [body]);
      return json({ ok: true, count: n }, 200, H);
    }
    if (action === 'bulk') {
      const body = await readJson(req);
      if (!Array.isArray(body) && !isObj(body)) return json({ error: 'expected array' }, 400, H);
      const recs = (Array.isArray(body) ? body : Object.values(body)).filter((r): r is Record<string, unknown> => isObj(r) && isset(r.id));
      const n = await oldUpsert(env, mode, recs);
      return json({ ok: true, merged: recs.length, count: n }, 200, H);
    }
    return json({ error: 'unknown action', actions: ['list', 'put', 'bulk', 'stats', 'board'] }, 400, H);
  } catch (e) {
    return json({ error: String((e as Error)?.message ?? e) }, 500, H);
  }
}
