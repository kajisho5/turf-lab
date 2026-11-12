/* 予想人格（観点別スコアリング）— ★唯一の定義場所★
 *
 * ■ なぜ1ファイルに集約するのか
 *   これまで tweet.html から必要な関数を「依存を辿ってコピー」して
 *   kochi.html を作っていた。その結果、抜けた関数が本番で未定義になり、
 *   v357/v359/v360/v364 と4回連鎖して本番が動かない期間が発生した。
 *   コピーが原因なので、**コピーをやめる**のが根本対策。
 *   このファイルは Node（バックテスト）からもブラウザ（表示）からも
 *   同じものが読まれる。数字がズレようがない。
 *
 * ■ 人格の作り方の原則
 *   1. **持っているデータで本当に区別できる観点だけ作る。**
 *      「20人格」のように数を先に決めて埋めない。水増しになる。
 *   2. **人気（pop）は原則として使わない。**
 *      オッズは最強の予測子なので、混ぜると全人格が市場に似てしまい、
 *      「観点が違う」という前提が崩れる。市場を使うのは比較用の1人だけ。
 *   3. 各人格の成績は必ず実測して公開する（backtest/bt_personas.js）。
 *      弱い人格を隠さない。SPAIAも18人中18位を出している。
 *
 * ■ 馬の持つ値（bt_all.jsonl と同じ）
 *   ar  近走平均着順（小さいほど良い）        np  出走数
 *   fpf 直近の最終コーナー位置率（小さいほど前）lpf 前走の同値
 *   bpf 自己ベストの同値                      wr  勝率
 *   dr  当該条件での連対率                    wt  馬体重   wd 増減
 *   age 年齢   wk 枠   n 馬番   pop 人気（比較用の人格のみ使用）
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.PERSONAS = factory();
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  /* 値が無いときに 0 を入れると「平均的な馬」と「データ無しの馬」が
     区別できなくなる。null は null のまま扱い、最後に中央値で埋める。 */
  const num = v => (v === null || v === undefined || v !== v) ? null : +v;

  /* レース内で標準化する（絶対値ではなく「そのレースの中での相対」を見る）
     頭数もクラスもバラバラなので、生値のまま比べると場の違いが混入する。 */
  function zscore(vals) {
    const ok = vals.filter(v => v !== null);
    if (ok.length < 2) return vals.map(() => 0);
    const m = ok.reduce((a, b) => a + b, 0) / ok.length;
    const sd = Math.sqrt(ok.reduce((a, b) => a + (b - m) * (b - m), 0) / ok.length) || 1;
    // データ欠損は「そのレースの平均」に置く＝有利にも不利にもしない
    return vals.map(v => v === null ? 0 : (v - m) / sd);
  }

  /* 各人格は「この馬の、この値を、この向きで見る」だけを宣言する。
     複数の軸を持つ場合は重みつきで足す。合計は必ず 1 にする（比較可能にするため）。 */
  const PERSONAS = [
    { id: 'kinso', name: '近走重視', desc: '直近のレースでどれだけ好走しているか',
      axes: [['ar', -1]] },

    { id: 'senko', name: '逃げ先行型', desc: '前に行ける馬を上に取る',
      axes: [['fpf', -1]] },

    /* ★「差し追込型」は外した（実測 176,014R）★
       複勝率 10.6%。偶然に1頭選ぶ水準 30.7% を **20pt下回る**。
       これは雑音ではなく「地方では差し追込が明確に不利」という確かな結果だが、
       逃げ先行型（54.9%）と同じ軸の符号違いなので、新しい情報は何も足していない。
       予想家として並べれば「必ず外すほうに賭ける人」を置くことになる。
       事実は docs/PERSONAS_AUDIT.md に残す。 */

    { id: 'best', name: '一発の脚', desc: '自己ベストの位置取り。普段は目立たないが一度だけ走った馬',
      axes: [['bpf', -1]] },

    { id: 'zenso', name: '前走だけ', desc: '前走の内容だけを見る。乗り替わりや調子の変化に敏感',
      axes: [['lpf', -1]] },

    { id: 'jisseki', name: '実績重視', desc: '通算の勝率。地力がある馬を素直に取る',
      axes: [['wr', +1]] },

    { id: 'tekisei', name: '条件適性', desc: 'この距離・この馬場での連対率',
      axes: [['dr', +1]] },

    /* ★「馬体重」は外した（実測 176,014R）★
       複勝率 31.2% に対し、偶然に1頭選ぶ水準が 30.7%。差は 0.5pt。
       件数が4万を超えるので統計的には有意になるが、**予想としては無内容**。
       有意であることと、意味があることは別。 */

    { id: 'wakaba', name: '若さ重視', desc: '若い馬の上積みに賭ける',
      axes: [['age', -1]] },

    /* ★「経験」は外した（実測 176,014R）★
       もとの名前は「キャリア」だったが、np は通算出走数ではなく
       **近3走のうち実際に走っていた本数（0〜3）**。経験のある馬は全員3で並ぶ。
       実測すると 意見なし61% / 複勝率23.5%（偶然30.7%を下回る）。
       名前を直しても中身が無いものは残さない。
       通算出走数は data/horses.json にあるので、使うなら別の軸として検証し直す。 */

    { id: 'balance', name: '総合', desc: '近走・実績・適性・位置取りをまとめて見る',
      axes: [['ar', -0.40], ['wr', +0.25], ['dr', +0.20], ['fpf', -0.15]] },

    // ★3連単1点・一点勝負★ 総合と同じ見立てで、◎→○→▲の3連単に全額つっこむ尖りモデル。
    { id: 'santan1', name: '3連単1点', desc: '◎→○→▲の3連単に全部つっこむ一点勝負',
      axes: [['ar', -0.40], ['wr', +0.25], ['dr', +0.20], ['fpf', -0.15]] },

    // ★衆知（総意）★ 見立ては他の全AIの印を集計して決める（アンサンブル）。
    //   axes はダミー（scoreRace 内で印集計に差し替える）。多くのAIが推す馬を上に。
    { id: 'consensus', name: '衆知（総意）', desc: '全AIの印を集計。多くのAIが推した馬を本命に',
      axes: [['ar', -1]], consensus: true },

    // ★順位学習（LambdaMART）★ 1観点ではなく14特徴量を同時に見る本格モデル。
    //   地方13万レースで全頭の着順を直接学習（core/ltr_model.js）。GBMとは別系統。
    //   ★市場は超えない（複勝率65.0%）が、非市場モデルでは最良★
    { id: 'ltr', name: '順位学習', desc: '13万Rで全頭の着順を直接学習した本格モデル(LambdaMART)。14の手掛かりを同時に見る',
      axes: [], ltr: true },

    // ★比較用★ これだけ人気（＝市場）を使う。他人格が市場を超えられるかの基準。
    { id: 'market', name: '市場（比較用）', market: true,
      desc: 'オッズの順番どおり。無料で手に入る最強の予測子で、超えるべき基準',
      axes: [['pop', -1]] }
  ];

  const AXES = ['ar', 'fpf', 'lpf', 'bpf', 'wr', 'dr', 'wd', 'age', 'np', 'wk', 'pop'];

  /* ★LTR（順位学習・LambdaMART）★ 決定木モデルは core/ltr_model.js（自動生成）。
     Node は require、ブラウザは race.php が先に読み込んで globalThis に載せる。
     GBM本体とは別系統の「もう一人のAI」。13万Rで全頭の着順を直接学習した順位モデル。
     ★市場は超えない（複勝率65.0%<市場76.4%）が、非市場モデルでは最良★ */
  let _LTR = null;
  try { if (typeof require === 'function') _LTR = require('./ltr_model.js'); } catch (e) {}
  function ltrScoreOf(f) {
    const fn = (_LTR && _LTR.ltrScore)
      || (typeof globalThis !== 'undefined' && globalThis.ltrScore)
      || (root && root.ltrScore);
    return fn ? fn(f) : null;
  }
  const GOING_CODE = { '良': 0, '稍': 1, '稍重': 1, '重': 2, '不': 3, '不良': 3 };
  /* LTRの入力（名前付き特徴量）。欠損は null のまま渡す＝木の default_left で辿る
     （0埋めより忠実。学習時も欠損は NaN で渡している）。 */
  function ltrFeat(h, horses, ctx) {
    ctx = ctx || {};
    const g = String(ctx.going || '');
    const going = g ? (g in GOING_CODE ? GOING_CODE[g]
                       : (g[0] in GOING_CODE ? GOING_CODE[g[0]] : null)) : null;
    return {
      wk: num(h.wk), age: num(h.age), ar: num(h.ar), fpf: num(h.fpf),
      lpf: num(h.lpf), bpf: num(h.bpf), np: num(h.np), wr: num(h.wr),
      dr: num(h.dr), owr: num(h.owr), o2r: num(h.o2r),
      wt: num(h.wt), wd: num(h.wd),
      dist: (ctx.dist != null ? +ctx.dist : null),
      fn: horses.length, going: going,
      /* ★2026-07-29: 履歴系12列（holdout複勝率+1.0pt / z=+4.86）★
         バックテスト(bt_all.jsonl)は全列を持つ。
         ライブ(netkeiba_past.js)は rest/dchg/tchg/prk/ppop/pmiss/trend/vrank/wma
         を供給し、通算系 cn/ct3/swin は復元不能なので欠損のまま
         （木は default_left で辿る。欠損3列でも holdout 66.1% > 旧 65.6% を実測済み）。 */
      rest: num(h.rest), dchg: num(h.dchg), tchg: num(h.tchg),
      prk: num(h.prk), ppop: num(h.ppop), pmiss: num(h.pmiss),
      trend: num(h.trend), vrank: num(h.vrank),
      cn: num(h.cn), ct3: num(h.ct3), wma: num(h.wma), swin: num(h.swin),
      /* ★2026-07-30: 場コード（カテゴリ特徴）★ ctx.tc（数値の場コード）で渡す。
         無ければ欠損＝木の default 方向。バックテストは rc.tc、ライブは rid の5〜6桁目。 */
      tc: (ctx.tc != null && isFinite(+ctx.tc) ? +ctx.tc : null),
      /* ★2026-07-30: 騎手・厩舎・父の事前複勝率★
         バックテストは h.jkr/trr/sir を直接持つ。ライブは race_app.js が
         索引(jockeys/trainers/sires.json)から引いて同じキーに入れる。
         ★3列とも欠損させると33列モデルを劣化させたまま動かすことになる★ */
      jkr: num(h.jkr), trr: num(h.trr), sir: num(h.sir),
      /* ★2026-07-30: 第2弾の5列★ モデルには入っていたのに、ここに渡し忘れていた
         （check_model_wiring.js を作って初めて気づいた。列を足すたびに
          供給側を手で辿るのは必ず漏れる）。
         jkchg=乗り替わり / pgap=前走の着差 / restdev=間隔の自分基準ズレ /
         clvchg=クラスの昇降 / sqr=季節適性。
         バックテストは h.* を持つ。ライブは NKPast が作れる範囲だけ入る。 */
      jkchg: num(h.jkchg), pgap: num(h.pgap), restdev: num(h.restdev),
      clvchg: num(h.clvchg), sqr: num(h.sqr),
    };
  }

  /* 1レース分を採点して、人格ごとの並び順を返す
     horses: [{n, ar, fpf, ...}]
     ctx:    {dist, going}（LTRが使う。無くても動く＝欠損扱い）
     戻り: { personaId: [{n, score, mark}, ...上位順] } */
  function scoreRace(horses, ctx) {
    if (!horses || horses.length < 2) return {};
    // 軸ごとにレース内標準化（1回だけ計算して使い回す）
    const z = {};
    for (const a of AXES) z[a] = zscore(horses.map(h => num(h[a])));

    const out = {};
    for (const p of PERSONAS) {
      const scored = horses.map((h, i) => {
        let s = 0;
        for (const [axis, w] of p.axes) s += w * z[axis][i];
        return { n: h.n, score: s };
      });

      /* ★全馬が同点なら、この人格はこのレースについて何も言っていない★
         その場合でも印を付けると、並び順の決め方（馬番）がそのまま印になり、
         「1番に◎、2番に○…」という**中身のない予想**が表示される。
         実際 3歳限定戦で「若さ重視」が全馬同い年のまま馬番順に印を出していた。
         意見が無いことは、嘘の意見より価値がある。空にして列ごと消す。 */
      const spread = Math.max(...scored.map(x => x.score))
                   - Math.min(...scored.map(x => x.score));
      if (spread < 1e-9) { out[p.id] = []; continue; }
      // 同点は馬番順で安定させる（実行のたびに順番が変わると検証できない）
      scored.sort((a, b) => (b.score - a.score) || (+a.n - +b.n));
      scored.forEach((x, i) => { x.mark = MARKS[i] || ''; });

      /* ★☆は「5番手」ではなく穴馬にする★
         もとは上位5頭に順番に印を付けるだけで、☆に意味が無かった。
         競馬の慣習でも☆は穴を指すので、実態と合っていなかった。

         ここでの穴 = **その人格が人気より高く評価している馬**。
         人気順位 − 人格順位 の差が最大で、かつ人気薄（6番人気以下）のもの1頭。
         「この人格は市場とどこで意見が違うのか」が1目盛りで分かる。
         人気が取れていないレース（発売前）では付けない。 */
      const byNum = new Map(horses.map(h => [String(h.n), h]));
      let best = null;
      scored.forEach((x, i) => {
        // ★既に印が付いた馬は最初から候補にしない★
        //   後から弾く形にすると、◎の馬が最大gapで選ばれて捨てられ、
        //   ☆が1つも付かなくなる（実際そうなった）。
        if (x.mark) return;
        const h = byNum.get(String(x.n));
        const pop = h && h.pop ? +h.pop : null;
        if (!pop || pop < 6) return;          // 人気馬は穴ではない
        const gap = pop - (i + 1);            // 人気より上に見ている度合い
        if (gap <= 0) return;                 // 人気以下の評価なら穴ではない
        if (!best || gap > best.gap) best = { x, gap };
      });
      if (best) best.x.mark = '☆';

      out[p.id] = scored;
    }

    /* ★衆知（総意）＝他のAIの印を集計して並べ直す★
       ◎4/○3/▲2/△1/☆1.5 で重み付けし、多くのAIが上に見た馬を本命にする。
       集計元は素の見立て人格だけ（市場・総意・その複製=3連単1点は除く）。 */
    const CONTRIB = ['kinso', 'senko', 'best', 'zenso', 'jisseki', 'tekisei', 'wakaba', 'balance'];
    const MW = { '◎': 4, '○': 3, '▲': 2, '△': 1, '☆': 1.5 };
    const tally = new Map(horses.map(h => [String(h.n), 0]));
    for (const id of CONTRIB) for (const x of (out[id] || []))
      if (x.mark) tally.set(String(x.n), (tally.get(String(x.n)) || 0) + (MW[x.mark] || 0));
    const cons = horses.map(h => ({ n: h.n, score: tally.get(String(h.n)) || 0 }));
    const cmax = Math.max(...cons.map(x => x.score));
    if (cmax > 0) {
      cons.sort((a, b) => (b.score - a.score) || (+a.n - +b.n));
      cons.forEach((x, i) => { x.mark = MARKS[i] || ''; });
      out['consensus'] = cons;
    } else {
      out['consensus'] = [];
    }

    /* ★LTR（順位学習）★ 全頭の特徴量を決定木モデルに入れ、raw スコアで並べる。
       他の人格が「1つの観点」なのに対し、これは14特徴量を同時に見る本格モデル。 */
    if (ltrScoreOf({ wk: 1 }) !== null) {
      const ls = horses.map(h => ({ n: h.n, score: ltrScoreOf(ltrFeat(h, horses, ctx)) }));
      const spread = Math.max(...ls.map(x => x.score)) - Math.min(...ls.map(x => x.score));
      if (spread > 1e-9) {
        ls.sort((a, b) => (b.score - a.score) || (+a.n - +b.n));
        ls.forEach((x, i) => { x.mark = MARKS[i] || ''; });
        out['ltr'] = ls;
      } else out['ltr'] = [];
    } else {
      out['ltr'] = [];
    }
    return out;
  }

  // 上位から順に付ける印は4つまで。☆は別枠（穴馬）で付ける
  const MARKS = ['◎', '○', '▲', '△'];

  /* ── 脚質（逃げ / 先行 / 差し / 追込） ──────────────────────────
     ★定義は tweet.html に元からあったものに合わせる★
       最初のコーナー通過順 ÷ 頭数 を近3走で平均し、0.20 / 0.45 / 0.75 で切る。
       最初は最終コーナー基準で別の閾値を作りかけたが、それでは
       **同じ商品の中に脚質の定義が2つ**できる。
       tweet.html から関数をコピーして本番を4回壊したのと同じ構図なので、
       新しく作らず既存に寄せて、ここを唯一の定義場所にする。

     ★最終コーナーで判定してはいけない★
       最終角の位置は「その日どこまで押し上げたか」＝走りの結果が混ざる。
       好走した差し馬は最終角では前にいるので、逃げ馬と見分けられない。
       脚質は「どう走る馬か」なので、隊列が決まる最初のコーナーで見る。

     ★実測（backtest/bt_style.py・13年・延べ1,715,654頭）★
       tweet.html には 988R の測定として
         逃 +15.1 / 先 +4.6 / 差 -2.9 / 追 -9.9 pt（人気統制）
       と書いてあったが、**大規模では再現しなかった**:

         脚質  延べ頭数    複勝率   人気統制リフト
         逃    153,166    42.9%     -1.2pt
         先    493,965    36.3%     +0.4pt
         差    692,155    27.8%     +0.7pt
         追    376,368    17.8%     -1.4pt

       複勝率の生の差は大きい（42.9% 対 17.8%）が、**人気で統制するとほぼ消える**。
       つまり「前に行く馬が有利」ではなく「強い馬が前に行ける」のであって、
       その分はすでにオッズに織り込まれている。
       事前に分かる脚質は、人気を超える手掛かりにはならない。

       だから脚質は**予想の根拠ではなく、馬を理解するための情報**として出す。
       tweet.html 側も「スコアには不採用（A/Bで◎成績が悪化）」としており、整合する。

     ※過去走が無く判定できない馬が 269,100頭（全体の13.6%）ある。これは「不明」。 */
  const STYLES = [
    { max: 0.20, name: '逃げ', cls: 'st1', fuku: 42.9, lift: -1.2 },
    { max: 0.45, name: '先行', cls: 'st2', fuku: 36.3, lift: +0.4 },
    { max: 0.75, name: '差し', cls: 'st3', fuku: 27.8, lift: +0.7 },
    { max: Infinity, name: '追込', cls: 'st4', fuku: 17.8, lift: -1.4 }
  ];

  /* 脚質を返す。ffpf = 近3走の**最初の**コーナー位置率の平均。
     近走が無ければ null（「不明」と「追込」を混同しない）。 */
  function runningStyle(ffpf) {
    const v = num(ffpf);
    if (v === null) return null;
    return STYLES.find(s => v <= s.max);
  }

  /* ★AIごとの買い方（人間の予想家っぽく・1レース10,000円）★
     回収率だけ追うと複勝1点に収束して臆病＝予想家っぽくない。
     各AIに買い方の性格を持たせる（単勝勝負／穴の万馬券／連下広め／ワイド軸）。
     ★backtest/bt_persona_bets.js の betRace と同じにすること★（片方だけ変えない）
     返り値: [{k:券種, c:[馬番...], s:掛け金, o?:true(順序あり=馬単/3連単)}] */
  const BETSTYLE = {
    // 本命勝負：◎の単勝に厚く、◎-相手の馬連で連も押さえる
    honmei(a, b, c) {
      const r = [{ k: '単勝', c: [a], s: 5000 }];
      if (b) r.push({ k: '馬連', c: [a, b], s: 3000 });
      if (c) r.push({ k: '馬連', c: [a, c], s: 2000 });
      else if (b) r[1].s = 5000;
      return r;
    },
    // 穴・万馬券：3連単フォメ（1着◎/2,3着=相手）＋3連複◎軸＋単勝の保険
    ana(a, b, c, d) {
      const o = [b, c, d].filter(Boolean), r = [];
      for (const x of o) for (const y of o) if (x !== y) r.push({ k: '3連単', c: [a, x, y], s: 1000, o: true });
      const tri = [[a, b, c], [a, b, d], [a, c, d]].filter(cc => cc.every(Boolean));
      for (const cc of tri) r.push({ k: '3連複', c: cc, s: 1000 });
      r.push({ k: '単勝', c: [a], s: 10000 - r.reduce((s, t) => s + t.s, 0) });
      return r.filter(t => t.s > 0);
    },
    // 連下広め：◎-相手の馬連流し＋◎-○-相手の3連複
    renka(a, b, c, d) {
      const o = [b, c, d].filter(Boolean), r = [];
      for (const x of o) r.push({ k: '馬連', c: [a, x], s: 2000 });
      for (const x of [c, d].filter(Boolean)) r.push({ k: '3連複', c: [a, b, x], s: 2000 });
      const tot = r.reduce((s, t) => s + t.s, 0);
      if (tot < 10000) r[0].s += 10000 - tot;
      return r;
    },
    // ワイド軸：◎の単勝＋◎-相手のワイド流し（当たりやすさ重視だが単勝で勝負気配）
    wide(a, b, c, d) {
      const o = [b, c, d].filter(Boolean);
      const r = [{ k: '単勝', c: [a], s: 4000 }];
      for (const x of o) r.push({ k: 'ワイド', c: [a, x], s: 2000 });
      const tot = r.reduce((s, t) => s + t.s, 0);
      if (tot < 10000) r[0].s += 10000 - tot;
      return r;
    },
    // 3連単1点：◎→○→▲に全部つっこむ一点勝負（尖りの極み）
    santan1(a, b, c) {
      if (!c) return [{ k: '馬単', c: [a, b], s: 10000, o: true }];
      return [{ k: '3連単', c: [a, b, c], s: 10000, o: true }];
    },
    // 衆知：◎の複勝で土台＋◎○▲△の3連複BOX（利用者の直感＝印が集まった馬で3連複）
    consensus(a, b, c, d) {
      const top = [a, b, c, d].filter(Boolean);
      const r = [{ k: '複勝', c: [a], s: 2000 }];
      // 上位のBOX（3頭の全組合せ）
      for (let i = 0; i < top.length; i++)
        for (let j = i + 1; j < top.length; j++)
          for (let k = j + 1; k < top.length; k++)
            r.push({ k: '3連複', c: [top[i], top[j], top[k]], s: 0 });
      const tri = r.filter(t => t.k === '3連複');
      const per = tri.length ? Math.floor(8000 / tri.length / 100) * 100 : 0;
      tri.forEach(t => { t.s = per; });
      const used = 2000 + per * tri.length;
      if (used < 10000 && tri.length) tri[0].s += 10000 - used;
      return r;
    },
  };
  const STYLE_OF = {
    senko: 'honmei', jisseki: 'honmei', best: 'ana', wakaba: 'ana',
    balance: 'renka', kinso: 'renka', tekisei: 'wide', zenso: 'wide',
    santan1: 'santan1', consensus: 'consensus', _gbm: 'renka', ltr: 'honmei',
  };
  const STYLE_LABEL = {
    honmei: '本命党・単勝勝負', ana: '穴党・万馬券狙い（3連単）',
    renka: '連下広め（馬連・3連複）', wide: 'ワイド軸で手広く',
    santan1: '3連単1点・一点勝負', consensus: '複勝＋3連複BOX（総意）',
  };
  function betStyleOf(personaId) { return STYLE_OF[String(personaId).replace(/^_/, '')] || STYLE_OF[personaId] || 'renka'; }
  function betStyleName(personaId) { return STYLE_LABEL[betStyleOf(personaId)] || ''; }
  function formationBets(top4, personaId) {
    const t = (top4 || []).map(String);
    const a = t[0], b = t[1], c = t[2], d = t[3];
    if (!a || !b) return [];                 // 最低◎○は要る
    const style = STYLE_OF[String(personaId).replace(/^_/, '')] || STYLE_OF[personaId] || 'renka';
    return (BETSTYLE[style] || BETSTYLE.renka)(a, b, c, d);
  }

  /* ★オッズ相談型の買い方（ケリー基準・EVベース）★ GBMとは別のモデル。
     馬の選択はスコア、賭け額はオッズと相談して決める。人間の予想家に近い。
       scored : [{n, score}]（scoreRace の1人格ぶん・上位順）
       oddsMap: { 馬番: 単勝オッズ }（無ければ見送り扱い）
       budget : 1レースの予算（既定10,000円）
     手順: スコア→勝率(softmax)。市場勝率=1/オッズを正規化。
       期待値 EV = 勝率×オッズ。EV>1.05 の馬に単勝、◎に複勝。
       賭け額は 1/4ケリーで大小をつけ、合計を予算に丸める。妙味が無ければ見送り。 */
  // ★AIの「◎から数えて k 番手」の実測勝率（地方・holdout 由来の較正値）★
  //   スコアの大小をそのまま確率にすると過信で期待値が壊れる。順位で較正する。
  //   1番手≈28%から緩やかに減衰。残りは下位に薄く配る。
  const RANKWIN = [0.30, 0.16, 0.09, 0.05, 0.028, 0.015, 0.008, 0.004];
  function valueBets(scored, oddsMap, budget) {
    budget = budget || 10000;
    const hs = (scored || []).filter(h => oddsMap && +oddsMap[h.n] > 1);
    if (hs.length < 3) return { bets: [], skip: true, reason: 'オッズがまだ出ていません' };
    // ★市場を土台に、AIの見立てで少しだけ傾ける★
    //   AIは市場に勝てないので、市場勝率をベースにし、AI順位ぶんを弱く混ぜる。
    //   こうしないと穴馬に過大な期待値が出て嘘になる。
    const q = {}; let qz = 0; hs.forEach(h => { q[h.n] = 1 / +oddsMap[h.n]; qz += q[h.n]; });
    hs.forEach(h => { q[h.n] /= qz; });                     // 市場勝率（正規化）
    const rraw = hs.map((h, i) => i < RANKWIN.length ? RANKWIN[i] : 0.02);
    const rz = rraw.reduce((a, b) => a + b, 0);
    // ★市場を強く土台にする（AIは市場に勝てない＝傾けは弱く）★
    //   傾けを大きくすると、AIが穴を◎にしただけで巨大な期待値が出て嘘になる。
    const W = 0.15;                                          // AIの見立ての重み（市場0.85）
    const p = {}; let pz = 0;
    hs.forEach((h, i) => { p[h.n] = (1 - W) * q[h.n] + W * (rraw[i] / rz); pz += p[h.n]; });
    hs.forEach(h => { p[h.n] /= pz; });
    // 期待値の判定はAIの上位4頭かつ単勝12倍以下だけ。
    //   穴（高オッズ）は市場が効率的に価格付けするので、AIの穴◎に妙味は出さない。
    //   控除を考え妙味10%以上のみ拾う（大半は見送りになるのが正直な姿）。
    const val = [];
    for (const h of hs.slice(0, 4)) {
      const o = +oddsMap[h.n], ev = p[h.n] * o;
      if (o <= 12 && ev > 1.10) {
        const kelly = Math.max(0, (p[h.n] * o - 1) / (o - 1)) * 0.25;
        val.push({ n: h.n, o, ev, kelly });
      }
    }
    val.sort((a, b) => b.ev - a.ev);
    const bets = [];
    const axis = hs[0].n;                                   // ◎＝スコア最上位
    if (!val.length) {
      // 妙味なし＝見送り。ただし◎の複勝だけ小さく押さえる（予想家の“保険”）
      return { bets: [{ k: '複勝', c: [axis], s: 2000, note: '妙味薄・保険' }],
               skip: true, reason: '単勝に妙味のある馬がいない（見送り級）' };
    }
    // ケリー比で単勝を配分（上位4頭まで）
    const top = val.slice(0, 4);
    const ksum = top.reduce((s, v) => s + v.kelly, 0) || 1;
    let spent = 0;
    top.forEach((v, i) => {
      let s = Math.round(budget * 0.8 * (v.kelly / ksum) / 100) * 100;
      if (i === 0 && s < 1000) s = 1000;
      if (s > 0) { bets.push({ k: '単勝', c: [v.n], s, ev: v.ev }); spent += s; }
    });
    // 残りは◎の複勝（当たりやすさの土台）
    const rest = budget - spent;
    if (rest >= 1000) bets.push({ k: '複勝', c: [axis], s: rest });
    else if (bets.length) bets[0].s += rest;
    return { bets, skip: false };
  }

  /* ★人格アイコン（自作SVGライン画）★ 色と中身のパスだけ持つ。
     ★backtest/gen_ai_page.py の ICON と同じ内容にすること★（片方だけ変えない） */
  const ICONS = {
    gbm:     ['#3b82f6', '<rect x="6" y="8" width="12" height="9" rx="2"/><path d="M12 8V5"/><circle cx="12" cy="4" r="1.1"/><circle cx="9.6" cy="12" r="1"/><circle cx="14.4" cy="12" r="1"/><path d="M6 20l3-2 2.5 1.2L17 15"/>'],
    kinso:   ['#06b6d4', '<circle cx="10.5" cy="10.5" r="5"/><path d="M14.5 14.5L19 19"/><path d="M8.5 11v-1.2M10.5 11V8M12.5 11v-2"/>'],
    senko:   ['#ef4444', '<path d="M3 12h7M4 8h5M4 16h5"/><path d="M11 5l7 7-7 7"/>'],
    best:    ['#f97316', '<path d="M13 3L6 13h5l-1 8 8-11h-5z"/>'],
    zenso:   ['#8b5cf6', '<path d="M20 12a8 8 0 1 1-3-6.2"/><path d="M20 4v4h-4"/><path d="M12 8v5M9.6 8H12"/>'],
    jisseki: ['#eab308', '<path d="M8 4h8v4a4 4 0 0 1-8 0z"/><path d="M8 6H5v1a3 3 0 0 0 3 3M16 6h3v1a3 3 0 0 1-3 3"/><path d="M12 12v4M9 20l1-4h4l1 4z"/>'],
    tekisei: ['#22c55e', '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2.6"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>'],
    wakaba:  ['#84cc16', '<path d="M12 21v-9"/><path d="M12 13c0-3.3 2.2-5.5 5.5-5.5C17.5 10.8 15.3 13 12 13z"/><path d="M12 14c0-3-2-5-5-5 0 3 2 5 5 5z"/>'],
    balance: ['#94a3b8', '<path d="M12 3l7.8 4.5v9L12 21l-7.8-4.5v-9z"/><circle cx="12" cy="12" r="1.6"/><path d="M12 4.5v4M18.5 8.2l-3.4 2M5.5 8.2l3.4 2M12 19.5v-4M18.5 15.8l-3.4-2M5.5 15.8l3.4-2"/>'],
    market:  ['#0ea5e9', '<path d="M7 4v16M12 3v18M17 5v14"/><rect x="5.5" y="8" width="3" height="7"/><rect x="10.5" y="6" width="3" height="9"/><rect x="15.5" y="9.5" width="3" height="5"/>'],
    santan1: ['#dc2626', '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3.4"/><circle cx="12" cy="12" r="0.9" fill="currentColor" stroke="none"/><path d="M12 2v2.4M12 19.6V22M2 12h2.4M19.6 12H22"/>'],
    consensus: ['#0d9488', '<circle cx="8" cy="9.5" r="2.3"/><circle cx="16" cy="9.5" r="2.3"/><circle cx="12" cy="14.5" r="2.3"/><path d="M4.5 18c.6-2 2-3 3.5-3M19.5 18c-.6-2-2-3-3.5-3M8.5 20c.7-1.6 2-2.4 3.5-2.4s2.8.8 3.5 2.4"/>'],
    ltr:     ['#6366f1', '<circle cx="5" cy="7" r="1.6"/><circle cx="5" cy="17" r="1.6"/><circle cx="12" cy="12" r="1.8"/><circle cx="19" cy="8.5" r="1.6"/><circle cx="19" cy="15.5" r="1.6"/><path d="M6.5 7.6L10.4 11M6.4 16.3L10.5 13M13.6 11L17.5 8.9M13.6 13L17.5 15.1"/>'],
    total:   ['#22c55e', '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4.3"/><circle cx="12" cy="12" r="1" fill="currentColor" stroke="none"/>'],
  };
  function iconSvg(id, size) {
    const it = ICONS[id] || ICONS[String(id).replace(/^_/, '')]; if (!it) return '';
    size = size || 22;
    return '<span class="pico" style="--pc:' + it[0] + ';width:' + size + 'px;height:' + size + 'px">'
      + '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
      + 'stroke-linecap="round" stroke-linejoin="round">' + it[1] + '</svg></span>';
  }

  return { PERSONAS, MARKS, STYLES, scoreRace, zscore, runningStyle, formationBets, betStyleOf, betStyleName, valueBets, ICONS, iconSvg };
}));
