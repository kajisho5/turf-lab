# -*- coding: utf-8 -*-
"""中央競馬の馬検索と馬詳細（血統図つき）

/db/jra/horse/         馬検索
/db/jra/horse/detail/  馬の詳細（3代血統図 + 戦績）

★血統図は3代（14頭）★
  UM_DATA（馬マスタ）に 46バイト×14世代 で入っている。
  父・母 / 父父・父母・母父・母母 / さらにその親8頭。
  地方は父・母父の2つしか持っていないので、血統図は中央だけ。

★袋分けは地方と同じ規則（馬名のMD5先頭2桁）★
  ページ側のMD5実装を使い回せる。規則を変えると実装が2つになる。

入力: deploy/db/jra/h/*.json（build_jra_pedigree.py が生成）
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import site_config                                            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = site_config.get()
OUT_SEARCH = os.path.join(ROOT, "deploy", "db", "jra", "horse", "index.html")
OUT_DETAIL = os.path.join(ROOT, "deploy", "db", "jra", "horse", "detail", "index.html")

NAV = ('<nav class="snav"><a href="/">レース一覧</a><a href="/ai/">AI予想家</a>'
       '<a href="/record/">予想の記録</a><a href="/articles/">記事</a>'
       '<a href="/db/">データベース</a><a href="/calendar/">重賞カレンダー</a></nav>')

JYO_JS = ("{'01':'札幌','02':'函館','03':'福島','04':'新潟','05':'東京',"
          "'06':'中山','07':'中京','08':'京都','09':'阪神','10':'小倉'}")

CSS = """*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);
  font-family:"Noto Sans JP",-apple-system,BlinkMacSystemFont,sans-serif;
  font-size:16px;line-height:1.8;-webkit-text-size-adjust:100%}
a{color:var(--blue)}
.wrap{max-width:960px;margin:0 auto;padding:22px 16px 72px}
h1{font-size:27px;margin:8px 0 4px;border-left:5px solid var(--yellow);padding-left:12px}
h2{font-size:20px;margin:32px 0 6px}
h2::before{content:"";display:inline-block;width:4px;height:16px;margin-right:8px;
  background:var(--blue);vertical-align:-2px;border-radius:2px}
.lead,.sub{color:var(--mute)}
.snav{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 16px}
.snav a{border:1px solid var(--line);background:var(--panel);border-radius:999px;
  padding:4px 13px;text-decoration:none;color:var(--mute);font-size:15px}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{width:100%;border-collapse:collapse;margin:10px 0;font-size:16px;min-width:560px}
th,td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{color:var(--mute);font-weight:700;background:var(--panel)}
tbody tr:nth-child(even){background:var(--stripe)}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.r1{color:var(--yellow);font-weight:700}
.r2{color:var(--blue);font-weight:700}
.r3{color:var(--green);font-weight:700}
.paid{color:var(--green);font-weight:700}
.kpi{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}
.kpi div{flex:1 1 120px;background:var(--panel);border:1px solid var(--line);
  border-top:3px solid var(--line);border-radius:12px;padding:11px 14px}
.kpi div:nth-child(2){border-top-color:var(--yellow)}
.kpi div:nth-child(3){border-top-color:var(--orange)}
.kpi div:nth-child(4){border-top-color:var(--green)}
.kpi div:nth-child(5){border-top-color:var(--blue)}
.kpi b{display:block;font-size:24px;font-variant-numeric:tabular-nums;line-height:1.3}
.kpi span{color:var(--mute);font-size:14px}
/* ── 血統図 ──────────────────────────────
   ★3代を「列＝世代」で並べる★
     縦に父系・母系、横に世代。競馬の血統表の並びに合わせる。
     grid の行数を 8 にして、各世代がその倍数の高さを占めるようにすると
     どの馬が誰の親か、線を引かなくても位置で分かる。 */
