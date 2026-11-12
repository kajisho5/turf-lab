# -*- coding: utf-8 -*-
"""重賞カレンダー（中央競馬）を作る

★格付けは JV-Data の GradeCD（RAレコード614バイト目）★
  netkeiba の Icon_GradeType を「付いていれば重賞」と扱って、
  南相馬特別・猪苗代特別・福島テレビ賞まで重賞と表示していた事故があった。
  公式データには格付けそのものが入っているので、こちらを正とする。

  値と実際の施行数（2024/2025年で照合。JRAの実数と一致した）:
    A = GⅠ    24件/年   フェブラリーS・高松宮記念・NHKマイルC
    B = GⅡ    38件/年
    C = GⅢ    67件/年
    D = 重賞（格付けなし）
    F = J・GⅠ  2件/年   中山グランドジャンプ・中山大障害
    G = J・GⅡ  3件/年
    H = J・GⅢ  5件/年
    L = リステッド 64件/年 → **重賞ではない**ので載せない
    E = 重賞以外の特別   → 載せない

出力: deploy/calendar/index.html
使い方: python backtest/gen_calendar_page.py
"""
import collections
import os
from urllib.parse import quote
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import site_config                                            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUMP = [os.path.join(ROOT, "backtest", "jvdata", "target_all.txt"),
        os.path.join(ROOT, "backtest", "jvdata", "setup_2026.txt")]
OUT = os.path.join(ROOT, "deploy", "calendar", "index.html")
SITE = site_config.SITES["public"]

# 載せる格付けだけ。リステッド(L)と特別(E)は重賞ではないので入れない
GRADE = {"A": ("GⅠ", "g1"), "B": ("GⅡ", "g2"), "C": ("GⅢ", "g3"),
         "D": ("重賞", "g3"), "F": ("J・GⅠ", "g1"), "G": ("J・GⅡ", "g2"),
         "H": ("J・GⅢ", "g3")}
ORDER = ["A", "F", "B", "G", "C", "H", "D"]

R_KEY, R_NAME, R_GRADE = slice(11, 27), slice(32, 92), slice(614, 615)
R_DIST, R_TRACK = slice(697, 701), slice(705, 707)
S_KEY, S_UMA, S_NAME, S_FIN = slice(11, 27), slice(28, 30), slice(40, 76), slice(334, 336)
S_JK = slice(306, 314)   # 騎手名（8バイト切り詰め。build_jra_jockey.py と同じ）

JYO = {"01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
       "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉"}


