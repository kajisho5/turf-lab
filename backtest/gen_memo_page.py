# -*- coding: utf-8 -*-
"""検証メモ（短文）の一覧ページを生成する

★なぜ作るか★
  既存の /data/ 配下には長文の検証ページが27本あるが、どれも「腰を据えて
  読む」ものしか無い。参考にした南関系の情報サイトは、1日に10本前後の
  短い投稿（データ・豆知識・小ネタ）を出し続けてサイトが生きている状態を
  作っていた。うちに足りないのはまさにそれ。

  そして**うちには在庫がある**。docs/SCORING_AUDIT.md に137節、
  docs/FACTS.md に55見出し。1本1本は小さいが「効かなかった検証」は
  他所が絶対に書けない在庫なので、短文の形で出す装置を用意する。

★中身は必ず人がキュレーションする★
  markdownから自動抽出すると文脈が壊れる（数字だけ拾って主語を落とす等）。
  memo_data.json に人が書いた短文を置き、このスクリプトは整形だけ行う。
  1件 = 1つの検証済み事実。出典とサンプル数を必ず持たせる。

入力: backtest/memo_data.json
出力: deploy/data/memo/index.html
使い方: python backtest/gen_memo_page.py
"""
import html
import json
import os
import sys
from collections import Counter

import site_config
SITE = site_config.get()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "backtest", "memo_data.json")
OUT = os.path.join(ROOT, "deploy", "data", "memo", "index.html")

C = {k: f"var(--{k})" for k in
     ("bg", "panel", "line", "txt", "mute", "dim",
      "green", "red", "yellow", "blue", "purple", "orange")}

# カテゴリ -> 色。「効かない」を赤系にしないのは、否定的結果は失敗ではなく
# こちらの主力コンテンツだから（BUSINESS.md の「唯一の堀」）。
CAT_COLOR = {
    "検証結果": C["green"],
    "効かない": C["blue"],
    "バグと訂正": C["orange"],
    "数字の見方": C["purple"],
}


def esc(s):
    return html.escape(str(s or ""))


def main():
    data = json.load(open(SRC, encoding="utf-8"))
    items = sorted(data["items"], key=lambda x: x["d"], reverse=True)
    cats = Counter(i["cat"] for i in items)

    chips = "".join(
        f'<button class="cchip" data-c="{esc(c)}" '
        f'style="border-color:{CAT_COLOR.get(c, C["line"])};color:{CAT_COLOR.get(c, C["txt"])}">'
        f'{esc(c)} <b>{n}</b></button>'
        for c, n in cats.most_common())

    cards = "".join(f"""
<article class="memo" data-c="{esc(it['cat'])}">
  <div class="mhead">
    <span class="cat" style="background:{CAT_COLOR.get(it['cat'], C['line'])}22;
      color:{CAT_COLOR.get(it['cat'], C['txt'])};
      border:1px solid {CAT_COLOR.get(it['cat'], C['line'])}66">{esc(it['cat'])}</span>
    <time>{esc(it['d'])}</time>
  </div>
  <h2>{esc(it['t'])}</h2>
  <p>{esc(it['b'])}</p>
  <p class="src">検証した規模: {esc(it['s'])}</p>
</article>""" for it in items)

    html_doc = f"""<title>検証メモ — 短く、全部出す | {SITE['name']}</title>
{site_config.adsense()}<link rel="stylesheet" href="{site_config.asset('core/theme.css')}">
<script src="{site_config.asset('core/theme.js')}"></script>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="{SITE['name']}の検証メモ。効いた因子も、効かなかった因子も、見つけたバグも短く全部出します。数字は必ずサンプル数つき。">
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:{C['bg']};color:{C['txt']};
  font-family:"Noto Sans JP",-apple-system,BlinkMacSystemFont,sans-serif;
  font-size:16px;line-height:1.8;-webkit-text-size-adjust:100%}}
a{{color:{C['blue']}}}
.wrap{{max-width:820px;margin:0 auto;padding:24px 18px 72px}}
h1{{font-size:28px;line-height:1.4;margin:8px 0 6px}}
.lead{{color:{C['mute']};margin:0 0 20px}}
.chips{{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 22px}}
.cchip{{background:transparent;border:1px solid {C['line']};border-radius:999px;
  padding:6px 14px;font-size:14px;font-weight:700;cursor:pointer;
  font-family:inherit;line-height:1.5}}
.cchip.off{{opacity:.35}}
.cchip b{{font-weight:800;margin-left:2px}}
.memo{{background:{C['panel']};border:1px solid {C['line']};border-radius:14px;
  padding:16px 18px;margin:0 0 14px}}
.memo.hide{{display:none}}
.mhead{{display:flex;align-items:center;gap:10px;margin-bottom:6px}}
.cat{{font-size:14px;font-weight:800;padding:2px 10px;border-radius:999px}}
.mhead time{{color:{C['mute']};font-size:14px;font-family:"Space Mono",monospace}}
.memo h2{{font-size:19px;line-height:1.5;margin:2px 0 8px}}
.memo p{{margin:0 0 6px}}
.src{{color:{C['mute']};font-size:14px}}
footer{{margin-top:52px;padding-top:18px;border-top:1px solid {C['line']};
  color:{C['mute']};font-size:15px}}
</style>
<div class="wrap">
<div style="display:flex;align-items:center;gap:12px;margin-bottom:4px">
<a href="/">← レース一覧</a><div style="flex:1"></div>
<button class="themebtn" type="button">☾</button></div>

<h1>検証メモ</h1>
<p class="lead">効いた因子も、<strong>効かなかった因子</strong>も、見つけたバグも短く出します。
数字は必ず「どれだけの規模で測ったか」つき。長い版は<a href="/articles/">記事一覧</a>にあります。</p>

<div class="chips">{chips}</div>
{cards}

<footer>
{SITE['name']}<br>
<a href="/">レース一覧</a> ／ <a href="/articles/">記事一覧</a> ／
<a href="/record/">予想の記録</a> ／ <a href="/about/">このサイトについて</a>
</footer>
</div>
<script>
/* カテゴリの絞り込み。押した分だけ残す（全部offなら全部出す） */
(function(){{
  var chips=[].slice.call(document.querySelectorAll('.cchip'));
  var cards=[].slice.call(document.querySelectorAll('.memo'));
  function apply(){{
    var on=chips.filter(function(c){{return !c.classList.contains('off');}})
                .map(function(c){{return c.dataset.c;}});
    var all=on.length===0||on.length===chips.length;
    cards.forEach(function(k){{
      k.classList.toggle('hide', !all && on.indexOf(k.dataset.c)<0);
    }});
  }}
  chips.forEach(function(c){{
    c.onclick=function(){{ c.classList.toggle('off'); apply(); }};
  }});
}})();
/* アクセス計測（Cookieなし・自前）。失敗しても本体に影響させない */
try{{ new Image().src = '/stats.php?p=' + encodeURIComponent(location.pathname)
   + '&r=' + encodeURIComponent(document.referrer) + '&t=' + Date.now(); }}catch(e){{}}
</script>
"""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(html_doc)
    print(f"生成: {os.path.relpath(OUT, ROOT)}  {len(items)}件 "
          f"({' / '.join(f'{c}{n}' for c, n in cats.most_common())})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
