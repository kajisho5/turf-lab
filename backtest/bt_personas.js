/* 人格ごとの成績を実測する
 *
 * ★core/personas.js を直接読む★
 *   バックテストと本番で別々に実装すると、必ずどこかでズレる。
 *   ブラウザが読むのと同じファイルをここでも読む。
 *
 * ★train/holdout を分ける★
 *   13人格 × 複数指標を眺めれば、偶然良く見えるものが必ず出る。
 *   2013-2022 を train、2023-2026 を holdout とし、
 *   **train で良かったものが holdout でも良いか**を見る。
 *   これをやらないと「たまたま」を実力と誤認する。
 *
 * ★ROIの分母は買った全レース★
 *   的中時だけ投資計上すると回収率は簡単に水増しできる。
 *
 * 使い方: node backtest/bt_personas.js
 * 出力  : backtest/personas_stats.json
 */
const fs = require('fs');
const path = require('path');
const readline = require('readline');
const { PERSONAS, scoreRace } = require('../core/personas.js');

const ROOT = path.dirname(__dirname);
/* ★地方と中央で同じコードを回す★
     形を揃えたので分岐は要らない。分岐を作ると
     「地方と中央で違う計算をしている」ことに気づけなくなる。 */
const WHICH = process.argv[2] === 'jra' ? 'jra' : 'nar';
const DATA = path.join(ROOT, 'backtest', 'nardata',
  WHICH === 'jra' ? 'bt_jra.jsonl' : 'bt_all.jsonl');
const OUT = path.join(ROOT, 'backtest',
  WHICH === 'jra' ? 'personas_stats_jra.json' : 'personas_stats.json');

const SPLIT = '20230101';   // これ未満が train、以上が holdout

/* ★「当たっているか」だけでは偽物を見抜けない★
   「内枠」人格は枠で並べていたが、枠は馬番に対して単調なので
   印は必ず馬番順になり、馬番以上のことを何も言っていなかった。
   それでも複勝率はそれなりに出る（内枠は実際に有利なので）。
   つまり **成績が出ている＝独自の意見がある、ではない**。
   そこで本物かどうかを次の4つで見る:

     silent   意見なし率  … 全馬同点で何も言えなかったレースの割合。
                            高いとそもそも仕事をしていない。
     lowNum   馬番最小率  … ◎が単に最小馬番だった割合。100%なら馬番の言い換え。
     fav      1番人気率   … ◎が単に1番人気だった割合。100%なら市場の言い換え。
     rand     偶然の水準  … 無作為に1頭選んだときの複勝率（3/頭数の平均）。
                            これを超えていなければ、当てているとは言えない。 */
function blank() {
  return { n: 0, hit1: 0, hit3: 0, invT: 0, retT: 0, invF: 0, retF: 0,
           silent: 0, lowNum: 0, fav: 0, randSum: 0, seen: 0,
           hits: [] };   // 直近の的中レース明細（holdoutのみ・末尾が最新）
}

function add(st, hit1, hit3, tan, fuku) {
  st.n++; st.hit1 += hit1 ? 1 : 0; st.hit3 += hit3 ? 1 : 0;
  st.invT += 100; st.retT += tan;
  st.invF += 100; st.retF += fuku;
}

