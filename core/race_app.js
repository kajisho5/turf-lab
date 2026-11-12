/* レース詳細ページの動作（race.php が読み込む）
 * ★race.html からの切り出し。コピーではなく移動。★
 *   サーバー側で土台を出し、この JS がその上を差し替える。
 *   URL は /race/{id}/ の1本。JSリダイレクトはしない（検索評価を壊すため）。
 */
/* 共通コアはコピーせず読み込む。tweet.html から関数を写して
   kochi.html を作った結果、抜けた関数が本番で未定義になり
   v357/v359/v360/v364 と4回連鎖して壊れた。二度とコピーしない。 */
const PERSONAS_API = window.PERSONAS;
/* レース詳細（出馬表 / 結果・払戻）
 *
 * ★取得は同一オリジンの /proxy.php 経由・絶対パスで叩く★
 *   相対だとサブディレクトリから404になる（過去に踏んだ）。
 *
 * ★オッズは出馬表HTMLには入っていない★
 *   HTMLの単勝欄は "---.-"、人気欄は "**" のまま。実体は別APIのJSON:
 *     /api/api_get_jra_odds.html?race_id=..&type=1&action=init
 *     data.odds["1"]["01"] = [単勝オッズ, 前回比, 人気]
 *   地方(nar)も同じパスで返る。発売前は空になるのでその場合は "―" を出す。
 *
 * ★race_id から中央/地方を判定する★
 *   中央 = YYYY+場(2桁 01-10)+回+日+R
 *   地方 = YYYY+場(2桁 30-55)+MMDD+R
 *   場コードが 10 以下なら中央。これで参照先ホストを決める。
 */
const $ = s => document.querySelector(s);
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const b64url = s => btoa(String.fromCharCode(...new TextEncoder().encode(s)))
  .replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');

// rid は /race/{id}/ のパス、無ければ ?id= から取る（両方のURLで動く）
const rid = (location.pathname.match(/\/race\/(\d{12})/) || [])[1]
         || new URLSearchParams(location.search).get('id') || '';
const isJra = (() => {
  const jyo = parseInt(rid.slice(4, 6), 10);
  return jyo >= 1 && jyo <= 10;
})();
const HOST = isJra ? 'race.netkeiba.com' : 'nar.netkeiba.com';
document.documentElement.dataset.mode = isJra ? 'jra' : 'nar';

async function grab(url){
  const r = await fetch(`/proxy.php?u=${b64url(url)}`, {cache:'no-store'});
  if(!r.ok) throw new Error('取得に失敗しました（' + r.status + '）');
  return r.text();
}
/* 馬名・騎手名を詳細ページへのリンクにする
   ★中央と地方でDBが分かれている★
     馬:   中央 /db/jra/horse/detail/  地方 /db/horse/detail/
     騎手: 地方 /db/jockey/detail/（中央の騎手個別ページはまだ無い）
   詳細ページ側が名前で引くので、名前をそのまま渡す。空なら素の文字。 */
function horseLink(name){
  if(!name) return '';
  const base = isJra ? '/db/jra/horse/detail/' : '/db/horse/detail/';
  return `<a href="${base}?name=${encodeURIComponent(name)}">${esc(name)}</a>`;
}
function jockeyLink(name){
  if(!name) return '';
  const base = isJra ? '/db/jra/jockey/detail/' : '/db/jockey/detail/';
  return `<a href="${base}?name=${encodeURIComponent(name)}">${esc(name)}</a>`;
}

const dom = t => new DOMParser().parseFromString(t, 'text/html');
const txt = (el, sel) => {
  const x = el.querySelector(sel);
  return x ? x.textContent.replace(/\s+/g,' ').trim() : '';
};

/* 単勝オッズ・人気を別APIから取る。取れなければ null（画面には「―」を出す） */
async function fetchOdds(){
  // ★中央と地方で エンドポイントもJSONの形も違う★
  //   中央 api_get_jra_odds.html → data.odds["1"]["01"] = [オッズ, 前回比, 人気]
  //   地方 api_get_nar_odds.html → ary_odds["01"] = {Odds, Ninki}
  //   地方に jra 版を投げると 404。共通だと思い込むと静かに「―」のままになる。
  const api = isJra ? 'api_get_jra_odds.html' : 'api_get_nar_odds.html';
  try{
    const j = JSON.parse(await grab(`https://${HOST}/api/${api}`
      + `?race_id=${encodeURIComponent(rid)}&type=1&action=init`));
    const m = {};
    if(isJra){
      const o = j && j.data && j.data.odds && j.data.odds['1'];
      if(!o) return null;
      for(const k in o) m[String(parseInt(k,10))] = {odds:o[k][0], pop:o[k][2]};
    }else{
      const o = j && j.ary_odds;
      if(!o) return null;
      for(const k in o) m[String(parseInt(k,10))] = {odds:o[k].Odds, pop:o[k].Ninki};
    }
    return Object.keys(m).length ? m : null;
  }catch(e){ console.warn('オッズ取得できず', e); return null; }
}

/* netkeiba の無名条件戦は "C2111213(C212)" のような生コードで返る。
   級(A1..D3)や「N歳」の後に連結された2桁組番号を「（十一）（十二）」に開く。
   SPAT4 と同じ読める形にする。名前付きレースはそのまま返す。
   ★同じ関数が index.html / race.html / php/race.php にもある。直すなら全部★ */
function prettyRaceName(name){
  if(!name) return name;
  const m = String(name).trim().match(/^([A-D][1-3]|\d+歳)(\d{4,})(?:\([^)]*\))?$/);
  if(!m || m[2].length % 2) return name;
  const gs = m[2].match(/../g).map(Number);
  if(!gs.every(g => g >= 1 && g <= 25)) return name;
  const dig = '〇一二三四五六七八九';
  const k = n => n < 10 ? dig[n] : n < 20 ? '十' + (n > 10 ? dig[n - 10] : '')
                                          : dig[Math.floor(n / 10)] + '十' + (n % 10 ? dig[n % 10] : '');
  return m[1] + gs.map(g => '（' + k(g) + '）').join('');
}

function header(doc){
  const name = prettyRaceName(txt(doc, '.RaceName')) || 'レース';
  const d1 = txt(doc, '.RaceData01');
  const d2 = txt(doc, '.RaceData02');
  // ★R番号は必ず出す★ netkeiba の .RaceNum が空でも rid から復元する
  //   条件戦は固有名が無いので、番号まで消えると見出しが空に見える。
  const num = txt(doc, '.RaceNum') || (curR ? curR + 'R' : '');
  $('#title').textContent = (num ? num + ' ' : '') + name;
  $('#sub').textContent = [d1, d2].filter(Boolean).join(' ／ ');
  document.title = `${(num ? num + ' ' : '')}${name} — カジ競馬`;
}

