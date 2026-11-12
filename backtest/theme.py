# -*- coding: utf-8 -*-
"""配色の唯一の定義場所。ここから core/theme.css を生成する

★なぜ1箇所にするのか★
  これまで各ページの生成スクリプトが同じ色辞書を個別に持っていた。
  ライト／ダークの2系統になると、5ファイルに同じ変更を入れることになり、
  必ずどこかがズレる（コピーが原因の事故は既に4回起きている）。
  色はここだけで決め、CSSは生成物として扱う。

★ライトを基本にする★
  一般の閲覧者はライトが既定の環境が多い。ダークは切り替えで提供する。
  端末がダーク設定でも、明示的に選ぶまではライトを出す
  （prefers-color-scheme に自動追従させない）。
  理由: 記事の図やOGP画像が明色前提で作られており、意図しない見え方を避けるため。

★DADS: コントラスト4.5:1以上を両モードで機械検証する★
  片方だけ確認して通すと、もう片方が読めなくなる。
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "core", "theme.css")

# 役割 -> 色。bg/panel/line は背景側なのでコントラスト検証の対象外
LIGHT = {
    "bg": "#ffffff", "panel": "#f4f6f9", "line": "#d3d8e0",
    "txt": "#16181d", "mute": "#575d68", "dim": "#5f6672",
    "green": "#127a45", "red": "#c62828", "yellow": "#8a6300",
    "blue": "#1461b8", "purple": "#6b3fb5", "orange": "#a2530a",
    # 表の縞。背景と差が出て、かつ本文・補助文字が4.5:1を保てる値を選んだ
    "stripe": "#f2f5fa", "hover": "#e6ecf5",
    # 脚質。前(逃げ)から後(追込)へ 赤→橙→青→灰 と並べ、順序が色でも分かるようにする
    "st1": "#b3261e", "st2": "#8a4b00", "st3": "#1461b8", "st4": "#5f6672",
}
DARK = {
    "bg": "#0a0e16", "panel": "#121826", "line": "#333333",
    "txt": "#ffffff", "mute": "#b3b3b3", "dim": "#999999",
    "green": "#51b883", "red": "#ff7171", "yellow": "#ffd43d",
    "blue": "#57b8ff", "purple": "#bb87ff", "orange": "#ff8d44",
    "stripe": "#161e2d", "hover": "#1e2739",
    "st1": "#ff8080", "st2": "#ffab5e", "st3": "#7cc4ff", "st4": "#a8b0bd",
}
BG_KEYS = ("bg", "panel", "line", "stripe", "hover")


def rel_lum(h):
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a, b):
    la, lb = rel_lum(a), rel_lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def check(name, pal):
    """本文色と強調色が、背景・パネル・縞のどれに乗っても4.5:1以上か

    ★縞を入れたら縞の上も見る★
      背景だけ確認して通すと、縞の行だけコントラスト不足になる。
      light の dim はパネル上で4.47:1になり、実際に一度弾かれている。
    """
    ng = []
    for k, v in pal.items():
        if k in BG_KEYS:
            continue
        cb = contrast(v, pal["bg"])
        cp = contrast(v, pal["panel"])
        cs = contrast(v, pal["stripe"])
        worst = min(cb, cp, cs)
        mark = "OK" if worst >= 4.5 else "NG"
        if worst < 4.5:
            ng.append((k, v, worst))
        print(f"  [{mark}] {name:<5} {k:<7} {v}  背景{cb:5.2f} / パネル{cp:5.2f} / 縞{cs:5.2f}")
    return ng


def vars_block(pal):
    return "\n".join(f"  --{k}: {v};" for k, v in pal.items())


def main():
    print("DADS コントラスト検証（本文16px以上・4.5:1以上）")
    ng = check("light", LIGHT) + check("dark", DARK)
    if ng:
        print("\n!! 4.5:1 を満たさない色がある。直すまで生成しない:")
        for k, v, c in ng:
            print(f"   {k} {v} {c:.2f}:1")
        return 1

    css = f"""/* 配色 — ★backtest/theme.py が生成する。直接編集しない★
   ライトが基本。ダークは data-theme="dark" で切り替える。
   端末のダーク設定には自動追従しない（明示的に選ぶまでライト）。 */
:root {{
  color-scheme: light;
{vars_block(LIGHT)}
}}
:root[data-theme="dark"] {{
  color-scheme: dark;
{vars_block(DARK)}
}}

/* ★表の共通スタイル★ 各ページで縞やソートを書くと必ず食い違うので、ここに置く。
   .zebra を付けた表は自動で縞になり、th[data-sort] は押せる見出しになる。 */
.zebra tbody tr:nth-child(even) > *, table.zebra tr:nth-child(even) > * {{
  background: var(--stripe);
}}
.zebra tbody tr:hover > *, table.zebra tr:hover > * {{ background: var(--hover); }}
th.sortable {{ cursor: pointer; user-select: none; white-space: nowrap; }}
th.sortable:hover {{ color: var(--txt); }}
th.sortable::after {{ content: " ⇅"; opacity: .45; font-size: 14px; }}
th.sortable[aria-sort="descending"]::after {{ content: " ▼"; opacity: 1; color: var(--accent, var(--blue)); }}
th.sortable[aria-sort="ascending"]::after {{ content: " ▲"; opacity: 1; color: var(--accent, var(--blue)); }}

/* 切り替えボタン */
.themebtn {{
  appearance: none; border: 1px solid var(--line); background: var(--panel);
  color: var(--mute); font: inherit; font-size: 16px; line-height: 1;
  padding: 7px 10px; border-radius: 999px; cursor: pointer;
}}
.themebtn:hover {{ border-color: var(--mute); }}
"""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(css)
    print(f"\n生成: {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
