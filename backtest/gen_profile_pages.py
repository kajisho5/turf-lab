# -*- coding: utf-8 -*-
"""馬・騎手の個別ページを作る（SPAT4のような戦績表示）

★これが無かったので「データベースが見れない」状態だった★
  一覧（馬検索・騎手リーディング）は出ていたが、名前を押しても何も起きない。
  build_profiles.py が作ったデータ（db/h/*.json・db/j/index.json）を
  読む**ページが存在せず、データ自体もアップロードしていなかった**。
  一覧だけ作って「データベースができた」と思っていたのが誤り。

出力:
  deploy/db/horse/detail/index.html   /db/horse/detail/?name=馬名
  deploy/db/jockey/detail/index.html  /db/jockey/detail/?name=騎手名

★馬のデータは256個の袋に分かれている★
  袋は「馬名のMD5先頭2桁」で決まる（build_profiles.py）。
  ブラウザに MD5 は無いので、小さな実装を1つだけ同梱する。
  袋分けの規則をJS都合で変えると、既存の78MBを作り直すことになるため。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import site_config                                            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = site_config.SITES["public"]
C = site_config.COLORS if hasattr(site_config, "COLORS") else {}

CSS = """
:root{color-scheme:light dark}
body{margin:0;background:var(--bg);color:var(--txt);
  font-family:system-ui,-apple-system,"Hiragino Kaku Gothic ProN","Noto Sans JP",sans-serif;
  font-size:15px;line-height:1.55}
/* ★余白を詰める★ SPAT4を参考に、情報密度を上げる。
   本文16px→15px、行間1.7→1.55、上下パディングを削る。 */
.wrap{max-width:1000px;margin:0 auto;padding:12px 12px 56px}
a{color:var(--blue)}
h1{font-size:23px;margin:8px 0 2px}
h2{font-size:17px;margin:20px 0 4px;padding-bottom:4px;border-bottom:1px solid var(--line)}
.sub{color:var(--mute);font-size:14px;margin:0 0 6px}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;position:relative}
table{width:100%;border-collapse:collapse;margin:6px 0;font-size:14px;min-width:640px}
th,td{padding:5px 7px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{color:var(--mute);font-weight:700;background:var(--panel);position:sticky;top:0}
tbody tr:nth-child(even){background:var(--stripe)}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
/* ← 横にスライド → のヒント（数秒で消える） */
.swipehint{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%) scale(.9);
  background:rgba(20,24,32,.86);color:#fff;padding:12px 20px;border-radius:12px;
  font-size:15px;font-weight:700;pointer-events:none;opacity:0;z-index:5;
  transition:opacity .3s,transform .3s;white-space:nowrap;
  box-shadow:0 4px 20px rgba(0,0,0,.3)}
.swipehint.on{opacity:1;transform:translate(-50%,-50%) scale(1)}
.swipehint span{display:inline-block;animation:swipeMove 1.1s ease-in-out infinite}
@keyframes swipeMove{0%,100%{transform:translateX(-4px)}50%{transform:translateX(4px)}}
/* ★数字に意味の色を付ける★
   もとは全部が本文色で、どこを見ればいいのか分からない「色のないページ」だった。
   意味のある所だけ色を持たせる（飾りで色を増やすと逆に読めなくなる）。
   色は theme.css の検証済みパレットのみ使う（コントラスト4.5:1確認済み）。 */
.kpi{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}
.kpi div{flex:1 1 130px;background:var(--panel);border:1px solid var(--line);
  border-top:3px solid var(--line);border-radius:12px;padding:12px 14px}
