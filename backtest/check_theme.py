# -*- coding: utf-8 -*-
"""テーマ変数の壊れ方を検出する

★なぜ要るか★
  core/race.css が theme.css より後に読み込まれる位置で :root{--bg:...} を
  持っていたため、ライトを選んでいてもレース画面だけダークのままだった。
  さらに機械置換で --bg:var(--bg) という**循環定義**になり、背景が透明化して
  ヘッダと場タブが重なって見えた（本番で発生）。

  どちらも見た目を1回見ただけでは気づきにくい。機械で検出する。

検出するもの:
  1. --x: var(--x) の循環定義
  2. theme.css 以外での色変数の再定義（theme.css を上書きしてしまう）

対象外:
  旧ページ（kaiko / lab / scoring_explainer / anomaly / tweet / tweet2）は
  独立したアプリで、共通テーマに乗っていないため除外する。
  ★tweet2.htmlが漏れていた★（2026-07-24発覚）。tweet.htmlの🧪LTRデモ
  サンドボックスで同じ独立アプリのはずが、f.endswith("tweet.html")では
  "tweet2.html"にマッチせず素通りしていた。npm run check を新設した際に
  「NG」として拾われて発覚した。

使い方: python backtest/check_theme.py    終了コード 0=OK / 1=問題あり
"""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = ("kaiko.html", "lab.html", "scoring_explainer.html", "anomaly.html",
        "tweet.html", "tweet2.html", "theme.css")
VARS = "bg|panel|line|txt|mute|dim|green|red|yellow|blue|purple|orange"

RE_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
RE_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
RE_CIRCULAR = re.compile(r"--(\w+)\s*:\s*var\(--\1\)")
RE_REDEF = re.compile(r":root[^{]*\{[^}]*--(?:" + VARS + r")\s*:\s*#")


def strip_comments(s):
    """コメント内の記述は拾わない（説明文に --bg:var(--bg) と書くことがある）"""
    return RE_HTML_COMMENT.sub("", RE_BLOCK_COMMENT.sub("", s))


def main():
    targets = (glob.glob(os.path.join(ROOT, "deploy", "**", "*.html"), recursive=True)
               + glob.glob(os.path.join(ROOT, "core", "*.css"))
               + [os.path.join(ROOT, "php", "race.php")])
    bad = 0
    for f in sorted(targets):
        if any(f.endswith(x) for x in SKIP):
            continue
        s = strip_comments(open(f, encoding="utf-8", errors="replace").read())
        rel = os.path.relpath(f, ROOT)

        circ = sorted(set(RE_CIRCULAR.findall(s)))
        redef = RE_REDEF.findall(s)
        if circ or redef:
            bad += 1
            print("  [NG] " + rel)
            if circ:
                print("       循環定義: " + ", ".join(circ))
            if redef:
                print("       theme.css を上書きする色定義がある")
    if bad:
        print("")
        print("!! " + str(bad) + "ファイルに問題がある。色は core/theme.css だけで持つこと。")
        return 1
    print("テーマ変数に問題なし。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