async function showCard(){
  const doc = dom(await grab(`https://${HOST}/race/shutuba.html?race_id=${encodeURIComponent(rid)}`));
  header(doc);
  const odds = await fetchOdds();
  const rows = [...doc.querySelectorAll('tr.HorseList')].map(tr => {
    const waku = txt(tr, '[class^="Waku"]');
    const uma  = txt(tr, '[class^="Umaban"]');
    const o = odds ? odds[String(parseInt(uma,10))] : null;
    return {
      waku, uma,
      name:    txt(tr, '.HorseInfo'),
      barei:   txt(tr, '.Barei'),
      kin:     txt(tr, 'td.Txt_C:not(.Barei):not([class^="Waku"]):not([class^="Umaban"])'),
      jockey:  txt(tr, '.Jockey'),
      trainer: txt(tr, '.Trainer'),
      weight:  txt(tr, '.Weight'),
      odds: o ? o.odds : '',
      pop:  o ? o.pop  : ''
    };
  });
  /* ★中身の無い行を捨てる★
     netkeiba の出馬表には馬番も馬名も入っていない tr.HorseList が混じる。
     そのまま出していたので、8頭立てなのに表の末尾に空の行が2本ぶら下がり、
     脚質列の枠線だけが浮いて見えていた。
     「馬番があり、馬名もある」行だけを馬とみなす。 */
  const solid = rows.filter(r => r.uma && r.name);
  rows.length = 0; rows.push(...solid);
  if(!rows.length){ $('#out').innerHTML = '<p class="msg">出馬表がまだ公開されていません。</p>'; return; }
  /* ★中身が1行も無い列は落とす★
     「―」だけが並ぶ列が残っていると、値が入っている列と見分けがつかず、
     表を横に読むときに目が滑る。地方の出馬表には性齢の列が無く、
     中央では馬体重が発表前だと空になる。 */
  const has = k => rows.some(r => r[k]);
  const hasBarei = has('barei'), hasWt = has('weight'), hasTr = has('trainer');
  $('#out').innerHTML = `<div class="scroll"><table>
    <tr><th class="stk1">枠</th><th class="stk2">馬番</th><th class="stk3">馬名</th><th>脚質</th>${hasBarei ? '<th>性齢</th>' : ''}<th class="n">斤量</th>
        <th>騎手</th>${hasTr ? '<th>厩舎</th>' : ''}${hasWt ? '<th class="n">馬体重</th>' : ''}
        <th class="n">単勝</th><th class="n">人気</th></tr>
    ${rows.map(r => `<tr>
      <td class="stk1"><span class="w w${esc(r.waku)}">${esc(r.waku)}</span></td>
      <td class="stk2 n">${esc(r.uma)}</td>
      <td class="stk3">${horseLink(r.name)}</td>
      <td class="sty" data-uma="${esc(r.uma)}"></td>
      ${hasBarei ? `<td>${esc(r.barei)}</td>` : ''}
      <td class="n">${esc(r.kin)}</td>
      <td>${jockeyLink(r.jockey)}</td>
      ${hasTr ? `<td>${esc(r.trainer)}</td>` : ''}
      ${hasWt ? `<td class="n">${esc(r.weight)}</td>` : ''}
      <td class="n">${r.odds ? esc(r.odds) : '―'}</td>
      <td class="n${r.pop === '1' ? ' pop1' : ''}">${r.pop ? esc(r.pop) : '―'}</td>
    </tr>`).join('')}
  </table></div>
  <p class="note">脚質＝近3走の<b>最初のコーナー</b>通過順÷頭数（自動判定・近走が無い馬は空欄）。
    複勝率は逃げ42.9%〜追込17.8%と差があるが、<b>人気で統制すると差はほぼ消える</b>
    （±1.4pt以内・延べ171万頭）。強い馬が前に行けるだけで、妙味ではない。</p>
  ${odds ? '' : '<p class="msg">単勝オッズは発売開始後に表示されます。</p>'}`;

  fillStyles();          // 脚質は別ページから取るので、表を出してから埋める
}

/* 脚質を出馬表に差し込む
   ★出馬表(shutuba.html)にはコーナー通過順が入っていない★
     近走つきの出馬表(shutuba_past.html)を別に取る必要がある。
     これを待ってから表を描くと、2本目の取得が遅い日に画面が真っ白になる。
     先に表を出し、取れ次第セルを埋める。取れなくても表は使える。 */
async function fillStyles(){
  let horses;
  try{
    const doc = dom(await grab(
      `https://${HOST}/race/shutuba_past.html?race_id=${encodeURIComponent(rid)}`));
    horses = NKPast.parseDoc(doc);
  }catch(e){ console.warn('脚質を取得できなかった', e); return; }
  if(!horses || !horses.length) return;

  const byNum = new Map(horses.map(h => [String(+h.n), h]));
  for(const td of document.querySelectorAll('td.sty')){
    const h = byNum.get(String(+td.dataset.uma));
    // ★ffpf（最初のコーナー）で判定する★ fpf（最終コーナー）は走りの結果が混ざる
    const s = h ? PERSONAS_API.runningStyle(h.ffpf) : null;
    // ★近走が無い馬は空欄にする★「追込」と「データ無し」を混同させない
    if(!s){ td.textContent = ''; td.title = '近走が無く判定できない'; continue; }
    td.innerHTML = `<span class="sty ${s.cls}">${s.name}</span>`;
    td.title = `近3走の最初のコーナー位置率 ${h.ffpf.toFixed(2)}`
             + `／この脚質の複勝率 ${s.fuku}%（人気で統制すると ${s.lift > 0 ? '+' : ''}${s.lift}pt）`;
  }
}

