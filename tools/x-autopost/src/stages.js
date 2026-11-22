/* =====================================================================
   段階に分けた自動投稿（2026-11-23）
     取得 fetch … 予想（朝）・結果（夜）をページに作らせてデータベースに保存させる。保存できた件数を数えて確認する
     生成 gen   … 保存したものから画像と文を作り、ここ（xpost_gen 表）に保存する。画像の枚数・文の有無を確認する
     投稿 post  … 保存した画像と文を X に出し、記録する
   各段階は、前の段階が「ok」のときだけ動く。欠けがあればそこで止め、理由を状態に残す（メールは呼ぶ側が送る）。
   状態は xpost_log の k="st:<日付>:<morning|evening>:<nar|jra>"、body={fetch:{s,at,...}, gen:{...}, post:{...}}。
     s … "ok"（済み）/"miss"（欠けあり）/"fail"（失敗）/"none"（出すものが無い日）/"run"（動いている途中）/"part"（途中まで投稿）
   ここはブラウザにも X にも触らない（試験しやすいように、通信は呼ぶ側の関数で受け取る）。
   ===================================================================== */
import { HITS_DDL } from "./hits.js";

export const STEPS = ["fetch", "gen", "post"];
const RUN_TTL = 15 * 60e3;   // 「動いている途中」の印がこれより古ければ、落ちたとみなす
const NO_RACE = /no races|レースがありません|確定レースなし/;
export const GEN_DDL = "CREATE TABLE IF NOT EXISTS xpost_gen (k TEXT PRIMARY KEY, date TEXT NOT NULL, body TEXT NOT NULL, ts INTEGER NOT NULL)";
const MAX_IMG_CHARS = 1900000;   // D1 の1行は2MBまで。画像1枚がこれを超えたら保存できない

const stKey = (date, kind, mode) => `st:${date}:${kind}:${mode}`;
export async function loadStage(env, date, kind, mode) {
  if (!env.DB) return {};
  await env.DB.prepare(HITS_DDL).run();
  const row = await env.DB.prepare("SELECT body FROM xpost_log WHERE k=?").bind(stKey(date, kind, mode)).first();
  if (!row || !row.body) return {};
  try { return JSON.parse(row.body) || {}; } catch { return {}; }
}
export async function saveStage(env, date, kind, mode, st) {
  if (!env.DB) return;
  await env.DB.prepare(HITS_DDL).run();
  await env.DB.prepare("INSERT OR REPLACE INTO xpost_log(k,date,mode,tweet_id,body,ts) VALUES(?,?,?,?,?,?)")
    .bind(stKey(date, kind, mode), date, mode, null, JSON.stringify(st), Date.now()).run();
}
/** その日の全部の段階の状態（確認の表示用） */
export async function listStages(env, date) {
  if (!env.DB) return [];
  await env.DB.prepare(HITS_DDL).run();
  const rs = await env.DB.prepare("SELECT k, body FROM xpost_log WHERE k LIKE ? ORDER BY k").bind(`st:${date}:%`).all();
  return ((rs && rs.results) || []).map(r => { let b = {}; try { b = JSON.parse(r.body); } catch {} const [, , kind, mode] = r.k.split(":"); return { kind, mode, ...b }; });
}
/** 動いている途中か（印が新しいときだけ） */
export function running(x, now = Date.now()) { return !!(x && x.s === "run" && now - (x.at || 0) < RUN_TTL); }

/* ---------- 保存した件数を数える（データベースの予想・結果） ---------- */
async function unpack(row) {
  if (row.body) return row.body;
  if (!row.body_gz) return null;
  try {
    const buf = row.body_gz instanceof ArrayBuffer ? row.body_gz : new Uint8Array(row.body_gz).buffer;
    const s = new Response(new Blob([buf]).stream().pipeThrough(new DecompressionStream("gzip")));
    return await s.text();
  } catch { return null; }
}
/** 保存した予想を場ごとに数える。races … その場の全レース（見送りを含む） */
export async function storedPredictions(env, date, mode) {
  const rs = await env.DB.prepare("SELECT k, body, body_gz FROM predictions WHERE date=? AND COALESCE(mode_raw,'')=?").bind(date, mode).all();
  const out = [];
  for (const row of (rs && rs.results) || []) {
    let j = null; try { j = JSON.parse(await unpack(row)); } catch {}
    if (!j || !Array.isArray(j.races)) { out.push({ tc: String(row.k).split("_").pop(), unreadable: 1, races: [] }); continue; }
    out.push({ tc: String(j.tc), trackName: String(j.trackName || ""), races: j.races.map(r => ({
      rid: r && r.race_id ? String(r.race_id) : null, no: r && r.no, skip: !!(r && r.skip), pred: !!(r && !r.skip && (r.marks || []).length) })) });
  }
  return out;
}
/** 保存した結果がある race_id の集まり */
export async function storedResults(env, rids) {
  const have = new Set();
  const ids = [...new Set(rids.filter(Boolean).map(String))];
  for (let i = 0; i < ids.length; i += 90) {
    const part = ids.slice(i, i + 90);
    const rs = await env.DB.prepare(`SELECT k FROM results WHERE k IN (${part.map(() => "?").join(",")})`).bind(...part).all();
    ((rs && rs.results) || []).forEach(r => have.add(String(r.k)));
  }
  return have;
}

