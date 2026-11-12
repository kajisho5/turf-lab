/* 管理口（移行・バックアップ・突き合わせ用）。ヘッダ X-Admin-Token が ADMIN_TOKEN と一致した時だけ動く。
 *   POST /__admin/import?table=T   本文=NDJSON（1行1件）→ {ok, n}
 *   GET  /__admin/export?table=T&after=K&limit=N → NDJSON（キー昇順）
 *   GET  /__admin/count            → 各テーブルの件数
 */
import { scheduled } from './cron';
import { Env, json, resp, isObj, isset, phpStr, phpCount, packBody, unpackBody } from './lib';

type Row = Record<string, unknown>;
const parseBody = (s: unknown): Row => { try { const j = JSON.parse(String(s)); return isObj(j) ? j : {}; } catch { return {}; } };
const modeRaw = (j: Row) => (isset(j.mode) ? phpStr(j.mode) : null);

/** テーブルごとの取り込み方（列は本文から計算して、保存APIと同じ値にする） */
const IMPORT: Record<string, (db: D1Database, r: Row) => Promise<D1PreparedStatement>> = {
  predictions: async (db, r) => {
    const j = parseBody(r.body); const p = await packBody(String(r.body));
    const ts = Number(j.ts ?? 0);
    return db.prepare('INSERT OR REPLACE INTO predictions(k,date,mode_raw,ts,body,body_gz) VALUES(?,?,?,?,?,?)')
      .bind(String(r.k), isset(j.date) ? phpStr(j.date) : '', modeRaw(j), Number.isFinite(ts) ? ts : 0, p.body, p.gz);
  },
  locks: async (db, r) => { const j = parseBody(r.body); return db.prepare('INSERT OR REPLACE INTO locks(k,date,mode_raw,body) VALUES(?,?,?,?)').bind(String(r.k), isset(j.date) ? phpStr(j.date) : '', modeRaw(j), String(r.body)); },
  bias: async (db, r) => { const j = parseBody(r.body); return db.prepare('INSERT OR REPLACE INTO bias(k,date,mode_raw,races,body) VALUES(?,?,?,?,?)').bind(String(r.k), isset(j.date) ? phpStr(j.date) : '', modeRaw(j), phpCount(j.races ?? []), String(r.body)); },
  kaiko: async (db, r) => db.prepare('INSERT OR REPLACE INTO kaiko(k,seq,body) VALUES(?,?,?)').bind(String(r.k), Number(r.seq), String(r.body)),
  results: async (db, r) => db.prepare('INSERT OR REPLACE INTO results(k,body) VALUES(?,?)').bind(String(r.k), String(r.body)),
  horses: async (db, r) => db.prepare('INSERT OR REPLACE INTO horses(hid,body) VALUES(?,?)').bind(String(r.hid), String(r.body)),
  jockeys: async (db, r) => db.prepare('INSERT OR REPLACE INTO jockeys(jkid,body) VALUES(?,?)').bind(String(r.jkid), String(r.body)),
  odds_snaps: async (db, r) => {
    let n = 0; try { const j = JSON.parse(String(r.body)); n = phpCount(j); } catch { /* noop */ }
    return db.prepare('INSERT OR REPLACE INTO odds_snaps(date,rid,n,body) VALUES(?,?,?,?)').bind(String(r.date), String(r.rid), n, String(r.body));
  },
  oddslog_old: async (db, r) => db.prepare('INSERT OR REPLACE INTO oddslog_old(mode,id,seq,body) VALUES(?,?,?,?)').bind(String(r.mode), String(r.id), Number(r.seq), String(r.body)),
  kv: async (db, r) => db.prepare('INSERT OR REPLACE INTO kv(k,v,at) VALUES(?,?,?)').bind(String(r.k), String(r.v), Number(r.at ?? 0)),
  pv: async (db, r) => db.prepare('INSERT INTO pv(site,day,t,path,ref,dev,vid) VALUES(?,?,?,?,?,?,?)').bind(String(r.site), String(r.day), String(r.t), String(r.path), String(r.ref), String(r.dev), String(r.vid)),
  js_errors: async (db, r) => db.prepare('INSERT INTO js_errors(site,day,body) VALUES(?,?,?)').bind(String(r.site), String(r.day), String(r.body)),
  line_outbox: async (db, r) => db.prepare('INSERT OR REPLACE INTO line_outbox(name,text,at) VALUES(?,?,?)').bind(String(r.name), String(r.text), Number(r.at ?? 0)),
  line_sent: async (db, r) => db.prepare('INSERT OR REPLACE INTO line_sent(rid,at) VALUES(?,?)').bind(String(r.rid), String(r.at)),
  official_results: async (db, r) => db.prepare('INSERT OR REPLACE INTO official_results(day,body) VALUES(?,?)').bind(String(r.day), String(r.body)),
  nar_hist: async (db, r) => db.prepare('INSERT OR REPLACE INTO nar_hist(name,hist) VALUES(?,?)').bind(String(r.name), String(r.hist)),
  race_index: async (db, r) => db.prepare('INSERT OR IGNORE INTO race_index(rid,day) VALUES(?,?)').bind(String(r.rid), String(r.day)),
};