async function showResult(){
  const doc = dom(await grab(`https://${HOST}/race/result.html?race_id=${encodeURIComponent(rid)}`));
  header(doc);
  /* ★結果行のクラス名が中央と地方で違う★
     中央: <tr class="FirstDisplay HorseList">
     地方: <tr>        ← クラスが無い
     tr.HorseList で拾っていたので、**地方は結果が永久に出なかった**
     （17:25発走のレースが4時間後も「まだ結果が出ていません」）。
     クラスではなく「着順セル(.Result_Num)を持つ行」で判定する。
     これは中央・地方の両方に存在する。 */
  let resRows = [...doc.querySelectorAll('#All_Result_Table tr, .RaceTable01 tr')]
    .filter(tr => tr.querySelector('td .Rank, td.Result_Num'));
  if (!resRows.length) resRows = [...doc.querySelectorAll('tr.HorseList')];
  const rows = resRows.map(tr => {
    const tds = tr.querySelectorAll('td');
    const cell = i => tds[i] ? tds[i].textContent.replace(/\s+/g,' ').trim() : '';
    // ★人気セルのクラスは着順で変わる★
    //   1着 "Odds BgYellow Txt_C" / 2着 "Odds BgBlue02 Txt_C" …
    //   .Odds.BgYellow で取ると1着しか埋まらない（実際そうなった）。列位置で取る。
    //   0着順 1枠 2馬番 3馬名 4性齢 5斤量 6騎手 7タイム 8着差 9人気 10単勝 11上り
    return {
      rank: txt(tr, '.Result_Num') || cell(0),
      waku: cell(1), uma: cell(2),
      name: txt(tr, '.Horse_Info'),
      jockey: txt(tr, '.Jockey'),
      time: txt(tr, '.Time'),
      pop:  cell(9),
      odds: cell(10)
    };
  });
  if(!rows.length){ $('#out').innerHTML = '<p class="msg">まだ結果が出ていません。</p>'; return; }

  /* 払戻
   *
   * ★券種1行の中に「複数の組」が入っている★
   *   複勝は3頭、ワイドは3組。素朴に全部の span を拾うと
   *   「複勝 10 12 11 / 10 / 12 / 11」のように重複し、金額も
   *   「150円200円180円」と連結してしまう（実際そうなった）。
   *
   *   組の区切り方が2通りある:
   *     ul がある券種（枠連・馬連・ワイド・馬単・3連複・3連単）→ ul 1つ = 1組
   *     ul が無い券種（単勝・複勝）→ div 3つ = 1組（空divで桁を埋めている）
   *   金額は1セルに <br> 区切りで入っているので分割して組と対応づける。
   */
  const clean = el => el.textContent.replace(/\s+/g,' ').trim();
  const pays = [];
  doc.querySelectorAll('.Payout_Detail_Table tr').forEach(tr => {
    const kind = txt(tr, 'th');
    const res = tr.querySelector('.Result');
    if(!kind || !res) return;

    let combos = [];
    const uls = res.querySelectorAll('ul');
    if(uls.length){
      combos = [...uls].map(ul =>
        [...ul.querySelectorAll('li')].map(clean).filter(Boolean).join('-'));
    }else{
      const divs = [...res.children].filter(e => e.tagName === 'DIV');
      for(let i = 0; i < divs.length; i += 3){
        const c = divs.slice(i, i + 3).map(clean).filter(Boolean).join('-');
        if(c) combos.push(c);
      }
    }
    const yens = [...tr.querySelectorAll('.Payout span')]
      .flatMap(s => s.innerHTML.split(/<br\s*\/?>/i))
      .map(x => x.replace(/<[^>]*>/g,'').trim()).filter(Boolean);
    /* 人気も金額と同じく <br> 区切りのことがある（地方の複勝で
       「1人気2人気6人気」が1行目に固まって出た）。span で割れていない場合は
       <br> で割り、さらに「N人気」の連結なら正規表現で分解する。 */
    let ninki = [...tr.querySelectorAll('.Ninki span')]
      .flatMap(s => s.innerHTML.split(/<br\s*\/?>/i))
      .map(x => x.replace(/<[^>]*>/g, '').trim()).filter(Boolean);
    if (ninki.length === 1 && combos.length > 1) {
      const m = ninki[0].match(/\d+\s*人気/g);
      if (m && m.length > 1) ninki = m;
    }

    combos.forEach((c, i) => {
      if(!yens[i]) return;
      pays.push({kind: i === 0 ? kind : '', nums: c, yen: yens[i], pop: ninki[i] || ''});
    });
  });

  $('#out').innerHTML = `<div class="scroll"><table>
    <tr><th>着</th><th>枠</th><th>馬番</th><th>馬名</th><th>騎手</th>
        <th class="n">タイム</th><th class="n">単勝</th><th class="n">人気</th></tr>
    ${rows.map(r => `<tr>
      <td class="rank${['1','2','3'].includes(r.rank) ? r.rank : ''}">${esc(r.rank)}</td>
      <td><span class="w w${esc(r.waku)}">${esc(r.waku)}</span></td>
      <td class="n">${esc(r.uma)}</td>
      <td>${horseLink(r.name)}</td>
      <td>${jockeyLink(r.jockey)}</td>
      <td class="n">${esc(r.time)}</td>
      <td class="n">${esc(r.odds)}</td>
      <td class="n${r.pop === '1' ? ' pop1' : ''}">${esc(r.pop)}</td>
    </tr>`).join('')}
  </table></div>
  ${pays.length ? `<div class="pay">${pays.map(p =>
      `<div class="payrow"><b>${esc(p.kind)}</b><i>${esc(p.nums)}</i>`
      + `<em>${esc(p.yen)}</em>`
      + `<span style="color:var(--mute);flex:0 0 62px;text-align:right">${esc(p.pop)}</span></div>`
    ).join('')}</div>` : ''}`;
}

/* ===== AI予想（人格別の印） ===================================== */

let horseIndex = null;      // 馬名 -> {t:{場:[複勝率,数]}, d:{距離帯:[率,数]}}
async function loadHorseIndex(){
  if(horseIndex) return horseIndex;
  /* ★中央と地方で索引ファイルが別★
     地方は data/horses.json、中央は data/jra_horses.json。
     形式は同じ（build_jra_horse_index.py が地方に合わせて作る）ので
     読むファイルを変えるだけで attachRates はそのまま動く。 */
  const file = isJra ? '/data/jra_horses.json' : '/data/horses.json';
  const r = await fetch(file, {cache:'force-cache'});
  if(!r.ok) throw new Error('馬データを読み込めませんでした');
  horseIndex = await r.json();
  return horseIndex;
}

/* 当地複勝率(wr) と 当距離複勝率(dr) を自前の履歴から引く。
   ★netkeibaには無い値なので、13年分の公式データから作った索引を使う★
     backtest/build_horse_index.py が deploy/data/horses.json を生成している。
     推定で埋めると、公開しているバックテスト成績が当てはまらない別物になる。 */
