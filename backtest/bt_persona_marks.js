/* ★人格の確定印スナップショット★（2026-08-04・不一致対策）
 *
 * なぜ要るか:
 *   人格の印は保存されず毎回再計算で、/ai/の的中カード（公式データで計算）と
 *   レースページのAI予想タブ（netkeibaデータでライブ計算）が僅差の馬で食い違った
 *   （盛岡8R: カードは◎5で3連単213万的中、ページは◎6で外れ。ユーザー指摘）。
 *   → 公式データによる印を「確定印」として書き出し、レースページは
 *     これがあるレースでは必ずこちらを使う。的中カードと同じ計算＝単一の正。
 *
 * 出力: deploy/data/pmarks.json  { rid: { personaId: [◎○▲△の馬番4つ] } }
 *   直近35日ぶん・トップ4だけ（表示と買い目が使うのはそこまで）。
 *   GBM本体は含めない（本体の正は predictions.php の保存値で、仕組みが別）。
 *
 * ★★地方だけ★★（中央を入れてはいけない）
 *   照合キーは公式rid = YYYY+TC+MMDD+RR。地方は netkeiba の race_id も同じ形式なので
 *   そのまま引ける（202665080312 = 帯広8/3 12R で実機確認済み）。
 *   だが**中央の netkeiba race_id は YYYY+場+開催回+日目+RR** で、桁数が同じまま
 *   意味が違う。例: 公式rid 202607040201(4/2 福島1R) と
 *   netkeiba race_id 202607040201(4回福島2日目1R) は別レースなのに文字列が一致する。
 *   → 中央を入れると「別レースの印」を貼る事故になるので、地方のみ書き出す。
 *   中央は暫定印のまま（表示側が⏳と明示する）。中央も確定印にしたければ、
 *   先に「公式rid ⇔ netkeiba race_id」の対応表を作ること。
 *
 * 使い方: node backtest/bt_persona_marks.js   （daily.py に組込み）
 */
const fs = require('fs');
const path = require('path');
const readline = require('readline');
const { PERSONAS, scoreRace } = require('../core/personas.js');

const ROOT = path.dirname(__dirname);
const OUT = path.join(ROOT, 'deploy', 'data', 'pmarks.json');
const DAYS = 35;

function cutoffStr() {
  const d = new Date(Date.now() - DAYS * 86400e3);
  return d.toISOString().slice(0, 10).replace(/-/g, '');
}

async function scan(file, cutoff, out) {
  if (!fs.existsSync(file)) return 0;
  let n = 0;
  const rl = readline.createInterface({
    input: fs.createReadStream(file), crlfDelay: Infinity
  });
  for await (const line of rl) {
    if (!line) continue;
    // 日付で先に粗く弾く（JSON.parseは高いので、対象外の行にはかけない）
    const dm = line.match(/"d":\s*"(\d{8})"/);
    if (!dm || dm[1] < cutoff) continue;
    let rc;
    try { rc = JSON.parse(line); } catch { continue; }
    const hs = rc.h.filter(h => h.rk !== null && h.rk !== undefined);
    if (hs.length < 5) continue;
    const marks = scoreRace(hs, { dist: rc.dist, going: rc.going, tc: +rc.tc || null });
    const rec = {};
    for (const p of PERSONAS) {
      const top = (marks[p.id] || []).slice(0, 4).map(x => String(x.n));
      if (top.length) rec[p.id] = top;
    }
    if (Object.keys(rec).length) { out[String(rc.rid)] = rec; n++; }
  }
  return n;
}

async function main() {
  const cutoff = cutoffStr();
  const out = {};
  const nar = await scan(path.join(ROOT, 'backtest', 'nardata', 'bt_all.jsonl'), cutoff, out);
  // ★中央(bt_jra)は入れない★ 理由は冒頭コメント（race_idの形式衝突で別レースに貼る）
  // 念のため機械でも守る: 地方の場コードでないキーは捨てる
  const NAR_TC = new Set(['11', '30', '35', '36', '42', '43', '44', '45', '46',
                          '47', '48', '50', '51', '54', '55', '65']);
  let dropped = 0;
  for (const k of Object.keys(out)) {
    if (!NAR_TC.has(k.slice(4, 6))) { delete out[k]; dropped++; }
  }
  /* ★空や激減で上書きしない★
     この出力が壊れると、レースページは「⏳暫定」に静かに戻り（エラーは出ない）、
     /ai/の的中カードとの不一致が復活する＝ユーザーが見つけた事故の再発。
     0件、または既存の半分未満なら書かずに異常終了して daily のログに残す。 */
  const cnt = Object.keys(out).length;
  let prev = 0;
  try { prev = Object.keys(JSON.parse(fs.readFileSync(OUT, 'utf8'))).length; } catch { /* 初回は0 */ }
  if (!cnt || (prev && cnt < prev / 2)) {
    console.error(`★異常★ 確定印が${cnt}R（前回${prev}R）。既存を守るため書き込みを中止した。`
      + ' bt_all.jsonl の再構築が失敗しているか、scoreRace の入力形が変わった可能性がある。');
    process.exit(1);
  }
  fs.writeFileSync(OUT, JSON.stringify(out));
  const kb = Math.round(fs.statSync(OUT).size / 1024);
  console.log(`確定印スナップショット: 地方${cnt}R（${cutoff}〜・走査${nar}R・非地方${dropped}件除外・前回${prev}R） → ${path.relative(ROOT, OUT)} (${kb}KB)`);
}

main();
