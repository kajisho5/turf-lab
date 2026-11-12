# -*- coding: utf-8 -*-
"""データベース（リーディング）ページを生成する

/db/          入口
/db/jockey/   騎手リーディング
/db/trainer/  調教師リーディング
/db/sire/     種牡馬リーディング
/db/damsire/  母父リーディング

★他所のリーディングとの違い★
  勝利数だけでなく**複勝回収率まで**出す。「勝つ騎手」と「買って得な騎手」は
  別物で、それが分かるのはROIを出しているサイトだけ。
  いつも通り: 分母は全騎乗、件数不足は載せない、数値は手書きしない。

入力: backtest/nardata/bt_all.jsonl + backtest/nardata/aux/YYYYMM.json
出力: deploy/db/{index,jockey,trainer,sire,damsire}/index.html
"""
import json
import os
from urllib.parse import quote
import sys
from collections import defaultdict

import site_config
SITE = site_config.get()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "backtest", "nardata", "bt_all.jsonl")
AUX = os.path.join(ROOT, "backtest", "nardata", "aux")
OUTBASE = os.path.join(ROOT, "deploy", "db")

C = {k: f"var(--{k})" for k in
     ("bg", "panel", "line", "txt", "mute", "dim",
      "green", "red", "yellow", "blue", "purple", "orange")}

RECENT = "20250101"        # 「直近」の区切り。動かすときはページの説明も直すこと
MIN_ALL = 500              # 通算でこの騎乗数未満は載せない（率が暴れるため）
MIN_RECENT = 100
TOP = 100

KINDS = [
    ("jockey", 0, "騎手", "騎乗"),
    ("trainer", 1, "調教師", "出走"),
    ("sire", 2, "種牡馬", "産駒出走"),
    ("damsire", 3, "母父", "出走"),
]


def collect():
    # name -> [n, win, top3, ret] を通算と直近で
    agg = {k: (defaultdict(lambda: [0, 0, 0, 0]),
               defaultdict(lambda: [0, 0, 0, 0])) for k, *_ in KINDS}
    races = 0
    cur_ym, aux = None, {}
    with open(DATA, encoding="utf-8") as f:
        for line in f:
            rc = json.loads(line)
            ym = rc["d"][:6]
            if ym != cur_ym:
                cur_ym = ym
                p = os.path.join(AUX, f"{ym}.json")
                aux = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
            amap = aux.get(rc["rid"])
            if not amap:
                continue
            pay = rc.get("pay") or {}
            fuku = pay.get("fuku") or {}
            recent = rc["d"] >= RECENT
            races += 1
            for h in rc["h"]:
                if h.get("rk") is None:
                    continue
                a = amap.get(str(h["n"]))
                if not a:
                    continue
                ret = fuku.get(h["n"], 0)
                for kind, idx, _, _ in KINDS:
                    name = a[idx]
                    if not name:
                        continue
                    for seg, use in ((0, True), (1, recent)):
                        if not use:
                            continue
                        e = agg[kind][seg][name]
                        e[0] += 1
                        e[1] += (h["rk"] == 1)
                        e[2] += (h["rk"] <= 3)
                        e[3] += ret
    return agg, races


CSS = f"""*{{box-sizing:border-box}}
body{{margin:0;background:{C['bg']};color:{C['txt']};
  font-family:"Noto Sans JP",-apple-system,BlinkMacSystemFont,sans-serif;
  font-size:16px;line-height:1.8;-webkit-text-size-adjust:100%}}
a{{color:{C['blue']}}}
.wrap{{max-width:880px;margin:0 auto;padding:24px 18px 72px}}
h1{{font-size:29px;line-height:1.4;margin:8px 0 4px}}
h2{{font-size:22px;margin:40px 0 10px;font-weight:700;
  border-left:5px solid {C['yellow']};padding-left:12px}}
h3{{font-size:19px;margin:28px 0 6px;font-weight:700}}
p{{margin:0 0 14px}}
ul{{margin:0 0 16px;padding-left:1.3em}}
li{{margin:0 0 8px}}
.lead{{color:{C['mute']};font-size:17px}}
.scroll{{overflow-x:auto;-webkit-overflow-scrolling:touch}}
table{{width:100%;border-collapse:collapse;margin:12px 0;font-size:16px;min-width:560px}}
th,td{{padding:8px 8px;border-bottom:1px solid {C['line']};text-align:left;white-space:nowrap}}
th{{color:{C['mute']};font-weight:700}}
td.n,th.n{{text-align:right;font-variant-numeric:tabular-nums}}
.g{{color:{C['green']};font-weight:700}}
.note{{color:{C['mute']};font-size:16px}}
.card{{display:block;background:{C['panel']};border:1px solid {C['line']};
  border-radius:12px;padding:16px;margin:12px 0;text-decoration:none;color:inherit}}
.card:hover{{border-color:{C['yellow']}}}
.card b{{font-size:19px;display:block}}
.card span{{color:{C['mute']}}}
.ad{{margin:22px 0}}.ad:empty{{display:none}}
footer{{margin-top:52px;padding-top:18px;border-top:1px solid {C['line']};
  color:{C['mute']};font-size:16px}}
/* ★どのページからも他の入口へ行けるようにする★
   戻りリンク1本しか置いていなかったため、データベースの入口が
   自分自身を指して行き止まりになっていた（利用者から「戻れん」と指摘）。
   1段戻るだけでなく、常に全部の入口を出す。 */
.snav{{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 16px}}
.snav a{{border:1px solid var(--line);background:var(--panel);border-radius:999px;
  padding:4px 13px;text-decoration:none;color:var(--mute);font-size:15px}}
.snav a:hover{{border-color:var(--mute);color:var(--txt)}}
"""

