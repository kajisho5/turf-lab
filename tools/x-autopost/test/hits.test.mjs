// ★勝負の的中速報の試験（Xにもネットにも触らない。名前は全部架空）
import { parseResult, battleRaces, dueRaces, hitText, postMin, runHits, rememberMorning } from "../src/hits.js";
let ok = 0, ng = 0;
const eq = (n, a, b) => { const r = JSON.stringify(a) === JSON.stringify(b); r ? ok++ : (ng++, console.log("NG", n, JSON.stringify(a), JSON.stringify(b))); };

// 結果のページ（払戻の表）の形だけまねた見本
const page = (tan, tanPay, fuku, fukuPay) => `<table class="Payout_Detail_Table"> <tr class="Tansho"> <th>単勝</th> <td  class="Result"> ${tan.map(n => `<div><span>${n}</span></div> <div><span></span></div>`).join("")} </td> <td class="Payout"><span>${tanPay.join("<br />")}</span></td> </tr> <tr class="Fukusho"> <th>複勝</th> <td  class="Result"> ${fuku.map(n => `<div><span>${n}</span></div> <div><span></span></div>`).join("")} </td> <td class="Payout"><span>${fukuPay.join("<br />")}</span></td> </tr> <tr class="Wakuren"><td class="Result"><span>6</span></td></tr></table>`;
eq("確定前は null", parseResult("<html>まだ</html>"), null);
eq("ふつうの結果", parseResult(page([9], ["420円"], [9, 7, 3], ["160円", "110円", "1,240円"])), { win: ["9"], tan: { 9: 420 }, fuku: { 9: 160, 7: 110, 3: 1240 } });
eq("同着（1着が2頭）", parseResult(page([4, 11], ["150円", "310円"], [4, 11, 2], ["110円", "170円", "130円"])).win, ["4", "11"]);
eq("数が合わない払戻は使わない", parseResult(page([9], ["420円"], [9, 7, 3], ["160円"])).fuku, {});

const records = [
  { tc: "91", trackName: "潮見", races: [
    { no: 3, race_id: "202691111403", post: "15:10", marks: [{ num: "7", name: "オッターダッシュ" }, { num: "3", name: "ラッコノユメ" }] },
    { no: 4, race_id: "202691111404", post: "15:45", marks: [{ num: "2", name: "カワウソブレイブ" }] },
    { no: 5, race_id: "202691111405", post: "16:20", skip: true, marks: [] } ] },
  { tc: "92", trackName: "鳴瀬", races: [
    { no: 1, race_id: "202692111401", post: "14:50", marks: [{ num: "11", name: "セセラギキング" }] } ] },
];
const locks = [{ tc: "pub_91", pub: { 3: { aim: 1, battle: 1 }, 4: { aim: 1, battle: 0 } } }, { tc: "pub_92", pub: { 1: { aim: 1, battle: 1 } } }, { tc: "91", firm: {} }];
const br = battleRaces(records, locks);
eq("★勝負だけ・発走順", br.map(r => r.rid), ["202692111401", "202691111403"]);
eq("時刻の読み", [postMin("15:10"), postMin("9:05"), postMin("")], [910, 545, null]);
eq("まだ早い", dueRaces(br, new Set(), 892).map(r => r.rid), []);
eq("発走3分後から", dueRaces(br, new Set(), 893).map(r => r.rid), ["202692111401"]);
eq("記録済みは除く", dueRaces(br, new Set(["202692111401"]), 920).map(r => r.rid), ["202691111403"]);
eq("2時間でやめる", dueRaces(br, new Set(), 890 + 121).map(r => r.rid), ["202691111403"]);
eq("文", hitText(br[1], { win: ["7"], tan: { 7: 250 }, fuku: { 7: 130 } }, 2, 2), "🎯 ★勝負 的中\n潮見3R ◎7 オッターダッシュ　1着\n単勝 250円／複勝 130円\n今日の★勝負：2戦2勝");
eq("強みの行", hitText({ ...br[1], strong: "近走の時計がメンバー1位" }, { win: ["7"], tan: { 7: 250 }, fuku: { 7: 130 } }, 1, 1), "🎯 ★勝負 的中\n潮見3R ◎7 オッターダッシュ　1着\n強み：近走の時計がメンバー1位\n単勝 250円／複勝 130円\n今日の★勝負：1戦1勝");
eq("強みは朝の保存から読む", battleRaces([{ tc: "91", trackName: "潮見", races: [{ no: 3, race_id: "X3", post: "15:10", strong: "この場で3着内 8走中6回", marks: [{ num: "7", name: "オッターダッシュ" }] }] }], [{ tc: "pub_91", pub: { 3: { battle: 1 } } }])[0].strong, "この場で3着内 8走中6回");
eq("払戻が読めない時は行を出さない", hitText(br[1], { win: ["7"], tan: {}, fuku: {} }, 3, 1), "🎯 ★勝負 的中\n潮見3R ◎7 オッターダッシュ　1着\n今日の★勝負：3戦1勝");