/* ---------- 確認（ゲート）。通信しない ---------- */
/** 取得の確認。page＝ページの返事（tracks）、store＝storedPredictions の結果、expectRids＝朝の前に一覧から拾った race_id（中央）、results＝結果のある race_id
    返す: { s:"ok"|"miss"|"none", total, got, missing:[...], why } */
export function gateFetch(kind, page, store, { expectRids = [], results = null } = {}) {
  const tracks = (page && page.tracks) || [];
  if (kind === "morning") {
    const want = new Set(expectRids.map(String));
    tracks.forEach(t => (t.rids || []).forEach(r => want.add(String(r))));
    const have = new Map();
    store.forEach(t => t.races.forEach(r => { if (r.rid) have.set(r.rid, r); }));
    if (!want.size && !have.size) return { s: "none", total: 0, got: 0, missing: [], why: "予想するレースが無い日" };
    if (!want.size) store.forEach(t => t.races.forEach(r => { if (r.rid) want.add(r.rid); }));
    const missing = [];
    let gotN = 0;
    for (const rid of want) {
      const r = have.get(rid);
      if (!r) missing.push(rid + "（保存なし）");
      else if (!r.skip && !r.pred) missing.push(rid + "（印なし）");
      else gotN++;
    }
    store.filter(t => t.unreadable).forEach(t => missing.push("場" + t.tc + "（保存を読めない）"));
    tracks.filter(t => !t.total).forEach(t => missing.push((t.trackName || "場" + t.tc) + "（レースが取れない）"));
    const total = want.size;
    return missing.length
      ? { s: "miss", total, got: gotN, missing, why: `予想が欠けている（${missing.length}件）` }
      : { s: "ok", total, got: total, missing: [] };
  }
  // evening: 印を付けたレース（見送りを除く）の結果が、全部保存されているか。取消のレースは結果が無くてよい
  const pred = [];
  store.forEach(t => t.races.forEach(r => { if (r.pred && r.rid) pred.push(r.rid); }));
  if (!pred.length) return { s: "none", total: 0, got: 0, missing: [], why: "答え合わせするレースが無い日" };
  const cancelled = new Set();
  tracks.forEach(t => (t.cancelledRids || []).forEach(r => cancelled.add(String(r))));
  const missing = pred.filter(r => !(results && results.has(r)) && !cancelled.has(r));
  return missing.length
    ? { s: "miss", total: pred.length, got: pred.length - missing.length, missing, why: `結果が取れていないレースがある（${pred.length - missing.length}/${pred.length}）` }
    : { s: "ok", total: pred.length, got: pred.length, missing: [] };
}
/** 生成の確認。out＝ページの返事、expectCards＝朝の場の数（保存した予想の場の数） */
export function gateGen(kind, out, { expectCards = 0 } = {}) {
  const bad = [];
  const isImg = (x) => typeof x === "string" && x.startsWith("data:image/") && x.length > 1000;
  if (!out || !out.ok) return { s: "fail", why: String((out && out.error) || "生成できなかった") };
  if (kind === "morning") {
    const cards = out.cards || [];
    if (!cards.length) bad.push("場のカードが0枚");
    if (expectCards && cards.length !== expectCards) bad.push(`場のカードが ${cards.length}/${expectCards} 枚`);
    cards.forEach(c => { if (!isImg(c.image)) bad.push(`${c.trackName || c.tc} の画像が無い`); });
    if (out.summary && !isImg(out.summary.image)) bad.push("★勝負の画像が無い");
    if (!out.caption) bad.push("投稿の文が無い");
    const images = cards.length + (out.summary ? 1 : 0);
    return bad.length ? { s: "miss", images, why: bad.join("・") } : { s: "ok", images, posts: 1 };
  }
  const posts = out.posts || [];
  if (!posts.length) bad.push("投稿が0件");
  let images = 0;
  posts.forEach((p, i) => { if (!String(p.text || "").trim() && !(p.images || []).length) bad.push(`${i + 1}件目が空`); (p.images || []).forEach(x => { if (isImg(x)) images++; else bad.push(`${i + 1}件目の画像が壊れている`); }); });
  if (!images) bad.push("画像が0枚");
  return bad.length ? { s: "miss", images, why: bad.join("・") } : { s: "ok", images, posts: posts.length };
}