function attachRates(horses, names, track, dist){
  if(!horseIndex) return;
  const band = dist ? String(Math.floor(dist / 200) * 200) : null;
  horses.forEach((h, i) => {
    const rec = horseIndex[names[i]];
    if(!rec) return;
    const t = track && rec.t ? rec.t[track] : null;
    const d = band && rec.d ? rec.d[band] : null;
    // 出走数が極端に少ないと率が暴れるので 3走未満は使わない（null のまま＝平均扱い）
    if(t && t[1] >= 3) h.wr = t[0] / 100;
    if(d && d[1] >= 3) h.dr = d[0] / 100;

    /* 索引は通算出走数（場ごとの[率,数]の合計）も持っているが、**入れていない**。
       バックテスト側の np は近3走の本数なので、表示だけ通算に差し替えると
       公開している成績と中身が食い違う。使うなら先に検証してから。 */
  });
}

/* ★2026-07-30: 騎手・厩舎・父の事前複勝率を引く★
   LTRの jkr/trr/sir 列。これを埋めないと33列モデルを3列欠損で動かすことになり、
   公開しているバックテスト成績（単勝◎ROI 76.9%）が当てはまらない別物になる。
   索引は build_jockey_index.py が作る（学習時と同じ50走以上の閾値で絞ってある）。
   ★名前の切り方★ 地方は3文字省略(川田将雅→川田将)、中央はJV-Dataが4文字。
   netkeibaは頭文字付き(C.ルメール)なので、正規化して完全一致→4文字→3文字で探す。 */
let jkIndex = null, trIndex = null, sireIndex = null;
async function loadPersonIndexes(isJra){
  if(jkIndex) return;
  const g = async (f) => { try{ const r = await fetch(f, {cache:'no-cache'});
    return r.ok ? await r.json() : {}; }catch(e){ return {}; } };
  const [a, b, c] = await Promise.all([
    g(isJra ? '/data/jra_jockeys.json' : '/data/jockeys.json'),
    g(isJra ? '/data/jra_trainers.json' : '/data/trainers.json'),
    isJra ? Promise.resolve({}) : g('/data/sires.json'),   // 父は地方のみ（中央データに無い）
  ]);
  jkIndex = a; trIndex = b; sireIndex = c;
}
/* ★tweet.html の _jkNorm と同一ロジックにすること★
   マークを列挙して消す方式だと漏れる（▽笹川翼が引けていなかった）。
   「名前に使う文字だけ残す」= 漢字・々・ひらがな・カタカナ・ー・英字・. */
function _pnNorm(s){
  return String(s || '').replace(/^[A-Za-z]{1,2}\s*[.．]\s*/, '')
                        .replace(/[^一-龥々ぁ-んァ-ヺーA-Za-z.]/g, '');
}
function _pnLook(idx, raw){
  if(!idx || !raw) return null;
  const n = _pnNorm(String(raw).split(/[・･]/).pop());   // 「美浦・田中」→「田中」
  if(!n) return null;
  let e = idx[n];
  if(!e && n.length > 4) e = idx[n.slice(0, 4)];
  if(!e && n.length > 3) e = idx[n.slice(0, 3)];
  return (e && e[0] != null) ? e[0] / 100 : null;
}
function attachPersonRates(horses){
  horses.forEach(h => {
    h.jkr = _pnLook(jkIndex, h.jockeyName);
    h.trr = _pnLook(trIndex, h.trainerName);
    h.sir = _pnLook(sireIndex, h.sireName);
  });
}

/* GBMの採点を人格と同じ形（[{n, mark}] 上位順）にして返す
   ★スコアの出し方は core/scoring.js の scoreEntries に集約してある★
     採点手順を画面側に書き写すと、tweet.html と数字がズレる。 */
const GBM_ID = '_gbm';
// ★縦書きの見出しは長いと上が切れる★「GBM（本命）」は8文字で切れた
const GBM_PERSONA = { id: GBM_ID, name: 'GBM本命', axes: [],
  desc: '決定木。当サイトが実際に使っている予想。人格とは別系統' };

function scoreWithGbm(rawHtml){
  if(typeof SCORING === 'undefined' || !SCORING || !SCORING.scoreEntries) return null;
  try{
    SCORING.MODE = isJra ? 'jra' : 'nar';
    const ps = SCORING.parseShutuba(rawHtml);
    if(!ps || !ps.entries || !Object.keys(ps.entries).length) return null;
    const scored = SCORING.scoreEntries(ps, rid, (ps.cond || {}).raceName);
    // ★GBMが出なかった場合は列ごと出さない★
    //   線形フォールバックのまま「GBMの予想」として見せない
    if(!scored.some(x => x.gbm != null)) return null;
    return scored.map((x, i) => ({
      n: String(+x.num), score: x.s,
      mark: PERSONAS_API.MARKS[i] || ''
    }));
  }catch(e){ console.warn('GBMを算出できなかった', e); return null; }
}