/** 書き出し: 主キー列と並び */
const EXPORT: Record<string, { key: string; cols: string }> = {
  predictions: { key: 'k', cols: 'k, body, body_gz' }, locks: { key: 'k', cols: 'k, body' }, bias: { key: 'k', cols: 'k, body' },
  kaiko: { key: 'k', cols: 'k, seq, body' }, results: { key: 'k', cols: 'k, body' }, horses: { key: 'hid', cols: 'hid, body' },
  jockeys: { key: 'jkid', cols: 'jkid, body' }, odds_snaps: { key: "date||'/'||rid", cols: "date||'/'||rid AS key, date, rid, body" },
  oddslog_old: { key: "mode||'/'||id", cols: "mode||'/'||id AS key, mode, id, seq, body" }, line_outbox: { key: 'name', cols: 'name, text, at' },
  line_sent: { key: 'rid', cols: 'rid, at' }, official_results: { key: 'day', cols: 'day, body' }, race_index: { key: 'rid', cols: 'rid, day' },
  js_errors: { key: 'id', cols: 'id, site, day, body' }, pv: { key: 'id', cols: 'id, site, day, t, path, ref, dev, vid' },
};

async function tokenOk(req: Request, env: Env): Promise<boolean> {
  const t = req.headers.get('x-admin-token') ?? '';
  if (!env.ADMIN_TOKEN || t.length !== env.ADMIN_TOKEN.length) return false;
  const a = new TextEncoder().encode(t); const b = new TextEncoder().encode(env.ADMIN_TOKEN);
  let d = 0; for (let i = 0; i < a.length; i++) d |= a[i] ^ b[i];
  return d === 0;
}

export async function admin(req: Request, env: Env, url: URL): Promise<Response> {
  if (!(await tokenOk(req, env))) return json({ error: 'forbidden' }, 403);
  const db = env.DB;
  const action = url.pathname.slice('/__admin/'.length);
  const table = url.searchParams.get('table') ?? '';

  // 定期実行を手で1回まわす（検証・切替直後の穴埋め用）: /__admin/cron?c=37+15+*+*+*
  if (action === 'cron') {
    const c = url.searchParams.get('c') ?? '';
    if (!['*/5 0-13 * * *', '17 * * * *', '37 15 * * *'].includes(c)) return json({ error: 'bad cron' }, 400);
    await scheduled({ cron: c, scheduledTime: Date.now(), noRetry() { /* noop */ } } as ScheduledController, env);
    return json({ ok: true, cron: c });
  }
  if (action === 'count') {
    const out: Record<string, number> = {};
    for (const t of Object.keys(IMPORT)) { const r = await db.prepare(`SELECT COUNT(*) AS n FROM ${t}`).first<{ n: number }>(); out[t] = r?.n ?? 0; }
    return json(out);
  }
  if (action === 'import' && req.method === 'POST') {
    const f = IMPORT[table];
    if (!f) return json({ error: 'bad table' }, 400);
    const lines = (await req.text()).split('\n').filter((l) => l.trim() !== '');
    let n = 0; const errors: string[] = [];
    let batch: D1PreparedStatement[] = []; let bytes = 0;
    const flush = async () => {
      if (!batch.length) return;
      try { await db.batch(batch); n += batch.length; } catch (e) { errors.push(String((e as Error).message ?? e).slice(0, 200)); }
      batch = []; bytes = 0;
    };
    for (const l of lines) {
      let r: Row;
      try { r = JSON.parse(l); } catch { errors.push('bad line'); continue; }
      batch.push(await f(db, r)); bytes += l.length;
      if (batch.length >= 50 || bytes > 4_000_000) await flush();
    }
    await flush();
    return json({ ok: errors.length === 0, n, errors: errors.slice(0, 5) });
  }
  if (action === 'export') {
    const spec = EXPORT[table];
    if (!spec) return json({ error: 'bad table' }, 400);
    const after = url.searchParams.get('after') ?? '';
    const limit = Math.min(2000, Math.max(1, parseInt(url.searchParams.get('limit') ?? '500', 10) || 500));
    const numeric = spec.key === 'id';
    const rs = await db.prepare(`SELECT ${spec.cols} FROM ${table} WHERE ${spec.key} > ? ORDER BY ${spec.key} LIMIT ?`)
      .bind(numeric ? Number(after || 0) : after, limit).all<Row>();
    const out: string[] = [];
    for (const r of rs.results) {
      if ('body_gz' in r) { r.body = await unpackBody(r); delete r.body_gz; }
      out.push(JSON.stringify(r));
    }
    return resp(out.join('\n') + (out.length ? '\n' : ''), 200, { 'Content-Type': 'application/x-ndjson; charset=utf-8' });
  }
  return json({ error: 'unknown' }, 404);
}
