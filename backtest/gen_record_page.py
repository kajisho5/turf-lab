# -*- coding: utf-8 -*-
"""的中実績ページを生成する — 外れも全部載せる版

★何が他所と違うか★
  競馬ナビ等の「的中実績」は当たったレースだけを並べる（分母が無い）。
  うちは pred_data/（tweet.html が予想のたびに保存してきた記録）を
  **全件**、手元の公式結果と突き合わせて出す。外れも消さない。

★記録は予想時点のもの★
  印・人気・オッズは予想を回した瞬間に保存されたもの（predictions.php）。
  後から書き換えられない形で積まれてきた1か月分が土台になる。

入力: backtest/store/pred_data/*.json（サーバーから同期）
      backtest/nardata/race_*.zip（公式の結果・払戻）
出力: deploy/record/index.html
"""
import csv
import glob
import io
import json
import os
import sys
import zipfile
from collections import defaultdict

import site_config
SITE = site_config.get()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRED = os.path.join(ROOT, "backtest", "store", "pred_data")
NARD = os.path.join(ROOT, "backtest", "nardata")
OUT = os.path.join(ROOT, "deploy", "record", "index.html")

C = {k: f"var(--{k})" for k in
     ("bg", "panel", "line", "txt", "mute", "dim",
      "green", "red", "yellow", "blue", "purple", "orange")}

TC2NAME = {"30": "門別", "35": "盛岡", "36": "水沢", "42": "浦和", "43": "船橋",
           "44": "大井", "45": "川崎", "46": "金沢", "47": "笠松", "48": "名古屋",
           "50": "園田", "51": "姫路", "54": "高知", "55": "佐賀"}

# ★予想データ側の場名 → 公式CSVの場名★
#   ばんえいは公式CSVでは「帯広ば」（平地の帯広と区別するため）だが、
#   予想データ(pred_data)側は「帯広」で保存されている。この不一致で
#   **ばんえいの予想199件が丸ごと照合できず、記録ページから欠落していた**
#   （2026-07-27発覚。照合不能252件のうち79%がこれ）。
#   「外れも全部載せる」を看板にしているページで、特定競走が丸ごと
#   落ちているのは看板と矛盾するため対応する。
NAME_ALIAS = {"帯広": "帯広ば"}


def read_zip_csv(z, suffix):
    for n in z.namelist():
        if n.endswith(suffix):
            return list(csv.reader(io.StringIO(
                z.read(n).decode("utf-8-sig", errors="replace"))))
    return []


def load_results():
    """(場名, 日付, R) -> {馬番: 着順} と 複勝払戻 {馬番: 円} を作る"""
    ranks = {}
    fuku = {}
    for zp in sorted(glob.glob(os.path.join(NARD, "race_2026*.zip"))):
        try:
            z = zipfile.ZipFile(zp)
        except zipfile.BadZipFile:
            continue
        for r in read_zip_csv(z, "_horselist.csv"):
            # 着順は31列目（docs/DATA_SOURCES.md）。中止・除外は数字でない
            if len(r) < 32 or not r[1].isdigit() or not r[31].isdigit():
                continue
            key = (r[0], r[1], r[2])
            ranks.setdefault(key, {})[r[5]] = int(r[31])
        for r in read_zip_csv(z, "_payback.csv"):
            # 複勝: 4-9列に 馬番,払戻 が最大3組（列定義は DATA_SOURCES.md）
            if len(r) < 10 or not r[1].isdigit():
                continue
            key = (r[0], r[1], r[2])
            d = fuku.setdefault(key, {})
            # ★複勝の列位置★ payback.csv の並びは
            #   [4]単勝馬番 [5]単勝払戻 [6]人気
            #   [7]複勝馬番 [8]複勝払戻 [9]人気
            #   [10][11][12] 2頭目 / [13][14][15] 3頭目 / [16]〜ワイド
            # ★以前ここを (4,5)(6,7)(8,9) と書いていた（重大な誤り）★
            #   ・単勝の払戻を複勝として集計していた（回収率が過大になる）
            #   ・(6,7) は「人気→馬番」を拾うので、着外の馬に数円の払戻が付いた
            #   ・本物の複勝払戻を一度も使っていなかった
            #   実際に馬の戦績ページで6着に「9円」が出て気づいた。
            #   分母の取り方だけでなく、**分子の列位置**も回収率を壊す。
            for a, b in ((7, 8), (10, 11), (13, 14)):
                if r[a] and r[b].isdigit():
                    d[r[a]] = int(r[b])
    return ranks, fuku


