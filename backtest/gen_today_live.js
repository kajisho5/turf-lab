/* 本日速報 — 公式データの払戻を待たずに、今日の的中を出す
 *
 * ★なぜ要るか★
 *   /ai/ の万馬券・高回収ページは bt_all.jsonl（keiba.go.jp公式）を見ているが、
 *   **公式は払戻の確定が翌日**（2026-07-30 16:31に取り直しても当日分は空だった。
 *   レース自体は当日分も入っているのに払戻欄だけ空）。
 *   そのためページは常に「最新確定＝1日前」になる。
 *
 * ★新しく取りに行かない★
 *   今日の予想は predictions.php（pred_data）に、
 *   着順と払戻は results.php（result_data）に**既に溜まっている**
 *   （lab.html の答え合わせが savebatch で保存している）。
 *   この2つを突き合わせるだけで当日の的中が出る。
 *   ★netkeibaへのアクセスは増やさない★（過去にサーバーIPをブロックされた事故がある）
 *
 * ★買い目ロジックは書き写さない★
 *   bt_persona_bets.js の betRace() をそのまま読み込んで使う。
 *   ここに配分を書き写すと、本体を直したときに速報だけ古い買い方で集計する
 *   （このリポジトリで何度も起きている二重管理の失敗）。
 *
 * 出力: deploy/ai/today_live.json
 *   { date, generatedAt, mode別: { races, hits:[...], sum:{inv,ret,roi,n,hit} } }
 * 使い方: node backtest/gen_today_live.js [YYYYMMDD]
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.dirname(__dirname);
const ODDS = 'https://seventh-well.com/odds/';
const OUT = path.join(ROOT, 'deploy', 'ai', 'today_live.json');

const bets = require('./bt_persona_bets.js');
if (typeof bets.betRace !== 'function') {
  console.log('!! bt_persona_bets.js が betRace を export していない。');
  console.log('   module.exports に betRace/formationBets を足すこと（ロジックの写経はしない）');
  process.exit(1);
}
const { betRace } = bets;
// 人格ID一覧は personas.js を正とする（速報側で列挙すると本体と食い違う）
const { PERSONAS } = require('../core/personas.js');
const PERSONA_IDS = PERSONAS.filter(p => !p.market && !p.control).map(p => p.id);

const jstToday = () => {
  const d = new Date(Date.now() + 9 * 3600e3);
  return d.getUTCFullYear() + String(d.getUTCMonth() + 1).padStart(2, '0')
       + String(d.getUTCDate()).padStart(2, '0');
};
const DATE = process.argv[2] || jstToday();

async function getJson(url, opt) {
  const r = await fetch(url, opt);
  if (!r.ok) throw new Error(url + ' -> ' + r.status);
  return r.json();
}

(async () => {
  const out = { date: DATE, generatedAt: new Date().toISOString(), modes: {} };
  for (const mode of ['nar', 'jra']) {
    /* 1) その日の予想（サーバー保存分）*/
    let preds = [];
    try {
      const j = await getJson(`${ODDS}predictions.php?action=list&date=${DATE}&mode=${mode}`);
      preds = (j && j.records) || [];   // ★キーは records★ predictions.php の reply(['records'=>...])
    } catch (e) { console.log(`  [${mode}] 予想の取得に失敗: ${e.message}`); }
    if (!preds.length) { out.modes[mode] = { races: 0, hits: [], sum: null }; continue; }

    /* 2) 予想したレースの結果（サーバー保存分。無いものは「まだ答え合わせしていない」）*/
    const ids = [];
    for (const p of preds) for (const r of (p.races || [])) if (r.race_id) ids.push(r.race_id);
    let res = {};
    if (ids.length) {
      try {
        const rr = await fetch(ODDS + 'results.php?action=get', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ids }),
        });
        const jj = await rr.json();
        res = (jj && jj.results) || {};
      } catch (e) { console.log(`  [${mode}] 結果の取得に失敗: ${e.message}`); }
    }

    /* 3) 突き合わせ。結果が無いレースは「未確定」として集計から外す（0扱いにしない）*/
    const hits = [];
    let inv = 0, ret = 0, n = 0, hit = 0, pending = 0;
    for (const p of preds) {
      for (const r of (p.races || [])) {
        if (!r.race_id || r.skip) continue;
        const st = res[r.race_id];
        if (!st || !st.pays || !st.ranks) { pending++; continue; }
        const rank = (r.ranked || r.marks || []).map(m => m.num || m.n).filter(Boolean);
        if (rank.length < 3) { pending++; continue; }
        for (const pid of (PERSONA_IDS || ['ltr'])) {
          let b;
          try { b = betRace(rank, st.pays, pid); } catch (_) { continue; }
          inv += b.inv; ret += b.ret; n++;
          if (b.ret > 0) hit++;
          if (b.ret >= 10000) {
            hits.push({ persona: pid, tc: p.tc, track: p.trackName, r: r.no,
                        name: r.name, inv: b.inv, ret: b.ret,
                        roi: Math.round(100 * b.ret / b.inv) });
          }
        }
      }
    }
    hits.sort((a, b) => b.ret - a.ret);
    out.modes[mode] = { races: n, pending,
      hits: hits.slice(0, 20),
      sum: n ? { inv, ret, roi: Math.round(1000 * ret / inv) / 10, n, hit } : null };
    console.log(`  [${mode}] 集計 ${n}件 / 未確定 ${pending}件 / 万馬券級 ${hits.length}件`);
  }
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT + '.tmp', JSON.stringify(out));
  fs.renameSync(OUT + '.tmp', OUT);
  console.log('出力: ' + path.relative(ROOT, OUT));
})();
