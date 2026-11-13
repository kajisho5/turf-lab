# -*- coding: utf-8 -*-
"""成績の公開ページの見本（iPhone 幅390）。python3 gen.py → score_page.svg。数字は全部架空"""
import html
BG, CARD, ROW, INK, SUB, WEAK, RED, REDFILL, GOLD = "#171614", "#211f1c", "#322b27", "#efe7d6", "#b8b0a0", "#6b665c", "#ff7a6b", "#a3271c", "#e8c268"
JP, SERIF, NUM = "'Noto Sans JP',sans-serif", "'Noto Serif JP',serif", "'Roboto Condensed','Noto Sans JP',sans-serif"
e = html.escape
def T(x, y, s, size, fill=INK, w=400, anchor="start", fam=None):
    a = f' font-family="{fam}"' if fam else ""
    return f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{w}" fill="{fill}" text-anchor="{anchor}"{a}>{e(str(s))}</text>'
def R(x, y, w, h, fill, stroke=None, sw=0):
    st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}"{st}/>'
W = 390; o = []; y = 0
o += [R(16, 20, W - 32, 4, INK), R(16, 27, W - 32, 1.5, INK), T(16, 74, "成績表", 40, INK, 900, fam=SERIF), T(W - 16, 56, "カジ競馬 AI予想", 16, INK, 700, "end"), T(W - 16, 78, "11月21日 更新", 16, SUB, 400, "end"),
      R(16, 90, W - 32, 1.5, INK)]
o += [T(16, 118, "朝に出した予想を、公式の着順と払戻で", 16, SUB), T(16, 142, "採点しています。外れも全部入っています。", 16, SUB)]
# 期間の切り替え
x = 16
for i, lab in enumerate(["直近7日", "直近30日", "全期間"]):
    w = 112 if i < 2 else 110
    o += [R(x, 162, w, 44, INK if i == 0 else CARD, None if i == 0 else WEAK, 0 if i == 0 else 1.5), T(x + w / 2, 190, lab, 16, BG if i == 0 else INK, 700, "middle")]; x += w + 6
# 大きい数字
y = 222
for i, (lab, v, sub) in enumerate([("◎が3着以内", "63.1", "287レース中 181回"), ("◎の複勝を全部買うと", "90.2", "100円が90円"), ("◎の単勝を全部買うと", "79.4", "100円が79円")]):
    o += [R(16, y, W - 32, 92, CARD, WEAK, 1.5), T(32, y + 34, lab, 16, SUB, 700), T(32, y + 72, sub, 16, SUB),
          f'<text x="{W-32}" y="{y+66}" text-anchor="end" font-family="{NUM}" font-weight="700" fill="{INK}"><tspan font-size="52">{v}</tspan><tspan font-size="24">%</tspan></text>']; y += 100
o += [T(16, y + 24, "100%未満＝買い続けると減ります。", 16, SUB), T(16, y + 48, "当たる予想を売るページではありません。", 16, SUB)]; y += 70
# 区分ごと
o += [T(16, y + 26, "区分ごと", 24, INK, 900, fam=SERIF)]; y += 42
o += [T(28, y + 20, "区分", 16, SUB, 700), T(196, y + 20, "レース", 16, SUB, 700, "end"), T(282, y + 20, "◎3着内", 16, SUB, 700, "end"), T(W - 28, y + 20, "複", 16, SUB, 700, "end"), R(16, y + 30, W - 32, 1.5, WEAK)]; y += 36
for i, (nm, col, a, b, c) in enumerate([("★勝負", RED, "54", "79.6%", "93.5%"), ("狙い目", INK, "121", "64.5%", "90.7%"), ("そのほか", SUB, "112", "53.6%", "88.1%")]):
    if i % 2 == 0: o.append(R(16, y, W - 32, 44, CARD))
    o += [T(28, y + 29, nm, 17, col, 700), T(196, y + 29, a, 18, INK, 400, "end", NUM), T(282, y + 29, b, 18, INK, 400, "end", NUM), T(W - 28, y + 29, c, 18, INK, 400, "end", NUM)]; y += 46
y += 18
# 日ごと
o += [T(16, y + 26, "日ごと", 24, INK, 900, fam=SERIF)]; y += 42
o += [T(28, y + 20, "日付", 16, SUB, 700), T(196, y + 20, "レース", 16, SUB, 700, "end"), T(282, y + 20, "◎3着内", 16, SUB, 700, "end"), T(W - 28, y + 20, "複", 16, SUB, 700, "end"), R(16, y + 30, W - 32, 1.5, WEAK)]; y += 36
for i, (d, n, p, f) in enumerate([("11/20（金）", 44, "70.5%", 104.2), ("11/19（木）", 36, "61.1%", 86.0), ("11/18（水）", 41, "68.3%", 97.4), ("11/17（火）", 46, "58.7%", 81.3), ("11/16（月）", 38, "65.8%", 92.6)]):
    if i % 2 == 0: o.append(R(16, y, W - 32, 44, CARD))
    o += [T(28, y + 29, d, 17, INK, 500), T(196, y + 29, n, 18, INK, 400, "end", NUM), T(282, y + 29, p, 18, INK, 400, "end", NUM), T(W - 28, y + 29, f"{f:.1f}%", 18, GOLD if f >= 100 else INK, 700 if f >= 100 else 400, "end", NUM)]; y += 46
o += [R(16, y + 8, W - 32, 48, CARD, WEAK, 1.5), T(W / 2, y + 38, "もっと前の日を見る", 16, INK, 700, "middle")]; y += 76
# 新旧モデル
o += [T(16, y + 26, "新しいモデルと前のモデル", 24, INK, 900, fam=SERIF), T(16, y + 54, "同じ 287レースで比べた結果（11/14〜）", 16, SUB)]; y += 70
for lab, col, v in [("新モデル（本番）", RED, "◎3着内 63.1%　複 90.2%"), ("前のモデル（記録だけ）", SUB, "◎3着内 59.8%　複 86.0%")]:
    o += [R(16, y, W - 32, 72, CARD, RED if col == RED else WEAK, 2 if col == RED else 1.5), T(32, y + 28, lab, 16, col, 700), T(32, y + 56, v, 17, INK, 400)]; y += 80
y += 10
# 注記とリンク
o += [R(16, y, W - 32, 1.5, INK), T(16, y + 30, "回収率は買った全レースが分母です。", 16, SUB), T(16, y + 54, "数字は毎朝、公式データで作り直します。", 16, SUB), T(16, y + 78, "馬券は20歳から。", 16, SUB)]; y += 96
o += [R(16, y, W - 32, 52, REDFILL), T(W / 2, y + 33, "今日の予想を X で見る", 17, "#ffffff", 700, "middle")]; y += 76
H = y
open("score_page.svg", "w", encoding="utf-8").write(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{JP}">\n' + R(0, 0, W, H, BG) + "\n" + "\n".join(o) + "\n</svg>")
print(H)
