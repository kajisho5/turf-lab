# -*- coding: utf-8 -*-
"""Xのプロフィール画像とヘッダー画像・作り直し（v2）。python3 gen.py → h1〜h3.svg・i1〜i4.svg"""
BG, CARD, INK, SUB, WEAK, RED, REDFILL, GOLD = "#171614", "#211f1c", "#efe7d6", "#b8b0a0", "#6b665c", "#ff7a6b", "#a3271c", "#e8c268"
JP, SERIF, NUM = "'Noto Sans JP',sans-serif", "'Noto Serif JP',serif", "'Roboto Condensed','Noto Sans JP',sans-serif"
def svg(name, W, H, body, defs=""):
    open(name + ".svg", "w", encoding="utf-8").write(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{JP}"><defs>{defs}</defs>\n<rect width="{W}" height="{H}" fill="{BG}"/>\n' + "\n".join(body) + "\n</svg>")
HATCH = f'<pattern id="hatch" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="10" height="10" fill="{BG}"/><rect width="2" height="10" fill="{INK}" opacity=".22"/></pattern>'
def ring(cx, cy, r, sw, col, op=1): return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{col}" stroke-width="{sw}" opacity="{op}"/>'
def tri(cx, cy, s, col, fill): 
    h = s * 0.866; p = f"{cx},{cy-h*0.62} {cx+s/2},{cy+h*0.38} {cx-s/2},{cy+h*0.38}"
    return f'<polygon points="{p}" fill="{col if fill else "none"}" stroke="{col}" stroke-width="{0 if fill else 16}" stroke-linejoin="miter"/>'

# ---- h1: 題字と宣言 ----
def h1():
    o = [ring(-30, 120, 330, 3, INK, .10), ring(-30, 120, 250, 3, INK, .10), ring(-30, 120, 170, 3, INK, .10),
         f'<text x="430" y="212" font-family="{SERIF}" font-weight="900" font-size="128" fill="{INK}" letter-spacing="-2">外れも、</text>',
         f'<text x="430" y="352" font-family="{SERIF}" font-weight="900" font-size="128" letter-spacing="-2"><tspan fill="{RED}">全部</tspan><tspan fill="{INK}">のせる。</tspan></text>',
         f'<rect x="432" y="384" width="760" height="2" fill="{INK}"/>',
         f'<text x="432" y="424" font-size="22" font-weight="500" fill="{SUB}">地方競馬 AI予想　／　毎朝 8:30 全場・全レース　／　毎晩 22:30 答え合わせ</text>',
         # 題字（縦書き）
         f'<rect x="1286" y="70" width="156" height="366" fill="url(#hatch)" stroke="{INK}" stroke-width="4"/>',
         f'<rect x="1298" y="82" width="132" height="342" fill="{BG}"/>',
         f'<text x="1364" y="104" writing-mode="vertical-rl" font-family="{SERIF}" font-weight="900" font-size="78" fill="{INK}" letter-spacing="2">カジ競馬</text>']
    svg("h1", 1500, 500, o, HATCH)

# ---- h2: 印（◎○▲△△）を大きく ----
def h2():
    y = 196; o = []
    xs = [520, 730, 940, 1150, 1360]
    o += [ring(xs[0], y, 84, 22, RED), ring(xs[0], y, 40, 22, RED), ring(xs[1], y, 84, 16, INK), tri(xs[2], y + 6, 186, INK, True), tri(xs[3], y + 6, 172, SUB, False), tri(xs[4], y + 6, 172, SUB, False)]
    for x, lab in zip(xs, ["本命", "対抗", "単穴", "押さえ", "押さえ"]):
        o.append(f'<text x="{x}" y="336" text-anchor="middle" font-size="22" font-weight="700" fill="{SUB}" letter-spacing="6">{lab}</text>')
    o += [f'<rect x="430" y="362" width="1020" height="2" fill="{INK}"/>',
          f'<text x="430" y="420" font-family="{SERIF}" font-weight="900" font-size="52" fill="{INK}">カジ競馬</text>',
          f'<text x="1450" y="414" text-anchor="end" font-size="24" font-weight="500" fill="{SUB}" letter-spacing="1">地方競馬 AI予想　毎朝 8:30 全場・全レース　外れも全部のせます</text>']
    svg("h2", 1500, 500, o)

# ---- 蹄鉄の印 ----
def shoe(cx, cy, s, col, hole):
    # s=全体の幅。上が丸く下が開いた形
    r = s * 0.5 - s * 0.14; sw = s * 0.28; top = cy - s * 0.12; bot = cy + s * 0.48
    d = f"M {cx-r} {bot} L {cx-r} {top} A {r} {r} 0 0 1 {cx+r} {top} L {cx+r} {bot}"
    o = [f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{sw}" stroke-linecap="butt"/>']
    import math
    for a in (200, 235, 270, 305, 340):           # 釘の穴（弧の上）
        o.append(f'<circle cx="{cx + r*math.cos(math.radians(a)):.1f}" cy="{top + r*math.sin(math.radians(a)):.1f}" r="{s*0.03:.1f}" fill="{hole}"/>')
    for yy in (0.18, 0.36):
        for sx in (-1, 1): o.append(f'<circle cx="{cx+sx*r}" cy="{cy + s*yy:.1f}" r="{s*0.03:.1f}" fill="{hole}"/>')
    return o
def h3():
    o = shoe(1260, 232, 300, INK, BG) + [ring(1260, 262, 44, 16, RED), ring(1260, 262, 14, 12, RED),
         f'<text x="430" y="262" font-family="{SERIF}" font-weight="900" font-size="150" fill="{INK}" letter-spacing="-3">カジ競馬</text>',
         f'<rect x="434" y="300" width="610" height="6" fill="{REDFILL}"/>',
         f'<text x="434" y="352" font-size="30" font-weight="700" fill="{INK}" letter-spacing="2">地方競馬 AI予想</text>',
         f'<text x="434" y="398" font-size="24" font-weight="500" fill="{SUB}" letter-spacing="1">毎朝 8:30 全場・全レース　／　外れも全部のせます</text>']
    svg("h3", 1500, 500, o)

# ---- プロフィール画像 ----
def i1(): svg("i1", 400, 400, [ring(200, 200, 132, 40, RED), ring(200, 200, 58, 40, RED)])
def i2():
    o = [f'<text x="186" y="262" text-anchor="middle" font-family="{SERIF}" font-weight="900" font-size="168" fill="{INK}" letter-spacing="-10">カシ</text>',
         ring(318, 96, 15, 9, RED), ring(318, 96, 4, 6, RED), ring(352, 128, 15, 8, INK),
         f'<rect x="96" y="292" width="208" height="5" fill="{INK}"/>', f'<text x="200" y="332" text-anchor="middle" font-size="24" font-weight="700" fill="{SUB}" letter-spacing="12">競馬</text>']
    svg("i2", 400, 400, o)
def i3(): svg("i3", 400, 400, shoe(200, 178, 250, INK, BG) + [ring(200, 206, 38, 15, RED), ring(200, 206, 11, 11, RED)])
def i4():
    o = [f'<rect x="118" y="52" width="164" height="296" fill="{INK}"/>', f'<rect x="130" y="64" width="140" height="272" fill="none" stroke="{BG}" stroke-width="3"/>',
         f'<text x="200" y="92" writing-mode="vertical-rl" font-family="{SERIF}" font-weight="900" font-size="104" fill="{BG}" letter-spacing="6">カジ</text>',
         ring(200, 312, 0, 0, RED)]
    svg("i4", 400, 400, o)
for f in (h1, h2, h3, i1, i2, i3, i4): f()
print("ok")
