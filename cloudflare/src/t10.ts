/* 発走10分前の記録（投稿はしない・記録だけ）
 *   5分ごとの oddsCron が取っている単勝オッズのうち、発走の 8〜12分前に取れた1回ぶんを t10_log に残す。
 *   同時に、その時点で保存されている予想（predictions）の◎を一緒に残す。
 *   目的: 「10分前のオッズで◎が1番人気／鉄板のレースだけ出す」案を、確定オッズではなく
 *        実際に手に入る10分前のオッズで確かめる（2026-11-13 ユーザー指示「記録だけとっといて」）。
 *   1レース1行（先に入った記録を残す）。失敗しても oddsCron を止めない（呼び出し側で握りつぶす）。 */
import { Env, safeKey, unpackBody, isObj } from './lib';

export const T10_FROM = 8, T10_TO = 12;          // 発走の何分前に取れた記録を残すか
const IRON_ODDS_MAX = 1.9, IRON_FIELD_MAX = 10;   // tweet.html の「鉄板」と同じ条件（◎が1番人気・1.9倍以下・10頭以下）

export const T10_DDL = `CREATE TABLE IF NOT EXISTS t10_log (
  rid    TEXT PRIMARY KEY,
  date   TEXT NOT NULL,
  mode   TEXT NOT NULL,
  track  TEXT,
  no     INTEGER,
  post   TEXT,
  ts     INTEGER NOT NULL,   -- 記録した時刻（秒）
  mtp    INTEGER NOT NULL,   -- 発走まで何分だったか
  field  INTEGER NOT NULL,   -- オッズが出ていた頭数
  o_num  TEXT,               -- その時点で保存されていた◎の馬番（予想が無ければ NULL）
  o_odds REAL,               -- ◎の単勝オッズ
  o_pop  INTEGER,            -- ◎の人気
  gap    REAL,               -- ◎と○の点差
  fav    INTEGER,            -- ◎が1番人気なら 1
  iron   INTEGER,            -- 鉄板の条件を満たせば 1
  mv     TEXT,               -- 予想を出したモデルのバージョン
  body   TEXT NOT NULL       -- 全頭の単勝オッズ {馬番: オッズ}
)`;

export interface T10Race { race_id: string; mode: string; track: string; no: number; post: string | null }
type PredCache = Map<string, Record<string, unknown> | null>;

/** オッズの低い順に人気を振る（同じオッズは同じ人気） */
export function popOf(win: Record<string, number>): Record<string, number> {
  const arr = Object.entries(win).filter(([, o]) => o > 0).sort((a, b) => a[1] - b[1]);
  const out: Record<string, number> = {};
  let prev: number | null = null, rank = 0;
  arr.forEach(([num, o], i) => { if (prev === null || o !== prev) rank = i + 1; out[num] = rank; prev = o; });
  return out;
}

async function loadPred(env: Env, cache: PredCache, date: string, mode: string, tc: string) {
  const k = safeKey(`${date}_${mode}_${tc}`);
  if (cache.has(k)) return cache.get(k) ?? null;
  let rec: Record<string, unknown> | null = null;
  try {
    const row = await env.DB.prepare('SELECT body, body_gz FROM predictions WHERE k=?').bind(k).first<{ body?: unknown; body_gz?: unknown }>();
    if (row) { const j = JSON.parse(await unpackBody(row)); if (isObj(j)) rec = j; }
  } catch { rec = null; }
  cache.set(k, rec);
  return rec;
}

/** 記録する1行を組み立てる（DBに触らない。試験しやすいように分けてある） */
export function buildT10(r: T10Race, date: string, mtp: number, ts: number, win: Record<string, number>, pred: Record<string, unknown> | null) {
  const pops = popOf(win);
  const field = Object.keys(pops).length;
  let oNum: string | null = null, gap: number | null = null, mv: string | null = null;
  if (pred) {
    mv = typeof pred.mv === 'string' ? pred.mv : null;
    const races = Array.isArray(pred.races) ? (pred.races as Record<string, any>[]) : [];
    const m = races.find((x) => x && String(x.race_id) === r.race_id);
    if (m && !m.skip && Array.isArray(m.marks) && m.marks[0] && m.marks[0].num != null) {
      oNum = String(parseInt(String(m.marks[0].num), 10));
      const rk = Array.isArray(m.ranked) ? m.ranked : [];
      if (rk.length >= 2 && typeof rk[0]?.s === 'number' && typeof rk[1]?.s === 'number') gap = Math.round((rk[0].s - rk[1].s) * 10) / 10;
    }
  }
  const oOdds = oNum !== null && win[oNum] > 0 ? win[oNum] : null;
  const oPop = oNum !== null && pops[oNum] ? pops[oNum] : null;
  const fav = oPop === 1 ? 1 : 0;
  const iron = (r.mode === 'nar' && fav === 1 && oOdds !== null && oOdds <= IRON_ODDS_MAX && field <= IRON_FIELD_MAX) ? 1 : 0;
  return { rid: r.race_id, date, mode: r.mode === 'nar' ? 'nar' : 'jra', track: r.track, no: r.no, post: r.post, ts, mtp, field, o_num: oNum, o_odds: oOdds, o_pop: oPop, gap, fav, iron, mv, body: JSON.stringify(win) };
}

let ddlDone = false;
export async function recordT10(env: Env, cache: PredCache, r: T10Race, date: string, mtp: number, ts: number, win: Record<string, number>): Promise<boolean> {
  if (mtp < T10_FROM || mtp > T10_TO) return false;
  if (!ddlDone) { await env.DB.prepare(T10_DDL).run(); ddlDone = true; }
  const mode = r.mode === 'nar' ? 'nar' : 'jra';
  const pred = await loadPred(env, cache, date, mode, r.race_id.slice(4, 6));
  const x = buildT10(r, date, mtp, ts, win, pred);
  const res = await env.DB.prepare(
    `INSERT OR IGNORE INTO t10_log(rid,date,mode,track,no,post,ts,mtp,field,o_num,o_odds,o_pop,gap,fav,iron,mv,body)
     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`,
  ).bind(x.rid, x.date, x.mode, x.track, x.no, x.post, x.ts, x.mtp, x.field, x.o_num, x.o_odds, x.o_pop, x.gap, x.fav, x.iron, x.mv, x.body).run();
  return (res.meta?.changes ?? 0) > 0;
}
