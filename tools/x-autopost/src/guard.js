/* =====================================================================
   自動投稿の見張り（2026-11-13）
   1) やり直し: 朝・夜の回が失敗したモードだけ、あとの回（朝 9:00・9:20／夜 22:50・23:10）で出し直す。
      ・鍵の失敗（Xが認証を断った）は出し直しても同じなので、やり直さない。
      ・途中まで投稿できた回、動いた記録が途中で切れている回は、二重投稿になり得るのでやり直さない（メールで知らせる）。
   2) 朝の前の点検（6:30）: 鍵・ページと索引が読めるか・索引の日付・記録の置き場を確かめ、問題がある時だけメールする。
      ブラウザは使わない（投稿も予想の保存もしない）。
   記録は D1 の xpost_log に 's:日付:morning|evening' で残す（body に各モードの状態）。
   ===================================================================== */
import { HITS_DDL } from "./hits.js";

export const GUARD_FROM = "20261114";   // この日より前は「記録が無い＝動いていない」とは見なさない（仕組みを入れる前の回には記録が無い）
const SITE = "https://seventh-well.com/odds";

export function jst(ms) {
  const j = new Date((Number(ms) || Date.now()) + 9 * 3600e3);
  return { date: j.toISOString().slice(0, 10).replace(/-/g, ""), h: j.getUTCHours(), m: j.getUTCMinutes() };
}
/** 朝の前の点検の時刻か（日本時間 5:00〜7:59 に動いた回） */
export function isRehearsalTime(ms) { const { h } = jst(ms); return h >= 5 && h < 8; }
/** やり直しを見る回か。朝 9:00・9:20 → "morning"／夜 22:50・23:10 → "evening"／それ以外 null */
export function retryKind(ms) {
  const { h, m } = jst(ms);
  if (h === 9 && (m === 0 || m === 20)) return "morning";
  if ((h === 22 && m === 50) || (h === 23 && m === 10)) return "evening";
  return null;
}
/** 週間まとめを出す回か。月曜の 9:10・12:10・15:10（日本時間）なら「先週の月曜の日付」を返す。それ以外は null。
    1回目で出せなかった時（毎朝の公開が遅れて日曜ぶんの結果がまだ無い等）だけ、あとの回が出す */