// 通し（にせのデータベースとにせの通信）
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
    async first() { return t.get(a[0]) || null; },
    async all() { return { results: [...t.values()].filter(r => r.date === a[0] && r.mode === a[1] && r.k.startsWith("h:")) }; } }; return st; } };
}
const j = new Date(Date.now() + 9 * 3600e3); const today = j.toISOString().slice(0, 10).replace(/-/g, "");
const now = j.getUTCHours() * 60 + j.getUTCMinutes(); const hm = m => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
if (now >= 30 && now <= 23 * 60) {          // 日付が変わる前後は時刻の試験ができないので通しは省く
  const recs = [{ tc: "91", trackName: "潮見", races: [
    { no: 1, race_id: "R1", post: hm(now - 20), marks: [{ num: "7", name: "オッターダッシュ" }] },      // 1着
    { no: 2, race_id: "R2", post: hm(now - 10), marks: [{ num: "2", name: "カワウソブレイブ" }] },      // 外れ
    { no: 3, race_id: "R3", post: hm(now - 5), marks: [{ num: "5", name: "イタチノホシ" }] },           // 未確定
    { no: 4, race_id: "R4", post: hm(now + 30), marks: [{ num: "1", name: "ミズカキエース" }] } ] }];    // まだ
  const lks = [{ tc: "pub_91", pub: { 1: { battle: 1 }, 2: { battle: 1 }, 3: { battle: 1 }, 4: { battle: 1 } } }];
  const pages = { R1: page([7], ["250円"], [7, 1, 4], ["130円", "110円", "200円"]), R2: page([9], ["900円"], [9, 1, 4], ["300円", "110円", "200円"]), R3: "<html></html>" };
  globalThis.fetch = async (u) => {
    u = String(u);
    if (u.includes("action=listlocks")) return { ok: true, json: async () => ({ locks: u.includes("mode=nar") ? lks : [] }) };
    if (u.includes("action=list")) return { ok: true, json: async () => ({ records: u.includes("mode=nar") ? recs : [] }) };
    const m = u.match(/proxy\.php\?u=([^&]+)/); const url = atob(m[1].replace(/-/g, "+").replace(/_/g, "/"));
    return { ok: true, text: async () => pages[url.match(/race_id=(\w+)/)[1]] || "" };
  };
  const env = { DB: fakeDB() }; const sent = [];
  const reply = async (text, to) => { sent.push([text, to]); return "T" + sent.length; };
  eq("朝の投稿が無ければ何もしない", (await runHits(env, reply)).checked, 0);
  await rememberMorning(env, today, "nar", "ROOT");
  let r = await runHits(env, reply);
  eq("見に行った数", r.checked, 3); eq("外れの数", r.missed, 1);
  eq("投稿は1件・朝の投稿への返信", sent, [["🎯 ★勝負 的中\n潮見1R ◎7 オッターダッシュ　1着\n単勝 250円／複勝 130円\n今日の★勝負：1戦1勝", "ROOT"]]);
  eq("投稿IDを記録", env.DB.rows.get("h:R1").tweet_id, "T1");
  r = await runHits(env, reply);
  eq("2回目は未確定の1件だけ見る・二重に出さない", [r.checked, sent.length], [1, 1]);
  pages.R3 = page([5], ["180円"], [5, 2, 3], ["110円", "120円", "130円"]);
  r = await runHits(env, reply);
  eq("後から確定したぶん（外れも分母に入る）", sent[1][0], "🎯 ★勝負 的中\n潮見3R ◎5 イタチノホシ　1着\n単勝 180円／複勝 110円\n今日の★勝負：3戦2勝");
}
console.log("OK", ok, "NG", ng); process.exit(ng ? 1 : 0);