def norm(name):
    """レース名の表記ゆれを吸収する

    ★同じレースが別名で二重に出る★
      「農林水産省賞典　安田記念」と「安田記念」が別レース扱いになっていた。
      冠称や全角空白を落として同じものは同じ名前にする。
    """
    n = name.replace("　", " ").strip()
    for pre in ("農林水産省賞典", "農林水産大臣賞典", "サラブレッド系"):
        if n.startswith(pre):
            n = n[len(pre):].strip()
    return n


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def main():
    races = {}
    winners = {}
    jwinners = {}   # レースキー -> 勝った騎手名
    for path in DUMP:
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            for line in f:
                t = line[:2]
                if t == b"RA":
                    g = line[R_GRADE].decode("cp932", "replace")
                    if g not in GRADE:
                        continue
                    k = line[R_KEY]
                    # ★中央のレースだけにする★
                    #   JRA-VAN は馬券発売の対象として **海外G1と地方交流重賞** も配信する。
                    #   絞らずに数えたら GⅠ が45件になった（実際は年24件）。
                    #   混ざっていたのはドバイワールドカップ・ケンタッキーダービー・
                    #   サウジカップ・東京大賞典・川崎記念・羽田盃など。
                    #   中央の競馬場コードは 01〜10 だけ。
                    if k[8:10].decode("ascii", "replace") not in JYO:
                        continue
                    dist = line[R_DIST].decode("ascii", "replace").strip()
                    tr = line[R_TRACK].decode("ascii", "replace")
                    races[k] = {
                        "g": g,
                        "name": norm(line[R_NAME].decode("cp932", "replace")),
                        "date": k[:8].decode(), "jyo": JYO.get(k[8:10].decode(), "?"),
                        "dist": dist,
                        "surf": "芝" if tr[:1] == "1" else ("ダ" if tr[:1] == "2" else "障"),
                    }
                elif t == b"SE":
                    k = line[S_KEY]
                    # ★着順はゼロ埋め2桁（'01'）★ 以前は == "1" で判定しており一度も
                    #   マッチせず、「近年の勝ち馬」欄が全458件「—」のまま公開されていた
                    #   （2026-07-24 に実測で発覚。target_all/setup_2026 とも '01' 形式）。
                    if line[S_FIN].decode("ascii", "replace").strip() in ("1", "01"):
                        winners[k] = line[S_NAME].decode("cp932", "replace").strip()
                        jwinners[k] = line[S_JK].decode("cp932", "replace").strip()
        print(f"  読了 {os.path.basename(path)}  重賞 {len(races):,}", flush=True)

    # レース名でまとめる（同じ重賞の毎年の施行をひとまとめに）
    by_name = collections.defaultdict(list)
    for k, r in races.items():
        r["winner"] = winners.get(k, "")
        r["jockey"] = jwinners.get(k, "")
        by_name[(r["name"], r["g"])].append(r)

    # 月ごとに並べる。基準は「直近の施行月」
    months = collections.defaultdict(list)
    for (name, g), rs in by_name.items():
        # ★同一年の重複を1つに絞る★ 雪などで順延になると、JVのsetupデータには
        #   旧日程のRAレコードが残る（きさらぎ賞2026は2/8・2/9・2/10の3本。
        #   勝ち馬(SE)が付くのは実際に施行された1本だけ）。勝ち馬の無い順延痕を
        #   そのまま出すと「2026 —」が並んでしまうため、同じ年に複数あるときは
        #   勝ち馬がある方＞日付が新しい方 の優先で1本だけ残す。
        #   （まだ施行されていない未来のレースはその年に1本しか無いので消えない）
        by_year = {}
        for r in rs:
            y = r["date"][:4]
            cur = by_year.get(y)
            if cur is None or (not cur["winner"] and r["winner"]) \
               or (bool(cur["winner"]) == bool(r["winner"]) and r["date"] > cur["date"]):
                by_year[y] = r
        rs = sorted(by_year.values(), key=lambda x: x["date"], reverse=True)
        latest = rs[0]
        if latest["date"] < "20200101":       # 10年以上前に無くなった重賞は載せない
            continue
        # ★このレースに強い騎手★ 全施行年（1986年〜）の勝ち騎手を数え、2勝以上の最多だけ出す。
        #   1勝どうしの並びは「強い」の根拠にならないので出さない（盛らない）。
        jc = collections.Counter(r["jockey"] for r in rs if r["jockey"])
        top_jk = None
        if jc:
            jkname, jkn = jc.most_common(1)[0]
            if jkn >= 2:
                top_jk = (jkname, jkn)
        months[int(latest["date"][4:6])].append({
            "name": name, "g": g, "latest": latest,
            "hist": rs[:6], "top_jk": top_jk,
        })
    for m in months:
        months[m].sort(key=lambda x: (ORDER.index(x["g"]), x["latest"]["date"][4:8]))

    total = sum(len(v) for v in months.values())
    counts = collections.Counter(x["g"] for v in months.values() for x in v)

    # ---- 表そのものから読み取れることを数字にする ----
    # 一覧を並べただけでは「で、何が言えるのか」が無い。
    # 掲載中の重賞（months に残ったもの）を横断して集計する。
    listed = [x for v in months.values() for x in v]
    surf_c = collections.Counter(x["latest"]["surf"] for x in listed)
    mon_c = {m: len(months.get(m, [])) for m in range(1, 13)}
    mon_top = max(mon_c, key=lambda m: mon_c[m])
    mon_low = min((m for m in mon_c if mon_c[m]), key=lambda m: mon_c[m])
    g1_mon = collections.Counter(
        m for m in months for x in months[m] if x["g"] == "A")
    g1_top = g1_mon.most_common(1)[0] if g1_mon else (0, 0)

    # 掲載重賞の全施行を横断した騎手の勝利数（1986年〜）
    jk_all = collections.Counter()
    for x in listed:
        for h in by_name[(x["name"], x["g"])]:
            if h["jockey"]:
                jk_all[h["jockey"]] += 1
    jk_top = jk_all.most_common(3)

    # 「このレースに強い騎手」が出せた割合＝同じ人が2回以上勝った重賞の割合
    rep = sum(1 for x in listed if x["top_jk"])
    surf_line = "・".join(f"{k}{v}レース" for k, v in surf_c.most_common())
    dirt_pct = 100 * surf_c.get("ダ", 0) / (total or 1)

    insight = f"""<h2>この一覧から実際に読み取れること</h2>

<h3>中央の重賞は、ほぼ芝のレースです</h3>
<p>掲載{total}レースの内訳は<strong>{surf_line}</strong>。
ダートは全体の<strong>{dirt_pct:.0f}%</strong>しかありません。
中央競馬は1日の番組で見ればダート戦のほうが多いくらいなのに、
<strong>賞金と格の付いたレースになると芝に極端に偏る</strong>——
これがこの表を縦に見たときに一番はっきり出る事実です。
中央のダート路線が手薄だと言われるのは、感覚ではなく番組表の構造の話です。</p>
<p class="note">なおこの一覧には地方交流重賞（東京大賞典・川崎記念など）を含めていません。
中央のダート重賞が少なく見えるのは、ダートの大レースの多くが
地方競馬場で行われているという事情も反映しています。</p>

<h3>重賞の数は、月によって{mon_c[mon_top]/max(mon_c[mon_low],1):.1f}倍違います</h3>
<p>もっとも多いのは<strong>{mon_top}月の{mon_c[mon_top]}レース</strong>、
もっとも少ないのは<strong>{mon_low}月の{mon_c[mon_low]}レース</strong>。
GⅠに限ると{g1_top[0]}月が{g1_top[1]}レースで最多です。
重賞は1年に均等には散らばっていません。
夏場に少ないのは主場（東京・中山・京都・阪神）が開催を離れ、
ローカル開催が中心になるためで、
<strong>「大きいレースが無い時期」が実際に存在します</strong>。
月の見出しから飛べるようにしてあるのはそのためです。</p>

<h3>「このレースに強い騎手」は、意外と成立します</h3>
<p>掲載{total}レースのうち<strong>{rep}レース</strong>
（{100*rep/(total or 1):.0f}%）では、同じ騎手が2回以上勝っています。
1986年以降の全施行を通した勝利数トップは
{"、".join(f"<strong>{n}</strong>（{c}勝）" for n, c in jk_top)}。</p>
<p>ただし<strong>これを「相性」と読むのは危険です。</strong>
勝ち鞍の多い騎手は、そもそも有力馬に乗る回数が多い。
同じ騎手が同じレースを何度も勝つのは、
そのレースと相性が良いからではなく、
毎年その厩舎の一番強い馬に乗っているからだと考えるほうが自然です。
実際、当サイトが
<a href="/db/jra/combo/">騎手×調教師コンビ成績</a>で同じ問いを検証したところ、
コンビごとの成績差は確かに存在するものの、
<strong>回収率で見ると100%に届く水準ではありません</strong>でした。
この欄も「よく勝っている人」の記録として見てください。</p>"""

    rows = []
    for m in range(1, 13):
        if not months.get(m):
            continue
        rows.append(f'<h2 id="m{m}">{m}月<span class="cnt">{len(months[m])}レース</span></h2>')
        rows.append('<div class="scroll"><table><thead><tr>'
                    '<th>格</th><th>レース</th><th>場</th><th>条件</th>'
                    '<th>直近施行</th><th>近年の勝ち馬</th><th>最多勝騎手</th></tr></thead><tbody>')
        for x in months[m]:
            lab, cls = GRADE[x["g"]]
            L = x["latest"]
            hist = "".join(
                f'<div class="w"><span>{h["date"][:4]}</span>{esc(h["winner"] or "—")}</div>'
                for h in x["hist"][:3])
            tj = x["top_jk"]
            tj_html = (f'<a href="/db/jra/jockey/detail/?name={quote(tj[0])}">{esc(tj[0])}</a>'
                       f'<small>{tj[1]}勝</small>' if tj else '<span class="none">—</span>')
            rows.append(
                f'<tr data-g="{x["g"]}">'
                f'<td><span class="gb {cls}">{lab}</span></td>'
                f'<td class="nm"><a href="/data/jusho/?r={quote(x["name"])}">{esc(x["name"])}</a></td>'
                f'<td>{L["jyo"]}</td>'
                f'<td class="n">{L["surf"]}{L["dist"]}m</td>'
                f'<td class="n">{L["date"][:4]}/{L["date"][4:6]}/{L["date"][6:8]}</td>'
                f'<td class="hist">{hist}</td>'
                f'<td class="tj">{tj_html}</td></tr>')
        rows.append("</tbody></table></div>")

    body = f"""<h1>重賞カレンダー</h1>
<p class="lead">中央競馬の重賞を月ごとに並べています。
格付けは<b>JRA-VAN公式データの格付けコード</b>そのままで、
オープン特別やリステッドは含めていません。</p>

<div class="kpi">
  <div><b>{counts['A']}</b><span>GⅠ</span></div>
  <div><b>{counts['B']}</b><span>GⅡ</span></div>
  <div><b>{counts['C']}</b><span>GⅢ</span></div>
  <div><b>{counts['F']+counts['G']+counts['H']}</b><span>障害重賞</span></div>
  <div><b>{total}</b><span>合計</span></div>
</div>

<div class="filt">
  <span>絞り込み</span>
  <button class="chip" data-f="" aria-pressed="true">すべて</button>
  <button class="chip" data-f="A">GⅠだけ</button>
  <button class="chip" data-f="B">GⅡだけ</button>
  <button class="chip" data-f="C">GⅢだけ</button>
  <button class="chip" data-f="FGH">障害だけ</button>
</div>

<nav class="mnav">{"".join(f'<a href="#m{m}">{m}月</a>' for m in range(1,13) if months.get(m))}</nav>

{"".join(rows)}

{insight}

<p class="note">※ 施行時期は年によって前後します。表の日付は直近に行われた日です。<br>
※ 最多勝騎手は1986年以降の全施行での勝利数。2勝以上の騎手がいないレースは「—」。
名前をタップすると騎手の詳細成績へ。<br>
※ 2020年以降に施行実績のある重賞のみ掲載しています。</p>"""

    css = """
:root{color-scheme:light dark}
body{margin:0;background:var(--bg);color:var(--txt);
  font-family:system-ui,-apple-system,"Hiragino Kaku Gothic ProN","Noto Sans JP",sans-serif;
  font-size:16px;line-height:1.7}
.wrap{max-width:1040px;margin:0 auto;padding:16px 16px 60px}
a{color:var(--blue)}
h1{font-size:28px;margin:12px 0 4px;border-left:5px solid var(--red);padding-left:12px}
h2{font-size:21px;margin:34px 0 4px;padding-bottom:6px;border-bottom:2px solid var(--line);
  display:flex;align-items:baseline;gap:10px}
h2 .cnt{font-size:14px;color:var(--mute);font-weight:400}
h3{font-size:18px;margin:26px 0 6px;font-weight:700}
p{margin:0 0 14px}
.lead{color:var(--mute)}
.kpi{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0}
.kpi div{flex:1 1 110px;background:var(--panel);border:1px solid var(--line);
  border-top:3px solid var(--line);border-radius:12px;padding:10px 14px}
.kpi div:nth-child(1){border-top-color:var(--red)}
.kpi div:nth-child(2){border-top-color:var(--orange)}
.kpi div:nth-child(3){border-top-color:var(--yellow)}
.kpi div:nth-child(4){border-top-color:var(--blue)}
.kpi b{display:block;font-size:25px;font-variant-numeric:tabular-nums}
.kpi span{color:var(--mute);font-size:14px}
.filt{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:14px 0}
.filt>span{color:var(--mute);font-size:14px;font-weight:700}
.chip{appearance:none;border:1px solid var(--line);background:var(--panel);color:var(--mute);
  font:inherit;font-size:15px;padding:5px 14px;border-radius:999px;cursor:pointer}
.chip[aria-pressed="true"]{background:var(--blue);color:var(--bg);border-color:var(--blue);
  font-weight:700}
.mnav{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0 4px}
.mnav a{border:1px solid var(--line);border-radius:8px;padding:3px 11px;
  text-decoration:none;font-size:15px}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{width:100%;border-collapse:collapse;margin:6px 0;font-size:16px;min-width:660px}
th,td{padding:8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--mute);font-weight:700;background:var(--panel);white-space:nowrap}
tbody tr:nth-child(even){background:var(--stripe)}
td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
td.nm{font-weight:700}
.gb{display:inline-block;font-size:14px;font-weight:800;border-radius:6px;
  padding:1px 8px;color:var(--bg);white-space:nowrap}
.gb.g1{background:var(--red)}
.gb.g2{background:var(--orange)}
.gb.g3{background:var(--yellow)}
.hist{font-size:14px;color:var(--mute);min-width:190px}
.tj{white-space:nowrap;font-size:15px}
.tj small{color:var(--mute);margin-left:4px}
.tj .none{color:var(--mute)}
.hist .w{white-space:nowrap}
.hist .w span{display:inline-block;width:3.4em;color:var(--dim)}
.note{color:var(--mute);font-size:15px;margin-top:26px}
footer{margin-top:48px;padding-top:18px;border-top:1px solid var(--line);
  color:var(--mute);font-size:15px}
"""

    js = """
document.querySelectorAll('.chip').forEach(b => b.onclick = () => {
  document.querySelectorAll('.chip').forEach(x => x.setAttribute('aria-pressed', x === b));
  const f = b.dataset.f;
  document.querySelectorAll('tbody tr').forEach(tr => {
    tr.hidden = !!f && !f.includes(tr.dataset.g);
  });
  // 中身が全部消えた月は見出しごと隠す（空の見出しだけ残ると壊れて見える）
  document.querySelectorAll('h2[id^="m"]').forEach(h => {
    const box = h.nextElementSibling;
    const any = [...box.querySelectorAll('tbody tr')].some(tr => !tr.hidden);
    h.hidden = box.hidden = !any;
  });
});
"""

    html = f"""<title>重賞カレンダー（中央競馬） — {SITE['name']}</title>
{site_config.adsense()}<link rel="stylesheet" href="{site_config.asset('core/theme.css')}">
<script src="{site_config.asset('core/theme.js')}"></script>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="中央競馬の重賞を月ごとに一覧。GⅠ・GⅡ・GⅢ・障害重賞を公式データの格付けで分類し、近年の勝ち馬も掲載。">
<link rel="canonical" href="{site_config.url('calendar/')}">
<meta property="og:type" content="article">
<meta property="og:title" content="重賞カレンダー（中央競馬）">
<meta property="og:description" content="GⅠ・GⅡ・GⅢを月ごとに。公式データの格付けで分類。">
<meta property="og:url" content="{site_config.url('calendar/')}">
<meta property="og:image" content="{site_config.url('data/ogp.png')}">
<meta name="twitter:card" content="summary_large_image">
<style>{css}</style>
<div class="wrap">
<div style="display:flex;align-items:center;gap:12px;margin-bottom:4px">
<a href="/">← レース一覧</a><div style="flex:1"></div>
<button class="themebtn" type="button">☾</button></div>
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
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    print(f"\n出力: {os.path.relpath(OUT, ROOT)}  {len(html.encode('utf-8')):,}B")
    print(f"  重賞 {total}レース  " + " ".join(f"{GRADE[g][0]}{counts[g]}" for g in ORDER if counts[g]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