async function showAi(){
  // ★生HTMLも保持する★ 人格は DOM から、GBM は parseShutuba が生HTMLを取る
  const raw = await grab(
    `https://${HOST}/race/shutuba_past.html?race_id=${encodeURIComponent(rid)}`);
  const doc = dom(raw);
  header(doc);

  const horses = NKPast.parseDoc(doc);
  if(!horses.length){ $('#out').innerHTML = '<p class="msg">出馬表がまだ公開されていません。</p>'; return; }

  // 馬名は parseDoc が同じ1回のパースで返す（別ループにすると添字がズレる）
  const names = horses.map(h => h.name);

  // 開催場と距離をヘッダから取る
  const sub = txt(doc, '.RaceData01') + ' ' + txt(doc, '.RaceData02');
  const track = (sub.match(/(門別|盛岡|水沢|浦和|船橋|大井|川崎|金沢|笠松|名古屋|園田|姫路|高知|佐賀|帯広|札幌|函館|福島|新潟|東京|中山|中京|京都|阪神|小倉)/) || [])[1] || '';
  const dist = parseInt((sub.match(/[ダ芝](\d{3,4})/) || [])[1], 10) || null;
  /* ★2026-07-29: LTRの履歴系特徴量（rest/dchg/tchg）を埋める★
     rid = YYYY(4)+TC(2)+MMDD(4)+RR(2) → 今日の日付が復元できる。 */
  NKPast.enrich(horses, { date: String(rid).slice(0,4) + String(rid).slice(6,10),
                          track: track, dist: dist });
  // LTR用の馬場（良/稍/重/不）。「馬場:良」の形。取れなければ欠損扱い。
  const going = (sub.match(/馬場[:：]?\s*(不良|稍重|良|稍|重|不)/) || [])[1] || '';

  try{ await loadHorseIndex(); attachRates(horses, names, track, dist); }
  catch(e){ console.warn('馬データ未取得', e); }
  // 騎手・厩舎・父の事前複勝率（LTRのjkr/trr/sir。失敗しても欠損で続行）
  try{ await loadPersonIndexes(isJra); attachPersonRates(horses); }
  catch(e){ console.warn('騎手/厩舎/父データ未取得', e); }

  // 人気（市場人格が使う）を単勝オッズAPIから
  const odds = await fetchOdds();
  if(odds) horses.forEach(h => { const o = odds[String(+h.n)]; if(o) h.pop = +o.pop || null; });

  // tc=場コード（ridの5〜6桁目。NAR:30門別..55佐賀 / JRA:01札幌..10小倉）。LTRのカテゴリ特徴
  const _tc = (String(rid).length === 12 && isFinite(+String(rid).slice(4, 6)))
    ? +String(rid).slice(4, 6) : null;
  const marks = PERSONAS_API.scoreRace(horses, { dist: dist, going: going, tc: _tc });

  /* ★確定印（2026-08-04・不一致対策）★
     人格の印は再計算のたびにデータ源の微差（公式vs netkeibaの人気・騎手名など）で
     僅差の馬が入れ替わりうる。実際に盛岡8Rで「/ai/の的中カードは◎5で3連単213万的中、
     このタブは◎6で外れ」という不一致が起きた（ユーザー指摘）。
     → 公式データで計算した確定印(pmarks.json・毎朝更新・直近35日)があるレースは
       必ずそちらで上書きする。/ai/ の成績・的中カードと同じ計算＝単一の正。
     GBM列は対象外（本体の正は predictions.php の保存値で仕組みが別）。 */
  let officialMarks = false;
  try{
    const _day = new Date(Date.now() + 9*3600e3).toISOString().slice(0,10).replace(/-/g,'');
    const pj = await fetch(`/data/pmarks.json?d=${_day}`);   // ?d=で日替わりキャッシュバスト
    if(pj.ok){
      const pm = (await pj.json())[String(rid)];
      if(pm){
        for(const pid in pm){
          if(Array.isArray(pm[pid]) && pm[pid].length)
            marks[pid] = pm[pid].map(n => ({ n: String(n) }));
        }
        officialMarks = true;
      }
    }
  }catch(e){ console.warn('確定印の取得失敗（暫定印で表示）', e); }

  /* ★これまでの予想（GBM）も1人の予想家として並べる★
     利用者から「入れといて」と言われていたのに、AI予想の表に
     人格しか出ていなかった。core/scoring.js を読み込んですらいなかった。
     GBM本体は触らない（鉄則3）。ここでやるのは呼び出しだけ。 */
  const gbm = scoreWithGbm(raw);
  if(gbm) marks[GBM_ID] = gbm;

  /* ★自信度バッジ★ GBMの◎○スコア差(gap)で「このレースはどれだけ絞れるか」を出す。
     ★実測（backtest/bt_gap_check.js・14頭未満7,169Rから）★
       gap<1.5 → ◎複勝60.5% / 1.5-4 → 63.7% / 4-8 → 68.0% / 8+ → 78.8%
       （14頭以上は64.1%で、頭数だけでは下がらないと判明。頭数別の特別扱いはしない）
     ★「見送り」とは呼ばない★ 最下位帯でも60.5%（ランダム約30%を大きく上回る）あり、
     tweet.html由来の「見送り」ラベルをそのまま使うと実態より弱く見せてしまう＝盛り過ぎの逆＝過小評価も不正直。
     4段階の自信度として出す。閾値はこの実測にそのまま合わせてあり、変えるなら再検証すること。 */
  let battleTier = null;
  if(gbm && gbm.length >= 2){
    const s = gbm.slice().sort((a, b) => b.score - a.score);
    const gap = s[0].score - s[1].score;
    if(gap >= 8) battleTier = { tier: '◎抜けてる', cls: 'battle', reason: '実測◎複勝78.8%（gap8以上）' };
    else if(gap >= 4) battleTier = { tier: '◎優勢', cls: 'aim', reason: '実測◎複勝68.0%（gap4-8）' };
    else if(gap >= 1.5) battleTier = { tier: '標準', cls: 'fuku', reason: '実測◎複勝63.7%（gap1.5-4）' };
    else battleTier = { tier: '◎○僅差', cls: 'pass', reason: '実測◎複勝60.5%（gap1.5未満）' };
  }

  /* ★行=馬 / 列=人格 の表にする★
     人格を行にすると「どの馬に印が集まっているか」が読み取れない。
     馬を行にして横に人格を並べると、集まり方が一目で分かる。
     馬番と馬名は position:sticky で左に固定し、人格側だけ横スクロールさせる。 */
  const nameOf = {}, wakuOf = {};
  horses.forEach((h, i) => { nameOf[h.n] = names[i] || h.n; wakuOf[h.n] = h.wk; });

  // 算出できない人格は列ごと落とす（空欄が並ぶより、無いほうが読みやすい）
  const has = axis => horses.some(h => h[axis] !== null && h[axis] !== undefined);
  /* 値が無い人格に加え、**全馬同点で意見が出なかった**人格も列ごと落とす。
     scoreRace は同点のとき空配列を返す（馬番順の印を「予想」として出さないため）。 */
  const cols = PERSONAS_API.PERSONAS.filter(
    p => p.axes.every(([a]) => has(a)) && (marks[p.id] || []).length);
  // GBMは先頭に置く。これが本命の予想で、人格は観点別の参考
  if((marks[GBM_ID] || []).length) cols.unshift(GBM_PERSONA);
  const dropped = PERSONAS_API.PERSONAS.filter(p => !cols.includes(p));

  // 馬番 -> 人格ID -> 印
  const markOf = {};
  for (const p of cols) {
    (marks[p.id] || []).forEach((x, i) => {
      if (i < PERSONAS_API.MARKS.length) {
        (markOf[x.n] = markOf[x.n] || {})[p.id] = PERSONAS_API.MARKS[i];
      }
    });
  }

  // 印の集計（◎が何人か、が一番知りたい情報）
  const tally = h => {
    const t = {'◎':0, '○':0, '▲':0, '△':0, '☆':0};
    for (const p of cols) {
      const m = markOf[h.n] && markOf[h.n][p.id];
      if (m) t[m]++;
    }
    return t;
  };

  // 中央のレースでは馬体重が取れないことがある。全行「―」なら列ごと落とす
  // （情報が無い列が残っていると、値が入っている列と見分けがつかなくなる）
  const hasWt = horses.some(h => h.wt);
  const sorted = [...horses].sort((a, b) => +a.n - +b.n);
  const maxMaru = Math.max(...sorted.map(h => tally(h)['◎']), 0);

  const body = sorted.map(h => {
    const t = tally(h);
    const o = odds ? odds[String(+h.n)] : null;
    const hot = t['◎'] === maxMaru && maxMaru > 0;
    return `<tr${hot ? ' class="hot"' : ''}>
      <td class="stick"><span class="w w${esc(h.wk)}">${esc(h.n)}</span><span class="hn">${esc(nameOf[h.n])}</span></td>
      ${cols.map(p => {
        const m = markOf[h.n] && markOf[h.n][p.id];
        return `<td class="mk">${m ? `<b class="m${'◎○▲△☆'.indexOf(m)}">${m}</b>` : ''}</td>`;
      }).join('')}
      <td class="mk total"><div class="totwrap">${t['◎'] ? `<b class="m0">◎<small>${t['◎']}</small></b>` : ''}${t['○'] ? `<b class="m1">○<small>${t['○']}</small></b>` : ''}</div></td>
    </tr>`;
  }).join('');

  // ★各AIの買い目（AIごとの尖った買い方）★ AI名タップで下に出す。これはギャンブル。
  const betHtmlOf = (pid) => {
    const p = cols.find(c => c.id === pid); if (!p) return '';
    const rank = (marks[pid] || []).slice(0, 4).map(x => x.n);
    if (rank.length < 2) return `<p class="msg">「${esc(p.name)}」はこのレースで買い目を作れません（印が足りない）。</p>`;
    const bets = PERSONAS_API.formationBets(rank, pid);
    const mk = ['◎', '○', '▲', '△'].map((m, i) => rank[i] ? `${m}${esc(rank[i])}` : '')
      .filter(Boolean).join(' ');
    const styleName = PERSONAS_API.betStyleName ? PERSONAS_API.betStyleName(pid) : '';
    const head = `<div class="aibhead">${PERSONAS_API.iconSvg(pid, 26)}` +
      `<span class="nm">${esc(p.name)}</span><span class="aibmk">${mk}</span></div>` +
      (styleName ? `<div class="aibstyle">買い方：${esc(styleName)}</div>` : '');
    if (!bets.length) return head + `<p class="msg" style="margin:6px 0 0">印が足りず買い目を作れません。</p>`;
    const axis = String(rank[0]);
    // 券種ごとにまとめる。順序あり(3連単/馬単)は「◎→○→▲」、無しは軸-流し。
    const g = {};
    bets.forEach(b => { const o = g[b.k] = g[b.k] || { items: [], s: b.s, o: !!b.o }; o.items.push(b.c.map(String)); });
    const rows = Object.entries(g).map(([k, o]) => {
      const cnt = o.items.length;
      let disp;
      if (o.items.every(c => c.length === 1)) disp = o.items.map(c => c[0]).join('.');
      else if (o.o) disp = o.items.map(c => c.join('→')).join('／');           // 順序あり
      else if (o.items.every(c => c.length === 2 && c.includes(axis))) {        // 馬連/ワイド 軸流し（2頭組）
        disp = axis + '-' + o.items.map(c => c.filter(x => x !== axis).join('.')).join('.');
      } else {
        // 3連複など3頭組。全組に共通する軸を検出して「軸-流し」表記にする（例 3-10-5.11）。
        const srt = a => a.slice().sort((x, y) => +x - +y);
        const tri = o.items.every(c => c.length === 3);
        const common = (tri && o.items.length > 1)
          ? o.items[0].filter(x => o.items.every(c => c.includes(x))) : [];
        if (common.length === 2) {                                             // 2頭軸流し
          const legs = o.items.map(c => c.filter(x => common.indexOf(x) < 0)[0]).filter(Boolean);
          disp = srt(common).join('-') + '-' + srt(legs).join('.');
        } else if (common.length === 1) {                                      // ◎1頭軸
          const others = [...new Set([].concat(...o.items.map(c => c.filter(x => x !== common[0]))))];
          const fullBox = others.length * (others.length - 1) / 2 === o.items.length;
          disp = fullBox ? common[0] + '-' + srt(others).join('.')
                         : o.items.map(c => srt(c).join('-')).join('・');
        } else {                                                               // 完全BOXなら "a.b.c BOX"、他は組列挙
          const uni = [...new Set([].concat(...o.items))];
          const isBox = tri && uni.length * (uni.length - 1) * (uni.length - 2) / 6 === o.items.length;
          disp = isBox ? srt(uni).join('.') + ' BOX'
                       : o.items.map(c => srt(c).join('-')).join('・');
        }
      }
      const amt = cnt > 1 ? `${cnt}点 各${o.s.toLocaleString()}円` : `${o.s.toLocaleString()}円`;
      return `<div class="tkrow"><b>${k}</b> ${esc(disp)}<span class="tks">${amt}</span></div>`;
    }).join('');
    // ★モンテカルロ：このレースを10万回やった時の的中率・期待回収・一発の大きさ★
    //   着順は市場（単勝オッズ）から作った勝率で引く（＝市場を正しいと仮定した世界）。
    //   AIの見立てで勝率を水増ししない＝嘘の期待値を出さない。エンジンは
    //   backtest/bt_montecarlo.js で実測の複勝率に合わせて較正済み（単勝誤差-0.1pt）。
    let mcHtml = '';
    try {
      if (typeof MONTECARLO !== 'undefined' && odds) {
        const oddsMap = {};
        for (const k in odds) if (+odds[k].odds > 1) oddsMap[k] = +odds[k].odds;
        const str = MONTECARLO.winProbsFromOdds(oddsMap);
        if (str && Object.keys(str).length >= 3 && bets.length) {
          const res = MONTECARLO.simulate(str, bets, null, 30000);
          const inv = bets.reduce((s, b) => s + (b.s || 0), 0);
          let ev = 0, maxMul = 0;
          res.perTicket.forEach((t, i) => {
            const b = bets[i];
            const pay = b.k === '単勝'
              ? (oddsMap[String(b.c[0])] || 0) * 100        // 単勝は実オッズ
              : MONTECARLO.fairPayout(b.k, t.hitRate);      // 他は控除率こみ理論配当
            ev += t.hitRate * pay / 100 * (b.s || 0);
            if (pay / 100 > maxMul) maxMul = pay / 100;
          });
          const evPct = inv ? Math.round(100 * ev / inv) : 0;
          mcHtml = `<div class="aibmc">🎲 <b>10万回シミュ</b>　`
            + `的中 <b class="mcv">${(res.hitAny * 100).toFixed(1)}%</b>`
            + `　期待回収 <b class="mcv">${evPct}%</b>`
            + `　一発最高 <b class="mcv">約${Math.round(maxMul).toLocaleString()}倍</b>`
            + `<div class="mcnote">市場オッズを正しいと仮定した的中率。3連単等の配当は控除率こみの推定。`
            + `どの買い方でも期待回収は控除率ぶん負ける＝違うのは<strong>的中率と一発の大きさ</strong>。</div></div>`;
        }
      }
    } catch (e) { console.warn('モンテカルロ算出できず', e); }

    return head + `<div class="aibtix2">${rows}</div>` + mcHtml +
      `<p class="msg" style="margin:6px 0 0">合計10,000円。各AIの通期成績は<a href="/ai/">AI予想家の成績</a>。` +
      `当たれば大きい、外れれば0。ギャンブルなので<strong>資金管理は自己責任</strong>で。</p>`;
  };

  // ★このレースの堅さ／波乱度（自信度）★ 市場の勝率分布から算出。MCエンジンを流用。
  let shapeHtml = '';
  try {
    if (typeof MONTECARLO !== 'undefined' && odds && MONTECARLO.raceShape) {
      const oddsMap = {};
      for (const k in odds) if (+odds[k].odds > 1) oddsMap[k] = +odds[k].odds;
      const str = MONTECARLO.winProbsFromOdds(oddsMap);
      const sh = str ? MONTECARLO.raceShape(str, 30000) : null;
      if (sh) {
        const stars = '★'.repeat(sh.stars) + '☆'.repeat(5 - sh.stars);
        shapeHtml = `<div class="raceshape rs${sh.stars}">`
          + `<span class="rslbl">🎯 このレースの堅さ</span>`
          + `<span class="rsstars">${stars}</span><span class="rslevel">${esc(sh.level)}</span>`
          + `<div class="rsmeta">1番人気(${esc(sh.favNum)}番)の勝率 約${Math.round(sh.p1 * 100)}%`
          + `　波乱度 ${Math.round(sh.upsetWin * 100)}%（3番人気以下が勝つ確率）`
          + `　※市場オッズからの推定。堅い＝絞れる／波乱＝手広く。</div></div>`;
      }
    }
  } catch (e) { console.warn('レースの堅さ算出できず', e); }

  // ★GBMの自信度（◎○のスコア差）★ 市場(raceShape)とは別ソース(自社モデル)。
  //   両方あれば併記、GBMが出せなければ市場側だけ表示。
  if (battleTier) {
    const cls = { battle: 'rs5', aim: 'rs4', fuku: 'rs3', pass: 'rs2' }[battleTier.cls] || 'rs3';
    shapeHtml += `<div class="raceshape ${cls}">`
      + `<span class="rslbl">🤖 AIの自信度</span>`
      + `<span class="rslevel">${esc(battleTier.tier)}</span>`
      + `<div class="rsmeta">${esc(battleTier.reason)}（自社モデルのgapによる4段階・7,169R実測）</div></div>`;

    /* ★買い目の目安（SITE_MAP P1「単複／馬連ワイド／3連単の、どこまで手を出すべきか」）★
       新しい実測は増やさず、上のgap実測（複勝率）だけから導く。券種ごとの当てやすさの
       一般的な序列（単勝＜馬連/ワイド＜3連複＜3連単、頭数が絡むほど難）に、
       gapが示す「◎の信頼度」を掛け合わせただけの目安。断定はしない＝「目安」と明記。 */
    /* ★3連単はどの帯でも推奨しない★（2026-08-04・ユーザー方針＋実測）
       ◎1着固定の3着頭数スイープ（holdout 44,103R）で全設定が赤字。マルチも
       日々の仮想集計で損側に出続けている。旧文の「3連系は点数を絞って」
       「手を広げるなら3連複・3連単で」は誘導になるため削除した。 */
    const GUIDE = {
      battle: '◎の単勝・複勝どちらも手が届く帯。馬連・ワイドまでは実測的に狙いやすい。',
      aim: '複勝・ワイドが本線。単勝は妙味次第。3連単（マルチ含む）は実測で赤字が出やすく推奨しません。',
      fuku: 'ワイド・馬連流しが手堅い帯。3連単は実測で赤字が出やすく推奨しません。',
      pass: '◎○が拮抗＝的を絞りにくい帯。無理に手を広げるより見送りが無難。',
    }[battleTier.cls];
    if (GUIDE) {
      shapeHtml += `<div class="raceshape rs3"><span class="rslbl">🎯 買い目の目安</span>`
        + `<div class="rsmeta" style="flex-basis:100%">${esc(GUIDE)}`
        + `　※上の自信度から導いた目安で、保証ではありません。実際の買い目はAI名タップで。</div></div>`;
    }
  }

  const markSrcNote = officialMarks
    ? `<p class="msg" style="padding:0 0 6px">✅ この印は<strong>公式確定データによる確定値</strong>です（毎朝更新・<a href="/ai/">AI別成績</a>の集計と同じ計算）。発走前に表示していた暫定印とは、僅差の馬で入れ替わっていることがあります。</p>`
    : `<p class="msg" style="padding:0 0 6px">⏳ この印は<strong>暫定</strong>です（netkeibaのデータからのライブ計算）。確定印は<strong>レース確定の翌朝から約35日間</strong>だけ保持しているため、これから走るレースと、それより古いレースでは暫定表示になります。</p>`;
  $('#out').innerHTML = shapeHtml + markSrcNote + `
  <p class="msg" style="padding:0 0 10px">観点の違う<strong>${cols.length}つの予想</strong>を並べています。
  <strong>◎が集まっている馬</strong>ほど、多くの観点から見て有力です。
  ☆はその人格の「穴」（人気より高く評価した馬）。オッズは<strong>出馬表</strong>タブにあります。
  各人格の実測成績は<a href="/ai/">AI予想家の成績</a>で公開しています。</p>
  <div class="scroll"><table class="ai">
    <tr>
      <th class="stick">馬番・馬名</th>
      ${cols.map(p => `<th class="mk aihdr" data-p="${esc(p.id)}" title="${esc(p.desc)}">
        ${PERSONAS_API.iconSvg(p.id, 20)}<span>${esc(p.name)}</span></th>`).join('')}
      <th class="mk total" title="全人格の◎○の集計（「総合」人格＝balanceとは別物）">${PERSONAS_API.iconSvg('total', 20)}<span>印の集計</span></th>
    </tr>
    ${body}
  </table></div>
  <p class="msg" style="padding:6px 0 4px"><strong>AI名をタップ</strong>すると、そのAIの買い目（10,000円配分）が出ます。</p>
  <div class="aibetbox" id="aibetbox">${betHtmlOf(cols[0].id)}</div>
  ${dropped.length ? `<p class="msg">※ ${esc(dropped.map(p => p.name).join('・'))} は
    このレースではデータ不足で算出できないため列を外しています。</p>` : ''}
  <p class="msg">※ 各人格は独立した観点で、当てるための最適解ではありません。
  <strong>市場（人気順）を上回った人格はまだ一つもありません。</strong>
  黄色の行は◎が最も集まった馬です。</p>`;

  // AI名（列見出し）タップでその買い目を下に出す
  const box = document.getElementById('aibetbox');
  const hdrs = $('#out').querySelectorAll('.aihdr');
  hdrs.forEach(th => th.addEventListener('click', () => {
    hdrs.forEach(x => x.classList.remove('sel'));
    th.classList.add('sel');
    if (box) box.innerHTML = betHtmlOf(th.dataset.p);
  }));
  if (hdrs[0]) hdrs[0].classList.add('sel');
}


