/* モンテカルロ・シミュレーション — 買い目の「的中率・配当分布」を10万回で出す
 *
 * ■ 何のためか
 *   各AIの買い目（単勝〜3連単フォメ）について「このレースを10万回やったら
 *   何%当たり、払戻はどう散らばるか」を可視化する。SPAIA/SPAT4 には無い、
 *   ギャンブルとしての“形”（コツコツ外してドカン か 小さく当て続ける か）を見せる。
 *
 * ■ 出力モデル（★誠実さの肝★）
 *   着順は Plackett-Luce（＝競馬の Harville モデル）で引く。
 *   強さ = 各馬の勝率。1着を勝率に比例で引き、除いて2着、除いて3着…と続ける。
 *   市場（単勝オッズ）から作った勝率を使えば、これは「市場が正しいと仮定した世界」
 *   での的中率になる。**AIの見立てで勝率を水増ししない**（それをやると嘘になる）。
 *
 * ■ 払戻
 *   単勝/複勝: 実オッズがあればそれを使う。
 *   3連単など: 実オッズが無ければ Harville の理論配当（(1-控除率)/的中確率）で推定。
 *   → 推定配当は「市場公正値」なので、期待回収は控除率ぶん負ける≈75-80%に収束する。
 *     これは捏造ではなく事実（控除率は必ず引かれる）。違うのは的中率と分散だけ、を見せる。
 *
 * Node（検証）からもブラウザ（表示）からも同じものが読まれる。
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else { root.MONTECARLO = factory(); }
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  /* 単勝オッズ {馬番:オッズ} → 勝率 {馬番:確率}（過剰ラウンド分を割って正規化） */
  function winProbsFromOdds(oddsMap) {
    const p = {}; let z = 0;
    for (const k in oddsMap) {
      const o = +oddsMap[k];
      if (o > 1) { p[k] = 1 / o; z += p[k]; }
    }
    if (z <= 0) return null;
    for (const k in p) p[k] /= z;
    return p;
  }

  /* ★2着以降の減衰指数★ 素のHarville（勝率をそのまま強さに）だと
     人気馬の複勝率を大きく過大評価する（実測+12pt）。勝つ強さは2・3着には
     そのまま効かない。1着は勝率どおり(指数1)、2着以降は 強さ^DISC で平す。
     DISC は backtest/bt_montecarlo.js で実測の複勝率に合うよう較正した値。 */
  const DISC = 0.70;

  /* Plackett-Luce で上位 k 頭の着順を1回引く。
     nums: 馬番配列 / str: {馬番:強さ(勝率)} / k: 取り出す頭数 / disc: 2着以降の減衰指数 */
  function sampleOrder(nums, str, k, disc) {
    disc = disc == null ? DISC : disc;
    const pool = nums.slice();
    const base = pool.map(n => Math.max(str[n] || 0, 1e-12));
    const order = [];
    const kk = Math.min(k, pool.length);
    for (let step = 0; step < kk; step++) {
      // 1着は勝率どおり、2着以降は強さを平す（^disc）
      const w = step === 0 ? base : base.map(v => Math.pow(v, disc));
      let tot = 0; for (let i = 0; i < w.length; i++) tot += w[i];
      let r = Math.random() * tot, idx = 0;
      for (; idx < pool.length; idx++) { r -= w[idx]; if (r <= 0) break; }
      if (idx >= pool.length) idx = pool.length - 1;
      order.push(pool[idx]);
      pool.splice(idx, 1); base.splice(idx, 1);
    }
    return order;               // [1着, 2着, 3着...]（馬番の文字列/数値そのまま）
  }

  const S = x => String(x);
  const eqSet = (a, b) => a.length === b.length && a.every(x => b.includes(S(x)));
  const eqSeq = (a, b) => a.length === b.length && a.every((x, i) => S(x) === S(b[i]));

  /* 1点が当たったか。t={k,c,o?}、top=[1着,2着,3着]（文字列化済み） */
  function hits(t, top) {
    const c = t.c.map(S), top3 = top.map(S), t2 = top3.slice(0, 2);
    switch (t.k) {
      case '単勝': return top3[0] === c[0];
      case '複勝': return top3.includes(c[0]);
      case 'ワイド': return top3.includes(c[0]) && top3.includes(c[1]);
      case '馬連': return eqSet(c, t2);
      case '馬単': return eqSeq(c, t2);
      case '3連複': return eqSet(c, top3);
      case '3連単': return eqSeq(c, top3);
      default: return false;
    }
  }

  /* シミュレーション本体。
       strengths: {馬番:勝率}
       tickets  : [{k,c,s,o?}]（formationBets と同形。s=掛け金）
       payoutFor: (t, top3)=>100円あたり払戻（当たったときの配当。呼び出し側が実オッズ/推定を渡す）
       N        : 試行回数
     戻り: { hitAny(1点でも当たる率), evReturn(期待回収率%), inv,
             perTicket:[{k,c,hitRate}], ret:{median,max,mean,p10x(10倍以上の率)} } */
  function simulate(strengths, tickets, payoutFor, N) {
    N = N || 100000;
    const nums = Object.keys(strengths);
    if (nums.length < 3 || !tickets.length) return null;
    const inv = tickets.reduce((s, t) => s + (t.s || 0), 0);
    const hitCnt = tickets.map(() => 0);
    let anyCnt = 0, retSum = 0, retMax = 0, big = 0;
    const rets = [];                        // 各試行の総払戻（分布用・サンプルのみ保持）
    const KEEP = Math.min(N, 20000);
    for (let i = 0; i < N; i++) {
      const top = sampleOrder(nums, strengths, 3);
      let any = false, ret = 0;
      for (let j = 0; j < tickets.length; j++) {
        if (hits(tickets[j], top)) {
          hitCnt[j]++; any = true;
          const pay = payoutFor ? payoutFor(tickets[j], top) : 0;
          ret += pay / 100 * (tickets[j].s || 0);
        }
      }
      if (any) anyCnt++;
      retSum += ret; if (ret > retMax) retMax = ret;
      if (inv > 0 && ret >= inv * 10) big++;
      if (i < KEEP) rets.push(ret);
    }
    rets.sort((a, b) => a - b);
    const median = rets.length ? rets[Math.floor(rets.length / 2)] : 0;
    return {
      N, inv,
      hitAny: anyCnt / N,
      evReturn: inv > 0 ? 100 * (retSum / N) / inv : 0,
      perTicket: tickets.map((t, j) => ({ k: t.k, c: t.c, s: t.s, hitRate: hitCnt[j] / N })),
      ret: { mean: retSum / N, median, max: retMax, p10x: big / N },
    };
  }

  /* Harville 理論配当（実オッズが無い券種の推定用）。
     的中確率 p（同じ強さから解析的/経験的に）→ 100円あたり配当 = (1-控除率)/p。
     控除率は券種ごと（単複0.20 / 馬連・ワイド0.225 / 3連系0.25 目安）。 */
  const TAKEOUT = { '単勝': 0.20, '複勝': 0.20, 'ワイド': 0.225, '馬連': 0.225,
                    '馬単': 0.25, '3連複': 0.25, '3連単': 0.275 };
  function fairPayout(k, p) {
    if (!(p > 0)) return 0;
    const t = TAKEOUT[k] != null ? TAKEOUT[k] : 0.25;
    return Math.max(100, Math.round((1 - t) / p * 100));   // 100円あたり
  }

  /* ★レースの堅さ／波乱度（自信度）★ 市場の勝率分布から「堅いレースか荒れるレースか」を出す。
     予想の当てやすさそのものではなく「このレースは絞れるか散るか」を1目盛りで見せる。
       strengths: {馬番:勝率}
     戻り: { favNum, p1(1番人気の勝率), kata(0-100堅さ), stars(1-5), level,
             chalkTrio(人気上位3頭で3連複決着する率), upsetWin(3番人気以下が勝つ率) } */
  function raceShape(strengths, N) {
    N = N || 30000;
    const nums = Object.keys(strengths);
    if (nums.length < 3) return null;
    const arr = nums.map(n => [n, strengths[n]]).sort((a, b) => b[1] - a[1]);
    const p1 = arr[0][1], favNum = arr[0][0];
    const topSet = new Set(arr.slice(0, 3).map(x => x[0]));   // 市場上位3頭
    const fav2 = new Set(arr.slice(0, 2).map(x => x[0]));     // 1・2番人気
    let chalk = 0, upset = 0;
    for (let i = 0; i < N; i++) {
      const top = sampleOrder(nums, strengths, 3).map(String);
      if (top.every(x => topSet.has(x))) chalk++;
      // 波乱＝1着が3番人気以下（1・2番人気のどちらも勝てなかった）
      if (!fav2.has(top[0])) upset++;
    }
    // 1番人気の勝率 0.12(荒れ)→0、0.55(堅い)→100 に線形マップ
    const kata = Math.max(0, Math.min(100, Math.round(100 * (p1 - 0.12) / (0.55 - 0.12))));
    const stars = Math.max(1, Math.min(5, Math.round(kata / 20)));
    const level = kata >= 75 ? '堅い' : kata >= 55 ? 'やや堅い'
                : kata >= 35 ? '標準' : kata >= 18 ? 'やや波乱' : '波乱含み';
    return { favNum, p1, kata, stars, level, chalkTrio: chalk / N, upsetWin: upset / N };
  }

  return { winProbsFromOdds, sampleOrder, hits, simulate, fairPayout, TAKEOUT, raceShape };
}));
