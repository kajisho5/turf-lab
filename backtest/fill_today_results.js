// 今日の結果を能動的に results.php へ貯める（受け身キャッシュのギャップ埋め）
//
// ★背景★ results.php は「誰かがtweet.html/lab.htmlで結果タブを開いた時だけ」保存される
//   受け身の仕組みで、見に来た人がいないレースは永遠に貯まらない。
//   これが「AI別成績の今日が空欄」の原因（2026-07-21に特定）。
//
// ★安全設計★
//   - 対象は predictions.php に載っている「今日」の予想済みレースだけ（1日ミ十数〜数十件）。
//     過去の大量バックフィルはしない＝netkeiba IPブロックの再発防止（過去に実際に起きた事故）。
//   - まだ発走していない/確定していないレースは飛ばす（post時刻+20分の余裕）。
//   - 開発機から直接fetch。本番プロキシ(proxy.php)は経由しない＝本番サーバーの負荷ゼロ。
//   - リクエスト間に1.5秒あける。
//
// 使い方: node backtest/fill_today_results.js [--dry]
const ODDS = "https://seventh-well.com/odds/";

function resultURL(mode, rid) {
  const host = mode === "jra" ? "race.netkeiba.com" : "nar.netkeiba.com";
  return "https://" + host + "/race/result.html?race_id=" + rid;
}
function parseRanks(html) {
  const out = {};
  if (/race_table_01/.test(html) && !/class="Rank"/.test(html)) {
    (html.match(/<tr[\s\S]*?<\/tr>/g) || []).filter(t => /\/horse\//.test(t)).forEach(t => {
      const c = [...t.matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].map(x => x[1].replace(/<[^>]+>/g, "").replace(/&nbsp;/g, " ").trim());
      if (c.length < 4) return;
      const rank = parseInt(c[0], 10), num = parseInt(c[2], 10);
      if (isFinite(rank) && isFinite(num)) out[String(num)] = rank;
    });
    return out;
  }
  (html.match(/<tr[\s\S]*?<\/tr>/g) || []).forEach(r => {
    if (!/class="Rank"/.test(r)) return;
    const rk = r.match(/class="Rank"[^>]*>\s*(\d{1,2})\s*</);
    if (!rk) return;
    const rank = parseInt(rk[1], 10);
    const nc = [];
    r.replace(/class="Num [^"]*"[^>]*>\s*<div[^>]*>\s*(\d{1,2})\s*</g, (_, n) => { nc.push(n); return ""; });
    const num = nc.length >= 2 ? parseInt(nc[1], 10) : (nc.length === 1 ? parseInt(nc[0], 10) : NaN);
    if (isFinite(rank) && isFinite(num)) out[String(num)] = rank;
  });
  return out;
}
function parsePayoutsRaw(html) {
  const pay = { tansho: [], fukusho: [], umaren: [], umatan: [], wide: [], fuku3: [], tan3: [] };
  const map = { Tansho: "tansho", Fukusho: "fukusho", Umaren: "umaren", Umatan: "umatan", Wide: "wide", Fuku3: "fuku3", Tan3: "tan3" };
  for (const cls in map) {
    const m = html.match(new RegExp('class="' + cls + '"[\\s\\S]{0,1500}?</tr>'));
    if (!m) continue;
    const block = m[0];
    const rp = (block.match(/class="Result"[\s\S]*?<\/td>/) || [""])[0];
    const nums = [...rp.matchAll(/<span>\s*(\d{1,2})\s*<\/span>/g)].map(x => x[1]);
    const pp = (block.match(/class="Payout"[\s\S]*?<\/td>/) || [""])[0];
    const yens = [...pp.replace(/<[^>]+>/g, " ").matchAll(/(\d[\d,]*)/g)].map(x => +x[1].replace(/,/g, "")).filter(v => v >= 100);
    if (!yens.length || !nums.length) continue;
    const per = (cls === "Tansho" || cls === "Fukusho") ? 1 : (cls === "Fuku3" || cls === "Tan3") ? 3 : 2;
    let idx = 0;
    for (let k = 0; k < yens.length; k++) {
      const ns = nums.slice(idx, idx + per); idx += per;
      if (ns.length < per) break;
      pay[map[cls]].push({ nums: ns.map(n => String(+n)), yen: yens[k] });
    }
  }
  return pay;
}
function toPayFmt(p) {
  const c = a => a.map(x => [x.nums.join("-"), x.yen]);
  return { tan: c(p.tansho), fuku: c(p.fukusho), wakuren: [], umaren: c(p.umaren), wide: c(p.wide), umatan: c(p.umatan), fuku3: c(p.fuku3), tan3: c(p.tan3) };
}
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
function jstNow() {
  return new Date(Date.now() + 9 * 3600 * 1000);
}
function todayStr() {
  const d = jstNow();
  return "" + d.getUTCFullYear() + String(d.getUTCMonth() + 1).padStart(2, "0") + String(d.getUTCDate()).padStart(2, "0");
}