BEACON = """<script>
try{ new Image().src = '/stats.php?p=' + encodeURIComponent(location.pathname)
   + '&r=' + encodeURIComponent(document.referrer) + '&t=' + Date.now(); }catch(e){}
</script>"""


def page(title, desc, path_, body, back=("/db/", "データベース")):
    """★戻り先はページごとに変える★
       全ページ一律で「← データベース」を出していたため、
       /db/ のトップが**自分自身へのリンク**になり、そこから戻れなくなっていた。
       戻り先を引数にして、入口ページはサイトのトップへ返す。"""
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
<meta property="og:site_name" content="{SITE['name']}">
<meta name="twitter:card" content="summary_large_image">
<style>{CSS}</style>
<div class="wrap">
<div style="display:flex;align-items:center;gap:12px;margin-bottom:4px">
<a href="{back[0]}">← {back[1]}</a><div style="flex:1"></div>
<button class="themebtn" type="button">☾</button></div>
<nav class="snav"><a href="/">レース一覧</a><a href="/ai/">AI予想家</a><a href="/record/">予想の記録</a><a href="/articles/">記事</a><a href="/db/">データベース</a><a href="/calendar/">重賞カレンダー</a></nav>
{body}
<footer>
{SITE['name']} ／ データ出典: 地方競馬全国協会 keiba.go.jp（公式データダウンロード）<br>
本ページは情報提供を目的としたもので、的中や利益を保証するものではありません。<br>
<a href="/privacy/">プライバシーポリシー・運営者情報</a>
</footer>
</div>
{BEACON}
"""


def leading_table(d, min_n, unit, kind=''):
    rows = [(name, e) for name, e in d.items() if e[0] >= min_n]
    rows.sort(key=lambda x: -x[1][1])
    out = []
    for i, (name, e) in enumerate(rows[:TOP], 1):
        n, win, top3, ret = e
        roi = 100 * ret / (100 * n)
        # ★名前は個別ページへのリンクにする★
        #   一覧だけ作って「データベースができた」としていたが、
        #   名前を押しても何も起きず「見れない」状態だった。
        link = (f'<a href="/db/jockey/detail/?name={quote(name)}">{name}</a>' if kind == 'jockey'
                else f'<a href="/db/trainer/detail/?name={quote(name)}">{name}</a>' if kind == 'trainer'
                else name)
        out.append(
            f'<tr><td class="n">{i}</td><td><strong>{link}</strong></td>'
            f'<td class="n">{win:,}</td><td class="n">{n:,}</td>'
            f'<td class="n">{100*win/n:.1f}%</td><td class="n">{100*top3/n:.1f}%</td>'
            f'<td class="n{" g" if roi >= 90 else ""}">{roi:.1f}%</td></tr>')
    header = (f'<tr><th class="n">順</th><th>名前</th><th class="n">勝利</th>'
              f'<th class="n">{unit}数</th><th class="n">勝率</th>'
              f'<th class="n">複勝率</th><th class="n">複勝回収率</th></tr>')
    return header + "".join(out), len(rows)


def insight(seg, min_n, unit, label, kind):
    """表そのものから読み取れることを、実測値を引いて文章にする。

    数字を手打ちすると集計を更新したときに嘘になるので、ここで毎回計算し直す。
    伝えたい中身は毎回同じ：「勝利数の順位」と「買って得な順位」は一致しない。
    """
    rows = [(name, e) for name, e in seg.items() if e[0] >= min_n]
    if len(rows) < 10:
        return ""
    by_win = sorted(rows, key=lambda x: -x[1][1])
    roi = lambda e: 100 * e[3] / (100 * e[0])                      # noqa: E731
    by_roi = sorted(rows, key=lambda x: -roi(x[1]))
    top_name, top_e = by_win[0]
    best_name, best_e = by_roi[0]
    over = sum(1 for _, e in rows if roi(e) >= 100)
    rois = sorted(roi(e) for _, e in rows)
    med = rois[len(rois) // 2]
    top_rank_in_roi = next(i for i, (n, _) in enumerate(by_roi, 1) if n == top_name)

    # 100%超がゼロのときは「0件だけ」では文にならない。
    # むしろ全員が控除率に負けたという、より強い事実なので言い方を変える。
    if over:
        over_line = (f'100%を超えているのは<strong>{over}件</strong>だけです'
                     f'（最高{rois[-1]:.1f}%）。')
        over_note = (f'複勝回収率が100%を超えた{over}件も、'
                     f'翌年そのまま再現する保証はどこにもありません。')
    else:
        over_line = (f'そして<strong>{len(rows):,}件すべてが100%を下回っています</strong>'
                     f'（最高でも{rois[-1]:.1f}%）。')
        over_note = ('この表には100%を超えた例がひとつもありません。'
                     'つまり「回収率の高い順に買う」という戦略自体が、'
                     'この単位では成立していないということです。')

    s = f"""<h2>この表から実際に何が読めるか</h2>
