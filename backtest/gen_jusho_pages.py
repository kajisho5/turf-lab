# -*- coding: utf-8 -*-
"""重賞データページ（1枚のSPA。?r=レース名 で切り替え）

★1レース1ファイルにしない★
  143重賞×HTMLファイルにすると管理が増える。1つのページが data.json を読み、
  ?r=有馬記念 のようにクエリで内容を出し分ける。
  サーバー側(race.php)のように各重賞を静的HTMLにするのはSEO的には理想だが、
  まずは1ページで全重賞を回遊できる形にして、需要を見てから静的化する。

  重賞カレンダーのレース名から /data/jusho/?r=名前 に飛べるようにする（別途）。

出力: deploy/data/jusho/index.html
"""
import os
from urllib.parse import quote
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import site_config                                            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "deploy", "data", "jusho", "index.html")
SITE = site_config.get()

NAV = ('<nav class="snav"><a href="/">レース一覧</a><a href="/ai/">AI予想家</a>'
       '<a href="/record/">予想の記録</a><a href="/articles/">記事</a>'
       '<a href="/db/">データベース</a><a href="/calendar/">重賞カレンダー</a></nav>')

CSS = """*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);
  font-family:"Noto Sans JP",-apple-system,BlinkMacSystemFont,sans-serif;
  font-size:16px;line-height:1.8;-webkit-text-size-adjust:100%}
a{color:var(--blue)}
.wrap{max-width:860px;margin:0 auto;padding:22px 16px 72px;overflow-x:hidden}
h1{font-size:27px;margin:8px 0 2px}
h2{font-size:19px;margin:30px 0 6px}
h3{font-size:17px;margin:24px 0 4px;font-weight:700}
p{margin:0 0 13px}
h2::before{content:"";display:inline-block;width:4px;height:16px;margin-right:8px;
  background:var(--blue);vertical-align:-2px;border-radius:2px}
.sub{color:var(--mute);margin:0 0 6px}
.snav{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 16px}
.snav a{border:1px solid var(--line);background:var(--panel);border-radius:999px;
  padding:4px 13px;text-decoration:none;color:var(--mute);font-size:15px}
.pick{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 4px}
.pick{max-width:100%}
.pick select,.pick input{appearance:none;border:1px solid var(--line);background:var(--panel);
  color:var(--txt);font:inherit;font-size:16px;padding:9px 12px;border-radius:10px;max-width:100%}
#sel{width:100%}
.pick input{flex:1;min-width:160px}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{width:100%;border-collapse:collapse;margin:8px 0;font-size:16px;min-width:0}
th,td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{color:var(--mute);font-weight:700;background:var(--panel)}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.gb{display:inline-block;font-size:14px;font-weight:800;border-radius:6px;padding:1px 8px;
  color:var(--bg)}
.g1{background:var(--red)}.g2{background:var(--orange)}.g3{background:var(--yellow)}
.hot{color:var(--green);font-weight:700}
.bar span{display:inline-block;height:12px;background:var(--blue);border-radius:3px;
  vertical-align:middle;margin-right:6px}
.list{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0}
.list a{border:1px solid var(--line);border-radius:8px;padding:4px 10px;
  text-decoration:none;font-size:14px}
.note{color:var(--mute);font-size:15px}
footer{margin-top:48px;padding-top:18px;border-top:1px solid var(--line);
  color:var(--mute);font-size:15px}"""

