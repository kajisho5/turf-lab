/* kaiko.php / results.php / horse.php / jockey.php / bias.php の置き換え */
import {
  Ctx, CORS, JSON_CT, NO_STORE, json, resp, q, readJson, isObj, isset, empty, phpStr, safeKey,
  dateC, nowSec, phpCount, phpValues, isArr, chunks, streamJson,
} from '../lib';

/* ============================== kaiko.php ============================== */
/* ソースがリポに無いため、実物の応答から仕様を起こした:
 *   POST ?action=put  本文=1レコード（key で上書き・無ければ末尾に追加）→ {"ok":true}
 *   GET  ?action=list（既定）→ {"records":[...]}（最初に入った順）
 *   それ以外 → 400 {"error":"unknown action"}                                   */
export async function kaiko(c: Ctx): Promise<Response> {
  const { env, req, url } = c;
  const H = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'GET,POST,OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type', 'Content-Type': JSON_CT };
  if (req.method === 'OPTIONS') return resp(null, 204, H);
  const action = q(url, 'action') ?? 'list';
  if (action === 'put') {
    const rec = await readJson(req);
    if (!isObj(rec) || !isset(rec.key)) return json({ error: 'invalid record' }, 400, H);
    const k = phpStr(rec.key);
    await env.DB.prepare(
      `INSERT INTO kaiko(k,seq,body) VALUES(?1,(SELECT COALESCE(MAX(seq),0)+1 FROM kaiko),?2)
         ON CONFLICT(k) DO UPDATE SET body=excluded.body`,
    ).bind(k, JSON.stringify(rec)).run();
    return json({ ok: true }, 200, H);
  }
  if (action === 'list') {
    return streamJson(H, async (write) => {
      await write('{"records":[');
      let first = true; let last = -1;
      for (;;) {
        const rs = await env.DB.prepare('SELECT seq, body FROM kaiko WHERE seq > ? ORDER BY seq LIMIT 500').bind(last).all<{ seq: number; body: string }>();
        for (const r of rs.results) { await write((first ? '' : ',') + r.body); first = false; last = r.seq; }
        if (rs.results.length < 500) break;
      }
      await write(']}');
    });
  }
  return json({ error: 'unknown action' }, 400, H);
}

/* ============================== results.php ============================== */
export async function results(c: Ctx): Promise<Response> {
  const { env, req, url } = c;
  const H = { ...CORS, 'Content-Type': JSON_CT, 'Cache-Control': NO_STORE };
  if (req.method === 'OPTIONS') return resp(null, 204, H);
  const action = q(url, 'action') ?? 'get';

  if (action === 'savebatch' || action === 'save') {
    const j = await readJson(req);
    const items = action === 'save' ? [j] : (isObj(j) ? phpValues(j.items) : []);
    const at = dateC();
    const stmts: D1PreparedStatement[] = [];
    for (const it of items) {
      if (!isObj(it) || empty(it.race_id)) continue;
      it.at = at;
      stmts.push(env.DB.prepare('INSERT OR REPLACE INTO results(k,body) VALUES(?,?)').bind(safeKey(phpStr(it.race_id)), JSON.stringify(it)));
    }
    let n = 0;
    for (const part of chunks(stmts, 50)) {
      try { await env.DB.batch(part); n += part.length; } catch (e) { console.error('results save', e); }
    }
    /* ★PHP版の「120日より古い結果を消す」はやめた★（docs/CLOUDFLARE_MIGRATION.md 7章） */
    return json({ ok: true, saved: n }, 200, H);
  }

  if (action === 'get') {
    let ids: unknown[] = [];
    const g = q(url, 'ids');
    if (!empty(g)) ids = (g as string).split(',');
    else {
      const j = await readJson(req);
      if (isObj(j) && Array.isArray(j.ids)) ids = j.ids;
    }
    const want: string[] = [];
    for (const r of ids) { const s = phpStr(r).trim(); if (s !== '') want.push(s); }
    const found = new Map<string, string>();
    const keys = [...new Set(want.map(safeKey))];
    for (const part of chunks(keys, 90)) {
      const rs = await env.DB.prepare(`SELECT k, body FROM results WHERE k IN (${part.map(() => '?').join(',')})`).bind(...part).all<{ k: string; body: string }>();
      for (const r of rs.results) found.set(r.k, r.body);
    }
    const out = new Map<string, string>();
    for (const rid of want) { const b = found.get(safeKey(rid)); if (b) out.set(rid, b); }
    // PHPの空配列は [] で出る
    const body = out.size === 0 ? '{"results":[]}'
      : '{"results":{' + [...out].map(([k, v]) => JSON.stringify(k) + ':' + v).join(',') + '}}';
    return resp(body, 200, H);
  }
  return json({ ok: false, error: 'unknown action' }, 400, H);
}

/* ============================== horse.php / jockey.php ============================== */
interface CacheSpec {
  table: 'horses' | 'jockeys'; col: 'hid' | 'jkid'; ok: RegExp;
  getParam: string; batchParam: string; badMsg: string; need: 'races' | 'tracks';
  build: (it: Record<string, unknown>) => Record<string, unknown>;
}
const HORSE: CacheSpec = {
  table: 'horses', col: 'hid', ok: /^[0-9]{6,14}$/, getParam: 'hid', batchParam: 'hids', badMsg: 'bad hid', need: 'races',
  build: (it) => ({ hid: phpStr(it.hid), races: it.races, updated: nowSec() }),
};
const JOCKEY: CacheSpec = {
  table: 'jockeys', col: 'jkid', ok: /^[a-z0-9]{3,10}$/i, getParam: 'id', batchParam: 'ids', badMsg: 'bad id', need: 'tracks',
  build: (it) => ({ jkid: phpStr(it.jkid), name: isset(it.name) ? it.name : '', tracks: it.tracks, updated: nowSec() }),
};