<p>順位は勝利数で並べています。まず見てほしいのは、
<strong>一番左の順位と、一番右の複勝回収率がまったく揃っていない</strong>ことです。</p>
<ul>
<li>勝利数1位は<strong>{top_name}</strong>（{top_e[1]:,}勝 / {top_e[0]:,}{unit}・
勝率{100*top_e[1]/top_e[0]:.1f}%）。ところが複勝回収率で並べ替えると
<strong>{top_rank_in_roi}位</strong>（{roi(top_e):.1f}%）まで下がります。</li>
<li>複勝回収率のトップは<strong>{best_name}</strong>の
<strong>{roi(best_e):.1f}%</strong>（{best_e[0]:,}{unit}・勝率{100*best_e[1]/best_e[0]:.1f}%）。
勝率で見れば上位ではありません。</li>
<li>掲載{len(rows):,}件の複勝回収率の中央値は<strong>{med:.1f}%</strong>。
{over_line}</li>
</ul>
<p>これは偶然ではなく、構造的にそうなります。
<strong>よく勝つ{label}は人気になり、人気になるとオッズが下がるからです。</strong>
勝率が高いことと、その馬券が儲かることは、市場が正しく評価している限り両立しません。
勝率の高さは実力の証明であって、買い目の理由にはならない——
この表が一番はっきり示しているのはそこです。</p>

<h3>じゃあ回収率の高い{label}を買えばいいのか</h3>
<p>それも違います。上位に来るのは<strong>{unit}数が基準ぎりぎりの層に偏りがち</strong>で、
高配当を1回引いただけで回収率は跳ね上がります。
{over_note}
このページで{unit}数を必ず併記しているのはそのためです。</p>
<p class="note">当サイトの予想では、{label}の成績を出走馬の評価材料に使っていますが、
<strong>「回収率が高いから買う」という使い方はしていません</strong>。
使っているのは勝率・複勝率のほう、つまり
「この馬がどれくらい上位に来そうか」を推定する材料としてです。
儲かるかどうかは、そのあとオッズと突き合わせて決める別の問題として扱っています。</p>"""
    return s


def main():
    print("集計中（17万レース × 178万頭を1パス）...", flush=True)
    agg, races = collect()

    for kind, idx, label, unit in KINDS:
        seg_all, seg_recent = agg[kind]
        t_recent, n_recent = leading_table(seg_recent, MIN_RECENT, unit, kind)
        t_all, n_all = leading_table(seg_all, MIN_ALL, unit, kind)
        body = f"""<h1>{label}リーディング</h1>