JS = r"""<script>
(function(){
  const $=s=>document.querySelector(s);
  const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const gcls=g=>/G[Ⅰ1]/.test(g)?'g1':/G[Ⅱ2]/.test(g)?'g2':'g3';
  const pct=(a,b)=>b?(100*a/b).toFixed(0)+'%':'—';
  let DATA=null;
  const params=new URLSearchParams(location.search);

  function rateTable(obj, headLabel, order){
    const keys=order?order.filter(k=>obj[k]):Object.keys(obj).sort((a,b)=>+a-+b);
    if(!keys.length) return '';
    let mx=0; keys.forEach(k=>{ mx=Math.max(mx, 100*obj[k][2]/obj[k][0]); });
    let rows='';
    for(const k of keys){
      const [nn,win,pl]=obj[k];
      const fk=100*pl/nn, w=Math.max(4,Math.round(fk/Math.max(mx,1)*90));
      rows+=`<tr><td>${esc(k)}</td><td class="n">${nn}</td>`
          +`<td class="n">${pct(win,nn)}</td>`
          +`<td class="n bar"><span style="width:${w}px"></span>${fk.toFixed(0)}%</td></tr>`;
    }
    return `<div class="scroll"><table><tr><th>${headLabel}</th><th class="n">頭数</th>`
      +`<th class="n">勝率</th><th class="n">複勝率</th></tr>${rows}</table></div>`;
  }

  function show(name){
    const o=DATA[name];
    if(!o){ $('#body').innerHTML='<p class="note">その重賞のデータが見つかりませんでした。</p>'; return; }
    document.title=name+' のデータ（過去'+o.runs+'年）— カジ競馬';
    const p1=o.pop['1']||[0,0,0];
    let h=`<h1><span class="gb ${gcls(o.grade)}">${esc(o.grade)}</span> ${esc(name)}</h1>`
      +`<p class="sub">${o.jyo.join('・')} ／ ${esc(o.surf)}${o.dist}m ／ 過去${o.runs}回のデータ</p>`;
    h+=`<h2>1番人気は信頼できるか</h2>`
      +`<p>過去${p1[0]}回で、1番人気の複勝率は <b class="hot">${pct(p1[2],p1[0])}</b>、`
      +`勝率は ${pct(p1[1],p1[0])} でした。</p>`;
    h+='<h2>人気別の成績</h2>'+rateTable(o.pop,'人気');
    h+='<h2>枠順の成績</h2>'+rateTable(o.waku,'枠');
    h+='<h2>脚質の成績（このレースでどう走ったか）</h2>';
    // 逃げ+先行 と 差し+追込 の複勝率を比べて、前傾か後傾かを一言で
    (function(){
      const st=o.style, fr=['逃げ','先行'], bk=['差し','追込'];
      let fn=0,fp=0,bn=0,bp=0;
      fr.forEach(k=>{ if(st[k]){ fn+=st[k][0]; fp+=st[k][2]; }});
      bk.forEach(k=>{ if(st[k]){ bn+=st[k][0]; bp+=st[k][2]; }});
      if(fn>=10&&bn>=10){
        const fr3=100*fp/fn, bk3=100*bp/bn, d=fr3-bk3;
        const msg = d>=8 ? `<b class="hot">前が有利</b>な傾向です（逃げ・先行の複勝率 ${fr3.toFixed(0)}% ＞ 差し・追込 ${bk3.toFixed(0)}%）。`
                  : d<=-8 ? `<b class="hot">後ろから届く</b>傾向です（差し・追込の複勝率 ${bk3.toFixed(0)}% ＞ 逃げ・先行 ${fr3.toFixed(0)}%）。`
                  : `脚質による差は小さめです（前 ${fr3.toFixed(0)}% / 後 ${bk3.toFixed(0)}%）。`;
        h+=`<p>${msg}</p>`;
      }
    })();
    h+=rateTable(o.style,'脚質',['逃げ','先行','差し','追込']);
    h+='<h2>近年の勝ち馬</h2><div class="scroll"><table>'
      +'<tr><th>年</th><th>勝ち馬</th><th class="n">人気</th><th class="n">単勝配当</th><th class="n">頭数</th></tr>';
    for(const r of o.runnings){
      h+=`<tr><td>${r.date.slice(0,4)}/${r.date.slice(4,6)}/${r.date.slice(6,8)}</td>`
        +`<td>${esc(r.winner||'—')}</td><td class="n">${r.wpop||'—'}</td>`
        +`<td class="n">${r.tan?r.tan.toLocaleString()+'円':'—'}</td><td class="n">${r.fn}</td></tr>`;
    }
    h+='</table></div>';
    h+='<p class="note">脚質は各年の最初のコーナー通過順÷頭数から機械的に付けています。'
      +'コースのペース傾向を見る目安で、個々の馬の脚質とは限りません。</p>';
    $('#body').innerHTML=h;
    history.replaceState(null,'','?r='+encodeURIComponent(name));
    $('#sel').value=name;
  }

  fetch('/data/jusho/data.json',{cache:'no-cache'}).then(r=>r.json()).then(j=>{
    DATA=j;
    const names=Object.keys(j).sort((a,b)=>j[b].runs-j[a].runs);
    const sel=$('#sel');
    // G1を先頭に、あとは五十音でなく施行回数順
    for(const nm of names){
      const o=j[nm];
      sel.appendChild(new Option(`${o.grade}  ${nm}`, nm));
    }
    // 一覧リンク（G1だけ手早く飛べるように）
    const g1=names.filter(n=>/G[Ⅰ1]/.test(j[n].grade)).sort();
    $('#g1list').innerHTML=g1.map(n=>`<a href="?r=${encodeURIComponent(n)}">${n}</a>`).join('');
    sel.onchange=()=>show(sel.value);
    const want=params.get('r');
    show(want && j[want] ? want : (g1.includes('有馬記念')?'有馬記念':names[0]));
  }).catch(()=>{ $('#body').innerHTML='<p class="note">データを読み込めませんでした。</p>'; });
})();
</script>"""


