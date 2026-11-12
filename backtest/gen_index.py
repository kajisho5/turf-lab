# -*- coding: utf-8 -*-
"""/odds/ の入口ページを生成する

背景:
  旧 index.html は「ODDS ANOMALY」という別ツールが置きっぱなしで、
  jusho.html / news.html / help.html など**存在しないページへのリンク**を
  4本抱えたまま放置されていた（サーバー上に実体なし＝404）。
  データページを作っても、そこへ辿り着く導線が無かった。

  旧ツールは消さずに /odds/anomaly.html として残し、ここからも辿れるようにする。

方針は他と同じ: **数字は手書きしない**。jra_nar_compare.json から取る。
"""
import json, os, sys

import site_config
SITE = site_config.get()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "backtest", "jra_nar_compare.json")
OUT = os.path.join(ROOT, "deploy", "about", "index.html")

# 色は CSS 変数を参照する。実体は core/theme.css（backtest/theme.py が生成）。
# ★ここで16進を持たない★ ライト/ダークの2系統になったので、
#   各ファイルが色を持つと必ずズレる。コントラスト検証も theme.py に集約した。
C = {k: f"var(--{k})" for k in
     ("bg", "panel", "line", "txt", "mute", "dim",
      "green", "red", "yellow", "blue", "purple", "orange")}


