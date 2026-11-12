/* 今日の全レースに13人格の印を打ち、記録として残す
 *
 * ★なぜ毎日記録するのか★
 *   「的中実績」を正直に出すには、**その日に何を予想したかの記録**が要る。
 *   後から遡って作ると、どうにでも盛れてしまう（競馬ナビ等は的中だけを
 *   並べているが、あれは分母が無いので検証できない）。
 *   うちは外れも含む全レースを記録し、結果と突き合わせて全部出す。
 *   人格の週次成績も /ai/ の詳細ページも、この記録が土台になる。
 *
 * ★画面と同じコアで採点する★
 *   core/personas.js + core/netkeiba_past.js をそのまま require する。
 *   別実装にすると、画面の印と記録の印がズレて信用が死ぬ。
 *
 * 出力: backtest/store/preds/YYYYMMDD.json
 *   { date, generated, races: [ { rid, kind, name, marks: {personaId: [馬番上位5]},
 *                                 pops: {馬番:人気} } ] }
 *   ★予想時点の人気も一緒に残す★ 結果側の人気で代用すると
 *   「市場（比較用）」の成績が後知恵になってしまうため。
 *
 * 使い方: node backtest/predict_today.js [YYYYMMDD]
 */
const fs = require("fs");
const path = require("path");
const { DOMParser } = require("linkedom");

const ROOT = path.dirname(__dirname);
const PERSONAS = require(path.join(ROOT, "core", "personas.js"));
const NKPast = require(path.join(ROOT, "core", "netkeiba_past.js"));

const DATE = process.argv[2] && /^\d{8}$/.test(process.argv[2])
  ? process.argv[2]
  : new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10).replace(/-/g, "");
const OUTDIR = path.join(ROOT, "backtest", "store", "preds");

const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36";
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function grab(url) {
  const r = await fetch(url, { headers: { "User-Agent": UA } });
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r.text();
}

/* 馬名 -> 当地/当距離複勝率（画面と同じ索引を使う） */
let HORSES = {};
try {
  HORSES = JSON.parse(fs.readFileSync(
    path.join(ROOT, "deploy", "data", "horses.json"), "utf8"));
} catch (e) { console.log("horses.json なし（wr/dr は空になる）"); }

const TRACKS = "門別|盛岡|水沢|浦和|船橋|大井|川崎|金沢|笠松|名古屋|園田|姫路|高知|佐賀|帯広|札幌|函館|福島|新潟|東京|中山|中京|京都|阪神|小倉";

async function racesOf(host) {
  try {
    const h = await grab(`https://${host}/top/race_list_sub.html?kaisai_date=${DATE}`);
    return [...new Set(h.match(/race_id=(\d{12})/g) || [])]
      .map(s => s.slice(8));
  } catch (e) {
    console.log(`  一覧取得失敗 ${host}: ${e.message}`);
    return [];
  }
}

async function scoreRace(rid, isJra) {
  const host = isJra ? "race.netkeiba.com" : "nar.netkeiba.com";
  const doc = new DOMParser().parseFromString(
    await grab(`https://${host}/race/shutuba_past.html?race_id=${rid}`), "text/html");

  const horses = NKPast.parseDoc(doc);
  if (horses.length < 5) return null;

  // レース名・場・距離
  const txt = s => { const e = doc.querySelector(s); return e ? e.textContent.replace(/\s+/g, " ").trim() : ""; };
  const name = txt(".RaceName") || "";
  const sub = txt(".RaceData01") + " " + txt(".RaceData02");
  const track = (sub.match(new RegExp(`(${TRACKS})`)) || [])[1] || "";
  const dist = parseInt((sub.match(/[ダ芝障](\d{3,4})/) || [])[1], 10) || null;

  // wr / dr（画面と同じ規則: 3走未満は使わない）
  const band = dist ? String(Math.floor(dist / 200) * 200) : null;
  for (const h of horses) {
    const rec = HORSES[h.name];
    if (!rec) continue;
    const t = track && rec.t ? rec.t[track] : null;
    const d = band && rec.d ? rec.d[band] : null;
    if (t && t[1] >= 3) h.wr = t[0] / 100;
    if (d && d[1] >= 3) h.dr = d[0] / 100;
  }

  // 人気（市場人格用）。発売前で無ければ pop は null のまま
  const pops = {};
  try {
    const api = isJra ? "api_get_jra_odds.html" : "api_get_nar_odds.html";
    const j = JSON.parse(await grab(
      `https://${host}/api/${api}?race_id=${rid}&type=1&action=init`));
    const src = isJra ? (j.data && j.data.odds && j.data.odds["1"]) : j.ary_odds;
    if (src) {
      for (const k in src) {
        const pop = isJra ? +src[k][2] : +src[k].Ninki;
        if (pop) pops[String(+k)] = pop;
      }
    }
  } catch (e) { /* オッズ未発売はままある。人気なしで記録する */ }
  for (const h of horses) h.pop = pops[h.n] || null;

  const marks = PERSONAS.scoreRace(horses);
  const out = {};
  for (const p of PERSONAS.PERSONAS) {
    const ok = p.axes.every(([a]) => horses.some(h => h[a] !== null && h[a] !== undefined));
    if (!ok) continue;                       // 算出できない人格は記録しない（後で0扱いしない）
    out[p.id] = (marks[p.id] || []).slice(0, 5).map(x => x.n);
  }
  return { rid, kind: isJra ? "jra" : "nar", name, track, dist,
           field: horses.length, marks: out, pops };
}

async function main() {
  console.log(`予想の記録: ${DATE}`);
  const jra = await racesOf("race.netkeiba.com");
  const nar = await racesOf("nar.netkeiba.com");
  console.log(`  中央 ${jra.length}R / 地方 ${nar.length}R`);
  if (!jra.length && !nar.length) {
    console.log("開催なし（または一覧が取れない）。記録は作らない");
    return 0;
  }

  const races = [];
  let fail = 0;
  for (const [ids, isJra] of [[jra, true], [nar, false]]) {
    for (const rid of ids) {
      try {
        const r = await scoreRace(rid, isJra);
        if (r) races.push(r);
      } catch (e) {
        fail++;
        if (fail <= 3) console.log(`  !! ${rid} ${e.message}`);
      }
      await sleep(400);              // 連打しない
    }
  }

  fs.mkdirSync(OUTDIR, { recursive: true });
  const out = path.join(OUTDIR, `${DATE}.json`);
  fs.writeFileSync(out, JSON.stringify({
    date: DATE, generated: new Date().toISOString(),
    core: "personas.js",             // どのコアで採点したかを残す（後で定義が変わっても追える）
    races
  }));
  console.log(`記録: ${races.length}R（失敗 ${fail}） -> ${path.relative(ROOT, out)}`);
  return 0;
}

main().then(c => process.exit(c)).catch(e => { console.error(e); process.exit(1); });