/* ===== 上部ナビ（場 / R番号） =====================================
 * ★R番号は race_id から直接作れる★
 *   中央 YYYY+場+回+日+RR / 地方 YYYY+場+MMDD+RR
 *   どちらも**末尾2桁がR番号**で、先頭10桁は同一開催で共通。
 *   なので先頭10桁 + ゼロ埋めR で兄弟レースのIDになる（取得不要）。
 * ★場タブはその日の一覧が要る★
 *   一覧から渡された ?d=YYYYMMDD を使う。無ければ地方は race_id から
 *   復元でき（YYYY + MMDD）、中央は日付を持たないので今日を使う。
 */
function ymdFromRid(){
  const q = new URLSearchParams(location.search).get('d');
  if(q && /^\d{8}$/.test(q)) return q;
  if(!isJra) return rid.slice(0,4) + rid.slice(6,10);   // 地方は復元できる
  const t = new Date();
  return t.getFullYear() + String(t.getMonth()+1).padStart(2,'0')
       + String(t.getDate()).padStart(2,'0');
}
const DATE = ymdFromRid();
const curR = parseInt(rid.slice(10,12), 10);

function buildRaceTabs(maxR){
  $('#rtabs').innerHTML = Array.from({length: maxR}, (_, i) => {
    const r = i + 1;
    const id = rid.slice(0,10) + String(r).padStart(2,'0');
    return `<a href="/race/${id}/?d=${DATE}"${r === curR ? ' aria-current="page"' : ''}>${r}R</a>`;
  }).join('');
}