def build_static():
    """★クローラーに見えるHTMLを用意する★

    このページは data.json を読んでJSで描く作りなので、
    HTMLだけを見ると「読み込み中…」しか無い＝中身ゼロのページに見える。
    実際AdSenseの審査でも、こういうページが「価値の低いコンテンツ」として扱われる。
    そこで (1) 143重賞を横断した実測の解説 (2) 全重賞への静的リンク
    をサーバー側で埋め込んでおく。数字はdata.jsonから毎回計算するので古びない。
    """
    import json
    src = os.path.join(ROOT, "deploy", "data", "jusho", "data.json")
    if not os.path.exists(src):
        return "", ""
    d = json.load(open(src, encoding="utf-8"))

    runs = sum(o.get("runs", 0) for o in d.values())
    n = w = t3 = 0
    fn = fp = bn = bp = 0
    front = back = flat = 0
    for o in d.values():
        p1 = o.get("pop", {}).get("1")
        if p1:
            n += p1[0]; w += p1[1]; t3 += p1[2]
        st = o.get("style", {})
        a_n = a_p = b_n = b_p = 0
        for k in ("逃げ", "先行"):
            if st.get(k):
                a_n += st[k][0]; a_p += st[k][2]
        for k in ("差し", "追込"):
            if st.get(k):
                b_n += st[k][0]; b_p += st[k][2]
        fn += a_n; fp += a_p; bn += b_n; bp += b_p
        if a_n >= 10 and b_n >= 10:
            gap = 100 * a_p / a_n - 100 * b_p / b_n
            front += gap >= 8
            back += gap <= -8
            flat += -8 < gap < 8
    if not n or not fn or not bn:
        return "", ""
    f3, b3 = 100 * fp / fn, 100 * bp / bn

    intro = f"""<h2>143重賞をまとめて見ると、2つのことが分かります</h2>

<h3>1. 重賞では1番人気があてになりません</h3>
<p>収録している{len(d)}重賞・延べ{runs:,}回の施行を合算すると、
1番人気の成績は<strong>勝率{100*w/n:.1f}% / 複勝率{100*t3/n:.1f}%</strong>でした
（{n:,}回ぶん）。中央競馬全体では1番人気の勝率はおよそ3分の1あるので、
<strong>重賞になると1番人気は目に見えて信頼できなくなる</strong>ということです。</p>
<p>理由は単純で、重賞には強い馬しか出てこないからです。
条件戦なら1頭だけ抜けていることがありますが、
重賞では相手も全部が実績馬で、力の差が詰まります。
<strong>「大レースだから堅い」は逆</strong>で、大レースだから紛れます。</p>

<h3>2. 重賞は「前に行った馬」が圧倒的に有利です</h3>
<p>各年の最初のコーナー通過順から脚質を機械的に付けて集計すると、
<strong>逃げ・先行の複勝率{f3:.1f}%</strong>に対し
<strong>差し・追込は{b3:.1f}%</strong>。{f3-b3:.1f}ポイントの差です。</p>
<p>レース単位で見るともっとはっきりします。
前が有利（逃げ・先行が差し・追込を8ポイント以上上回る）と言えるのは
<strong>{front}レース</strong>、逆に後ろから届くと言えるのは
<strong>わずか{back}レース</strong>、どちらとも言えないのが{flat}レースでした。
<strong>前有利のレースは、後ろ有利のレースの{front/max(back,1):.0f}倍以上あります。</strong></p>
<p class="note">ただしこれは「逃げれば勝てる」という意味ではありません。
強い馬が好位を取れる、という因果の向きも含まれています。
また脚質はコーナー通過順から機械的に付けたもので、
その馬本来の脚質とは限りません（同じ馬でもレースによって位置取りは変わります）。
このページの数字は<strong>そのレースのペース傾向を知る目安</strong>として使ってください。</p>

<h3>このページの使い方</h3>
<p>上のプルダウンか下の一覧からレースを選ぶと、そのレース単体の
人気別・枠順別・脚質別の成績と、近年の勝ち馬（人気・単勝配当つき）が出ます。
<strong>1番人気が信頼できるレースなのか、内枠と外枠のどちらが来ているのか、
前と後ろのどちらが有利なのか</strong>を、そのレースの過去10年前後の実績だけで確認できます。</p>
<p class="note">出典はJRA-VAN Data Lab.の公式データです。
施行回数はレースによって違います（新設重賞は数年分しかありません）。
回数が少ないレースの率は大きく振れるので、必ず「過去○回」の表示を見てください。</p>"""

    rows = sorted(d.items(), key=lambda kv: (kv[1]["grade"], kv[0]))
    links = "".join(
        f'<a href="?r={quote(nm)}">{o["grade"]} {nm}</a>'
        for nm, o in rows)
    listing = f"""<h2>収録している重賞（{len(d)}レース）</h2>
<div class="list">{links}</div>"""
    return intro, listing