async function main() {
  /* ★対照群（既知の偽物）を混ぜる★
     判定の仕組み自体が正しいかを確かめるため、
     「馬番が一番小さい馬を◎にするだけ」という中身ゼロの人格を一緒に測る。
     これが「本物」と判定されたら、判定基準のほうが間違っている。
     削除した「内枠」は枠が馬番に単調なので、実質これと同じものだった。 */
  const CONTROL = { id: '_lownum', name: '馬番最小(対照)', control: true,
                    desc: '馬番が一番小さい馬を◎にするだけ。中身は無い' };
  const ALL = PERSONAS.concat([CONTROL]);

  const acc = {};                       // persona -> {train, holdout, daily}
  // daily は「人格の週次成績」(SITE_MAP P2) 用。holdout期間だけ日付キーで積む。
  for (const p of ALL) acc[p.id] = { train: blank(), holdout: blank(), daily: {} };
  let maxD = '';                        // データに存在する最終開催日

  // 人格どうしの◎の一致を数える（重複した人格を見つけるため。holdoutのみ）
  const agree = {}, agreeBoth = {};

  let races = 0, skipped = 0;
  const rl = readline.createInterface({
    input: fs.createReadStream(DATA), crlfDelay: Infinity
  });

  for await (const line of rl) {
    if (!line) continue;
    let rc;
    try { rc = JSON.parse(line); } catch { continue; }
    const pay = rc.pay || {};
    if (!pay.tan || !pay.fuku) { skipped++; continue; }

    const hs = rc.h.filter(h => h.rk !== null && h.rk !== undefined);
    if (hs.length < 5) { skipped++; continue; }

    const seg = rc.d < SPLIT ? 'train' : 'holdout';
    const marks = scoreRace(hs, { dist: rc.dist, going: rc.going });
    // 対照群: 馬番最小を◎にするだけ（scoreRace は触らない）
    marks['_lownum'] = [...hs].sort((a, b) => +a.n - +b.n).map(h => ({ n: h.n }));
    const byNum = new Map(hs.map(h => [String(h.n), h]));
    races++;

    // このレースの「馬番最小」と「1番人気」。人格の◎がこれの言い換えでないかを見る
    const lowNum = hs.reduce((a, b) => (+b.n < +a.n ? b : a)).n;
    const favH = hs.filter(h => h.pop).sort((a, b) => a.pop - b.pop)[0];
    const fav = favH ? favH.n : null;
    const rand = 3 / hs.length;          // 無作為に1頭選んだときの複勝率

    for (const p of ALL) {
      const st = acc[p.id][seg];
      st.seen++; st.randSum += rand;
      const top = marks[p.id] && marks[p.id][0];
      if (!top) { st.silent++; continue; }   // 全馬同点＝この人格は何も言っていない
      const h = byNum.get(String(top.n));
      if (!h) continue;
      if (String(top.n) === String(lowNum)) st.lowNum++;
      if (fav !== null && String(top.n) === String(fav)) st.fav++;
      // ★払戻の引き当てキーは文字列の馬番★ 数値で引くと全部0になる（過去に踏んだ）
      const key = String(h.n);
      const tanY = pay.tan[key] || 0, fukuY = pay.fuku[key] || 0;
      add(acc[p.id][seg], h.rk === 1, h.rk <= 3, tanY, fukuY);
      if (seg === 'holdout') {
        if (rc.d > maxD) maxD = rc.d;
        const dd = acc[p.id].daily[rc.d] ||
          (acc[p.id].daily[rc.d] = { n: 0, hit1: 0, hit3: 0, retT: 0, retF: 0 });
        dd.n++; dd.hit1 += h.rk === 1 ? 1 : 0; dd.hit3 += h.rk <= 3 ? 1 : 0;
        dd.retT += tanY; dd.retF += fukuY;
      }
      // ◎が複勝圏に来たレースを明細で残す（holdout・直近40件・末尾が最新）
      if (seg === 'holdout' && h.rk <= 3 && !p.control && !p.market) {
        const hits = st.hits;
        hits.push({ d: rc.d, tc: rc.tc, r: rc.r, name: rc.name || '',
                    n: h.n, rk: h.rk, pop: h.pop || null, tan: tanY, fuku: fukuY });
        if (hits.length > 40) hits.shift();
      }
    }

    if (seg === 'holdout') {
      const ids = ALL.map(p => p.id);
      for (let i = 0; i < ids.length; i++) {
        const a = marks[ids[i]] && marks[ids[i]][0];
        if (!a) continue;
        for (let j = i + 1; j < ids.length; j++) {
          const b = marks[ids[j]] && marks[ids[j]][0];
          if (!b) continue;
          const k = ids[i] + '|' + ids[j];
          agreeBoth[k] = (agreeBoth[k] || 0) + 1;
          if (String(a.n) === String(b.n)) agree[k] = (agree[k] || 0) + 1;
        }
      }
    }
  }

  const pct = (a, b) => b ? 100 * a / b : 0;
  /* 週次: データ最終日から遡って7日間（月曜に見ると先週月〜日にほぼ一致）。
     Nが小さい週の順位は揺れるが、それも含めて「今週」の事実として出す。 */
  const wkFrom = (() => {
    if (!maxD) return '99999999';
    const d = new Date(`${maxD.slice(0, 4)}-${maxD.slice(4, 6)}-${maxD.slice(6, 8)}`);
    d.setDate(d.getDate() - 6);
    return d.toISOString().slice(0, 10).replace(/-/g, '');
  })();
  const weeklyOf = pid => {
    const w = { n: 0, hit1: 0, hit3: 0, retT: 0, retF: 0 };
    for (const [d, v] of Object.entries(acc[pid].daily)) {
      if (d < wkFrom) continue;
      w.n += v.n; w.hit1 += v.hit1; w.hit3 += v.hit3; w.retT += v.retT; w.retF += v.retF;
    }
    return { n: w.n, win: pct(w.hit1, w.n), fuku: pct(w.hit3, w.n),
             tanRoi: pct(w.retT, w.n), fukuRoi: pct(w.retF, w.n),
             from: wkFrom, to: maxD };
  };
  const rows = ALL.map(p => {
    const t = acc[p.id].train, o = acc[p.id].holdout;
    return {
      id: p.id, name: p.name, desc: p.desc, market: !!p.market, control: !!p.control,
      train:   { n: t.n, win: pct(t.hit1, t.n), fuku: pct(t.hit3, t.n),
                 tanRoi: pct(t.retT, t.invT), fukuRoi: pct(t.retF, t.invF) },
      holdout: { n: o.n, win: pct(o.hit1, o.n), fuku: pct(o.hit3, o.n),
                 tanRoi: pct(o.retT, o.invT), fukuRoi: pct(o.retF, o.invF),
                 silent: pct(o.silent, o.seen), lowNum: pct(o.lowNum, o.n),
                 fav: pct(o.fav, o.n), rand: 100 * o.randSum / (o.seen || 1) },
      weekly: weeklyOf(p.id),
      // 直近の的中レース（◎が複勝圏・新しい順）。対照/市場には付けない。
      hits: (p.control || p.market) ? [] : o.hits.slice().reverse()
    };
  });
  /* 週次順位: 対照群は除き、市場（人気順）は基準として含めて順位を振る。
     同率は件数が多いほうを上位（少数サンプルの100%が首位を取り続けないように）。 */
  {
    const ranked = rows.filter(r => !r.control && r.weekly.n > 0)
      .sort((a, b) => (b.weekly.fuku - a.weekly.fuku) || (b.weekly.n - a.weekly.n));
    ranked.forEach((r, i) => { r.weekly.rank = i + 1; r.weekly.of = ranked.length; });
  }

  /* ★偽物の判定★ 数字を見て人が判断すると、都合よく読んでしまう。
     基準を先に書いておき、機械に言わせる。 */
  for (const r of rows) {
    const h = r.holdout;
    const bad = [];
    if (h.silent > 50) bad.push(`意見なしが${h.silent.toFixed(0)}%`);
    if (h.lowNum > 90) bad.push(`◎が馬番最小と${h.lowNum.toFixed(0)}%一致（馬番の言い換え）`);
    if (!r.market && h.fav > 90) bad.push(`◎が1番人気と${h.fav.toFixed(0)}%一致（市場の言い換え）`);
    /* ★「偶然を上回った」だけでは足りない★
       件数が4万を超えると、実質ゼロの差でも統計的には有意になる。
       実際「馬体重」は偶然+0.5ptで有意判定になったが、
       予想家として並べる意味は無い。95%区間の下限が偶然+3ptを超えることを求める。 */
    const se = Math.sqrt((h.fuku / 100) * (1 - h.fuku / 100) / (h.n || 1)) * 100;
    const lo = h.fuku - 1.96 * se;
    if (lo <= h.rand + 3) {
      bad.push(h.fuku < h.rand
        ? `複勝率${h.fuku.toFixed(1)}%が偶然(${h.rand.toFixed(1)}%)を下回る`
        : `偶然(${h.rand.toFixed(1)}%)との差が小さすぎる（区間下限${lo.toFixed(1)}%）`);
    }
    r.verdict = bad.length ? '偽' : '本物';
    r.reasons = bad;
  }

  // holdout の複勝率で並べる（train で選んで holdout で評価、が順序として正しい）
  rows.sort((a, b) => b.holdout.fuku - a.holdout.fuku);

  const w = (s, n) => String(s).padEnd(n);
  console.log(`【${WHICH === 'jra' ? '中央競馬' : '地方競馬'}】対象 ${races.toLocaleString()} レース（除外 ${skipped.toLocaleString()}）`);
  console.log(`train = 〜${SPLIT} / holdout = ${SPLIT}〜\n`);
  console.log(w('人格', 14) + ' tr複勝 ho複勝  偶然  複ROI 意見無 馬番最小 1番人気  件数  判定');
  console.log('-'.repeat(88));
  for (const r of rows) {
    const h = r.holdout;
    console.log(
      w(r.name, 14) +
      `${r.train.fuku.toFixed(1).padStart(6)}%` +
      `${h.fuku.toFixed(1).padStart(6)}%` +
      `${h.rand.toFixed(1).padStart(6)}%` +
      `${h.fukuRoi.toFixed(0).padStart(6)}%` +
      `${h.silent.toFixed(0).padStart(5)}%` +
      `${h.lowNum.toFixed(0).padStart(8)}%` +
      `${h.fav.toFixed(0).padStart(7)}%` +
      `${h.n.toLocaleString().padStart(8)}  ${r.verdict}`);
  }
  const fakes = rows.filter(r => r.verdict === '偽');
  if (fakes.length) {
    console.log('\n【偽物と判定】');
    for (const r of fakes) console.log(`  ${r.name}: ${r.reasons.join(' / ')}`);
  } else {
    console.log('\n偽物と判定された人格は無し。');
  }

  // 人格どうしの重複（◎が一致する率）。90%超なら実質同じものを2つ置いている
  console.log('\n【◎の一致率が高い組（実質同じ人格でないか）】');
  const ids = ALL.map(p => p.id);
  let dup = 0;
  for (let i = 0; i < ids.length; i++) {
    for (let j = i + 1; j < ids.length; j++) {
      const k = ids[i] + '|' + ids[j];
      const both = agreeBoth[k] || 0, agr = agree[k] || 0;
      if (both < 500) continue;
      const p = 100 * agr / both;
      if (p >= 80) {
        const nm = id => ALL.find(x => x.id === id).name;
        console.log(`  ${nm(ids[i])} と ${nm(ids[j])}: ${p.toFixed(0)}%一致（${both.toLocaleString()}R）`);
        dup++;
      }
    }
  }
  if (!dup) console.log('  80%以上一致する組は無し。観点はきちんと分かれている。');

  const mk = rows.find(r => r.market);
  const best = rows.filter(r => !r.market && !r.control)[0];
  console.log('\n' + '='.repeat(72));
  console.log(`最良の人格「${best.name}」 holdout複勝率 ${best.holdout.fuku.toFixed(1)}%`);
  console.log(`市場（人気順）        holdout複勝率 ${mk.holdout.fuku.toFixed(1)}%`);
  console.log(best.holdout.fuku > mk.holdout.fuku
    ? '→ 市場を上回った。ただしROIも見ること。'
    : '→ 市場に届いていない。ここを誇張しないこと。');

  fs.writeFileSync(OUT, JSON.stringify({ split: SPLIT, races, rows }, null, 1));
  console.log(`\n出力: ${path.relative(ROOT, OUT)}`);
}

main();
