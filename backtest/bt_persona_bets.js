/* 各AI（人格）に 1レース 10,000円 を持たせて買い目を組ませ、回収率を実測する
 *
 * ★狙い★
 *   SPAIA/SPAT4 のように「購入額 ▶ 払戻額 ▶ 回収率」と買い目を出す。
 *   人格ごとに◎○▲△の順位は違うが、買い方(配分)は全員同じテンプレにする。
 *   （買い方まで人格ごとに変えると、勝った買い方を後から選ぶ水増しになるため）
 *
 * ★配分テンプレ（合計10,000円）★ 比率まで実測して選んだ「買い目らしさ×回収率」の最良点
 *   ◎複勝                         7,000円
 *   ワイド ◎-{○,▲,△} 3点×1,000    3,000円
 *   （純◎複勝77.5%が最高だが1点。ワイドを残しつつ最良なのがこの配分＝74.9%）
 *
 * ★回収率の分母は必ず「買った全レース×10,000円」★（外れも分母に入れる）
 *
 * 入力  : backtest/nardata/bt_all.jsonl（tan/fuku=dict, wide=dict, umaren/sanpuku=[[馬番...],払戻]）
 * 出力  : backtest/persona_bets.json
 */
const fs = require('fs');
const path = require('path');
const readline = require('readline');
const { PERSONAS, scoreRace } = require('../core/personas.js');

const ROOT = path.dirname(__dirname);
const DATA = path.join(ROOT, 'backtest', 'nardata', 'bt_all.jsonl');
const OUT = path.join(ROOT, 'backtest', 'persona_bets.json');
const SPLIT = '20230101';                 // holdout の開始（検証区間だけ集計）
const UNIT = 100;                          // 払戻は100円あたり
const RECENT = 40;                         // 直近の的中買い目を人格ごとに残す件数
const BIG_KEEP = 120;                      // 万馬券/高回収タブ用に全AI横断で残す上位

const { formationBets, betStyleName } = require('../core/personas.js');
const pair = (a, b) => [a, b].sort((x, y) => (+x) - (+y)).join('-');
const setEq = (arr, s) => arr.length === s.size && arr.every(x => s.has(String(x)));

/* 1点の払戻を返す。b = {k, c:[馬番...], s, o?:順序あり}。払戻は100円あたり×(s/100)。
   tan/fuku=dict, wide=dict, umaren/umatan/sanpuku/santan = 当たり1組 [[馬番...],円] */
function payout(b, pay) {
  const c = b.c.map(String), u = s => s / 100 * b.s;
  const single = (dict) => u((dict || {})[c[0]] || 0);
  const one = (arr, ordered) => {
    if (!Array.isArray(arr) || arr.length !== 2) return 0;
    const won = arr[0].map(String);
    if (ordered) return c.length === won.length && c.every((x, i) => x === won[i]) ? u(arr[1]) : 0;
    return setEq(c, new Set(won)) ? u(arr[1]) : 0;
  };
  switch (b.k) {
    case '単勝': return single(pay.tan);
    case '複勝': return single(pay.fuku);
    case 'ワイド': return u((pay.wide || {})[pair(c[0], c[1])] || 0);
    case '馬連': return one(pay.umaren, false);
    case '馬単': return one(pay.umatan, true);
    case '3連複': return one(pay.sanpuku, false);
    case '3連単': return one(pay.santan, true);
    default: return 0;
  }
}

/* 1レース・ある順位(top4)＋人格の買い方(スタイル)で買った全点と払戻を返す。
   ★買い方は personas.js の formationBets（人格ごとに尖ったスタイル）と同じ★ */
function betRace(rank, pay, personaId) {
  const raw = formationBets(rank.map(String), personaId);
  const bets = raw.map(b => ({
    k: b.k, c: b.c.map(String), s: b.s, o: b.o || undefined, r: payout(b, pay),
  }));
  const inv = bets.reduce((s, t) => s + t.s, 0);
  const ret = bets.reduce((s, t) => s + t.r, 0);
  return { inv, ret, bets };
}