async function careerCache(c: Ctx, s: CacheSpec): Promise<Response> {
  const { env, req, url } = c;
  const H = { ...CORS, 'Content-Type': JSON_CT };
  if (req.method === 'OPTIONS') return resp(null, 204, H);
  const action = q(url, 'action') ?? '';
  const okId = (v: unknown) => s.ok.test(phpStr(v));

  if (action === 'get') {
    const id = q(url, s.getParam) ?? '';
    if (!okId(id)) return json({ error: s.badMsg }, 200, H);
    const row = await env.DB.prepare(`SELECT body FROM ${s.table} WHERE ${s.col}=?`).bind(id).first<{ body: string }>();
    if (row) return resp(row.body, 200, H);
    return json({ [s.col]: id, miss: true }, 200, H);
  }
  if (action === 'getbatch') {
    const p = q(url, s.batchParam);
    const ids = (p === undefined ? [] : p.split(',')).map((x) => x.trim()).filter(okId);
    const found = new Map<string, string>();
    for (const part of chunks([...new Set(ids)], 90)) {
      const rs = await env.DB.prepare(`SELECT ${s.col} AS id, body FROM ${s.table} WHERE ${s.col} IN (${part.map(() => '?').join(',')})`).bind(...part).all<{ id: string; body: string }>();
      for (const r of rs.results) found.set(r.id, r.body);
    }
    const out: string[] = [];
    const seen = new Set<string>();
    for (const id of ids) { const b = found.get(id); if (b && !seen.has(id)) { seen.add(id); out.push(JSON.stringify(id) + ':' + b); } }
    return resp(out.length ? '{"records":{' + out.join(',') + '}}' : '{"records":[]}', 200, H);
  }
  if (action === 'save') {
    const data = await readJson(req);
    if (empty(data) || !isArr(data)) return json({ error: 'bad json' }, 200, H);
    const d = data as Record<string, unknown>;
    let items: unknown[] = [];
    if (isset(d.records) && isArr(d.records)) items = phpValues(d.records);
    else if (isset(d[s.col])) items = [d];
    const stmts: D1PreparedStatement[] = [];
    for (const it of items) {
      if (!isObj(it) || !isset(it[s.col]) || !okId(it[s.col])) continue;
      if (!isset(it[s.need]) || !isArr(it[s.need])) continue;
      stmts.push(env.DB.prepare(`INSERT OR REPLACE INTO ${s.table}(${s.col},body) VALUES(?,?)`).bind(phpStr(it[s.col]), JSON.stringify(s.build(it))));
    }
    let n = 0;
    for (const part of chunks(stmts, 50)) { await env.DB.batch(part); n += part.length; }
    return json({ saved: n }, 200, H);
  }
  return json({ error: 'unknown action' }, 200, H);
}
export const horse = (c: Ctx) => careerCache(c, HORSE);
export const jockey = (c: Ctx) => careerCache(c, JOCKEY);

/* ============================== bias.php ============================== */
export async function bias(c: Ctx): Promise<Response> {
  const { env, req, url } = c;
  const H = { 'Content-Type': JSON_CT, ...CORS };
  if (req.method === 'OPTIONS') return resp(null, 204, H);
  const action = q(url, 'action') ?? 'list';
  const db = env.DB;

  if (action === 'save') {
    const rec = await readJson(req);
    if (!isObj(rec) || empty(rec) || empty(rec.date)) return json({ ok: false, error: 'invalid payload' }, 400, H);
    const mode = isset(rec.mode) ? phpStr(rec.mode) : 'nar';
    rec.savedAt = dateC();
    const key = phpStr(rec.date) + '_' + mode;
    const races = phpCount(rec.races ?? []);
    await db.prepare('INSERT OR REPLACE INTO bias(k,date,mode_raw,races,body) VALUES(?,?,?,?,?)')
      .bind(safeKey(key), phpStr(rec.date), isset(rec.mode) ? phpStr(rec.mode) : null, races, JSON.stringify(rec)).run();
    return json({ ok: true, key, races }, 200, H);
  }
  if (action === 'get') {
    const date = q(url, 'date') ?? ''; const mode = q(url, 'mode') ?? 'nar';
    if (date === '') return json({ miss: true }, 200, H);
    const row = await db.prepare('SELECT body FROM bias WHERE k=?').bind(safeKey(`${date}_${mode}`)).first<{ body: string }>();
    if (row) return resp(row.body, 200, H);
    return json({ miss: true }, 200, H);
  }
  if (action === 'list') {
    const t = (n: string) => { const v = q(url, n) ?? ''; return v === '0' ? '' : v; };
    const rs = await db.prepare(
      `SELECT body FROM bias WHERE (?1='' OR date=?1) AND (?2='' OR COALESCE(mode_raw,'')=?2)
         AND (?3='' OR date>=?3) AND (?4='' OR date<=?4) ORDER BY date DESC, k ASC`,
    ).bind(t('date'), t('mode'), t('from'), t('to')).all<{ body: string }>();
    return resp('{"records":[' + rs.results.map((r) => r.body).join(',') + ']}', 200, H);
  }
  if (action === 'dates') {
    const rs = await db.prepare(
      `SELECT date, COALESCE(mode_raw,'nar') AS mode, races FROM bias WHERE date NOT IN ('','0') ORDER BY date DESC, k ASC`,
    ).all<{ date: string; mode: string; races: number }>();
    return json({ items: rs.results }, 200, H);
  }
  return json({ ok: false, error: 'unknown action' }, 400, H);
}