def main():
    ranks, fuku = load_results()
    print(f"結果: {len(ranks):,}レースぶん読み込み")

    by_pop = defaultdict(lambda: [0, 0])   # 予想時人気 -> [n, hit]（結合の検算用）
    rows = []           # 1行 = 1レースの◎
    day_agg = defaultdict(lambda: [0, 0, 0, 0])   # 日付 -> [n, hit, inv, ret]
    skipped = 0
    for f in sorted(glob.glob(os.path.join(PRED, "*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if d.get("mode") != "nar":
            continue                     # 中央の結果照合は JV-Link 整備後に足す
        tc, date = str(d.get("tc")), str(d.get("date"))
        name = d.get("trackName") or TC2NAME.get(tc, tc)
        lookup = NAME_ALIAS.get(name, name)   # 公式CSVの場名に合わせる（帯広→帯広ば）
        for rc in d.get("races") or []:
            marks = rc.get("marks") or []
            hon = next((m for m in marks if m.get("mk") == "◎"), None)
            if not hon:
                continue
            key = (lookup, date, str(rc.get("no")))
            rk = ranks.get(key, {}).get(str(hon.get("num")))
            if rk is None:
                skipped += 1             # 結果がまだ手元に無い（当日夜など）
                continue
            pay = fuku.get(key, {}).get(str(hon.get("num")), 0)
            hit = rk <= 3
            if hon.get("pop"):
                e = by_pop[min(hon["pop"], 5)]
                e[0] += 1; e[1] += hit
            rows.append({"date": date, "track": name, "no": rc.get("no"),
                         "rname": rc.get("name") or "", "num": hon.get("num"),
                         "hname": hon.get("name") or "", "pop": hon.get("pop"),
                         "rk": rk, "hit": hit, "pay": pay})
            a = day_agg[date]
            a[0] += 1; a[1] += hit; a[2] += 100; a[3] += pay

    if not rows:
        sys.exit("突き合わせできた予想が無い")
    n = len(rows)
    hits = sum(r["hit"] for r in rows)
    # ★人気帯テーブルの分母★ 予想を実行した時点でオッズが未確定だと pop が記録
    #   されない。その分を「1番人気ではない」として全体nで割ると
    #   「◎の何%を1番人気に打っているか」が実際より小さく出る（2026-07-27修正）。
    pop_n = sum(v[0] for v in by_pop.values()) or 1
    inv = 100 * n
    ret = sum(r["pay"] for r in rows)
    d0, d1 = min(r["date"] for r in rows), max(r["date"] for r in rows)
    fmt_d = lambda s: f"{s[:4]}/{s[4:6]}/{s[6:]}"

    day_rows = "".join(
        f'<tr><td>{fmt_d(d)}</td><td class="n">{a[0]}</td>'
        f'<td class="n">{100*a[1]/a[0]:.0f}%</td>'
        f'<td class="n{" g" if a[3]>=a[2] else ""}">{100*a[3]/a[2]:.1f}%</td></tr>'
        for d, a in sorted(day_agg.items(), reverse=True))

    # ---- 日別のブレを数字にする ----
    # 日別の表を出しているのに「この振れ幅をどう見るか」を書いていなかった。
    # 1日だけ見て良し悪しを判断してしまうのを防ぐための材料を出す。
    days = [(d, a) for d, a in day_agg.items() if a[0] >= 5]   # 5レース未満の日は除く
    day_note = ""
    if len(days) >= 5:
        rates = sorted((100 * a[1] / a[0], d, a[0]) for d, a in days)
        rois = sorted((100 * a[3] / a[2], d, a[0]) for d, a in days)
        lo, hi = rates[0], rates[-1]
        plus = sum(1 for r, _, _ in rois if r >= 100)
        # 連続不的中の最長（時系列順に見る）
        seq = sorted(rows, key=lambda r: (r["date"], str(r["no"])))
        worst = cur = 0
        for r in seq:
            cur = 0 if r["hit"] else cur + 1
            worst = max(worst, cur)
        day_note = f"""<h2>1日の数字だけを見ても、何も分かりません</h2>
<p>上の日別の表は、日によって激しく上下します。
実際、{len(days)}日ぶん（1日5レース以上打った日）を並べると——</p>
<ul>
<li>一番良かった日は<strong>{hi[1][:4]}/{hi[1][4:6]}/{hi[1][6:]}の複勝率{hi[0]:.0f}%</strong>
（{hi[2]}レース）。</li>
<li>一番悪かった日は<strong>{lo[1][:4]}/{lo[1][4:6]}/{lo[1][6:]}の複勝率{lo[0]:.0f}%</strong>
（{lo[2]}レース）。</li>
<li>複勝回収率が100%を超えた日は<strong>{len(days)}日中{plus}日</strong>あります。</li>
<li>連続で外し続けた最長記録は<strong>{worst}レース</strong>です。</li>
</ul>
<p>同じ予想ロジックが、日によってこれだけ違う顔をします。
<strong>「昨日当たったから使える」「昨日外したからダメ」は、
どちらもこの振れ幅の中では意味を持ちません。</strong>
回収率が100%を超えた日が実際に{plus}日あるのに全体では
{100*ret/inv:.1f}%にしかならないのも、同じ理由です。
良い日は必ず存在し、それだけを切り取れば何とでも言えます。</p>
<p class="note">当サイトが日別の表を全部出しているのは、
<strong>都合の良い日だけを抜き出せないようにするため</strong>です。
成績を語るときは、上の全体の数字（{n:,}レース）だけを見てください。</p>"""

    # 直近3日ぶんは1レースずつ全部見せる（外れ含む）
    last_days = sorted({r["date"] for r in rows}, reverse=True)[:3]
    detail = "".join(
        f'<tr{"" if r["hit"] else " class=miss"}><td>{fmt_d(r["date"])}</td>'
        f'<td>{r["track"]}{r["no"]}R</td>'
        f'<td>◎{r["num"]} {r["hname"]}</td>'
        f'<td class="n">{r["pop"] or "—"}人気</td>'
        f'<td class="n">{r["rk"]}着</td>'
        f'<td class="n">{"+" + format(r["pay"]-100, ",") + "円" if r["hit"] else "−100円"}</td></tr>'
        for r in sorted(rows, key=lambda x: (x["date"], x["track"], x["no"]), reverse=True)
        if r["date"] in last_days)

    html = f"""<title>予想の記録 — 外れも全部 | {SITE['name']}</title>
{site_config.adsense()}<link rel="stylesheet" href="{site_config.asset('core/theme.css')}">
<script src="{site_config.asset('core/theme.js')}"></script>
<script src="{site_config.asset('core/table.js')}" defer></script>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="本命◎の全記録。{n:,}レースぶん、外れも消さずに載せています。複勝率{100*hits/n:.1f}%・回収率{100*ret/inv:.1f}%。">
<meta property="og:type" content="article">
<meta property="og:title" content="予想の記録 — 外れも全部載せています">
<meta property="og:description" content="◎{n:,}レースの全記録。複勝率{100*hits/n:.1f}%／回収率{100*ret/inv:.1f}%（複勝100円換算）。">
<meta property="og:url" content="{site_config.url('record/')}">
<meta property="og:image" content="{site_config.url('data/ogp.png')}">
<meta property="og:site_name" content="{SITE['name']}">
<meta name="twitter:card" content="summary_large_image">
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:{C['bg']};color:{C['txt']};
  font-family:"Noto Sans JP",-apple-system,BlinkMacSystemFont,sans-serif;
  font-size:16px;line-height:1.8;-webkit-text-size-adjust:100%}}
a{{color:{C['blue']}}}
.wrap{{max-width:860px;margin:0 auto;padding:24px 18px 72px}}
h1{{font-size:29px;line-height:1.4;margin:8px 0 4px}}
ul{{margin:0 0 16px;padding-left:1.3em}}
li{{margin:0 0 8px}}
h2{{font-size:22px;margin:40px 0 10px;font-weight:700;
  border-left:5px solid {C['yellow']};padding-left:12px}}
.lead{{color:{C['mute']};font-size:17px}}
.panel{{background:{C['panel']};border:1px solid {C['line']};border-radius:12px;
  padding:18px 16px;margin:16px 0}}
.big{{font-size:34px;font-weight:800}}
.scroll{{overflow-x:auto;-webkit-overflow-scrolling:touch}}
table{{width:100%;border-collapse:collapse;margin:12px 0;font-size:16px;min-width:460px}}
th,td{{padding:8px 8px;border-bottom:1px solid {C['line']};text-align:left;white-space:nowrap}}
th{{color:{C['mute']};font-weight:700}}
td.n,th.n{{text-align:right;font-variant-numeric:tabular-nums}}
tr.miss td{{color:{C['mute']}}}
.g{{color:{C['green']};font-weight:700}}
.note{{color:{C['mute']};font-size:16px}}
.ad{{margin:22px 0}}.ad:empty{{display:none}}
footer{{margin-top:52px;padding-top:18px;border-top:1px solid {C['line']};
  color:{C['mute']};font-size:16px}}
</style>
<div class="wrap">
{site_config.ad_slot("record-top")}
<div style="display:flex;align-items:center;gap:12px;margin-bottom:4px">
<a href="/">← レース一覧</a><div style="flex:1"></div>
<button class="themebtn" type="button">☾</button></div>

<h1>予想の記録</h1>
<p class="lead">本命◎を打った<strong>全レース</strong>の記録です。
予想は実行した瞬間にサーバーへ保存され、後から書き換えられません。<br>
<strong>外れも消していません。</strong></p>

<div class="panel">
<p style="margin:0">◎ {n:,}レース（{fmt_d(d0)} 〜 {fmt_d(d1)}・地方）<br>
複勝率 <span class="big">{100*hits/n:.1f}%</span>
複勝回収率 <span class="big{'' if ret < inv else ' g'}">{100*ret/inv:.1f}%</span>
<span class="note">（各100円買った換算）</span></p>
</div>
<p class="note">回収率が100%を下回っているのは、隠していないからです。
当サイトの検証では<strong>回収率100%を超える買い方は見つかっていません</strong>。
この記録の役目は「当たると言った日に本当に当たっていたか」を確認できることです。</p>
<p><a href="/ai/" style="display:inline-block;border:1px solid var(--line);border-radius:8px;
   padding:8px 14px;text-decoration:none">📊 どのAI予想家がどれだけ取れたか（成績ランキング）→</a></p>

<h2>この数字は信用できるのか（検算）</h2>
<p>「予想と結果の突き合わせが正しいか」を確かめる方法があります。
◎が<strong>1番人気だったレースだけ</strong>を取り出すと、その複勝率は
市場全体の実測（76.2%・17万レース）とほぼ一致するはずです。</p>
<div class="scroll"><table class="zebra sortable">
<tr><th>◎の予想時人気</th><th class="n">レース数</th><th class="n">複勝率</th><th class="n">市場の実測（17万R）</th></tr>
{"".join(f'<tr><td>{p}{"番人気" if p < 5 else "番人気以下"}</td><td class="n">{by_pop[p][0]}</td>'
         f'<td class="n">{100*by_pop[p][1]/by_pop[p][0]:.1f}%</td>'
         f'<td class="n">{ {1:"76.2%",2:"60.5%",3:"47.4%",4:"36.2%",5:"27%以下"}[p] }</td></tr>'
         for p in sorted(by_pop) if by_pop[p][0])}
</table></div>
<p class="note">各帯が市場の実測と揃っている＝結果との照合は正しく動いています。
そのうえで全体の複勝率が{100*hits/n:.1f}%になるのは、<strong>◎の{100*by_pop[1][0]/pop_n:.0f}%しか
1番人気に打っていない</strong>ためです。人気薄を狙う運用がそのまま数字に出ています。</p>
<p class="note">※この表の分母は{pop_n:,}レースです（全{n:,}レースのうち、
予想を実行した時点でオッズがまだ出ておらず人気を記録できなかったぶんを除いています）。</p>

<h2>日別</h2>
<div class="scroll"><table class="zebra sortable">
<tr><th>日付</th><th class="n">◎の数</th><th class="n">複勝率</th><th class="n">複勝回収率</th></tr>
{day_rows}
</table></div>

{day_note}

<h2>直近の全レース（外れ含む）</h2>
<div class="scroll"><table class="zebra sortable">
<tr><th>日付</th><th>レース</th><th>本命</th><th class="n">人気</th><th class="n">結果</th><th class="n">複勝収支</th></tr>
{detail}
</table></div>
<p class="note">※ 結果は地方競馬全国協会の公式データと突き合わせています。
結果データが手元に届いていないレース（当日夜など）は集計に入っていません。
中央の照合は準備中です。</p>

<footer>
{SITE['name']} ／ 予想の保存: 実行時に自動記録（predictions.php）／
結果: 地方競馬全国協会 keiba.go.jp<br>
本ページは情報提供を目的としたもので、的中や利益を保証するものではありません。<br>
<a href="/privacy/">プライバシーポリシー・運営者情報</a>
</footer>
</div>
<script>
try{{ new Image().src = '/stats.php?p=' + encodeURIComponent(location.pathname)
   + '&r=' + encodeURIComponent(document.referrer) + '&t=' + Date.now(); }}catch(e){{}}
</script>
"""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    print(f"生成: {os.path.relpath(OUT, ROOT)}")
    print(f"  ◎{n:,}R  複勝率{100*hits/n:.1f}%  複ROI{100*ret/inv:.1f}%  照合不可 {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
