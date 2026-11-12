# -*- coding: utf-8 -*-
"""★14px未満のフォント指定を検出する★（2026-08-04）

なぜ要るか（実際に起きた）:
  DADS_DESIGN.md は「本文・UIは16px以上、**14px未満は原則禁止**」と決めているのに、
  /ai/ には 11px・12px・12.5px・13px が18箇所あった。目視では気づけず、
  モバイル実機で全要素のcomputedStyleを測って初めて分かった。
  さらに <small> は既定で親の約0.83倍＝16px→13.3px になるため、
  **書いていなくても違反する**。これも機械で見張る。

検査対象: deploy/*.html と backtest/gen_*.py（生成側のCSS文字列）
使い方: python backtest/check_fontsize.py   （npm run check に組込み）
"""
import glob
import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 1〜13px（13.5px等の小数も含む）。14px以上は許容。
PAT = re.compile(r"font-size:\s*(1[0-3](?:\.\d+)?|[1-9](?:\.\d+)?)px")
# <small> に明示サイズが無いと13.3pxになる。ページ内に small を使うなら
# どこかで font-size を与えているべき（タグ/クラスどちらでもよい）。
SMALL_USE = re.compile(r"<small[\s>]")
SMALL_SIZE = re.compile(r"small\s*(?:\{|[^{]*\{)[^}]*font-size")


"""★baseline方式★（2026-08-04）
既存ページには 544箇所の違反が積み上がっている（tweet系169+166、anomaly144…）。
これを一度に機械置換するとcanvas描画やバッジのレイアウトが崩れる危険が大きい。
かといって毎回赤くすると**警報疲れ**で誰も見なくなる（CLAUDE.mdが繰り返し警告している罠）。
→ 現状を baseline として凍結し、**増えたときだけ落とす**。
   減らしたら baseline も減らす（--update で更新）。新規ページは0が初期値。
"""
BASE = os.path.join(ROOT, "backtest", "fontsize_baseline.json")


def scan():
    counts = {}
    targets = sorted(glob.glob(os.path.join(ROOT, "deploy", "*.html")))
    targets += sorted(glob.glob(os.path.join(ROOT, "backtest", "gen_*.py")))
    targets += sorted(glob.glob(os.path.join(ROOT, "core", "*.css")))
    # ★core/*.js も対象★ 下部ナビ(theme.js)が11pxだったのを検出器が見逃していた。
    #   全ページに出る要素がCSSファイルではなくJS内の文字列で定義されている。
    targets += sorted(glob.glob(os.path.join(ROOT, "core", "*.js")))
    for path in targets:
        rel = os.path.relpath(path, ROOT).replace("\\", "/")
        try:
            s = open(path, encoding="utf-8").read()
        except OSError:
            continue
        n = len(PAT.findall(s))
        # <small>を使うのにサイズ指定が無い＝13.3pxで表示される（書かなくても違反する）
        if rel.startswith("deploy") and SMALL_USE.search(s) and not SMALL_SIZE.search(s):
            n += 1
        counts[rel] = n
    return counts


def main():
    import json
    counts = scan()
    if "--update" in sys.argv:
        json.dump({"note": "14px未満のfont-size箇所数の基準線。増えたらNG。"
                           "減らしたら --update で更新する。0にするのが目標。",
                   "counts": {k: v for k, v in counts.items() if v}},
                  open(BASE, "w", encoding="utf-8", newline="\n"),
                  ensure_ascii=False, indent=1)
        print(f"baselineを更新: {sum(counts.values())}箇所")
        return 0
    base = {}
    if os.path.exists(BASE):
        base = json.load(open(BASE, encoding="utf-8"))["counts"]
    ng = 0
    for rel, n in sorted(counts.items()):
        b = base.get(rel, 0)
        if n > b:
            print(f"NG [{rel}] 14px未満のfont-sizeが増えた: {b} → {n}箇所")
            print("    → DADS_DESIGN.md「14px未満は原則禁止」。"
                  "意図的に減らした場合は --update で基準線を下げる")
            ng += 1
    if ng:
        print(f"\nフォントサイズ検査: {ng}ファイルで増加。")
        return 1
    tot, btot = sum(counts.values()), sum(base.values())
    print(f"OK  フォントサイズ検査: 増加なし（既知の残り{tot}箇所/基準線{btot}・"
          "既存ページの積み残しで、減らすのが目標）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
