/* 重賞の日の1枚（2026-11-13・docs/design/X_HIT_AND_GRADE_DESIGN.md）
   朝の回で分かった重賞のレースを覚えておき、発走の2時間前に単独で1枚出す。予想は朝に出したものと同じ（作り直さない）。
   - 1日2本まで（格の高い順、同じなら発走の早い順）。地方と中央を合わせて数える。
   - 同じレースは1回だけ（先に記録が取れた時だけ投稿する）。発走10分前を過ぎたら出さない。
   - 止める時は wrangler.toml の GRADE を "0" にする。
   記録: gl:日付:モード＝その日の重賞の一覧／g:レースID＝出した記録 */
import { HITS_DDL, postMin } from "./hits.js";

export const GRADE_BEFORE_MIN = 120;   // 発走の何分前から出すか
export const GRADE_STOP_MIN = 10;      // 発走の何分前を過ぎたら出さないか
export const GRADE_MAX = 2;            // 1日に出す本数

/* 格の順位（小さいほど上）。G1・JpnⅠ=1／G2・JpnⅡ=2／G3・JpnⅢ=3／それ以外の重賞=4 */
export function gradeRank(g) {
  g = String(g || "");
  if (/^G1$|Jpn\s*[Ⅰ1]$/.test(g)) return 1;
  if (/^G2$|Jpn\s*[Ⅱ2]$/.test(g)) return 2;
  if (/^G3$|Jpn\s*[Ⅲ3]$/.test(g)) return 3;
  return 4;
}

/* その日の重賞（全モード）から、出す2本を選ぶ。list の要素は {rid,track,no,name,grade,post,mode} */
export function pickGrades(list) {
  return (list || []).filter(r => r && r.rid && postMin(r.post) != null)
    .slice().sort((a, b) => gradeRank(a.grade) - gradeRank(b.grade) || postMin(a.post) - postMin(b.post) || (a.rid < b.rid ? -1 : 1))
    .slice(0, GRADE_MAX);
}

/* 今出すもの（発走2時間前〜10分前・まだ出していないもの） */
export function dueGrades(picked, doneSet, nowMin) {
  return (picked || []).filter(r => { const p = postMin(r.post); return !doneSet.has(r.rid) && nowMin >= p - GRADE_BEFORE_MIN && nowMin <= p - GRADE_STOP_MIN; });
}

/* 朝の回が見つけた重賞の一覧を覚える（朝の投稿ができた時だけ呼ぶ） */
export async function saveGrades(env, date, mode, list) {
  if (!env.DB || !Array.isArray(list)) return;
  await env.DB.prepare(HITS_DDL).run();
  const slim = list.filter(r => r && r.rid).map(r => ({ rid: String(r.rid), track: String(r.track || ""), no: r.no, name: String(r.name || ""), grade: String(r.grade || "重賞"), post: String(r.post || "") }));
  await env.DB.prepare("INSERT OR REPLACE INTO xpost_log(k,date,mode,tweet_id,body,ts) VALUES(?,?,?,?,?,?)")
    .bind(`gl:${date}:${mode}`, date, mode, null, JSON.stringify(slim), Date.now()).run();
}

/* 10分おきの回。post(r, mode, date) は画像つきで投稿して投稿IDを返す関数（worker.js が渡す） */
export async function runGrades(env, post, { dry, now } = {}) {
  const out = { date: null, listed: 0, posted: [], skipped: null };
  if (!env.DB) { out.skipped = "DB なし"; return out; }
  const j = new Date((now || Date.now()) + 9 * 3600e3)   // now は試験用（ふだんは今の時刻）;
  const date = j.toISOString().slice(0, 10).replace(/-/g, ""); out.date = date;
  const nowMin = j.getUTCHours() * 60 + j.getUTCMinutes();
  await env.DB.prepare(HITS_DDL).run();
  const list = [];
  for (const mode of ["nar", "jra"]) {
    const row = await env.DB.prepare("SELECT body FROM xpost_log WHERE k=?").bind(`gl:${date}:${mode}`).first();
    if (!row || !row.body) continue;
    try { JSON.parse(row.body).forEach(r => list.push({ ...r, mode })); } catch { /* 読めない一覧は無いものとする */ }
  }
  out.listed = list.length;
  const picked = pickGrades(list);
  if (!picked.length) return out;
  const done = new Set();
  for (const r of picked) { if (await env.DB.prepare("SELECT k FROM xpost_log WHERE k=?").bind(`g:${r.rid}`).first()) done.add(r.rid); }
  for (const r of dueGrades(picked, done, nowMin)) {
    if (dry) { out.posted.push({ rid: r.rid, name: r.name, dry: true }); continue; }
    const ins = await env.DB.prepare("INSERT OR IGNORE INTO xpost_log(k,date,mode,tweet_id,body,ts) VALUES(?,?,?,?,?,?)")
      .bind(`g:${r.rid}`, date, r.mode, null, JSON.stringify({ name: r.name, grade: r.grade, post: r.post }), Date.now()).run();
    if (!ins.meta || !ins.meta.changes) continue;
    try {
      const id = await post(r, r.mode, date);
      await env.DB.prepare("UPDATE xpost_log SET tweet_id=? WHERE k=?").bind(String(id), `g:${r.rid}`).run();
      out.posted.push({ rid: r.rid, name: r.name, id });
    } catch (e) {
      out.posted.push({ rid: r.rid, name: r.name, error: String(e && e.message || e) });   // 失敗しても出し直さない
    }
  }
  return out;
}
