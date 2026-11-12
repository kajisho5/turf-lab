# -*- coding: utf-8 -*-
"""中央競馬のデータベース（騎手・調教師・馬主リーディング）

/db/jra/jockey/   騎手リーディング
/db/jra/trainer/  調教師リーディング
/db/jra/owner/    馬主リーディング   ★地方版には無い★

★地方版と同じ体裁にする★
  gen_db_pages.py と見た目・列・注意書きを揃える。
  片方だけ違う作りにすると、同じ数字なのか別の数字なのか読み手に伝わらない。

★「勝つ」と「買って得」は別物★
  勝利数だけでなく複勝回収率まで出す。分母は全騎乗（的中時だけ投資計上しない）。
  ほぼ全員100%を下回る。それが控除率。

入力: backtest/jra_leading.json（build_jra_leading.py が生成）
"""
import json
import os
import sys
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import site_config
from gen_db_pages import insight   # 解説文は地方版と共有（二重管理を避ける）                                            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "backtest", "jra_leading.json")
OUTBASE = os.path.join(ROOT, "deploy", "db", "jra")
SITE = site_config.get()

MIN_ALL = 500
MIN_RECENT = 100
TOP = 100

KINDS = [("jockey", "騎手", "騎乗"), ("trainer", "調教師", "出走"),
         ("owner", "馬主", "出走"),
         # ★血統は別ソース★ SEに入っていないので UM_DATA（馬マスタ）から作る
         ("sire", "種牡馬", "産駒出走"), ("damsire", "母父", "出走"),
         # ★生産者も別ソース★ SEに無く、UMの生産者名(890-962)を血統登録番号で結合
         ("breeder", "生産者", "出走")]
SIRE_SRC = os.path.join(ROOT, "backtest", "jra_sire_leading.json")
BREEDER_SRC = os.path.join(ROOT, "deploy", "db", "jra", "br", "index.json")

NAV = ('<nav class="snav"><a href="/">レース一覧</a><a href="/ai/">AI予想家</a>'
       '<a href="/record/">予想の記録</a><a href="/articles/">記事</a>'
       '<a href="/db/">データベース</a><a href="/calendar/">重賞カレンダー</a></nav>')

CSS = """*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);
  font-family:"Noto Sans JP",-apple-system,BlinkMacSystemFont,sans-serif;
  font-size:16px;line-height:1.8;-webkit-text-size-adjust:100%}
a{color:var(--blue)}
.wrap{max-width:880px;margin:0 auto;padding:24px 18px 72px}
h1{font-size:29px;line-height:1.4;margin:8px 0 4px}
h2{font-size:22px;margin:40px 0 10px;font-weight:700;
  border-left:5px solid var(--yellow);padding-left:12px}
h3{font-size:19px;margin:28px 0 6px;font-weight:700}
p{margin:0 0 14px}
ul{margin:0 0 16px;padding-left:1.3em}
li{margin:0 0 8px}
.lead{color:var(--mute);font-size:17px}
.snav{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 16px}
.snav a{border:1px solid var(--line);background:var(--panel);border-radius:999px;
  padding:4px 13px;text-decoration:none;color:var(--mute);font-size:15px}
.snav a:hover{border-color:var(--mute);color:var(--txt)}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{width:100%;border-collapse:collapse;margin:12px 0;font-size:16px;min-width:560px}
th,td{padding:8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{color:var(--mute);font-weight:700;background:var(--panel)}
tbody tr:nth-child(even){background:var(--stripe)}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.g{color:var(--green);font-weight:700}
.note{color:var(--mute);font-size:16px}
.card{display:block;background:var(--panel);border:1px solid var(--line);
  border-radius:12px;padding:16px;margin:12px 0;text-decoration:none;color:inherit}
.card:hover{border-color:var(--yellow)}
.card b{font-size:19px;display:block}
.card span{color:var(--mute)}
footer{margin-top:52px;padding-top:18px;border-top:1px solid var(--line);
  color:var(--mute);font-size:16px}"""


def page(title, desc, path_, body, back):
    return f"""<title>{title} — {SITE['name']}</title>
{site_config.adsense()}<link rel="stylesheet" href="{site_config.asset('core/theme.css')}">
<script src="{site_config.asset('core/theme.js')}"></script>
<script src="{site_config.asset('core/table.js')}" defer></script>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="{desc}">
<meta property="og:type" content="article">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{site_config.url(path_)}">
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
<script>
try{{ new Image().src = '/stats.php?p=' + encodeURIComponent(location.pathname)
   + '&r=' + encodeURIComponent(document.referrer) + '&t=' + Date.now(); }}catch(e){{}}
</script>
"""