.ped{display:grid;grid-template-columns:repeat(3,minmax(112px,1fr));
  grid-template-rows:repeat(8,minmax(38px,auto));gap:4px;margin:12px 0;min-width:360px}
.ped div{background:var(--panel);border:1px solid var(--line);border-radius:8px;
  padding:5px 8px;display:flex;align-items:center;font-size:14px;line-height:1.3;
  word-break:break-all;overflow:hidden}
.ped .g1{grid-row:span 4;font-size:16px;font-weight:700}
.ped .g2{grid-row:span 2}
.ped .g3{grid-row:span 1;font-size:14px;color:var(--mute)}
/* 父系は上半分、母系は下半分。境目を色で示す */
.ped .sireside{border-left:3px solid var(--blue)}
.ped .damside{border-left:3px solid var(--red)}
.fbox{border:1px solid var(--line);border-radius:12px;padding:6px 14px 14px;
  margin:16px 0;background:var(--panel)}
.fbox legend{padding:0 8px;font-weight:700;font-size:16px}
.fbox legend span{font-weight:400;color:var(--mute);font-size:14px}
.filters{display:grid;gap:10px;grid-template-columns:1fr 1fr;margin:10px 0 0}
@media(min-width:640px){.filters{grid-template-columns:repeat(4,1fr)}}
.filters label{display:flex;flex-direction:column;gap:3px;
  font-size:14px;color:var(--mute);font-weight:700}
.filters input,.filters select{appearance:none;border:1px solid var(--line);
  background:var(--bg);color:var(--txt);font:inherit;font-size:16px;
  padding:9px 11px;border-radius:10px;width:100%}
.chip{appearance:none;border:1px solid var(--line);background:var(--bg);
  color:var(--mute);font:inherit;font-size:15px;padding:5px 14px;border-radius:999px;
  cursor:pointer;margin-right:8px}