async function buildNav(){
  buildRaceTabs(12);                       // まず12個出す（取得を待たせない）
  try{
    const url = `https://${HOST}/top/race_list_sub.html?kaisai_date=${DATE}`;
    const doc = dom(await grab(url));
    let boxes = doc.querySelectorAll('.RaceList_DataList');
    if(!boxes.length) boxes = doc.querySelectorAll('.RaceList_Box');
    const vs = [];
    boxes.forEach(box => {
      const title = box.querySelector('.RaceList_DataTitle, .RaceList_Date, h3');
      const ids = [...new Set([...box.querySelectorAll('a[href*="race_id="]')]
        .map(a => (a.getAttribute('href').match(/race_id=(\d+)/) || [])[1]).filter(Boolean))];
      if(!ids.length) return;
      const nm = title ? title.textContent.replace(/\s+/g,' ').trim() : '';
      vs.push({
        name: (nm.match(/(札幌|函館|福島|新潟|東京|中山|中京|京都|阪神|小倉|門別|盛岡|水沢|浦和|船橋|大井|川崎|金沢|笠松|名古屋|園田|姫路|高知|佐賀|帯広)/) || [, nm])[1],
        first: ids[0], prefix: ids[0].slice(0,10), n: ids.length
      });
    });
    if(vs.length){
      $('#vtabs').innerHTML = vs.map(v =>
        `<a href="/race/${v.prefix}${String(Math.min(curR, v.n)).padStart(2,'0')}/?d=${DATE}"`
        + `${v.prefix === rid.slice(0,10) ? ' aria-current="page"' : ''}>${esc(v.name)}</a>`).join('');
      const me = vs.find(v => v.prefix === rid.slice(0,10));
      if(me) buildRaceTabs(me.n);          // 実際のレース数に合わせ直す
    }
  }catch(e){
    console.warn('ナビを作れず', e);       // ナビが出なくても本体は見られる
  }
}