def main():
    intro, listing = build_static()
    body = f"""<h1 style="margin-bottom:2px">重賞データ</h1>
<p class="sub">中央競馬の重賞を、過去のデータで見ます。人気・枠・脚質の成績と勝ち馬の一覧。</p>
<div class="pick">
  <select id="sel"><option>読み込み中…</option></select>
</div>
<h2 style="font-size:16px;border:0;margin:16px 0 4px;color:var(--mute)">GⅠから選ぶ</h2>
<div class="list" id="g1list"></div>
<div id="body"><p class="note">読み込み中…</p></div>
{intro}
{listing}"""

    html = f"""<title>重賞データ — {SITE['name']}</title>
{site_config.adsense()}<link rel="stylesheet" href="{site_config.asset('core/theme.css')}">
<script src="{site_config.asset('core/theme.js')}"></script>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="中央競馬の重賞を過去データで分析。人気別・枠順別・脚質別の成績と近年の勝ち馬。有馬記念・日本ダービー・皐月賞ほか143重賞。">
<link rel="canonical" href="{site_config.url('data/jusho/')}">
<meta property="og:type" content="website">
<meta property="og:title" content="重賞データ — 過去の傾向で見る">
<meta property="og:description" content="人気・枠・脚質の成績と勝ち馬。143重賞を実データで。">
<meta property="og:url" content="{site_config.url('data/jusho/')}">
<meta property="og:image" content="{site_config.url('data/ogp.png')}">
<meta name="twitter:card" content="summary_large_image">
<style>{CSS}</style>
<div class="wrap">
<div style="display:flex;align-items:center;gap:12px;margin-bottom:4px">
<a href="/calendar/">← 重賞カレンダー</a><div style="flex:1"></div>
<button class="themebtn" type="button">☾</button></div>
{NAV}
{body}
<footer>
{SITE['name']} ／ データ出典: JRA-VAN Data Lab.（公式データ）<br>
本ページは情報提供を目的としたもので、的中や利益を保証するものではありません。<br>
<a href="/privacy/">プライバシーポリシー・運営者情報</a>
</footer>
</div>
{JS}
<script>
try{{ new Image().src = '/stats.php?p=' + encodeURIComponent(location.pathname)
   + '&r=' + encodeURIComponent(document.referrer) + '&t=' + Date.now(); }}catch(e){{}}
</script>
"""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    print(f"出力: {os.path.relpath(OUT, ROOT)}  {len(html.encode('utf-8')):,}B")
    return 0


if __name__ == "__main__":
    sys.exit(main())