/* ---------- 生成物の保存（画像は1枚1行。D1 の1行2MBの上限のため） ---------- */
const genKey = (date, kind, mode) => `g:${date}:${kind}:${mode}`;
/** out の中の画像（data:image/...）を抜き出して別の行に置き、本体には {"$img":番号} を残す */
export function splitImages(out) {
  const imgs = [];
  const walk = (v) => {
    if (typeof v === "string" && v.startsWith("data:image/")) { imgs.push(v); return { $img: imgs.length - 1 }; }
    if (Array.isArray(v)) return v.map(walk);
    if (v && typeof v === "object") { const o = {}; for (const k of Object.keys(v)) o[k] = walk(v[k]); return o; }
    return v;
  };
  return { meta: walk(out), imgs };
}
export function joinImages(meta, imgs) {
  const walk = (v) => {
    if (v && typeof v === "object" && !Array.isArray(v) && Object.keys(v).length === 1 && Number.isInteger(v.$img)) return imgs[v.$img];
    if (Array.isArray(v)) return v.map(walk);
    if (v && typeof v === "object") { const o = {}; for (const k of Object.keys(v)) o[k] = walk(v[k]); return o; }
    return v;
  };
  return walk(meta);
}
export async function saveGen(env, date, kind, mode, out) {
  await env.DB.prepare(GEN_DDL).run();
  const { meta, imgs } = splitImages(out);
  const big = imgs.findIndex(x => x.length > MAX_IMG_CHARS);
  if (big >= 0) throw new Error(`画像が大きすぎて保存できない（${big + 1}枚目 ${Math.round(imgs[big].length / 1e6 * 10) / 10}MB）`);
  const base = genKey(date, kind, mode), now = Date.now();
  const stmts = [env.DB.prepare("DELETE FROM xpost_gen WHERE k LIKE ?").bind(base + ":%")];
  imgs.forEach((x, i) => stmts.push(env.DB.prepare("INSERT OR REPLACE INTO xpost_gen(k,date,body,ts) VALUES(?,?,?,?)").bind(`${base}:${i}`, date, x, now)));
  stmts.push(env.DB.prepare("INSERT OR REPLACE INTO xpost_gen(k,date,body,ts) VALUES(?,?,?,?)").bind(base, date, JSON.stringify({ meta, n: imgs.length }), now));
  for (let i = 0; i < stmts.length; i += 20) await env.DB.batch(stmts.slice(i, i + 20));
  // 4日より前の生成物は消す（投稿の記録・予想・結果は消さない。消すのはこの表の画像だけ）
  const old = new Date(Date.UTC(+date.slice(0, 4), +date.slice(4, 6) - 1, +date.slice(6, 8)) - 4 * 86400e3).toISOString().slice(0, 10).replace(/-/g, "");
  try { await env.DB.prepare("DELETE FROM xpost_gen WHERE date < ?").bind(old).run(); } catch {}
  return imgs.length;
}
export async function loadGen(env, date, kind, mode) {
  await env.DB.prepare(GEN_DDL).run();
  const base = genKey(date, kind, mode);
  const head = await env.DB.prepare("SELECT body FROM xpost_gen WHERE k=?").bind(base).first();
  if (!head) return null;
  const { meta, n } = JSON.parse(head.body);
  const imgs = [];
  for (let i = 0; i < n; i++) {
    const r = await env.DB.prepare("SELECT body FROM xpost_gen WHERE k=?").bind(`${base}:${i}`).first();
    if (!r) return null;   // 欠けていたら使わない（作り直す）
    imgs.push(r.body);
  }
  return joinImages(meta, imgs);
}