def table(d, min_n, unit, kind=""):
    rows = [(k, v) for k, v in d.items() if v[0] >= min_n]
    rows.sort(key=lambda x: -x[1][1])
    out = []
    for i, (name, (n, win, top3, ret)) in enumerate(rows[:TOP], 1):
        roi = 100 * ret / (100 * n)
        link = (f'<a href="/db/jra/jockey/detail/?name={quote(name)}">{name}</a>' if kind == 'jockey'
                else f'<a href="/db/jra/trainer/detail/?name={quote(name)}">{name}</a>' if kind == 'trainer'
                else f'<a href="/db/jra/owner/detail/?name={quote(name)}">{name}</a>' if kind == 'owner'
                else f'<a href="/db/jra/sire/detail/?name={quote(name)}">{name}</a>' if kind == 'sire'
                else f'<a href="/db/jra/damsire/detail/?name={quote(name)}">{name}</a>' if kind == 'damsire'
                else f'<a href="/db/jra/breeder/detail/?name={quote(name)}">{name}</a>' if kind == 'breeder'
                else name)
        out.append(
            f'<tr><td class="n">{i}</td><td><strong>{link}</strong></td>'
            f'<td class="n">{win:,}</td><td class="n">{n:,}</td>'
            f'<td class="n">{100*win/n:.1f}%</td><td class="n">{100*top3/n:.1f}%</td>'
            f'<td class="n{" g" if roi >= 90 else ""}">{roi:.1f}%</td></tr>')
    head = (f'<tr><th class="n">順</th><th>名前</th><th class="n">勝利</th>'
            f'<th class="n">{unit}数</th><th class="n">勝率</th>'
            f'<th class="n">複勝率</th><th class="n">複勝回収率</th></tr>')
    return head + "".join(out), len(rows)


