/* predictions.php の置き換え（予想の保存/一覧・狙い目ロック） */
import {
  Ctx, CORS, JSON_CT, NO_STORE, json, resp, q, readJson, isObj, isset, empty, phpStr, safeKey,
  dateC, packBody, unpackBody, streamJson,
} from '../lib';

const H = { ...CORS, 'Content-Type': JSON_CT, 'Cache-Control': NO_STORE };
const reply = (o: unknown, status = 200) => json(o, status, H);

type Rec = Record<string, unknown>;
const modeRaw = (j: Rec) => (typeof j.mode === 'string' ? j.mode : isset(j.mode) ? phpStr(j.mode) : null);
const dateOf = (j: Rec) => (isset(j.date) ? phpStr(j.date) : '');
const tsOf = (j: Rec) => { const n = Number(j.ts ?? 0); return Number.isFinite(n) ? n : 0; };

export async function predictions(c: Ctx): Promise<Response> {
  const { env, req, url } = c;
  if (req.method === 'OPTIONS') return resp(null, 204, H);
  const action = q(url, 'action') ?? 'list';
  const db = env.DB;

  /* ---- 狙い目ロック ---- */
  if (action === 'savelock') {
    const rec = await readJson(req);
    if (!isObj(rec) || empty(rec) || empty(rec.date) || !isset(rec.tc)) return reply({ ok: false }, 400);
    const mode = isset(rec.mode) ? phpStr(rec.mode) : 'nar';
    rec.savedAt = dateC();
    const k = safeKey(phpStr(rec.date) + '_' + mode + '_' + phpStr(rec.tc));
    await db.prepare('INSERT OR REPLACE INTO locks(k,date,mode_raw,body) VALUES(?,?,?,?)')
      .bind(k, dateOf(rec), modeRaw(rec), JSON.stringify(rec)).run();
    return reply({ ok: true });
  }
  if (action === 'listlocks') {
    const date = q(url, 'date') ?? '';
    const mode = q(url, 'mode') ?? '';
    const rs = await db.prepare(
      `SELECT body FROM locks WHERE (?1 IN ('','0') OR date = ?1) AND (?2 IN ('','0') OR COALESCE(mode_raw,'') = ?2) ORDER BY k`,
    ).bind(date, mode).all<{ body: string }>();
    return resp('{"locks":[' + rs.results.map((r) => r.body).join(',') + ']}', 200, H);
  }
  if (action === 'deletelock') {
    const date = q(url, 'date') ?? ''; const mode = q(url, 'mode') ?? 'nar'; const tc = q(url, 'tc') ?? '';
    if (date !== '' && tc !== '') await db.prepare('DELETE FROM locks WHERE k=?').bind(safeKey(`${date}_${mode}_${tc}`)).run();
    return reply({ ok: true });
  }

  /* ---- 1件取得 ---- */
  if (action === 'get') {
    const date = q(url, 'date') ?? ''; const mode = q(url, 'mode') ?? 'nar'; const tc = q(url, 'tc') ?? '';
    if (date === '' || tc === '') return reply({ miss: true });
    const row = await db.prepare('SELECT body, body_gz FROM predictions WHERE k=?').bind(safeKey(`${date}_${mode}_${tc}`)).first();
    if (row) return resp(await unpackBody(row), 200, H);
    return reply({ miss: true });
  }

  /* ---- 削除 ---- */
  if (action === 'delete') {
    const date = q(url, 'date') ?? ''; const mode = q(url, 'mode') ?? 'nar'; const tc = q(url, 'tc') ?? '';
    if (date === '' || tc === '') return reply({ ok: false, error: 'date/tc required' });
    const r = await db.prepare('DELETE FROM predictions WHERE k=?').bind(safeKey(`${date}_${mode}_${tc}`)).run();
    return reply({ ok: (r.meta.changes ?? 0) > 0 });
  }

  /* ---- 保存 ---- */
  if (action === 'save') {
    const rec = await readJson(req);
    if (!isObj(rec) || empty(rec) || empty(rec.date) || !isset(rec.tc)) return reply({ ok: false, error: 'invalid payload' }, 400);
    const mode = isset(rec.mode) ? phpStr(rec.mode) : 'nar';
    const key = phpStr(rec.date) + '_' + mode + '_' + phpStr(rec.tc);
    const k = safeKey(key);
    // ★noclobber★ 既に記録があれば上書きしない（朝の版を再採点で潰さない）
    if (!empty(rec.noclobber)) {
      const ex = await db.prepare('SELECT 1 AS x FROM predictions WHERE k=?').bind(k).first();
      if (ex) return reply({ ok: true, kept: true, key });
    }
    rec.savedAt = dateC();
    const s = JSON.stringify(rec);
    try {
      const p = await packBody(s);
      await db.prepare('INSERT OR REPLACE INTO predictions(k,date,mode_raw,ts,body,body_gz) VALUES(?,?,?,?,?,?)')
        .bind(k, dateOf(rec), modeRaw(rec), tsOf(rec), p.body, p.gz).run();
    } catch (e) {
      console.error('predictions save', e);
      return reply({ ok: false, error: 'disk full or write failed', wrote: -1 });
    }
    return reply({ ok: true, key });
  }

  /* ---- 一覧（全件は数十MBになるので分割して流す） ---- */
  if (action === 'list') {
    const date = q(url, 'date') ?? '';
    const mode = q(url, 'mode') ?? '';
    const PAGE = 40;
    return streamJson(H, async (write) => {
      await write('{"records":[');
      let first = true;
      for (let off = 0; ; off += PAGE) {
        const rs = await db.prepare(
          `SELECT body, body_gz FROM predictions
             WHERE (?1 IN ('','0') OR date = ?1) AND (?2 IN ('','0') OR COALESCE(mode_raw,'') = ?2)
             ORDER BY date DESC, ts DESC, k ASC LIMIT ?3 OFFSET ?4`,
        ).bind(date, mode, PAGE, off).all();
        for (const r of rs.results) {
          const b = await unpackBody(r as { body?: unknown; body_gz?: unknown });
          if (!b) continue;
          await write((first ? '' : ',') + b);
          first = false;
        }
        if (rs.results.length < PAGE) break;
      }
      await write(']}');
    });
  }

  /* ---- 件数の確認（2026-11-23・自動投稿の段階の確認用。読むだけ）----
     ?action=summary&date=YYYYMMDD&mode=nar|jra → 場ごとに レース数・印あり・見送り・印なし（欠け）・結果のある数 */
  if (action === 'summary') {
    const date = q(url, 'date') ?? ''; const mode = q(url, 'mode') ?? '';
    if (!/^\d{8}$/.test(date) || (mode !== 'nar' && mode !== 'jra')) return reply({ ok: false, error: 'date=YYYYMMDD と mode=nar|jra が必要' }, 400);
    const rs = await db.prepare('SELECT k, body, body_gz FROM predictions WHERE date=? AND COALESCE(mode_raw,\'\')=? ORDER BY k').bind(date, mode).all();
    const tracks: Rec[] = []; const predRids: string[] = [];
    for (const row of rs.results) {
      let j: Rec | null = null;
      try { j = JSON.parse(await unpackBody(row as { body?: unknown; body_gz?: unknown })) as Rec; } catch { j = null; }
      const races = (j && Array.isArray(j.races)) ? (j.races as Rec[]) : [];
      const pred = races.filter((r) => r && !r.skip && Array.isArray(r.marks) && (r.marks as unknown[]).length);
      pred.forEach((r) => { if (r.race_id) predRids.push(String(r.race_id)); });
      tracks.push({ tc: j ? phpStr(j.tc) : String((row as Rec).k), trackName: j ? phpStr(j.trackName ?? '') : '', races: races.length,
        pred: pred.length, skip: races.filter((r) => r && r.skip).length,
        noMarks: races.filter((r) => r && !r.skip && !(Array.isArray(r.marks) && (r.marks as unknown[]).length)).length,
        predRids: pred.map((r) => String(r.race_id ?? '')), unreadable: j ? 0 : 1 });
    }
    const have = new Set<string>();
    for (let i = 0; i < predRids.length; i += 90) {
      const part = predRids.slice(i, i + 90).map(safeKey);
      const r2 = await db.prepare(`SELECT k FROM results WHERE k IN (${part.map(() => '?').join(',')})`).bind(...part).all<{ k: string }>();
      r2.results.forEach((x) => have.add(x.k));
    }
    let pred = 0, res = 0;
    for (const t of tracks) {
      const ids = (t.predRids as string[]);
      t.results = ids.filter((x) => have.has(safeKey(x))).length;
      t.noResult = ids.filter((x) => !have.has(safeKey(x)));
      pred += ids.length; res += t.results as number;
      delete t.predRids;
    }
    return reply({ ok: true, date, mode, tracks, total: { tracks: tracks.length, pred, results: res } });
  }

  /* ---- 保存日一覧 ---- */
  if (action === 'dates') {
    const rs = await db.prepare(
      `SELECT COALESCE(mode_raw,'jra') AS m, date, MAX(ts) AS ts, MIN(k) AS fk FROM predictions
         WHERE date NOT IN ('','0') GROUP BY m, date ORDER BY ts DESC, fk ASC`,
    ).all<{ m: string; date: string; ts: number; fk: string }>();
    const items = rs.results.map((r) => ({ mode: r.m, date: r.date, ts: r.ts }));
    // array_keys() は数字だけのキーを整数に変える（"20261029" → 20261029）。PHP版の出力に合わせる
    const dates: (string | number)[] = [];
    const seen = new Set<string>();
    for (const it of items) {
      if (seen.has(it.date)) continue; seen.add(it.date);
      dates.push(/^(0|-?[1-9]\d{0,17})$/.test(it.date) && Number.isSafeInteger(Number(it.date)) ? Number(it.date) : it.date);
    }
    return reply({ items, dates });
  }

  return reply({ ok: false, error: 'unknown action' }, 400);
}