<p class="lead">地方競馬 {races:,}レース（2013年〜）の実測です。
勝利数だけでなく、<strong>買って得だったか（複勝回収率）</strong>まで出しています。</p>
{site_config.ad_slot(f"db-{kind}")}
<h2>直近（2025年以降・{unit}{MIN_RECENT}以上）</h2>
<div class="scroll"><table class="zebra sortable">{t_recent}</table></div>
<h2>通算（2013年〜・{unit}{MIN_ALL}以上）</h2>
<div class="scroll"><table class="zebra sortable">{t_all}</table></div>
<p class="note">※ {unit}数が基準に満たない場合は載せていません。
少ない数の率は大きく振れ、順位が偶然で入れ替わるためです。
複勝回収率は「全{unit}の複勝を100円ずつ買った」計算で、
<strong>ほぼ全員が100%を下回ります</strong>。それが控除率です。</p>
{insight(seg_all, MIN_ALL, unit, label, kind)}"""
        d = os.path.join(OUTBASE, kind)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "index.html"), "w", encoding="utf-8", newline="\n") as f:
            f.write(page(f"{label}リーディング（地方競馬）",
                         f"地方競馬{races:,}レースの実測。{label}別の勝率・複勝率・複勝回収率。",
                         f"db/{kind}/", body))
        print(f"  /db/{kind}/  直近{n_recent}人 / 通算{n_all}人")

    # 入口
    cards = ('<a class="card" href="/db/horse/"><b>馬検索</b>'
             '<span>馬名・父・母父・毛色・性別で絞り込み（直近3年・約2.8万頭）</span></a>')
    cards += "".join(
        f'<a class="card" href="/db/{kind}/"><b>{label}リーディング</b>'
        f'<span>勝利数・勝率・複勝率・複勝回収率</span></a>'
        for kind, _, label, _ in KINDS)
    cards += ('<a class="card" href="/db/combo/"><b>騎手×調教師コンビ成績</b>'
              '<span>「相性の良いコンビ」を勝率・複勝回収率で検証</span></a>')
    cards += ('<a class="card" href="/db/g1/"><b>重賞・準重賞ランキング</b>'
              '<span>通算成績ではなく、大レースに強いのは誰かだけを見る</span></a>')
    cards += ('<a class="card" href="/db/trainer-homeaway/"><b>厩舎の地元開催vs遠征</b>'
              '<span>「遠征厩舎は弱い」説を444厩舎ぶんで検証中</span></a>')
    body = f"""<h1>データベース</h1>
<p class="lead"><a href="/db/jra/">▶ 中央競馬のデータベースはこちら</a></p>
<p class="lead">地方競馬 {races:,}レース（2013年〜）を集計したリーディングです。<br>
どの表にも<strong>複勝回収率</strong>を付けています。
「勝つ{KINDS[0][2]}」と「買って得な{KINDS[0][2]}」は別物だからです。</p>
{cards}

<h2>なぜ勝利数だけのランキングを出さないのか</h2>
<p>リーディングは普通「勝利数」で並べます。それは正しいのですが、
<strong>勝利数の順位を見て馬券を買うと、たいてい損をします</strong>。
よく勝つ人は人気になり、人気になればオッズが下がるからです。
実力の証明と、買って得かどうかは、別の話です。</p>
<p>そこで当サイトの表には必ず<strong>複勝回収率</strong>を入れています。
「その人の関わった馬の複勝を、全レース100円ずつ買っていたら手元にいくら残ったか」
という数字です。並べ替えれば、勝利数の順位とまったく揃わないことがすぐ分かります。</p>

<h2>回収率の見方で、ひとつだけ約束していること</h2>
<p>回収率は<strong>買った全レースを分母</strong>にしています。
当たったレースだけを分母にすると、回収率はいくらでも大きく見せられます。
この分母の取り方の違いだけで「複勝で黒字」という誤った結論に一度たどり着いたことがあり、
それ以来ここは徹底しています。</p>
<p>もうひとつ、<strong>件数が少ない行は載せません</strong>。
数十回の成績では複勝率も回収率も偶然だけで大きく動き、
順位が意味を持たなくなるためです。各ページに最低件数を明記しています。</p>

<h2>このデータの出どころ</h2>
<p>地方競馬全国協会（keiba.go.jp）が公開している公式データを、
2013年以降ぶんダウンロードして自前で集計したものです。
スクレイピングではなく公式配布データを使っているので、
同じ手順を踏めば誰でも同じ数字にたどり着けます。
着順・払戻とも公式の確定値です。</p>
<p class="note">※ 地方競馬の公式データは仕様上、騎手名・調教師名が
3〜4文字に切り詰められています。同じ略称になる別人が
1人として集計されている可能性があり、これは元データの制約で解消できません。
名前は目安として見てください。</p>"""
    os.makedirs(OUTBASE, exist_ok=True)
    with open(os.path.join(OUTBASE, "index.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(page("データベース（地方競馬）",
                     f"騎手・調教師・種牡馬・母父のリーディング。地方競馬{races:,}レースの実測。",
                     "db/", body, back=("/", "レース一覧")))
    print("  /db/  入口")
    return 0


if __name__ == "__main__":
    sys.exit(main())