async function main() {
  const dry = process.argv.includes("--dry");
  const today = todayStr();
  console.log(`今日(JST): ${today}${dry ? " [--dry: 保存はしない]" : ""}`);

  const predRes = await fetch(ODDS + "predictions.php?action=list", { cache: "no-store" });
  const predJson = await predRes.json();
  const records = (predJson && predJson.records) || [];
  const todays = records.filter(r => r.date === today);
  const races = [];
  for (const r of todays) {
    for (const race of r.races || []) {
      if (race.race_id) races.push({ race_id: race.race_id, post: race.post, mode: r.mode, track: r.trackName });
    }
  }
  console.log(`予想済みレース: ${races.length}件`);
  if (!races.length) { console.log("対象なし。終了。"); return; }

  // 既に results.php にあるものは除外
  const idList = races.map(r => r.race_id);
  const haveRes = await fetch(ODDS + "results.php?action=get&ids=" + idList.join(","), { cache: "no-store" });
  const haveJson = await haveRes.json();
  const have = new Set(Object.keys((haveJson && haveJson.results) || {}));
  console.log(`既に保存済み: ${have.size}件`);

  // 発走時刻+20分を過ぎたものだけ対象
  const now = jstNow();
  const nowMin = now.getUTCHours() * 60 + now.getUTCMinutes();
  const todo = races.filter(r => {
    if (have.has(r.race_id)) return false;
    const m = (r.post || "").match(/^(\d{1,2}):(\d{2})$/);
    if (!m) return false;
    const postMin = (+m[1]) * 60 + (+m[2]);
    return nowMin >= postMin + 20;
  });
  console.log(`取得対象（発走+20分経過・未保存）: ${todo.length}件`);
  if (!todo.length) { console.log("対象なし。終了。"); return; }

  const toSave = [];
  let ok = 0, ng = 0;
  for (const r of todo) {
    try {
      const res = await fetch(resultURL(r.mode, r.race_id), {
        headers: { "User-Agent": "Mozilla/5.0" },
      });
      if (!res.ok) { console.log(`  ! ${r.track} ${r.race_id}: HTTP ${res.status}`); ng++; continue; }
      const html = await res.text();
      const ranks = parseRanks(html);
      if (!Object.keys(ranks).length) { console.log(`  - ${r.track} ${r.race_id}: 未確定（着順取れず）`); ng++; continue; }
      const pr = parsePayoutsRaw(html);
      const pays = (pr.tansho || []).length ? toPayFmt(pr) : null;
      toSave.push({ race_id: r.race_id, ranks, pays });
      ok++;
      console.log(`  OK ${r.track} ${r.race_id}（${Object.keys(ranks).length}頭ぶん着順${pays ? "+払戻" : ""}）`);
    } catch (e) {
      console.log(`  ! ${r.track} ${r.race_id}: ${e.message}`);
      ng++;
    }
    await sleep(1500);
  }

  console.log(`\n取得できた: ${ok} / 未確定・失敗: ${ng}`);
  if (dry || !toSave.length) { console.log("保存はスキップ（--dry または対象0件）。"); return; }

  const saveRes = await fetch(ODDS + "results.php?action=savebatch", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items: toSave }),
  });
  const saveJson = await saveRes.json();
  console.log(`保存結果: ${JSON.stringify(saveJson)}`);
}

main().catch(e => { console.error("失敗:", e); process.exit(1); });
