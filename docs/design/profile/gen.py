# -*- coding: utf-8 -*-
"""Xのプロフィール画像とヘッダー画像の見本（F案）。python3 gen.py → header_a/b.svg・icon_a/b/c.svg"""
import html
BG, CARD, ROW, INK, SUB, WEAK, RED, REDFILL, GOLD = "#171614", "#211f1c", "#322b27", "#efe7d6", "#b8b0a0", "#6b665c", "#ff7a6b", "#a3271c", "#e8c268"
JP, SERIF, NUM = "'Noto Sans JP',sans-serif", "'Noto Serif JP',serif", "'Roboto Condensed','Noto Sans JP',sans-serif"
e = html.escape
def T(x, y, s, size, fill=INK, w=400, anchor="start", fam=None, ls=None):
    a = f' font-family="{fam}"' if fam else ""; l = f' letter-spacing="{ls}"' if ls else ""
    return f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{w}" fill="{fill}" text-anchor="{anchor}"{a}{l}>{e(str(s))}</text>'
def R(x, y, w, h, fill, stroke=None, sw=0, extra=""):
    st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}"{st}{extra}/>'
def svg(name, W, H, body):
    open(name + ".svg", "w", encoding="utf-8").write(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{JP}">\n' + "\n".join(body) + "\n</svg>")
GUIDE = lambda W, H: [  # Xの表示で隠れやすい所（見本にだけ描く。書き出す画像には入れない）
    f'<rect x="0" y="0" width="{W}" height="60" fill="#ff00ff" opacity=".10"/>', f'<rect x="0" y="{H-60}" width="{W}" height="60" fill="#ff00ff" opacity=".10"/>',
    f'<circle cx="190" cy="{H-10}" r="150" fill="#ff00ff" opacity=".12"/>']

def header(name, guide, variant):
    W, H = 1500, 500; o = [R(0, 0, W, H, BG)]
    if variant == "a":   # 新聞の題字。右に約束ごと3つ
        o += [R(420, 96, 1010, 6, INK), R(420, 106, 1010, 2, INK),
              T(420, 232, "カジ競馬", 124, INK, 900, fam=SERIF), T(940, 178, "地方競馬　AI予想", 34, INK, 700), T(940, 228, "毎朝 8:30　全場・全レース", 34, INK, 700),
              R(420, 262, 1010, 2, INK)]
        x = 420
        for lab, sub in [("朝に出したら変えない", "オッズを見る前に出します"), ("外れも全部のせる", "毎晩 22:30 に答え合わせ"), ("成績は全部公開", "週ごと・月ごとにまとめます")]:
            o += [R(x, 296, 322, 108, CARD, WEAK, 2), R(x, 296, 322, 8, REDFILL), T(x + 20, 346, lab, 28, INK, 700), T(x + 20, 384, sub, 22, SUB)]; x += 344
    else:                # 予想の1枠をそのまま見せる
        o += [R(420, 96, 560, 6, INK), R(420, 106, 560, 2, INK), T(420, 232, "カジ競馬", 124, INK, 900, fam=SERIF),
              R(420, 262, 560, 2, INK), T(420, 312, "地方競馬　AI予想", 32, INK, 700), T(420, 356, "毎朝 8:30　全場・全レース", 26, SUB), T(420, 394, "外れも全部のせます　／　毎晩 22:30 答え合わせ", 26, SUB)]
        x, y, w, h = 1030, 96, 400, 312
        o += [R(x, y, w, h, CARD, INK, 4), R(x + 2, y + 2, w - 4, 10, REDFILL), R(x + 20, y + 28, 70, 46, REDFILL), T(x + 55, y + 62, "5R", 28, "#ffffff", 700, "middle", NUM),
              T(x + 106, y + 62, "C3ー5", 28, INK, 700), R(x + w - 20 - 112, y + 31, 112, 40, REDFILL), T(x + w - 20 - 56, y + 60, "★勝負", 24, "#ffffff", 700, "middle"),
              R(x + 20, y + 90, w - 40, 2, WEAK), R(x + 12, y + 104, w - 24, 46, ROW), R(x + 12, y + 104, 6, 46, RED)]
        rows = [("◎", 5, "オッターダッシュ", RED, True), ("○", 7, "ラッコノユメ", INK, False), ("▲", 2, "カワウソブレイブ", INK, False), ("△", 4, "セセラギキング", SUB, False)]
        for k, (mk, n, nm, col, big) in enumerate(rows):
            b = y + 138 + k * 46
            o += [T(x + 28, b, mk, 30 if big else 26, col, 700), T(x + 96, b, n, 30 if big else 26, INK, 700, "end", NUM), T(x + 114, b, nm, 28 if big else 25, INK, 700 if big else 500)]
    if guide: o += GUIDE(W, H)
    svg(name, W, H, o)

def icon(name, variant, guide):
    W = H = 400; o = [R(0, 0, W, H, BG)]
    if variant == "a":    # 題字の1字
        o += [R(70, 96, 260, 6, INK), R(70, 106, 260, 2, INK), T(200, 262, "カジ", 120, INK, 900, "middle", SERIF), R(70, 290, 260, 2, INK), T(200, 326, "AI予想", 26, RED, 700, "middle", ls="6")]
    elif variant == "b":  # ◎
        o += [f'<circle cx="200" cy="176" r="92" fill="none" stroke="{RED}" stroke-width="18"/>', f'<circle cx="200" cy="176" r="50" fill="none" stroke="{RED}" stroke-width="18"/>',
              T(200, 330, "カジ競馬", 44, INK, 900, "middle", SERIF)]
    else:                 # 赤い札
        o += [R(60, 100, 280, 200, REDFILL), T(200, 196, "カジ", 92, "#ffffff", 900, "middle", SERIF), T(200, 266, "競馬", 60, "#ffffff", 900, "middle", SERIF)]
    if guide: o.append(f'<circle cx="200" cy="200" r="199" fill="none" stroke="#ff00ff" stroke-width="2" stroke-dasharray="8 8" opacity=".7"/>')
    svg(name, W, H, o)

for v in "ab":
    header("header_" + v, False, v); header("header_" + v + "_guide", True, v)
for v in "abc":
    icon("icon_" + v, v, False); icon("icon_" + v + "_guide", v, True)
print("ok")