.kpi div:nth-child(1){border-top-color:var(--mute)}
.kpi div:nth-child(2){border-top-color:var(--yellow)}
.kpi div:nth-child(3){border-top-color:var(--orange)}
.kpi div:nth-child(4){border-top-color:var(--green)}
.kpi div:nth-child(5){border-top-color:var(--blue)}
.kpi b{display:block;font-size:26px;font-variant-numeric:tabular-nums;line-height:1.3}
.kpi div:nth-child(2) b{color:var(--yellow)}
.kpi div:nth-child(3) b{color:var(--orange)}
.kpi div:nth-child(4) b{color:var(--green)}
.kpi div:nth-child(5) b{color:var(--blue)}
.kpi span{color:var(--mute);font-size:14px}
/* 着順は1・2・3着だけ色を変える。4着以下に色を付けると差が消える */
.r1{color:var(--yellow);font-weight:700;font-size:18px}
.r2{color:var(--blue);font-weight:700}
.r3{color:var(--green);font-weight:700}
tbody tr:has(td.r1){background:color-mix(in srgb, var(--yellow) 10%, transparent)}
.paid{color:var(--green);font-weight:700}   /* 払戻が付いた行 */
h1{border-left:5px solid var(--yellow);padding-left:12px}
h2{color:var(--txt)}
h2::before{content:"";display:inline-block;width:4px;height:16px;margin-right:8px;
  background:var(--blue);vertical-align:-2px;border-radius:2px}