def main():
    if not os.path.exists(SRC):
        print("先に build_jra_leading.py を回すこと")
        return 1
    src = json.load(open(SRC, encoding="utf-8"))
    races = src["races"]
    since = src["recent_from"]

    # 血統（種牡馬・母父）を合流。こちらは通算のみなので直近は同じものを使う
    if os.path.exists(SIRE_SRC):
        sl = json.load(open(SIRE_SRC, encoding="utf-8"))
        for k in ("sire", "damsire"):
            src["data"][k] = [sl[k], sl[k]]

    # 生産者を合流（br/index.json の詳細形式 → leading表のフラット形式へ変換）
    if os.path.exists(BREEDER_SRC):
        br = json.load(open(BREEDER_SRC, encoding="utf-8"))
        # roi = 100*ret/(100*n) で丸めたものなので ret ≒ roi*n（表示は再計算で同じ丸めに戻る）
        flat = {name: [e["n"], e["w"], e["t3"], e["roi"] * e["n"]] for name, e in br.items()}
        src["data"]["breeder"] = [flat, flat]

    for kind, label, unit in KINDS:
        if kind not in src["data"]:
            print(f"  /db/jra/{kind}/  スキップ（データ無し。先に build_jra_breeder.py 等を回す）")
            continue
        all_, recent = src["data"][kind]
        blood = kind in ("sire", "damsire", "breeder")
        t_r, n_r = ("", 0) if blood else table(recent, MIN_RECENT, unit, kind)
        t_a, n_a = table(all_, MIN_ALL, unit, kind)
        recent_block = "" if blood else (
            f'<h2>直近（{since[:4]}年以降・{unit}{MIN_RECENT}以上）</h2>'
            f'<div class="scroll"><table class="zebra sortable">{t_r}</table></div>')
        body = f"""<h1>{label}リーディング（中央競馬）</h1>
<p class="lead">中央競馬 {races:,}レース（1986年〜）の実測です。
勝利数だけでなく、<strong>買って得だったか（複勝回収率）</strong>まで出しています。</p>
{site_config.ad_slot(f"jradb-{kind}")}
{recent_block}
<h2>通算（1986年〜・{unit}{MIN_ALL}以上）</h2>
<div class="scroll"><table class="zebra sortable">{t_a}</table></div>
<p class="note">※ {unit}数が基準に満たない場合は載せていません。
少ない数の率は大きく振れ、順位が偶然で入れ替わるためです。<br>
※ 複勝回収率は「全{unit}の複勝を100円ずつ買った」計算で、
<strong>ほぼ全員が100%を下回ります</strong>。それが控除率です。</p>
{insight(all_, MIN_ALL, unit, label, kind)}"""
        d = os.path.join(OUTBASE, kind)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "index.html"), "w", encoding="utf-8", newline="\n") as f:
            f.write(page(f"{label}リーディング（中央競馬）",
                         f"中央競馬{races:,}レースの実測。{label}別の勝率・複勝率・複勝回収率。",
                         f"db/jra/{kind}/", body, ("/db/jra/", "中央のデータベース")))
        print(f"  /db/jra/{kind}/  直近{n_r} / 通算{n_a}")

    # 中央の入口
    cards = ('<a class="card" href="/db/jra/horse/"><b>馬検索</b>'
             '<span>馬名・父・母父で絞り込み（直近3年・約2.3万頭）</span></a>')
    cards += "".join(
        f'<a class="card" href="/db/jra/{k}/"><b>{lab}リーディング</b>'
        f'<span>勝利数・勝率・複勝率・複勝回収率</span></a>'
        for k, lab, _ in KINDS)
    cards += ('<a class="card" href="/db/jra/trainer-homeaway/"><b>厩舎の地元開催vs遠征</b>'
              '<span>「遠征厩舎は弱い」説を455厩舎ぶんで検証中</span></a>')
    cards += ('<a class="card" href="/db/jra/combo/"><b>騎手×調教師コンビ成績</b>'
              '<span>「相性の良いコンビ」を勝率・複勝回収率で検証</span></a>')
    cards += ('<a class="card" href="/db/jra/g1/"><b>重賞(GI/GII/GIII)ランキング</b>'
              '<span>通算成績ではなく、大レースに強いのは誰かだけを見る</span></a>')
    body = f"""<h1>データベース（中央競馬）</h1>
<p class="lead">中央競馬 {races:,}レース（1986年〜）を集計したリーディングです。
どの表にも複勝回収率を付けています。「勝つ騎手」と「買って得な騎手」は別物だからです。</p>
{cards}
<p class="note">馬主リーディングは中央だけの表です。<br>
地方競馬のデータベースは<a href="/db/">こちら</a>。</p>

<h2>なぜ勝利数だけのランキングを出さないのか</h2>
<p>リーディングは普通「勝利数」で並べます。それは正しいのですが、
<strong>勝利数の順位を見て馬券を買うと、たいてい損をします</strong>。
よく勝つ人は人気になり、人気になればオッズが下がるからです。
実力の証明と、買って得かどうかは、別の話です。</p>
<p>そこで当サイトの表には必ず<strong>複勝回収率</strong>を入れています。
「その人の関わった馬の複勝を、全レース100円ずつ買っていたら手元にいくら残ったか」
という数字です。並べ替えれば、勝利数の順位とまったく揃わないことがすぐ分かります。</p>

<h2>1986年からの40年分を通しで見られます</h2>
<p>集計対象は{races:,}レース。ここまで長い期間を通しで並べると、
<strong>時代ごとに主役が入れ替わっていくのがそのまま見える</strong>のが面白いところです。
種牡馬リーディングを開けば、その世代を支配した父がどれだけの数字を残したのかが
一目で分かります。</p>
<p>ただし長期の通算は<strong>現役かどうかを区別しません</strong>。
すでに引退した人・供用を終えた種牡馬も、積み上げた勝利数のまま上位に残ります。
「今どうか」を見たいときは、各ページの<strong>直近の表</strong>のほうを見てください。</p>

<h2>回収率の見方で、ひとつだけ約束していること</h2>
<p>回収率は<strong>買った全レースを分母</strong>にしています。
当たったレースだけを分母にすると、回収率はいくらでも大きく見せられます。
この分母の取り方の違いだけで「複勝で黒字」という誤った結論に一度たどり着いたことがあり、
それ以来ここは徹底しています。</p>
<p>もうひとつ、<strong>件数が少ない行は載せません</strong>。
数十回の成績では複勝率も回収率も偶然だけで大きく動き、順位が意味を持たなくなるためです。</p>

<h2>このデータの出どころ</h2>
<p>JRA-VAN Data Lab. の公式データ（JV-Data）を取得して自前で集計したものです。
着順・払戻とも公式の確定値で、スクレイピングは使っていません。</p>"""
    os.makedirs(OUTBASE, exist_ok=True)
    with open(os.path.join(OUTBASE, "index.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(page("データベース（中央競馬）",
                     f"中央競馬{races:,}レースの騎手・調教師・馬主リーディング。複勝回収率つき。",
                     "db/jra/", body, ("/db/", "データベース")))
    print("  /db/jra/  入口")

    # ★check_stale.py対策★ サブディレクトリ配下を上書きしただけだとOUTBASEの
    #   mtimeが更新されず「古い」と誤検知し続ける（gen_ai_detail_pages.pyと同じ理由）。
    os.utime(OUTBASE, None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
