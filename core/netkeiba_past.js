/* netkeiba の「出馬表（過去5走）」から、personas.js が使う特徴量を作る
 *
 * ★バックテストと同じ定義に合わせること★
 *   backtest/build_dataset.py は N_PAST = 3。つまり ar/fpf/np は**近3走**で計算している。
 *   ここで5走使うと、公開している成績と違うものを表示することになる。
 *   なので過去5走のうち**新しい3走だけ**を使う。
 *
 * ★netkeiba から取れない軸がある★
 *   wr（当地複勝率）と dr（当距離複勝率）は keiba.go.jp が配信している値で、
 *   出馬表からは復元できない。近5走から推定すると母数が小さすぎて別物になり、
 *   公開しているバックテスト成績が当てはまらなくなる。
 *   よって **null のままにする**。personas.js 側で「算出不可」として扱う。
 *
 * 先行度 pf の定義（build_dataset.py と同じ）:
 *   最終コーナーの通過順 ÷ 出走頭数。小さいほど前。
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.NKPast = factory();
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const N_PAST = 3;   // ★build_dataset.py の N_PAST と必ず一致させる★

  const clean = el => (el ? el.textContent : '').replace(/\s+/g, ' ').trim();

  /* 過去走セル1つを読む。読めない項目は null（0で埋めない） */
  function parsePast(td) {
    const t = clean(td);
    if (!t) return null;
    // 着順: Rank クラス優先、無ければ「16頭 13番 15人」直前の数字を使わない（誤検出のもと）
    const rankEl = td.querySelector('.Rank, .Race_Result, .Num');
    let rank = rankEl ? parseInt(clean(rankEl), 10) : NaN;
    if (!Number.isFinite(rank)) {
      const m = t.match(/(?:^|\s)(\d{1,2})\s+[^\d]/);
      rank = m ? parseInt(m[1], 10) : NaN;
    }
    // 頭数・馬番・人気「16頭 13番 15人」
    const fm = t.match(/(\d{1,2})頭/);
    const field = fm ? parseInt(fm[1], 10) : NaN;
    /* コーナー通過順「9-8-7-8」
       pf = 最後の数字÷頭数（最終コーナー位置。スコアリングの「実測先行力」で使う）
       ff = 最初の数字÷頭数（★脚質はこちら★）

       ★脚質に最終コーナーを使ってはいけない★
         最終コーナーの位置は「その日どこまで押し上げたか」＝走りの結果が混ざる。
         好走した差し馬は最終角では前にいるので、逃げ馬と区別できない。
         脚質は「どう走る馬か」なので、隊列が決まる最初のコーナーで見る。
         tweet.html も昔からこの定義（最初のコーナー）で判定していた。 */
    const cm = t.match(/(\d{1,2}(?:-\d{1,2}){1,3})\s*\(/) || t.match(/(\d{1,2}(?:-\d{1,2}){1,3})/);
    let pf = null, ff = null;
    if (cm && Number.isFinite(field) && field > 1) {
      const legs = cm[1].split('-').map(Number);
      const last = legs[legs.length - 1];
      if (Number.isFinite(last)) pf = last / field;
      if (Number.isFinite(legs[0])) ff = legs[0] / field;
    }
    if (!Number.isFinite(rank)) return null;

    /* ★2026-07-29追加：履歴系特徴量の材料★
       LTRに rest/dchg/prk/ppop/pmiss/trend/vrank/wma を渡すため、
       過去走セルから日付・場・距離・人気・馬体重も取る。
       実物のセル構造（門別2026-07-29で確認）:
         Data01: 「2026.07.15 門別」+ <span class="Num">着順</span>
         Data03: 「9頭 9番 8人 騎手 57.0」
         Data05: 「ダ1200 1:14.8 稍」
         Data06: 「9-9 (36.8) 498(+2)」← 体重はkgなしの3桁+括弧
       取れない項目は null（0で埋めない）。 */
    const dm = t.match(/(20\d{2})\.(\d{1,2})\.(\d{1,2})/);
    const date = dm ? dm[1] + dm[2].padStart(2, '0') + dm[3].padStart(2, '0') : null;
    const trm = t.match(/(門別|盛岡|水沢|浦和|船橋|大井|川崎|金沢|笠松|名古屋|園田|姫路|高知|佐賀|帯広|札幌|函館|福島|新潟|東京|中山|中京|京都|阪神|小倉)/);
    const dim = t.match(/[ダ芝障](\d{3,4})/);
    const pm = t.match(/(\d{1,2})人/);
    const wtm = t.match(/(\d{3})\(([-+]?\d+)\)/);
    return {
      rank, pf, ff,
      date, track: trm ? trm[1] : null,
      dist: dim ? +dim[1] : null,
      pop: pm ? +pm[1] : null,
      wt: wtm ? +wtm[1] : null,
    };
  }

  /* 1行（1頭）から特徴量を作る
     ★馬名もここで取る★
       以前は「特徴量は parseDoc、馬名は呼び出し側で別ループ」にしていた。
       parseDoc は不正な行を捨てるのに、馬名側は捨てないので**添字がズレ**、
       画面に馬番が馬名として出た（本番で発生）。同じ1回のパースで両方取る。 */
  function parseHorse(tr) {
    const info = tr.querySelector('.Horse_Info');
    const infoTxt = clean(info);

    // 馬番: Waku の隣のセル。行頭2セルが 枠 / 馬番
    const tds = tr.querySelectorAll('td');
    const waku = parseInt(clean(tds[0]), 10);
    const uma = parseInt(clean(tds[1]), 10);

    // 馬体重と増減「512kg(+12)」
    const wm = infoTxt.match(/(\d{3})kg\s*\(([-+]?\d+)\)/);
    // 性齢「牡4鹿」
    const am = clean(tr.querySelector('.Jockey')).match(/[牡牝セ](\d{1,2})/);

    const pasts = [...tr.querySelectorAll('td.Past')]
      .map(parsePast).filter(Boolean).slice(0, N_PAST);

    const ranks = pasts.map(p => p.rank);
    const pfs = pasts.map(p => p.pf).filter(v => v !== null);
    const ffs = pasts.map(p => p.ff).filter(v => v !== null && v !== undefined);

    const avg = a => a.length ? a.reduce((x, y) => x + y, 0) / a.length : null;

    // 馬名は Horse_Info の中の db.netkeiba.com/horse/ リンク（父や調教師と紛れる）
    const nameEl = tr.querySelector('.Horse_Info a[href*="db.netkeiba.com/horse/"]');

    /* ★2026-07-30追加: 騎手・調教師・父★
       LTRに jkr/trr/sir（それぞれの事前複勝率）を渡すために名前が必要。
       これを取らないと33列モデルを3列欠損で動かすことになる
       （母父で「本番で出ない情報でバックテスト値を語るな」と決めた直後に
        自分で同じ穴を作りかけた。2026-07-30）。
       ・騎手: /jockey/ へのリンク
       ・調教師: /trainer/ へのリンク（「美浦・田中」形式のこともあるので後段で処理）
       ・父: Horse_Info 内の /horse/ping/ または sire リンク。無ければ null */
    const jkEl = tr.querySelector('a[href*="/jockey/"]');
    const trEl = tr.querySelector('a[href*="/trainer/"]');
    const sireEl = tr.querySelector('.Horse_Info a[href*="/horse/ped/"], .Horse_Info .Horse01 a, .Horse01 a');

    return {
      name: nameEl ? clean(nameEl) : '',
      jockeyName: jkEl ? clean(jkEl) : null,
      trainerName: trEl ? clean(trEl) : null,
      sireName: sireEl ? clean(sireEl) : null,
      n: Number.isFinite(uma) ? String(uma) : '',
      wk: Number.isFinite(waku) ? waku : null,
      age: am ? +am[1] : null,
      wt: wm ? +wm[1] : null,
      wd: wm ? +wm[2] : null,
      np: pasts.length,
      ar: ranks.length ? avg(ranks) : null,
      fpf: pfs.length ? avg(pfs) : null,
      // 脚質用（近3走の最初のコーナー位置率の平均）
      ffpf: ffs.length ? avg(ffs) : null,
      lpf: pasts.length && pasts[0].pf !== null ? pasts[0].pf : null,
      bpf: pfs.length ? Math.min(...pfs) : null,
      // ★netkeibaからは復元できない。推定で埋めない（下記コメント参照）
      wr: null,
      dr: null,
      /* ★2026-07-29追加：履歴系（build_dataset.py と同じ定義）★
         prk=前走着順 / ppop=前走人気 / pmiss=着順-人気（正=裏切り）
         trend=古い平均-最新（正=上向き） / vrank=着順の振れ幅
         wma=馬体重の近3走平均との差
         rest/dchg/tchg はレース側の情報（今日の日付・場・距離）が要るので
         enrich() で後から埋める。ここでは材料 _p0 を持たせておく。
         cn/ct3/swin（通算系）は出馬表から復元できない → null のまま。 */
      prk: ranks.length ? ranks[0] : null,
      ppop: pasts.length && pasts[0].pop != null ? pasts[0].pop : null,
      pmiss: (ranks.length && pasts[0].pop != null) ? ranks[0] - pasts[0].pop : null,
      trend: ranks.length >= 2
        ? +(avg(ranks.slice(1)) - ranks[0]).toFixed(3) : null,
      vrank: ranks.length >= 2 ? Math.max(...ranks) - Math.min(...ranks) : null,
      wma: (function () {
        const ws = pasts.map(p => p.wt).filter(v => v != null);
        if (!ws.length || !wm) return null;
        return +wm[1] - Math.round(avg(ws));
      })(),
      _p0: pasts.length ? { date: pasts[0].date, track: pasts[0].track,
                            dist: pasts[0].dist } : null,
    };
  }

  /* レース側の情報（今日の日付・場・距離）が要る特徴量を埋める。
     ctx = { date: "YYYYMMDD", track: "門別", dist: 1200 }
     呼ばなくても他の特徴量は使える（rest等が null になるだけ）。 */
  function enrich(horses, ctx) {
    if (!horses || !ctx) return horses;
    const today = parseDate(ctx.date);
    for (const h of horses) {
      const p = h._p0;
      if (!p) continue;
      const pd = parseDate(p.date);
      h.rest = (today && pd) ? Math.round((today - pd) / 86400000) : null;
      h.dchg = (ctx.dist && p.dist) ? ctx.dist - p.dist : null;
      h.tchg = (ctx.track && p.track) ? (p.track !== ctx.track ? 1 : 0) : null;
    }
    return horses;
  }

  function parseDate(s) {
    if (!s || !/^\d{8}$/.test(String(s))) return null;
    const d = new Date(+s.slice(0, 4), +s.slice(4, 6) - 1, +s.slice(6, 8));
    return isNaN(d) ? null : d;
  }

  /* 出馬表(過去5走)のドキュメント全体 → 馬の配列
     ★tr.HorseList は実馬以外にも付いている★
       14頭のレースで21行ヒットした。見出し行や空行にも同じクラスがある。
       馬番が数字で、馬名が取れている行だけを実馬とみなす。
       さらに馬番で一意化する（同じ馬が2行出る事故を防ぐ）。 */
  function parseDoc(doc) {
    const seen = new Set();
    const out = [];
    for (const tr of doc.querySelectorAll('tr.HorseList')) {
      const h = parseHorse(tr);
      if (!h.n || !h.name) continue;
      if (seen.has(h.n)) continue;
      seen.add(h.n);
      out.push(h);
    }
    return out;
  }

  return { parseDoc, parseHorse, enrich, N_PAST };
}));