let tab = 'card';
async function load(){
  $('#tCard').setAttribute('aria-pressed', tab === 'card');
  $('#tAi').setAttribute('aria-pressed', tab === 'ai');
  $('#tResult').setAttribute('aria-pressed', tab === 'result');
  $('#out').innerHTML = '<p class="msg">読み込み中…</p>';
  try{
    if(!rid) throw new Error('レースが指定されていません');
    if(tab === 'card') await showCard();
    else if(tab === 'ai') await showAi();
    else await showResult();
  }catch(e){
    // ★握り潰さない★ 原因が見えないと直せない
    $('#out').innerHTML = `<p class="msg err">読み込めませんでした：${esc(e.message)}</p>`;
    console.error(e);
  }
}
$('#tCard').onclick = () => { tab = 'card'; load(); };
$('#tAi').onclick = () => { tab = 'ai'; load(); };
$('#tResult').onclick = () => { tab = 'result'; load(); };
// サーバーが出した土台を消してから動的版を描く（二重に見せない）
//   ★#ssr を消したら動的版の #title を必ず見せる★
//   race.php は SSR の見出し(#ssr内)と、JSが埋める #title(初期display:none)を
//   二重に持つ。#ssr を消しただけだと #title が隠れたままで、レース名が
//   どこにも出なくなっていた（本番で発覚）。
const ssr = document.getElementById('ssr');
if (ssr) {
  ssr.remove();
  const t = document.getElementById('title');
  if (t) t.style.display = '';
}
buildNav();
load();
