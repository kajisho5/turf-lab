// 重賞の日の1枚の試験（Xにもネットにも触らない。名前は全部架空）
import { gradeRank, pickGrades, dueGrades, saveGrades, runGrades } from "../src/grade.js";
let ok = 0, ng = 0;
const eq = (n, a, b) => { const r = JSON.stringify(a) === JSON.stringify(b); r ? ok++ : (ng++, console.log("NG", n, JSON.stringify(a), JSON.stringify(b))); };
eq("格の順位", ["G1", "JpnⅠ", "Jpn1", "G2", "JpnⅡ", "G3", "JpnⅢ", "重賞", ""].map(gradeRank), [1, 1, 1, 2, 2, 3, 3, 4, 4]);
const L = [
  { rid: "A", name: "汐入記念", grade: "重賞", post: "20:10", mode: "nar" },
  { rid: "B", name: "鳴瀬ステークス", grade: "G3", post: "15:35", mode: "jra" },
  { rid: "C", name: "白波杯", grade: "G2", post: "15:45", mode: "jra" },
  { rid: "D", name: "潮見盃", grade: "重賞", post: "", mode: "nar" } ];
eq("格の高い順に2本・時刻の無いものは除く", pickGrades(L).map(r => r.rid), ["C", "B"]);
eq("同じ格は発走の早い順", pickGrades([L[0], { rid: "E", grade: "重賞", post: "18:00" }]).map(r => r.rid), ["E", "A"]);
const P = pickGrades(L);
eq("2時間前より前は出さない", dueGrades(P, new Set(), 15 * 60 + 35 - 121).map(r => r.rid), []);
eq("2時間前から", dueGrades(P, new Set(), 15 * 60 + 35 - 120).map(r => r.rid), ["B"]);
eq("10分前まで", dueGrades(P, new Set(), 15 * 60 + 35 - 10).map(r => r.rid), ["C", "B"]);
eq("10分前を過ぎたら出さない", dueGrades(P, new Set(), 15 * 60 + 45 - 9).map(r => r.rid), []);
eq("出したものは除く", dueGrades(P, new Set(["B"]), 15 * 60 + 35 - 60).map(r => r.rid), ["C"]);

function fakeDB() {
  const t = new Map();
  return { rows: t, prepare(sql) { let a = []; const st = {
    bind(...x) { a = x; return st; },
    async run() {
      if (/^CREATE/.test(sql)) return { meta: { changes: 0 } };
      if (/^INSERT OR REPLACE/.test(sql)) { t.set(a[0], { k: a[0], date: a[1], mode: a[2], tweet_id: a[3], body: a[4] }); return { meta: { changes: 1 } }; }
      if (/^INSERT OR IGNORE/.test(sql)) { if (t.has(a[0])) return { meta: { changes: 0 } }; t.set(a[0], { k: a[0], date: a[1], mode: a[2], tweet_id: a[3], body: a[4] }); return { meta: { changes: 1 } }; }
      if (/^UPDATE/.test(sql)) { t.get(a[1]).tweet_id = a[0]; return { meta: { changes: 1 } }; }
      throw new Error(sql); },
    async first() { return t.get(a[0]) || null; } }; return st; } };
}
const NOW = Date.UTC(2026, 10, 14, 3, 0);   // 試験の中の「今」＝日本時間 2026-11-14 12:00（いつ動かしても同じ結果にする）
const j = new Date(NOW + 9 * 3600e3); const today = j.toISOString().slice(0, 10).replace(/-/g, "");
const now = j.getUTCHours() * 60 + j.getUTCMinutes(); const hm = m => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
{
  const env = { DB: fakeDB() }; const sent = [];
  const post = async (r, mode, date) => { sent.push([r.rid, mode, date, r.grade]); return "P" + sent.length; };
  eq("一覧が無い日は何もしない", (await runGrades(env, post, { now: NOW })).posted, []);
  await saveGrades(env, today, "nar", [{ rid: "N1", track: "潮見", no: 11, name: "汐入記念", grade: "重賞", post: hm(now + 60) }]);
  await saveGrades(env, today, "jra", [{ rid: "J1", track: "鳴瀬", no: 11, name: "白波杯", grade: "G2", post: hm(now + 90) },
    { rid: "J2", track: "鳴瀬", no: 10, name: "鳴瀬ステークス", grade: "G3", post: hm(now + 200) }]);
  let r = await runGrades(env, post, { now: NOW });
  eq("出すのは上位2本のうち時間に入ったもの（3本目の地方の重賞は出さない）", sent, [["J1", "jra", today, "G2"]]);
  eq("記録", [env.DB.rows.get("g:J1").tweet_id, env.DB.rows.has("g:N1"), r.listed], ["P1", false, 3]);
  r = await runGrades(env, post, { now: NOW });
  eq("2回目は出さない", sent.length, 1);
  const env2 = { DB: fakeDB() }; await saveGrades(env2, today, "nar", [{ rid: "N1", name: "汐入記念", grade: "重賞", post: hm(now + 60) }]);
  r = await runGrades(env2, async () => { throw new Error("card: 朝の予想が保存されていない"); }, { now: NOW });
  eq("失敗は記録に残す", r.posted.map(x => x.error), ["card: 朝の予想が保存されていない"]);
  r = await runGrades(env2, post, { now: NOW });
  eq("失敗した分を出し直さない", r.posted, []);
  const env3 = { DB: fakeDB() }; await saveGrades(env3, today, "nar", [{ rid: "N1", name: "汐入記念", grade: "重賞", post: hm(now + 60) }]);
  r = await runGrades(env3, async () => { throw new Error("呼ばれてはいけない"); }, { dry: true, now: NOW });
  eq("ドライランは投稿も記録もしない", [r.posted.map(x => x.dry), env3.DB.rows.has("g:N1")], [[true], false]);
}
console.log("OK", ok, "NG", ng); process.exit(ng ? 1 : 0);