/* ---------- 依頼（手で段階を動かす）。10分ごとの回が1件ずつ動かす ---------- */
const jobKey = (date, kind, mode) => `job:${date}:${kind}:${mode}`;
const yday = (ms) => new Date((Number(ms) || Date.now()) + 9 * 3600e3 - 86400e3).toISOString().slice(0, 10).replace(/-/g, "");
const today = (ms) => new Date((Number(ms) || Date.now()) + 9 * 3600e3).toISOString().slice(0, 10).replace(/-/g, "");
/** step … "fetch"|"gen"|"post"|"all"（all＝足りない段階から最後まで）。force＝済みの取得・生成をやり直す（投稿済みは何をしても出し直さない） */
export async function queueJob(env, ms, { kind, mode, date, step, force, accept }) {
  if (!env.DB) return { refused: true, reason: "DB が無い" };
  if (kind !== "morning" && kind !== "evening") return { refused: true, reason: "kind は morning か evening" };
  if (mode !== "nar" && mode !== "jra") return { refused: true, reason: "mode は nar か jra" };
  const steps = step === "all" || !step ? STEPS.slice() : STEPS.includes(step) ? [step] : null;
  if (!steps) return { refused: true, reason: "step は fetch・gen・post・all のどれか" };
  const d = String(date || today(ms));
  if (d !== today(ms) && d !== yday(ms)) return { refused: true, reason: "日付は今日か昨日だけ" };
  const st = await loadStage(env, d, kind, mode);
  if (steps.includes("post") && st.post && (st.post.s === "ok" || st.post.s === "part")) return { refused: true, reason: "もう投稿しています（二重には出しません）", state: st };
  await env.DB.prepare(HITS_DDL).run();
  const k = jobKey(d, kind, mode);
  const row = await env.DB.prepare("SELECT body FROM xpost_log WHERE k=?").bind(k).first();
  if (row && row.body) { try { const j = JSON.parse(row.body); if (j && !j.done) return { refused: true, reason: "待っている依頼があります（10分以内に動きます）", pending: j }; } catch {} }
  const job = { kind, mode, date: d, steps, force: !!force, accept: !!accept, at: Date.now() };
  await env.DB.prepare("INSERT OR REPLACE INTO xpost_log(k,date,mode,tweet_id,body,ts) VALUES(?,?,?,?,?,?)").bind(k, d, mode, null, JSON.stringify(job), Date.now()).run();
  return { queued: true, ...job, note: "次の10分ごとの回で動きます。結果はメールと /stage の表示で分かります" };
}
/** 待っている依頼を1件動かす。run(job) は summary を返す関数、notify(kind, summary, note) はメール */
export async function runJobs(env, ms, run, notify) {
  if (!env.DB) return null;
  await env.DB.prepare(HITS_DDL).run();
  const rs = await env.DB.prepare("SELECT k, body FROM xpost_log WHERE k LIKE 'job:%' AND (date=? OR date=?) ORDER BY ts").bind(today(ms), yday(ms)).all();
  for (const row of (rs && rs.results) || []) {
    let j = null; try { j = JSON.parse(row.body); } catch { continue; }
    if (!j || j.done) continue;
    // 先に「済み」の印（途中で落ちても二重に動かさない）
    await env.DB.prepare("UPDATE xpost_log SET body=?, ts=? WHERE k=?").bind(JSON.stringify({ ...j, done: 1, started: Date.now() }), Date.now(), row.k).run();
    let s = null;
    try { s = await run(j); } catch (e) { s = { modes: { [j.mode]: { ok: false, error: String(e && e.message || e) } } }; }
    const r = (s && s.modes && s.modes[j.mode]) || { ok: false, error: "結果なし" };
    await env.DB.prepare("UPDATE xpost_log SET body=?, ts=? WHERE k=?").bind(JSON.stringify({ ...j, done: 1, ok: !!r.ok && !r.error, error: r.error ? String(r.error).slice(0, 300) : null, stage: r.stage || null }), Date.now(), row.k).run();
    try { await notify(j.kind, { kind: j.kind, dry: false, at: new Date().toISOString(), modes: { [j.mode]: r } }, `依頼された段階（${j.date} ${j.steps.join("→")}）`); } catch {}
    return { job: j, result: r };
  }
  return null;
}
export async function listJobs(env, date) {
  if (!env.DB) return [];
  const rs = await env.DB.prepare("SELECT k, body FROM xpost_log WHERE k LIKE ?").bind(`job:${date}:%`).all();
  return ((rs && rs.results) || []).map(r => { try { return JSON.parse(r.body); } catch { return { k: r.k }; } });
}

/** 中央の先行取得の回か（日本時間 7:00・7:20・7:40・8:00）。最後の回だけ、欠けをメールで知らせる */
export function earlyFetchTime(ms) {
  const j = new Date((Number(ms) || Date.now()) + 9 * 3600e3), h = j.getUTCHours(), m = j.getUTCMinutes();
  if (h === 7 && (m === 0 || m === 20 || m === 40)) return { last: false };
  if (h === 8 && m === 0) return { last: true };
  return null;
}
export const isNoRace = (e) => NO_RACE.test(String(e || ""));
