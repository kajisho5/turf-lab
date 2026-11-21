// 朝の予想の前に、中央のページ（開催一覧と出馬表）を少しずつ取っておく（2026-11-15）
// なぜ: 中央のページは、うちのサーバーから取りに行くと断られることが多い。8:30 に 36 レースぶんを一気に取りに行くと取れず、
//       11/15 は朝の予想が出なかった。サイトの中継（proxy.php）は一度取れたページを6時間は取っておき、取れなかった時にそれを返す。
//       なので 5:00〜8:20 に少しずつ取りに行っておけば、8:30 の回は取っておいたものを使える。
// 何も投稿しない。鍵も使わない。触るのは自分のサイトの中継と、進み具合の記録（xpost_log の wm:日付）だけ。
import { HITS_DDL } from "./hits.js";
const SITE = "https://seventh-well.com/odds";
export const WARM_MAX = 6, WARM_GAP_MS = 3000;
const b64u = s => btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const jstParts = ms => { const j = new Date((Number(ms) || Date.now()) + 9 * 3600e3); return { h: j.getUTCHours(), m: j.getUTCMinutes(), date: j.toISOString().slice(0, 10).replace(/-/g, "") }; };
/** 取っておく回か。日本時間 5:00〜8:20 の10分おき */
export function warmSlot(ms) { const { h, m } = jstParts(ms); return m % 10 === 0 && (h >= 5 && (h < 8 || (h === 8 && m <= 20))); }
/** 一覧のページからレースの番号を拾う（重複なし・並びはそのまま） */
export function listRids(html) { return [...new Set((String(html || "").match(/race_id=(\d{12})/g) || []).map(s => s.slice(8)))]; }
/** 今回取りに行くもの。まだのものから max 件。見はじめる場所は回ごとにずらす（同じレースで詰まり続けないように） */
export function pickWarm(rids, done, slot, max = WARM_MAX) {
  const d = new Set(done || []), left = (rids || []).filter(r => !d.has(r));
  if (!left.length) return [];
  const s = ((Number(slot) || 0) % left.length + left.length) % left.length;
  return left.slice(s).concat(left.slice(0, s)).slice(0, max);
}
async function via(url) {
  try {
    const h = await fetch(`${SITE}/proxy.php?u=${b64u(url)}&_=${Date.now()}`);
    const t = h.ok ? await h.text() : "";
    return { ok: h.ok, text: t, how: (h.headers && h.headers.get && h.headers.get("x-proxy-cache")) || "" };
  } catch { return { ok: false, text: "", how: "" }; }
}
export async function runWarm(env, ms, { sleep } = {}) {
  if (!warmSlot(ms) || !env.DB) return null;
  const { date, h, m } = jstParts(ms), k = `wm:${date}`;
  const dow = new Date((Number(ms) || Date.now()) + 9 * 3600e3).getUTCDay(), weekend = dow === 0 || dow === 6 || dow === 1;   // 月曜も最後まで見る（祝日の開催がある）
  const wait = sleep || (t => new Promise(r => setTimeout(r, t)));
  await env.DB.prepare(HITS_DDL).run();
  const row = await env.DB.prepare("SELECT body FROM xpost_log WHERE k=?").bind(k).first();
  let st = { rids: [], done: [], none: 0, tries: 0 };
  try { if (row && row.body) st = Object.assign(st, JSON.parse(row.body)); } catch {}
  if (st.none) return { date, none: true };
  const save = () => env.DB.prepare("INSERT OR REPLACE INTO xpost_log(k,date,mode,tweet_id,body,ts) VALUES(?,?,?,?,?,?)").bind(k, date, "jra", null, JSON.stringify(st), Date.now()).run();
  if (!st.rids.length) {
    const r = await via(`https://race.netkeiba.com/top/race_list_sub.html?kaisai_date=${date}`);
    const rids = listRids(r.text);
    st.tries = (st.tries || 0) + 1;
    if (rids.length) st.rids = rids;
    // 土日は最後まで取りに行く（取れないのか開催が無いのかは中身では決めない。中継が空のページを返すことがある）。
    // 平日は中央の開催がほぼ無いので、3回見て無ければ今日はもう見ない
    else if (!weekend && st.tries >= 3) st.none = 1;
    await save();
    if (!st.rids.length) return { date, list: false, none: !!st.none };
    await wait(WARM_GAP_MS);
  }
  const pick = pickWarm(st.rids, st.done, h * 6 + Math.floor(m / 10));
  let got = 0;
  for (let i = 0; i < pick.length; i++) {
    if (i) await wait(WARM_GAP_MS);
    const r = await via(`https://race.netkeiba.com/race/shutuba_past.html?race_id=${pick[i]}`);
    if (r.ok && r.text.length > 20000) { st.done.push(pick[i]); got++; }
  }
  if (got) await save();
  return { date, races: st.rids.length, done: st.done.length, tried: pick.length, got };
}