async function main() {
  const ALL = PERSONAS.filter(p => !p.market && !p.control);
  const acc = {};
  for (const p of ALL) acc[p.id] = { name: p.name, desc: p.desc, inv: 0, ret: 0, n: 0, hit: 0, hits: [], daily: {} };
  const big = [];
  let races = 0, skipped = 0;

  const rl = readline.createInterface({ input: fs.createReadStream(DATA), crlfDelay: Infinity });
  for await (const line of rl) {
    if (!line) continue;
    let rc; try { rc = JSON.parse(line); } catch { continue; }
    if (rc.d < SPLIT) continue;                          // holdout だけ
    const pay = rc.pay || {};
    if (!pay.fuku) { skipped++; continue; }
    const hs = rc.h.filter(h => h.rk !== null && h.rk !== undefined);
    if (hs.length < 6) { skipped++; continue; }          // フォメが組めない少頭数は除く
    const marks = scoreRace(hs, { dist: rc.dist, going: rc.going });
    races++;

    for (const p of ALL) {
      const mk = marks[p.id];
      if (!mk || mk.length < 4) continue;                // 4頭ぶんの順位が要る
      const rank = mk.slice(0, 4).map(m => m.n);
      const { inv, ret, bets } = betRace(rank, pay, p.id);
      const st = acc[p.id];
      st.inv += inv; st.ret += ret; st.n++;
      // 期間別（今日/昨日/週/月）の集計用に日別で貯める
      const dg = st.daily[rc.d] || (st.daily[rc.d] = { inv: 0, ret: 0, n: 0, hit: 0 });
      dg.inv += inv; dg.ret += ret; dg.n++; if (ret > 0) dg.hit++;
      if (ret > 0) {
        st.hit++;
        const roi = Math.round(100 * ret / inv);
        const rec = { d: rc.d, tc: rc.tc, r: rc.r, name: rc.name || '',
                      inv, ret, roi, bets };
        st.hits.push(rec);
        if (st.hits.length > RECENT) st.hits.shift();
        if (roi >= 300) {
          big.push({ persona: p.name, ...rec });
          if (big.length > 800) { big.sort((x, y) => y.roi - x.roi); big.length = BIG_KEEP; }
        }
      }
    }
  }

  big.sort((x, y) => y.roi - x.roi);
  const pct = (a, b) => b ? Math.round(1000 * a / b) / 10 : 0;
  const rows = ALL.map(p => {
    const s = acc[p.id];
    return {
      id: p.id, name: s.name, desc: s.desc,
      style: betStyleName(p.id),                          // 実際の買い方（人格ごとに違う）
      n: s.n, roi: pct(s.ret, s.inv), hitRate: pct(s.hit, s.n),
      inv: s.inv, ret: s.ret,
      hits: s.hits.slice().reverse()                     // 新しい順
    };
  });
  rows.sort((a, b) => b.roi - a.roi);

  // ★期間別ランキング★ 最新の開催日を「今日」として、そこから遡って集計する。
  const allDates = new Set();
  for (const p of ALL) for (const dt in acc[p.id].daily) allDates.add(dt);
  const dates = [...allDates].sort();
  const maxD = dates[dates.length - 1] || SPLIT;
  const asDate = s => new Date(+s.slice(0, 4), +s.slice(4, 6) - 1, +s.slice(6, 8));
  const shift = (s, days) => {
    const t = asDate(s); t.setDate(t.getDate() + days);
    return `${t.getFullYear()}${String(t.getMonth() + 1).padStart(2, '0')}${String(t.getDate()).padStart(2, '0')}`;
  };
  const label = d => `${+d.slice(4, 6)}/${+d.slice(6, 8)}`;
  const prevYm = (() => { const t = asDate(maxD); t.setDate(1); t.setMonth(t.getMonth() - 1);
    return `${t.getFullYear()}${String(t.getMonth() + 1).padStart(2, '0')}`; })();
  // 「昨日」＝最新開催日の1つ前の開催日（前日にレースが無い日があるため）
  const prevRaceDay = dates.filter(x => x < maxD).slice(-1)[0] || maxD;

  /* ★payback（確定払戻）は keiba.go.jp の月次ZIPで、直近2-3日ぶんが未反映のことがある★
     （タスク#3で観測・実測: 生成日が7/21でも払戻確定はd7/17止まり、ということが起きる）。
     この状態で「今日」と表示すると、本当の今日と食い違って「データが無い」ように見える。
     実際の生成日と比べて2日以上古ければ、正直に「最新確定」表記にする。 */
  const jstNow = new Date(Date.now() + 9 * 3600 * 1000);
  const todayStr = `${jstNow.getUTCFullYear()}${String(jstNow.getUTCMonth() + 1).padStart(2, '0')}${String(jstNow.getUTCDate()).padStart(2, '0')}`;
  const lagDays = Math.round((asDate(todayStr) - asDate(maxD)) / 86400000);
  // ★1日でもズレていたら「今日」と呼ばない★ 「今日」は実際の今日以外を指してはいけない。
  //   1日ラグを許容していたら「今日は7/21なのに7/20と出る」という嘘になった（実際に指摘された）。
  const todayLabel = lagDays >= 1 ? `最新確定（${label(maxD)}）` : `今日（${label(maxD)}）`;

  const PERIODS = {
    today: { label: todayLabel, ok: d => d === maxD },
    yesterday: { label: `前開催（${label(prevRaceDay)}）`, ok: d => d === prevRaceDay },
    week: { label: '直近7日', ok: d => d > shift(maxD, -7) && d <= maxD },
    lastweek: { label: '先週(その前7日)', ok: d => d > shift(maxD, -14) && d <= shift(maxD, -7) },
    month: { label: `今月(${maxD.slice(0, 4)}/${+maxD.slice(4, 6)})`, ok: d => d.slice(0, 6) === maxD.slice(0, 6) },
    lastmonth: { label: `先月(${prevYm.slice(0, 4)}/${+prevYm.slice(4, 6)})`, ok: d => d.slice(0, 6) === prevYm },
    all: { label: '通期(2023-)', ok: () => true },
  };
  const periods = {};
  for (const [key, def] of Object.entries(PERIODS)) {
    const pr = ALL.map(p => {
      let inv = 0, ret = 0, n = 0, hit = 0;
      for (const dt in acc[p.id].daily) if (def.ok(dt)) {
        const x = acc[p.id].daily[dt]; inv += x.inv; ret += x.ret; n += x.n; hit += x.hit;
      }
      return { id: p.id, name: acc[p.id].name, roi: pct(ret, inv), hitRate: pct(hit, n), n };
    });
    pr.sort((a, b) => (b.n ? b.roi : -1) - (a.n ? a.roi : -1));
    periods[key] = { label: def.label, rows: pr };
  }

  // ★万馬券的中/高回収タブの期間フィルタ★ big[] を PERIODS と同じ ok() で
  //   期間ごとに分けておく（JS側でロジックを再実装すると条件がズレるので、生成時点で確定させる）。
  const bigByPeriod = {};
  for (const [key, def] of Object.entries(PERIODS)) {
    bigByPeriod[key] = big.filter(h => def.ok(h.d)).slice(0, BIG_KEEP);
  }

  const out = {
    split: SPLIT, races, maxDate: maxD,
    // ★template削除★ 人格ごとに違う買い方（formationBets）を使っており、単一配分ではない。
    //   固定文字列を持つと実態と食い違う（実際に嘘だと指摘された）。
    rows, big: big.slice(0, BIG_KEEP), bigByPeriod, periods,
    dataLagDays: lagDays,   // 払戻確定の最新日と生成日の差。2以上なら表示側で注記する
  };
  fs.writeFileSync(OUT, JSON.stringify(out));
  console.log(`集計 ${races.toLocaleString()}レース（holdout・6頭以上）`);
  for (const r of rows) {
    console.log(`  ${r.name.padEnd(6)} 回収率 ${r.roi}%  的中率 ${r.hitRate}%  (${r.n.toLocaleString()}R)`);
  }
  console.log(`高配当(300%+) ${big.length}件 / 出力: ${path.relative(ROOT, OUT)}`);
}
/* ★2026-07-30: 直接実行のときだけ集計する★
   本日速報(gen_today_live.js)が betRace を再利用するために require するので、
   無条件で main() が走ると 44万行の再集計が始まってしまう。
   ★買い目ロジックを速報側に書き写さないため★ の措置（写すと二重管理でズレる）。 */
if (require.main === module) main();

module.exports = { betRace, payout };