def main():
    d = json.load(open(SRC, encoding="utf-8"))
    nar, jra = d["nar"], d["jra"]
    total = nar["races"] + jra["races"]
    n1, j1 = nar["pop"]["1"], jra["pop"]["1"]

    html = f"""<title>このサイトについて — {SITE['name']}</title>
{site_config.adsense()}<link rel="stylesheet" href="{site_config.asset('core/theme.css')}">
<script src="{site_config.asset('core/theme.js')}"></script>
<script src="{site_config.asset('core/table.js')}" defer></script>
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="地方{nar['races']:,}レース・中央{jra['races']:,}レースの実測から、競馬を数字で見るサイト。予想を売るのではなく、検証結果をそのまま公開しています。">
<meta property="og:type" content="website">
<meta property="og:title" content="{SITE['name']} — データで見る競馬">
<meta property="og:description" content="{total:,}レースの実測。効かなかった検証も公開しています。">
<meta property="og:url" content="{site_config.url('about/')}">
<meta property="og:image" content="{site_config.url('data/ogp.png')}">
<meta property="og:site_name" content="{SITE['name']}">
<meta name="twitter:card" content="summary_large_image">
<style>
:root{{color-scheme:dark}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--txt);
  font-family:"Noto Sans JP",-apple-system,BlinkMacSystemFont,sans-serif;
  font-size:16px;line-height:1.75;-webkit-text-size-adjust:100%}}
.wrap{{max-width:820px;margin:0 auto;padding:32px 18px 72px}}
h1{{font-size:34px;line-height:1.35;margin:6px 0 6px;font-weight:700;letter-spacing:.01em}}
h2{{font-size:22px;line-height:1.4;margin:44px 0 6px;font-weight:700;
  border-left:5px solid var(--yellow);padding-left:12px}}
p{{margin:10px 0}}
.lead{{color:var(--mute);font-size:17px}}
.card{{display:block;background:var(--panel);border:1px solid var(--line);
  border-radius:14px;padding:20px 18px;margin:14px 0;text-decoration:none;color:inherit}}
.card:hover,.card:focus{{border-color:var(--yellow)}}
.card .t{{font-size:20px;font-weight:700;line-height:1.4}}
.card .d{{color:var(--mute);margin-top:6px}}
.card .k{{color:var(--yellow);font-size:16px;font-weight:700}}
.stat{{display:flex;flex-wrap:wrap;gap:10px;margin-top:14px}}
.stat div{{background:var(--bg);border:1px solid var(--line);border-radius:10px;
  padding:8px 12px;font-size:16px;color:var(--mute)}}
.stat b{{color:var(--txt);font-size:19px;font-variant-numeric:tabular-nums}}
.mini{{color:var(--mute);font-size:16px}}
.mini .ad{{margin:22px 0}}
.ad:empty{{display:none}}
a{{color:var(--blue)}}
footer{{margin-top:56px;padding-top:18px;border-top:1px solid var(--line);
  color:var(--mute);font-size:16px}}
a{{color:var(--blue)}}
</style>
<div class="wrap">

<p><a href="/">← レース一覧</a></p>
<div style="display:flex;align-items:center;gap:12px;margin-bottom:4px"><div style="flex:1"></div><button class="themebtn" type="button">☾</button></div>
<h1>このサイトについて</h1>
<p class="lead">競馬を、数字で見るためのサイトです。<br>
地方 <strong>{nar['races']:,}レース</strong>／中央 <strong>{jra['races']:,}レース</strong>、
あわせて<strong>{total:,}レース</strong>の公式データを集計しています。</p>
<p class="lead">予想を売る場所ではありません。<strong>効かなかった検証も、そのまま公開します。</strong></p>

{site_config.ad_slot("index-top")}
<h2>データで読む</h2>

<a class="card" href="/data/">
  <div class="k">地方競馬 {nar['races']:,}レース</div>
  <div class="t">AI予想は、市場に勝てるのか</div>
  <div class="d">券種ごとの「壁」、人気薄が割高である証拠、
  そして自分のモデルが「1番人気を買うだけ」に負けているという話。
  試して駄目だったことも6件載せています。</div>
  <div class="stat">
    <div>1番人気の複勝ROI <b>{n1['fuku_roi']:.1f}%</b></div>
    <div>12番人気 <b>{nar['pop']['12']['fuku_roi']:.1f}%</b></div>
  </div>
</a>

<a class="card" href="/data/jra/">
  <div class="k">中央 {jra['races']:,}R × 地方 {nar['races']:,}R</div>
  <div class="t">「荒れやすいのは地方」は本当か</div>
  <div class="d">中央と地方を同じ計算式に通して並べました。
  1番人気の信頼度、公表されている払戻率と実際に失う額がずれる理由。</div>
  <div class="stat">
    <div>1番人気の勝率　地方 <b>{n1['win']:.1f}%</b></div>
    <div>中央 <b>{j1['win']:.1f}%</b></div>
  </div>
</a>

<h2>今日のレース</h2>

<a class="card" href="/data/debut/">
  <div class="k">高知ファイナル</div>
  <div class="t">今日の高知12Rを自動で取得</div>
  <div class="d">開くだけで、その日の高知ファイナルの出馬表と買い目候補を表示します。</div>
</a>

<h2>このサイトの立場</h2>
<p>回収率100%を超える買い方は、<strong>まだ見つかっていません</strong>。
43通りの戦略と条件別の総当たりを試して、天井は92.2%でした。
見つかっていないことを「見つかった」と書かないために、
このサイトの数字は<strong>全て計算で埋めていて、手入力は一つもありません</strong>。</p>
<p>回収率は必ず「買った全レースを分母」にしています。
的中したレースだけを分母にすると、回収率は簡単に水増しできるためです。</p>

<h2>その他</h2>
<p class="mini">
<a href="anomaly.html">ODDS ANOMALY（旧・異常オッズ検知ツール）</a><br>
<a href="scoring_explainer.html">スコアの付け方について</a><br>
<a href="kaiko.html">回顧・実績</a>
</p>

<footer>
{SITE['name']} ／ データ出典: 地方＝地方競馬全国協会 keiba.go.jp、中央＝JRA-VAN Data Lab.<br>
本サイトは情報提供を目的としたもので、的中や利益を保証するものではありません。<br>
<a href="/privacy/">プライバシーポリシー・運営者情報</a>
</footer>
</div>
<script>
/* アクセス計測（Cookieなし・自前）。失敗しても本体に影響させない */
try{{ new Image().src = '/stats.php?p=' + encodeURIComponent(location.pathname)
   + '&r=' + encodeURIComponent(document.referrer) + '&t=' + Date.now(); }}catch(e){{}}
</script>
"""


    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    print(f"\n生成: {os.path.relpath(OUT, ROOT)}  ({len(html.encode('utf-8'))//1024}KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