export function weeklyTarget(ms) {
  const t = (Number(ms) || Date.now()) + 9 * 3600e3, j = new Date(t);
  if (j.getUTCDay() !== 1 || j.getUTCMinutes() !== 10 || ![9, 12, 15].includes(j.getUTCHours())) return null;
  return new Date(t - 7 * 86400e3).toISOString().slice(0, 10).replace(/-/g, "");
}
/** 週間まとめの二重投稿の防止。まだ出していなければ印を付けて true（印が付けられた時だけ投稿する） */
export async function claimWeekly(env, wk) {
  if (!env.DB) return false;
  await env.DB.prepare(HITS_DDL).run();
  const r = await env.DB.prepare("INSERT OR IGNORE INTO xpost_log(k,date,mode,tweet_id,body,ts) VALUES(?,?,?,?,?,?)")
    .bind(`w:${wk}`, wk, "nar", null, null, Date.now()).run();
  return !!(r.meta && r.meta.changes);
}
export async function weeklyDone(env, wk) {
  if (!env.DB) return true;
  await env.DB.prepare(HITS_DDL).run();
  return !!(await env.DB.prepare("SELECT k FROM xpost_log WHERE k=?").bind(`w:${wk}`).first());
}
const NO_RACE = /no races|レースがありません|0件|count":0/;
const AUTH = /Bad Authentication|Unauthorized|Could not authenticate|"code":\s*(215|32|89)\b|\b(401|403):/i;
/** 1モードぶんの結果 → "ok"（投稿した）/"part"（途中まで）/"none"（出すものが無い）/"dry"/"auth"（鍵）/"fail"（やり直せる失敗） */
export function modeState(m) {
  if (!m) return "fail";
  if (m.posted && m.posted.length) return "ok";
  if (m.partial && m.partial.length) return "part";
  if (m.error) {
    const e = String(m.error);
    if (NO_RACE.test(e)) return "none";
    if (AUTH.test(e)) return "auth";
    return "fail";
  }
  if ((m.posts || []).length) return "dry";
  return "none";
}
export function stateOf(summary, modes) {
  const out = {};
  for (const mode of modes) out[mode] = (summary && summary.dry && !((summary.modes || {})[mode] || {}).error) ? "dry" : modeState(((summary && summary.modes) || {})[mode]);
  return out;
}
const key = (date, kind) => `s:${date}:${kind}`;
export async function markStart(env, date, kind) {
  if (!env.DB) return;
  await env.DB.prepare(HITS_DDL).run();
  await env.DB.prepare("INSERT OR IGNORE INTO xpost_log(k,date,mode,tweet_id,body,ts) VALUES(?,?,?,?,?,?)")
    .bind(key(date, kind), date, "-", null, JSON.stringify({ started: 1 }), Date.now()).run();
}
export async function saveState(env, date, kind, st) {
  if (!env.DB) return;
  await env.DB.prepare(HITS_DDL).run();
  await env.DB.prepare("INSERT OR REPLACE INTO xpost_log(k,date,mode,tweet_id,body,ts) VALUES(?,?,?,?,?,?)")
    .bind(key(date, kind), date, "-", null, JSON.stringify(st), Date.now()).run();
}
export async function loadState(env, date, kind) {
  if (!env.DB) return undefined;
  await env.DB.prepare(HITS_DDL).run();
  const row = await env.DB.prepare("SELECT body FROM xpost_log WHERE k=?").bind(key(date, kind)).first();
  if (!row) return null;
  try { return JSON.parse(row.body); } catch { return { broken: 1 }; }
}
/** 記録から「やり直すモード」と「知らせるだけの注意」を決める（ここは通信しない） */
export function planRetry(st, date, modes) {
  if (st === undefined) return { run: [], warn: null };                         // DB が無い
  if (st === null) return date >= GUARD_FROM ? { run: modes.slice(), warn: null, fresh: true } : { run: [], warn: null };
  if (!st.modes) return { run: [], warn: st.warned ? null : "回が途中で止まった記録があります（投稿できたか分かりません）。Xを見て、出ていなければ手で出してください。" };
  if ((st.tries || 0) >= 2) return { run: [], warn: null };
  return { run: modes.filter(mode => st.modes[mode] === "fail"), warn: null };
}
/** やり直しの回。runAll(kind, mode) は1モードだけ回して summary を返す関数、notify(kind, summary, note) はメール */
export async function runRetry(env, ms, modes, runAll, notify) {
  const kind = retryKind(ms); if (!kind) return null;
  const { date } = jst(ms);
  const st = await loadState(env, date, kind);
  const plan = planRetry(st, date, modes);
  if (plan.warn) {
    await saveState(env, date, kind, Object.assign({}, st, { warned: 1 }));
    await notify(kind, null, plan.warn);
    return { kind, date, warned: true };
  }
  let run = plan.run;
  if (plan.fresh && kind === "morning") {
    // 記録が無い日でも、朝の投稿のIDが残っているモードは出し直さない
    const keep = [];
    for (const mode of run) {
      const m = await env.DB.prepare("SELECT tweet_id FROM xpost_log WHERE k=?").bind(`m:${date}:${mode}`).first();
      if (!m || !m.tweet_id) keep.push(mode);
    }
    run = keep;
  }
  if (!run.length) return { kind, date, run: [] };
  const next = { modes: Object.assign({}, (st && st.modes) || {}), tries: ((st && st.tries) || 0) + 1 };
  await saveState(env, date, kind, Object.assign({}, next, { modes: Object.assign({}, next.modes, Object.fromEntries(run.map(m => [m, "part"]))) }));   // 先に「触った」印（途中で落ちても二重に出さない）
  const merged = { kind, dry: false, at: new Date().toISOString(), modes: {} };
  for (const mode of run) {
    let s = null;
    try { s = await runAll(kind, mode); } catch (e) { s = { modes: { [mode]: { ok: false, error: String(e && e.message || e) } } }; }
    merged.modes[mode] = (s && s.modes && s.modes[mode]) || { ok: false, error: "結果なし" };
    next.modes[mode] = modeState(merged.modes[mode]);
  }
  await saveState(env, date, kind, next);
  await notify(kind, merged, `やり直し（${next.tries}回目）`);
  return { kind, date, run, state: next };
}

/** 朝の前の点検。問題の一覧（空なら問題なし）を返す。whoami() は { ok, status, body } を返す関数 */
export async function rehearsal(env, ms, whoami, get = fetch) {
  const bad = [];
  try { const w = await whoami(); if (!w.ok) bad.push(`Xの鍵が通りません（Xの返答 ${w.status}）: ${String(w.body || "").slice(0, 160)}`); }
  catch (e) { bad.push("Xの鍵を確かめられませんでした（通信の失敗）: " + String(e && e.message || e)); }
  const t = Date.now();
  for (const [f, need] of [["tweet.html", "__autoOut"], ["core/ltr_model_t.js", "narT"], ["data/horses.json", "{"], ["data/horses_time.json", "{"]]) {
    try {
      const r = await get(`${SITE}/${f}?_=${t}`);
      const head = r.ok ? (f === "tweet.html" || f.endsWith(".js") ? await r.text() : (await r.text()).slice(0, 50)) : "";
      if (!r.ok) bad.push(`${f} が読めません（${r.status}）`);
      else if (!head.includes(need)) bad.push(`${f} の中身がおかしい（目印が見つからない）`);
    } catch (e) { bad.push(`${f} が読めません: ` + String(e && e.message || e)); }
  }
  try {
    const r = await get(`${SITE}/data/nar_index_asof.json?_=${t}`);
    const j = await r.json();
    const d2 = jst((Number(ms) || Date.now()) - 2 * 86400e3).date;       // おととい
    if (!j.asof || String(j.asof) < d2) bad.push(`成績の索引が古いままです（${j.asof || "不明"} まで）。毎朝の公開が2日以上止まっています。`);
  } catch (e) { bad.push("索引の日付を読めません: " + String(e && e.message || e)); }
  try { if (env.DB) await env.DB.prepare("SELECT 1").first(); else bad.push("記録の置き場（D1）がつながっていません"); }
  catch (e) { bad.push("記録の置き場（D1）が読めません: " + String(e && e.message || e)); }
  return bad;
}