.msg{color:var(--mute);padding:24px 0}
.xnote{background:var(--panel,rgba(128,128,128,.12));border-left:4px solid var(--blue,#4a90d9);
  border-radius:0 8px 8px 0;padding:12px 14px;margin:12px 0 0;font-size:15px;line-height:1.6}
.xnote a{display:inline-block;margin-top:4px;font-weight:700}
.fav{appearance:none;border:1px solid var(--line);background:var(--panel);color:var(--mute);
  border-radius:999px;padding:6px 14px;font:inherit;font-size:15px;cursor:pointer}
.fav[aria-pressed="true"]{color:var(--yellow);border-color:var(--yellow)}
footer{margin-top:52px;padding-top:18px;border-top:1px solid var(--line);
  color:var(--mute);font-size:15px}
/* ★どのページからも他の入口へ行けるようにする★
   戻りリンク1本しか置いていなかったため、データベースの入口が
   自分自身を指して行き止まりになっていた（利用者から「戻れん」と指摘）。
   1段戻るだけでなく、常に全部の入口を出す。 */
.snav{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 16px}
.snav a{border:1px solid var(--line);background:var(--panel);border-radius:999px;
  padding:4px 13px;text-decoration:none;color:var(--mute);font-size:15px}
.snav a:hover{border-color:var(--mute);color:var(--txt)}
"""

# 公開されている実装（RFC1321）。袋分けの規則を変えないためだけに置いている。
MD5_JS = r"""
/* MD5（袋の番号を出すためだけに使う。暗号用途ではない）
   ★なぜ必要か★ 馬データは「馬名のMD5先頭2桁」で256個に分けてある。
   JS都合で分け方を変えると78MBを作り直すことになるので、こちらを合わせる。 */
function md5(s){
  function rl(n,c){return(n<<c)|(n>>>(32-c))}
  function au(x,y){const l=(x&0xFFFF)+(y&0xFFFF);return(((x>>16)+(y>>16)+(l>>16))<<16)|(l&0xFFFF)}
  function cmn(q,a,b,x,s,t){return au(rl(au(au(a,q),au(x,t)),s),b)}
  function ff(a,b,c,d,x,s,t){return cmn((b&c)|((~b)&d),a,b,x,s,t)}
  function gg(a,b,c,d,x,s,t){return cmn((b&d)|(c&(~d)),a,b,x,s,t)}
  function hh(a,b,c,d,x,s,t){return cmn(b^c^d,a,b,x,s,t)}
  function ii(a,b,c,d,x,s,t){return cmn(c^(b|(~d)),a,b,x,s,t)}
  const bytes=new TextEncoder().encode(s), nb=bytes.length*8;
  const x=[]; for(let i=0;i<bytes.length;i++) x[i>>2]=(x[i>>2]||0)|(bytes[i]<<((i%4)*8));
  x[nb>>5]=(x[nb>>5]||0)|(0x80<<(nb%32));
  const need=(((nb+64)>>>9)<<4)+14; for(let i=0;i<=need+1;i++) x[i]=x[i]||0;
  x[need]=nb;
  let a=1732584193,b=-271733879,c=-1732584194,d=271733878;
  const S=[7,12,17,22,5,9,14,20,4,11,16,23,6,10,15,21];
  for(let i=0;i<x.length;i+=16){
    const oa=a,ob=b,oc=c,od=d;
    a=ff(a,b,c,d,x[i],S[0],-680876936);   d=ff(d,a,b,c,x[i+1],S[1],-389564586);
    c=ff(c,d,a,b,x[i+2],S[2],606105819);  b=ff(b,c,d,a,x[i+3],S[3],-1044525330);
    a=ff(a,b,c,d,x[i+4],S[0],-176418897); d=ff(d,a,b,c,x[i+5],S[1],1200080426);
    c=ff(c,d,a,b,x[i+6],S[2],-1473231341);b=ff(b,c,d,a,x[i+7],S[3],-45705983);
    a=ff(a,b,c,d,x[i+8],S[0],1770035416); d=ff(d,a,b,c,x[i+9],S[1],-1958414417);
    c=ff(c,d,a,b,x[i+10],S[2],-42063);    b=ff(b,c,d,a,x[i+11],S[3],-1990404162);
    a=ff(a,b,c,d,x[i+12],S[0],1804603682);d=ff(d,a,b,c,x[i+13],S[1],-40341101);
    c=ff(c,d,a,b,x[i+14],S[2],-1502002290);b=ff(b,c,d,a,x[i+15],S[3],1236535329);
    a=gg(a,b,c,d,x[i+1],S[4],-165796510); d=gg(d,a,b,c,x[i+6],S[5],-1069501632);
    c=gg(c,d,a,b,x[i+11],S[6],643717713); b=gg(b,c,d,a,x[i],S[7],-373897302);
    a=gg(a,b,c,d,x[i+5],S[4],-701558691); d=gg(d,a,b,c,x[i+10],S[5],38016083);
    c=gg(c,d,a,b,x[i+15],S[6],-660478335);b=gg(b,c,d,a,x[i+4],S[7],-405537848);
    a=gg(a,b,c,d,x[i+9],S[4],568446438);  d=gg(d,a,b,c,x[i+14],S[5],-1019803690);
    c=gg(c,d,a,b,x[i+3],S[6],-187363961); b=gg(b,c,d,a,x[i+8],S[7],1163531501);
    a=gg(a,b,c,d,x[i+13],S[4],-1444681467);d=gg(d,a,b,c,x[i+2],S[5],-51403784);
    c=gg(c,d,a,b,x[i+7],S[6],1735328473); b=gg(b,c,d,a,x[i+12],S[7],-1926607734);
    a=hh(a,b,c,d,x[i+5],S[8],-378558);    d=hh(d,a,b,c,x[i+8],S[9],-2022574463);
    c=hh(c,d,a,b,x[i+11],S[10],1839030562);b=hh(b,c,d,a,x[i+14],S[11],-35309556);
    a=hh(a,b,c,d,x[i+1],S[8],-1530992060);d=hh(d,a,b,c,x[i+4],S[9],1272893353);
    c=hh(c,d,a,b,x[i+7],S[10],-155497632);b=hh(b,c,d,a,x[i+10],S[11],-1094730640);
    a=hh(a,b,c,d,x[i+13],S[8],681279174); d=hh(d,a,b,c,x[i],S[9],-358537222);
    c=hh(c,d,a,b,x[i+3],S[10],-722521979);b=hh(b,c,d,a,x[i+6],S[11],76029189);
    a=hh(a,b,c,d,x[i+9],S[8],-640364487); d=hh(d,a,b,c,x[i+12],S[9],-421815835);
    c=hh(c,d,a,b,x[i+15],S[10],530742520);b=hh(b,c,d,a,x[i+2],S[11],-995338651);
    a=ii(a,b,c,d,x[i],S[12],-198630844);  d=ii(d,a,b,c,x[i+7],S[13],1126891415);
    c=ii(c,d,a,b,x[i+14],S[14],-1416354905);b=ii(b,c,d,a,x[i+5],S[15],-57434055);
    a=ii(a,b,c,d,x[i+12],S[12],1700485571);d=ii(d,a,b,c,x[i+3],S[13],-1894986606);
    c=ii(c,d,a,b,x[i+10],S[14],-1051523);b=ii(b,c,d,a,x[i+1],S[15],-2054922799);
    a=ii(a,b,c,d,x[i+8],S[12],1873313359);d=ii(d,a,b,c,x[i+15],S[13],-30611744);
    c=ii(c,d,a,b,x[i+6],S[14],-1560198380);b=ii(b,c,d,a,x[i+13],S[15],1309151649);
    a=ii(a,b,c,d,x[i+4],S[12],-145523070);d=ii(d,a,b,c,x[i+11],S[13],-1120210379);
    c=ii(c,d,a,b,x[i+2],S[14],718787259);b=ii(b,c,d,a,x[i+9],S[15],-343485551);
    a=au(a,oa);b=au(b,ob);c=au(c,oc);d=au(d,od);
  }
  const hex=n=>{let s='';for(let i=0;i<4;i++)s+=((n>>(i*8+4))&15).toString(16)+((n>>(i*8))&15).toString(16);return s};
  return hex(a)+hex(b)+hex(c)+hex(d);
}
"""

COMMON_JS = r"""
const $ = s => document.querySelector(s);
const esc = s => String(s==null?'':s).replace(/[&<>"']/g,
  c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const NAME = new URLSearchParams(location.search).get('name') || '';

/* お気に入りは端末に持つ（サーバーに個人の情報を置かない） */
const FAV = {
  key: k => 'fav_' + k,
  has(k, n){ return (JSON.parse(localStorage.getItem(FAV.key(k)) || '[]')).includes(n); },
  toggle(k, n){
    const a = JSON.parse(localStorage.getItem(FAV.key(k)) || '[]');
    const i = a.indexOf(n);
    if(i < 0) a.push(n); else a.splice(i, 1);
    localStorage.setItem(FAV.key(k), JSON.stringify(a));
    return i < 0;
  }
};
function favButton(kind){
  const b = $('#fav');
  const set = on => { b.setAttribute('aria-pressed', on); b.textContent = on ? '★ お気に入り' : '☆ お気に入り'; };
  set(FAV.has(kind, NAME));
  b.onclick = () => set(FAV.toggle(kind, NAME));
}
const rankCls = r => (r===1?'r1':(r===2?'r2':(r===3?'r3':'')));
const pct = (a,b) => b ? (100*a/b).toFixed(1) + '%' : '—';

/* 横スクロールできる表に「← 横にスライド →」のヒントを数秒出す。
   ★スマホだと右に列があることに気づかれない★（SPAT4もこの案内を出している）。
   一度出したらこの端末では二度と出さない（毎回はうるさい）。
   実際にスクロール可能な（はみ出している）表にだけ付ける。 */
function swipeHint(sel){
  if(localStorage.getItem('swipeHintSeen')) return;
  const box = $(sel);
  if(!box) return;
  // はみ出していなければ出さない（PCや少列では不要）
  if(box.scrollWidth <= box.clientWidth + 4) return;
  const tip = document.createElement('div');
  tip.className = 'swipehint';
  tip.innerHTML = '<span>← 横にスライド →</span>';
  box.style.position = 'relative';
  box.appendChild(tip);
  requestAnimationFrame(() => tip.classList.add('on'));
  const kill = () => { tip.classList.remove('on'); setTimeout(() => tip.remove(), 400);
    localStorage.setItem('swipeHintSeen', '1'); box.removeEventListener('scroll', kill); };
  box.addEventListener('scroll', kill, {passive:true});
  setTimeout(kill, 3500);
}
"""

HORSE_JS = r"""
/* 1走の並び（build_profiles.py と同じ。ここを変えたら向こうも変える）
   0日付 1場 2R 3レース名 4頭数 5枠 6馬番 7人気 8着順 9騎手 10斤量 11馬体重 12増減 13複勝払戻 14距離 */
async function main(){
  if(!NAME){ $('#out').innerHTML = '<p class="msg">馬名が指定されていません。</p>'; return; }
  $('#name').textContent = NAME;
  document.title = NAME + ' の戦績 — カジ競馬';
  favButton('horse');

  const b = md5(NAME).slice(0,2);
  // ★中央(JRA)にも居る馬は、統合ページ（中央側）へ送る★
  //   中央ページが中央＋地方(交流)をまとめて出す。ここで二重に集計させない。
  //   ギュルヴィ（中央のみ）・ドゥラエレーデ（中央＋地方）ともここで中央へ。
  try{
    const jr = await fetch(`/db/jra/h/${b}.json`, {cache:'no-cache'});
    if(jr.ok && (await jr.json())[NAME]){
      location.replace('/db/jra/horse/detail/?name=' + encodeURIComponent(NAME));
      return;
    }
  }catch(e){}

  let rec;
  try{
    const r = await fetch(`/db/h/${b}.json`, {cache:'no-cache'});
    if(!r.ok) throw new Error(r.status);
    rec = (await r.json())[NAME];
  }catch(e){
    $('#out').innerHTML = '<p class="msg">データを読み込めませんでした。</p>'; return;
  }
  if(!rec){
    $('#out').innerHTML = '<p class="msg">この馬の記録は見つかりませんでした。'
      + '（収録は直近3年に地方で出走した馬。初出走の馬は載りません）</p>';
    const d = $('#detail'); if(d) d.style.display = 'none';    // 空の見出しを残さない
    return;
  }

  const [sex, color, birth, sire, dam, dsire, trainer] = rec.p || [];
  $('#sub').textContent = [sex, color, birth ? birth+'年生' : '', trainer ? trainer+'厩舎' : '']
    .filter(Boolean).join(' ／ ');

  const rs = rec.r || [];
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

  $('#ped').innerHTML = `<table><tr><th>父</th><td>${esc(sire||'—')}</td></tr>
    <tr><th>母</th><td>${esc(dam||'—')}</td></tr>
    <tr><th>母父</th><td>${esc(dsire||'—')}</td></tr></table>`;

  const d = s => s ? `${s.slice(0,4)}/${s.slice(4,6)}/${s.slice(6,8)}` : '';
  $('#runs').innerHTML = `<table><thead><tr>
      <th>日付</th><th>場</th><th class="n">R</th><th>レース</th><th class="n">距離</th>
      <th class="n">頭数</th><th class="n">枠</th><th class="n">馬番</th><th class="n">人気</th>
      <th class="n">着順</th><th>騎手</th><th class="n">馬体重</th><th class="n">複勝払戻</th>
    </tr></thead><tbody>` + rs.map(x => `<tr>
      <td>${d(x[0])}</td><td>${esc(x[1])}</td><td class="n">${esc(x[2])}</td>
      <td>${esc(x[3])}</td><td class="n">${esc(x[14]||'')}</td><td class="n">${esc(x[4])}</td>
      <td class="n">${esc(x[5])}</td><td class="n">${esc(x[6])}</td><td class="n">${esc(x[7])}</td>
      <td class="n ${rankCls(x[8])}">${esc(x[8])}</td>
      <td><a href="/db/jockey/detail/?name=${encodeURIComponent(x[9])}">${esc(x[9])}</a></td>
      <td class="n">${esc(x[11]||'')}${x[12]?`<small>(${esc(x[12])})</small>`:''}</td>
      <td class="n ${x[13] ? 'paid' : ''}">${x[13] ? x[13].toLocaleString() : '—'}</td>
    </tr>`).join('') + '</tbody></table>';
  // ★収録上限を隠さない★ 60走で切っているので、それを書かないと「全部」に見える
  $('#cap').textContent = n >= 60
    ? '※ 直近60走まで収録しています。それ以前は表示していません。' : '';
  swipeHint('#runs');   // 戦績表は列が多い。横スクロールできると気づかせる
}
main();
"""

JOCKEY_JS = r"""
async function main(){
  if(!NAME){ $('#out').innerHTML = '<p class="msg">名前が指定されていません。</p>'; return; }
  $('#name').textContent = NAME;
  document.title = NAME + ' の成績 — カジ競馬';
  favButton('__KIND__');

  let all;
  try{
    const r = await fetch('/db/j/index.json', {cache:'no-cache'});
    if(!r.ok) throw new Error(r.status);
    all = await r.json();
  }catch(e){
    $('#out').innerHTML = '<p class="msg">データを読み込めませんでした。</p>'; return;
  }
  const e = all[NAME];
  if(!e){
    $('#out').innerHTML = '<p class="msg">この「__ENTITY__」の記録は見つかりませんでした。'
      + '（収録は50回以上）</p>';
    const d = $('#detail'); if(d) d.style.display = 'none';    // 空の見出しを残さない
    return;
  }

  const hasGrade = e.gr && Object.keys(e.gr).length;   // 重賞成績テーブルを出すかどうか
  const isJra = !!(e.gr && e.gr.GI);       // JRAはGI/GII/GIII、地方は重賞/準重賞（キーの語彙で判定）
  let gradeBadge = '';
  if(isJra){
    gradeBadge = `<div><b>${(e.gr.GI||[0,0])[1].toLocaleString()}</b><span>GI勝利</span></div>`;
  }else if(hasGrade){
    const stakes = (e.gr['重賞']||[0,0])[1] + (e.gr['準重賞']||[0,0])[1];
    gradeBadge = `<div><b>${stakes.toLocaleString()}</b><span>重賞勝利</span></div>`;
  }
  $('#kpi').innerHTML = `
    <div><b>${e.n.toLocaleString()}</b><span>出走</span></div>
    <div><b>${e.w.toLocaleString()}</b><span>勝利</span></div>
    <div><b>${pct(e.w,e.n)}</b><span>勝率</span></div>
    <div><b>${pct(e.t3,e.n)}</b><span>複勝率</span></div>
    <div><b>${e.roi}%</b><span>複勝回収率</span></div>` + gradeBadge;
  $('#sub').textContent = isJra ? '1986年〜の中央競馬（JRA-VAN公式データ）' : '2013年〜の地方競馬（公式データ）';
  if(hasGrade){
    $('#g1link').innerHTML = `<a href="${isJra ? '/db/jra/g1/' : '/db/g1/'}">`
      + (isJra ? '重賞(GI/GII/GIII)ランキングで他の人物と比べる →' : '重賞・準重賞ランキングで他の人物と比べる →') + '</a>';
  }

  const tbl = (obj, head) => `<table><thead><tr><th>${head}</th>
      <th class="n">出走</th><th class="n">勝利</th><th class="n">勝率</th><th class="n">複勝率</th>
    </tr></thead><tbody>` + Object.entries(obj).map(([k,v]) => `<tr>
      <td>${esc(k)}</td><td class="n">${v[0].toLocaleString()}</td>
      <td class="n">${v[1].toLocaleString()}</td>
      <td class="n">${pct(v[1],v[0])}</td><td class="n">${pct(v[2],v[0])}</td>
    </tr>`).join('') + '</tbody></table>';
  $('#bytrack').innerHTML = tbl(e.tr, '競馬場');
  $('#byyear').innerHTML  = tbl(e.yr, '年');
  if(hasGrade){
    $('#gradewrap').style.display = '';
    $('#bygrade').innerHTML = `<table><thead><tr><th>格付け</th>
        <th class="n">出走</th><th class="n">勝利</th><th class="n">勝率</th>
      </tr></thead><tbody>` + Object.entries(e.gr).map(([k,v]) => `<tr>
        <td>${esc(k)}</td><td class="n">${v[0].toLocaleString()}</td>
        <td class="n">${v[1].toLocaleString()}</td><td class="n">${pct(v[1],v[0])}</td>
      </tr>`).join('') + '</tbody></table>';
  }
  swipeHint('#bytrack');
}
main();
"""


def page(title, desc, path_, body, js):
    return f"""<title>{title} — {SITE['name']}</title>
{site_config.adsense()}<link rel="stylesheet" href="{site_config.asset('core/theme.css')}">
<script src="{site_config.asset('core/theme.js')}"></script>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="{desc}">
<meta name="robots" content="noindex">
<style>{CSS}</style>
<div class="wrap">
<div style="display:flex;align-items:center;gap:12px;margin-bottom:4px">
<a href="/db/">← データベース</a><div style="flex:1"></div>
<button class="themebtn" type="button">☾</button></div>
<nav class="snav"><a href="/">レース一覧</a><a href="/ai/">AI予想家</a><a href="/record/">予想の記録</a><a href="/articles/">記事</a><a href="/db/">データベース</a><a href="/calendar/">重賞カレンダー</a></nav>
{body}
<footer>
{SITE['name']} ／ データ出典: 地方競馬全国協会 keiba.go.jp（公式データダウンロード）<br>
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


def write(rel, html):
    p = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    print(f"  {rel}  {len(html.encode('utf-8')):,}B")


def main():
    # ★記録なしのとき見出しだけ残ると壊れて見える★
    #   血統/戦績の見出しは #detail で囲み、記録が無ければ丸ごと隠す。
    horse_body = """<h1 id="name">…</h1>
<p class="sub" id="sub"></p>
<button class="fav" id="fav" type="button" aria-pressed="false">☆ お気に入り</button>
<div class="kpi" id="kpi"></div>
<div id="out"></div>
<div id="detail">
<h2>血統</h2><div class="scroll" id="ped"></div>
<h2>戦績</h2><div class="scroll" id="runs"></div>
<p class="sub" id="cap"></p>
</div>"""

    jockey_body = """<h1 id="name">…</h1>
<p class="sub" id="sub"></p>
<button class="fav" id="fav" type="button" aria-pressed="false">☆ お気に入り</button>
<div class="kpi" id="kpi"></div>
<div id="out"></div>
<div id="detail">
<div id="gradewrap" style="display:none"><h2>重賞成績</h2><div class="scroll" id="bygrade"></div>
<p class="sub" id="g1link"></p></div>
<h2>競馬場別</h2><div class="scroll" id="bytrack"></div>
<h2>年別</h2><div class="scroll" id="byyear"></div>
</div>"""

    def person_js(json_url, kind, entity_label):
        return (JOCKEY_JS.replace("'/db/j/index.json'", f"'{json_url}'")
                .replace("__KIND__", kind).replace("__ENTITY__", entity_label))

    print("個別ページを生成:")
    write("deploy/db/horse/detail/index.html",
          page("馬の戦績", "地方競馬の馬の戦績・血統・全出走記録",
               "db/horse/detail/", horse_body, MD5_JS + COMMON_JS + HORSE_JS))
    write("deploy/db/jockey/detail/index.html",
          page("騎手の成績", "地方競馬の騎手の成績・競馬場別・年別・重賞",
               "db/jockey/detail/", jockey_body, COMMON_JS + person_js("/db/j/index.json", "jockey", "騎手")))
    write("deploy/db/trainer/detail/index.html",
          page("調教師の成績", "地方競馬の調教師の成績・競馬場別・年別・重賞",
               "db/trainer/detail/", jockey_body, COMMON_JS + person_js("/db/t/index.json", "trainer", "調教師")))
    # ★中央の騎手/調教師/馬主/種牡馬/母父ページ★ jockey_body/JOCKEY_JSは中身が汎用
    #   （IDと文言だけ）なので、読むJSONと文言差し替えだけでそのまま使い回せる。
    write("deploy/db/jra/jockey/detail/index.html",
          page("騎手の成績（中央競馬）", "中央競馬の騎手の成績・競馬場別・年別",
               "db/jra/jockey/detail/", jockey_body,
               COMMON_JS + person_js("/db/jra/j/index.json", "jockey", "騎手")))
    write("deploy/db/jra/trainer/detail/index.html",
          page("調教師の成績（中央競馬）", "中央競馬の調教師の成績・競馬場別・年別・重賞",
               "db/jra/trainer/detail/", jockey_body,
               COMMON_JS + person_js("/db/jra/t/index.json", "trainer", "調教師")))
    write("deploy/db/jra/owner/detail/index.html",
          page("馬主の成績（中央競馬）", "中央競馬の馬主の成績・競馬場別・年別・重賞",
               "db/jra/owner/detail/", jockey_body,
               COMMON_JS + person_js("/db/jra/o/index.json", "owner", "馬主")))
    write("deploy/db/jra/sire/detail/index.html",
          page("種牡馬の産駒成績（中央競馬）", "中央競馬・種牡馬別の産駒成績・競馬場別・年別・重賞",
               "db/jra/sire/detail/", jockey_body,
               COMMON_JS + person_js("/db/jra/s/index.json", "sire", "種牡馬")))
    write("deploy/db/jra/damsire/detail/index.html",
          page("母父の産駒成績（中央競馬）", "中央競馬・母父別の産駒成績・競馬場別・年別・重賞",
               "db/jra/damsire/detail/", jockey_body,
               COMMON_JS + person_js("/db/jra/ds/index.json", "damsire", "母父")))
    write("deploy/db/jra/breeder/detail/index.html",
          page("生産者の成績（中央競馬）", "中央競馬・生産者（牧場）別の成績・競馬場別・年別・重賞",
               "db/jra/breeder/detail/", jockey_body,
               COMMON_JS + person_js("/db/jra/br/index.json", "breeder", "生産者")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