.note{color:var(--mute);font-size:15px}
.msg{color:var(--mute);padding:22px 0}
.xnote{background:var(--panel,rgba(128,128,128,.12));border-left:4px solid var(--blue,#4a90d9);
  border-radius:0 8px 8px 0;padding:12px 14px;margin:12px 0 0;font-size:15px;line-height:1.6}
.xnote a{display:inline-block;margin-top:4px;font-weight:700}
footer{margin-top:48px;padding-top:18px;border-top:1px solid var(--line);
  color:var(--mute);font-size:15px}"""


def page(title, desc, path_, body, js, back, noindex=False):
    return f"""<title>{title} — {SITE['name']}</title>
{site_config.adsense()}<link rel="stylesheet" href="{site_config.asset('core/theme.css')}">
<script src="{site_config.asset('core/theme.js')}"></script>
<script src="{site_config.asset('core/table.js')}" defer></script>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="{desc}">
{'<meta name="robots" content="noindex">' if noindex else
 f'<link rel="canonical" href="{site_config.url(path_)}">'}
<meta property="og:type" content="website">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:image" content="{site_config.url('data/ogp.png')}">
<meta name="twitter:card" content="summary_large_image">
<style>{CSS}</style>
<div class="wrap">
<div style="display:flex;align-items:center;gap:12px;margin-bottom:4px">
<a href="{back[0]}">← {back[1]}</a><div style="flex:1"></div>
<button class="themebtn" type="button">☾</button></div>
{NAV}
{body}
<footer>
{SITE['name']} ／ データ出典: JRA-VAN Data Lab.（公式データ）<br>
本ページは情報提供を目的としたもので、的中や利益を保証するものではありません。<br>
<a href="/privacy/">プライバシーポリシー・運営者情報</a>
</footer>
</div>
<script>{js}</script>
<script>
try{{ new Image().src = '/stats.php?p=' + encodeURIComponent(location.pathname)
   + '&r=' + encodeURIComponent(document.referrer) + '&t=' + Date.now(); }}catch(e){{}}
</script>
"""


SEARCH_JS = r"""
/* 中央の馬検索
   索引は build_jra_pedigree.py が作る配列の配列（地方版と同じ並び）:
     0馬名 1父 2母父 3毛色 4性 5生年 6出走 7勝利 8複勝率% 9複ROI% 10主戦場 11所属 12最終出走日
   ★列を地方と揃えてある★ 揃えないと画面を2つ作ることになる。 */
const $ = s => document.querySelector(s);
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let DB = [];
const F = ['fName','fSire','fDsire','fActive','fRuns','fWin','fFuku','fRoi'];

/* 現役/引退は推定。引退は公表されないので最終出走からの経過で線を引く */
const RETIRE_DAYS = 210;
let NEWEST = null;
const dnum = s => Date.UTC(+s.slice(0,4), +s.slice(4,6)-1, +s.slice(6,8)) / 86400000;
const isActive = d => (!d || !NEWEST) ? null : (NEWEST - dnum(d)) <= RETIRE_DAYS;

function render(){
  const v = {}; F.forEach(id => v[id] = $('#'+id).value.trim());
  const hit = [];
  for(const r of DB){
    if(v.fName  && !r[0].includes(v.fName)) continue;
    if(v.fSire  && !(r[1]||'').includes(v.fSire)) continue;
    if(v.fDsire && !(r[2]||'').includes(v.fDsire)) continue;
    if(v.fRuns  && r[6] < +v.fRuns) continue;
    if(v.fWin   && r[7] < +v.fWin) continue;
    if(v.fFuku  && r[8] < +v.fFuku) continue;
    if(v.fRoi   && r[9] < +v.fRoi) continue;
    if(v.fActive){
      const a = isActive(r[12]);
      if(a === null) continue;
      if(v.fActive === 'active' && !a) continue;
      if(v.fActive === 'retired' && a) continue;
    }
    hit.push(r);
    if(hit.length >= 4000) break;
  }
  const on = F.filter(id => $('#'+id).value.trim()).length;
  $('#fCount').textContent = on ? `（${on}件の条件を適用中）` : '（条件なし・すべて表示）';
  $('#rows').innerHTML = hit.slice(0,100).map(r => `<tr>
    <td><a href="/db/jra/horse/detail/?name=${encodeURIComponent(r[0])}"><strong>${esc(r[0])}</strong></a></td>
    <td>${(a => a===null?'—':(a?'現役':'引退'))(isActive(r[12]))}</td>
    <td class="n">${esc(r[5])}</td><td>${esc(r[1])}</td><td>${esc(r[2])}</td>
    <td class="n">${r[6]}</td><td class="n">${r[7]}</td>
    <td class="n">${r[8]}%</td><td class="n">${r[9]}%</td></tr>`).join('');
  $('#stat').textContent =
    `${hit.length.toLocaleString()}頭が該当（上位100頭を表示・出走数順）`;
  $('#tbl').hidden = false;
}

fetch('/db/jra/horses_search.json', {cache:'no-cache'})
  .then(r => { if(!r.ok) throw new Error(r.status); return r.json(); })
  .then(d => {
    DB = d;
    NEWEST = dnum(d.reduce((a,r) => r[12] > a ? r[12] : a, '00000000'));
    F.forEach(id => $('#'+id).addEventListener('input', render));
    $('#fClear').onclick = () => { F.forEach(id => $('#'+id).value=''); render(); };
    render();
  })
  .catch(e => { $('#stat').textContent = '読み込めませんでした：' + e.message; });
"""


def detail_js(md5_js):
    return md5_js + r"""
const $ = s => document.querySelector(s);
const esc = s => String(s==null?'':s).replace(/[&<>"']/g,
  c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const NAME = new URLSearchParams(location.search).get('name') || '';
const JYO = """ + JYO_JS + r""";
const JRA_TRACKS = new Set(Object.values(JYO));   // 中央+地方統合戦績で騎手リンク先を出し分ける用
const pct = (a,b) => b ? (100*a/b).toFixed(1)+'%' : '—';
const rankCls = r => (r===1?'r1':(r===2?'r2':(r===3?'r3':'')));

/* 3代血統の並び（UM_DATAの順序そのまま）
   0父 1母 2父父 3父母 4母父 5母母
   6父父父 7父父母 8父母父 9父母母 10母父父 11母父母 12母母父 13母母母 */
function pedigree(g){
  if(!g || !g.length) return '<p class="msg">血統データがありません。</p>';
  // ★父(0)・母父(4)だけ種牡馬/母父の産駒成績ページへリンク★
  //   3代目以降は同名でも別個体の可能性が上がる（登録番号を持っていない）ため、
  //   確実にリンクできる直系の2つだけに絞る。
  const cell = (i, cls, side) => {
    const name = g[i];
    if(!name) return `<div class="${cls} ${side}">—</div>`;
    const href = i===0 ? '/db/jra/sire/detail/?name='+encodeURIComponent(name)
               : i===4 ? '/db/jra/damsire/detail/?name='+encodeURIComponent(name) : '';
    return `<div class="${cls} ${side}">${href ? `<a href="${href}">${esc(name)}</a>` : esc(name)}</div>`;
  };
  // 列＝世代。1列目に父・母、2列目に4頭、3列目に8頭を縦に並べる
  return '<div class="ped">'
    + cell(0,'g1','sireside') + cell(2,'g2','sireside') + cell(6,'g3','sireside')
    + cell(7,'g3','sireside')
    + cell(3,'g2','sireside') + cell(8,'g3','sireside') + cell(9,'g3','sireside')
    + cell(1,'g1','damside')  + cell(4,'g2','damside')  + cell(10,'g3','damside')
    + cell(11,'g3','damside')
    + cell(5,'g2','damside')  + cell(12,'g3','damside') + cell(13,'g3','damside')
    + '</div>';
}

async function main(){
  if(!NAME){ $('#out').innerHTML = '<p class="msg">馬名が指定されていません。</p>'; return; }
  $('#name').textContent = NAME;
  document.title = NAME + ' の血統と戦績 — カジ競馬';

  let rec;
  try{
    const r = await fetch(`/db/jra/h/${md5(NAME).slice(0,2)}.json`, {cache:'no-cache'});
    if(!r.ok) throw new Error(r.status);
    rec = (await r.json())[NAME];
  }catch(e){
    $('#out').innerHTML = '<p class="msg">データを読み込めませんでした。</p>'; return;
  }
  if(!rec){
    // ★中央に無い＝地方の馬かもしれない★ 同形式の地方バッグを引いて誘導する。
    try{
      const nr = await fetch(`/db/h/${md5(NAME).slice(0,2)}.json`, {cache:'no-cache'});
      if(nr.ok && (await nr.json())[NAME]){
        location.replace('/db/horse/detail/?name=' + encodeURIComponent(NAME));
        return;
      }
    }catch(e){}
    $('#out').innerHTML = '<p class="msg">この馬の記録は見つかりませんでした。'
      + '（収録は直近3年に出走した中央の馬）</p>';
    const d = $('#detail'); if(d) d.style.display = 'none';
    return;
  }

  const [birth, sire, dsire, breeder] = rec.p || [];
  $('#sub').innerHTML = [birth ? birth+'年生' : '', sire ? '父 '+esc(sire) : '',
                         dsire ? '母父 '+esc(dsire) : '',
                         breeder ? '生産 <a href="/db/jra/breeder/detail/?name='
                           + encodeURIComponent(breeder) + '">' + esc(breeder) + '</a>' : '']
                         .filter(Boolean).join(' ／ ');

  // ★中央＋地方（交流重賞など）を1つの戦績に統合する★（SPAT4と同じ見え方）
  //   両バッグは同じ15列スキーマ。場が違う（中央=01-10 / 地方）ので重複はない。
  //   [0日付 1場 2R 3レース名 4頭数 5枠 6馬番 7人気 8着順 9騎手 10斤量 11馬体重 12増減 13複勝払戻 14距離]
  let rs = (rec.r || []).slice();
  let hasNar = false;
  try{
    const nr = await fetch(`/db/h/${md5(NAME).slice(0,2)}.json`, {cache:'no-cache'});
    if(nr.ok){
      const nrec = (await nr.json())[NAME];
      if(nrec && nrec.r && nrec.r.length){ rs = rs.concat(nrec.r); hasNar = true; }
    }
  }catch(e){}
  rs.sort((a,b) => a[0] < b[0] ? 1 : a[0] > b[0] ? -1 : 0);   // 日付の新しい順

  const n = rs.length;
  const win = rs.filter(x => x[8] === 1).length;
  const t3  = rs.filter(x => x[8] <= 3).length;
  const ret = rs.reduce((s,x) => s + (x[13]||0), 0);
  $('#kpi').innerHTML = `
    <div><b>${n}</b><span>出走</span></div>
    <div><b>${win}</b><span>勝利</span></div>
    <div><b>${pct(win,n)}</b><span>勝率</span></div>
    <div><b>${pct(t3,n)}</b><span>複勝率</span></div>
    <div><b>${n?(100*ret/(100*n)).toFixed(0)+'%':'—'}</b><span>複勝回収率</span></div>`;
  if(hasNar) $('#sub').innerHTML += ' ／ 中央＋地方(交流)を統合';

  $('#ped').innerHTML = pedigree(rec.g);

  const d = s => s ? `${s.slice(0,4)}/${s.slice(4,6)}/${s.slice(6,8)}` : '';
  $('#runs').innerHTML = `<table><thead><tr>
      <th>日付</th><th>場</th><th class="n">R</th><th>レース名</th><th>距離</th>
      <th class="n">頭数</th><th class="n">馬番</th><th class="n">人気</th>
      <th class="n">着順</th><th>騎手</th><th class="n">複勝払戻</th>
    </tr></thead><tbody>` + rs.map(x => `<tr>
      <td>${d(x[0])}</td><td>${esc(x[1])}</td><td class="n">${x[2]}</td>
      <td>${esc(x[3]||'—')}</td><td>${esc(x[14]||'')}</td>
      <td class="n">${x[4]||''}</td><td class="n">${x[6]}</td><td class="n">${x[7]||'—'}</td>
      <td class="n ${rankCls(x[8])}">${x[8]}</td>
      <td>${x[9] ? (JRA_TRACKS.has(x[1])
          ? `<a href="/db/jra/jockey/detail/?name=${encodeURIComponent(x[9])}">${esc(x[9])}</a>`
          : `<a href="/db/jockey/detail/?name=${encodeURIComponent(x[9])}">${esc(x[9])}</a>`) : ''}</td>
      <td class="n ${x[13]?'paid':''}">${x[13] ? x[13].toLocaleString() : '—'}</td>
    </tr>`).join('') + '</tbody></table>';
  $('#cap').textContent = n >= 80
    ? '※ 直近80走まで収録しています。それ以前は表示していません。' : '';
}
main();
"""


def main():
    # 血統図ページは地方の詳細ページと同じMD5を使う（袋分けの規則が同じ）
    src = open(os.path.join(ROOT, "backtest", "gen_profile_pages.py"),
               encoding="utf-8").read()
    m = re.search(r'MD5_JS = r"""(.*?)"""', src, re.S)
    if not m:
        print("MD5 実装を gen_profile_pages.py から取れなかった")
        return 1
    md5_js = m.group(1)

    search_body = """<h1>馬検索（中央競馬）</h1>
<p class="lead">直近3年に出走した中央の馬を、馬名・父・母父で探せます。
馬名を押すと<b>3代血統図</b>と全戦績が出ます。</p>
<fieldset class="fbox">
  <legend>絞り込み<span id="fCount"></span></legend>
  <div class="filters">
    <label>馬名<input id="fName" placeholder="部分一致"></label>
    <label>父<input id="fSire" placeholder="部分一致"></label>
    <label>母父<input id="fDsire" placeholder="部分一致"></label>
    <label>状態<select id="fActive"><option value="">すべて</option>
      <option value="active">現役（推定）</option>
      <option value="retired">引退（推定）</option></select></label>
    <label>出走数<select id="fRuns"><option value="">すべて</option>
      <option value="5">5走以上</option><option value="10">10走以上</option>
      <option value="20">20走以上</option><option value="30">30走以上</option></select></label>
    <label>勝利数<select id="fWin"><option value="">すべて</option>
      <option value="1">1勝以上</option><option value="3">3勝以上</option>
      <option value="5">5勝以上</option><option value="10">10勝以上</option></select></label>
    <label>複勝率<select id="fFuku"><option value="">すべて</option>
      <option value="30">30%以上</option><option value="40">40%以上</option>
      <option value="50">50%以上</option><option value="60">60%以上</option></select></label>
    <label>複勝回収率<select id="fRoi"><option value="">すべて</option>
      <option value="80">80%以上</option><option value="100">100%以上</option>
      <option value="120">120%以上</option></select></label>
  </div>
  <p class="note" style="margin:8px 0 0">
    <button id="fClear" class="chip" type="button">条件をクリア</button></p>
</fieldset>
<p class="note" id="stat">読み込み中…</p>
<div class="scroll"><table id="tbl" class="zebra sortable" hidden>
<thead><tr><th>馬名</th><th>状態</th><th class="n">生年</th><th>父</th><th>母父</th>
<th class="n">出走</th><th class="n">勝利</th><th class="n">複勝率</th>
<th class="n">複勝回収率</th></tr></thead><tbody id="rows"></tbody></table></div>
<p class="note">複勝回収率は「その馬の複勝を全レース100円ずつ買った」計算です。
出走数が少ない馬の率は大きく振れるので、そのまま鵜呑みにしないでください。<br>
「現役／引退」は<b>推定</b>です。引退は公表されないため、最終出走から210日以上
あいた馬を引退として扱っています（休養明けで戻る馬もいます）。</p>"""

    detail_body = """<h1 id="name">…</h1>
<p class="sub" id="sub"></p>
<div class="kpi" id="kpi"></div>
<div id="out"></div>
<div id="detail">
<h2>血統（3代）</h2><div class="scroll" id="ped"></div>
<p class="note">左が父系（青）、下が母系（赤）。列が世代です。</p>
<h2>戦績</h2><div class="scroll" id="runs"></div>
<p class="sub" id="cap"></p>
</div>"""

    for path_, title, desc, body, js, back, noidx in (
        (OUT_SEARCH, "馬検索（中央競馬）",
         "中央競馬の馬検索。馬名・父・母父で絞り込み。3代血統図と全戦績つき。",
         search_body, SEARCH_JS, ("/db/jra/", "中央のデータベース"), False),
        (OUT_DETAIL, "馬の血統と戦績（中央競馬）",
         "中央競馬の馬の3代血統図と全出走記録。",
         detail_body, detail_js(md5_js), ("/db/jra/horse/", "馬検索"), True),
    ):
        os.makedirs(os.path.dirname(path_), exist_ok=True)
        html = page(title, desc,
                    "db/jra/horse/" + ("detail/" if noidx else ""),
                    body, js, back, noidx)
        with open(path_, "w", encoding="utf-8", newline="\n") as f:
            f.write(html)
        print(f"  {os.path.relpath(path_, ROOT)}  {len(html.encode('utf-8')):,}B")
    return 0


if __name__ == "__main__":
    sys.exit(main())
