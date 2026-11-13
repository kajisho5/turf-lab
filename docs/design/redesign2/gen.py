# -*- coding: utf-8 -*-
"""予想画像の作り直し・ダーク10案。python3 gen.py → d01〜d10.svg。名前と数字は全部架空"""
import html, math
e = html.escape
RACES = [
 dict(no=1, cls="C3ー5", dist=1400, post="15:35", tier="battle", N=10, strong="近走の時計がメンバー1位",
      m=[("◎",5,"オッターダッシュ",64),("○",7,"ラッコノユメ",31),("▲",2,"カワウソブレイブ",None),("△",4,"セセラギキング",None),("△",9,"ミズカキエース",None)]),
 dict(no=2, cls="2歳ー3", dist=1300, post="16:05", tier="aim", N=12, strong=None,
      m=[("◎",10,"イタチノホシ",52),("○",3,"コツメスマイル",45),("▲",6,"ナガレボシオー",None),("△",1,"カワベノハナ",None),("△",12,"ツキヨノラッコ",None)]),
 dict(no=3, cls="C2ー4", dist=1400, post="16:40", tier="", N=9, strong=None,
      m=[("◎",2,"ミナモノカゼ",47),("○",9,"シオカゼテイオー",41),("▲",4,"ハマベノユウヒ",None),("△",3,"ナギサブルー",None),("△",8,"ウミネコライト",None)]),
 dict(no=4, cls="B3ー2", dist=1600, post="17:15", tier="", N=11, strong=None,
      m=[("◎",8,"セセラギオウジ",49),("○",1,"カワモノガタリ",44),("▲",5,"ヨアケノラッコ",None),("△",11,"ミズベノユメ",None),("△",6,"アサナギスター",None)]),
]
VENUE, DATE = "潮見", "11月14日（土）"
WAKU = {1:("#f4f4f4","#111"),2:("#1a1a1a","#fff"),3:("#e23a2e","#fff"),4:("#2f73e0","#fff"),5:("#f4cf1f","#111"),6:("#2fa35a","#fff"),7:("#f28c28","#111"),8:("#f4a3c0","#111")}
def waku(n, N):
    if N <= 8: return n
    dbl = N - 8                       # 2頭入る枠の数（8枠から内へ）
    single = 8 - dbl
    if n <= single: return n
    return single + (n - single + 1) // 2
def T(x, y, s, size, fill="#fff", w=400, anchor="start", fam=None, extra=""):
    a = f' font-family="{fam}"' if fam else ""
    return f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{w}" fill="{fill}" text-anchor="{anchor}"{a} {extra}>{e(str(s))}</text>'
def R(x, y, w, h, fill, rx=0, stroke=None, sw=0, extra=""):
    st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}"{st} {extra}/>'
def out(name, W, H, body, defs="", fam="'Noto Sans JP',sans-serif"):
    open(name + ".svg", "w", encoding="utf-8").write(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{fam}"><defs>{defs}</defs>\n' + "\n".join(body) + "\n</svg>")
def grid(i, x0, y0, cw, ch, gx, gy): return x0 + (i % 2) * (cw + gx), y0 + (i // 2) * (ch + gy)
TIERLAB = {"battle": "★勝負", "aim": "狙い目"}
W = 1240

# ---------- 01 枠色: 馬番を「枠の色」の札で見せる ----------
def d01():
    BG, P, INK, SUB = "#0e1014", "#181b22", "#f5f6f8", "#9aa3b2"; o = [R(0, 0, W, 1090, BG)]
    G = "'Zen Kaku Gothic New','Noto Sans JP',sans-serif"; N_ = "'Barlow Condensed','Noto Sans JP',sans-serif"
    o += [T(48, 128, VENUE, 100, INK, 900, fam=G), T(270, 92, "カジ競馬 AI予想", 26, SUB, 700), T(270, 130, DATE, 34, INK, 700)]
    x = 1192
    for i in range(8, 0, -1): o.append(R(x - 34, 84, 34, 46, WAKU[i][0], 4, "#3a3f4a" if i == 2 else None, 2)); x -= 40
    o.append(T(1192, 66, "馬番の色は枠の色です", 22, SUB, 400, "end"))
    for i, rc in enumerate(RACES):
        x, y = grid(i, 48, 176, 560, 404, 24, 24); bt = rc["tier"]
        o += [R(x, y, 560, 404, P, 18), T(x + 28, y + 62, f'{rc["no"]}R', 44, INK, 700, fam=N_), T(x + 104, y + 60, f'{rc["cls"]}　{rc["dist"]}m', 26, INK, 700), T(x + 104 + 250, y + 60, rc["post"], 26, SUB, 400, fam=N_)]
        if bt: o += [R(x + 560 - 28 - 118, y + 26, 118, 46, "#f5f6f8" if bt == "battle" else P, 23, None if bt == "battle" else "#f5f6f8", 2), T(x + 560 - 28 - 59, y + 58, TIERLAB[bt], 24, "#0e1014" if bt == "battle" else INK, 700, "middle")]
        for k, (mk, n, nm, sc) in enumerate(rc["m"]):
            big = k == 0; yy = y + 96 + (0 if big else 92 + (k - 1) * 54); c, tc = WAKU[waku(n, rc["N"])]
            s = 72 if big else 44
            o += [T(x + 28, yy + (52 if big else 33), mk, 40 if big else 28, INK if k < 3 else SUB, 700),
                  R(x + 84, yy, s, s, c, 10 if big else 7, "#3a3f4a" if c == "#1a1a1a" else None, 2), T(x + 84 + s / 2, yy + (53 if big else 33), n, 48 if big else 30, tc, 700, "middle", N_),
                  T(x + 84 + s + 20, yy + (52 if big else 32), nm, 38 if big else 27, INK, 900 if big else 500, fam=G)]
            if sc is not None: o.append(T(x + 532, yy + (52 if big else 32), sc, 40 if big else 26, INK if big else SUB, 700, "end", N_))
    o.append(T(48, 1056, "近走・騎手・血統・時計から自動算出（オッズ非依存）／馬券は20歳から", 22, SUB))
    out("d01", W, 1090, o)

# ---------- 02 馬柱: 競馬新聞の縦の柱 ----------
def d02():
    BG, INK, SUB, LINE, RED = "#141210", "#ece4d4", "#a59c8a", "#4a443a", "#e2543f"; M = "'Shippori Mincho B1','Noto Serif JP',serif"; N_ = "'Barlow Condensed',sans-serif"
    o = [R(0, 0, W, 1120, BG), T(48, 124, VENUE, 92, INK, 800, fam=M), T(250, 88, "カジ競馬　AI予想", 26, SUB, 500, fam=M), T(250, 126, DATE, 32, INK, 600, fam=M), R(48, 150, 1144, 3, INK)]
    for i, rc in enumerate(RACES):
        x, y = grid(i, 48, 182, 560, 420, 24, 28); cw = 88
        o += [R(x, y, 560, 420, "none", 0, LINE, 2)]
        # 右端: レースの柱
        tx = x + 560 - 104
        o += [R(tx, y, 104, 420, INK if rc["tier"] == "battle" else "none", 0, LINE, 2)]
        col = BG if rc["tier"] == "battle" else INK
        o += [T(tx + 52, y + 56, f'{rc["no"]}R', 44, col, 700, "middle", N_), T(tx + 52, y + 92, rc["post"], 24, col, 400, "middle", N_),
              T(tx + 52, y + 124, f'{rc["cls"]}　{rc["dist"]}m', 24, col, 600, "start", M, 'writing-mode="vertical-rl"')]
        if rc["tier"]: o.append(T(tx + 52, y + 400, TIERLAB[rc["tier"]], 22, col if rc["tier"] == "battle" else RED, 700, "middle"))
        for k, (mk, n, nm, sc) in enumerate(rc["m"]):
            cx = tx - (k + 1) * cw - (8 if k else 0) + cw / 2 + (0 if k else 0); cx = tx - 16 - cw / 2 - k * cw
            if k == 0: o.append(R(cx - cw / 2 + 4, y + 8, cw - 8, 404, "#221e19"))
            o += [T(cx, y + 58, mk, 46 if k == 0 else 34, RED if k == 0 else (INK if k < 3 else SUB), 700, "middle"),
                  R(cx - 26, y + 76, 52, 44, "none", 0, INK if k == 0 else LINE, 2), T(cx, y + 110, n, 32, INK, 700, "middle", N_),
                  T(cx, y + 138, nm, 30 if k == 0 else 26, INK, 800 if k == 0 else 500, "start", M, 'writing-mode="vertical-rl"')]
            if sc is not None: o.append(T(cx, y + 404, sc, 26, INK if k == 0 else SUB, 700, "middle", N_))
            if k < 4: o.append(R(cx - cw / 2, y, 1.5, 420, LINE))
    o += [R(48, 1054, 1144, 1.5, LINE), T(48, 1094, "右から ◎本命 ○対抗 ▲単穴 △押さえ。下の数字は点数（オッズ非依存）／馬券は20歳から", 22, SUB, fam=M)]
    out("d02", W, 1120, o)

# ---------- 03 着順掲示板: 電光の点文字 ----------
def d03():
    BG, AMB, WHT, DIM, RED, GRN = "#050505", "#ffb21c", "#f2f2f2", "#6f6a5e", "#ff3b30", "#2ee06a"; D = "'DotGothic16','Noto Sans JP',monospace"
    dots = '<pattern id="dot" width="6" height="6" patternUnits="userSpaceOnUse"><rect width="6" height="6" fill="#0c0c0c"/><circle cx="3" cy="3" r="1" fill="#1d1b17"/></pattern>'
    o = [R(0, 0, W, 1100, BG), R(24, 24, 1192, 1052, "url(#dot)", 10, "#2a2a2a", 3), T(60, 122, VENUE, 84, AMB, 400, fam=D), T(250, 86, "カジ競馬 AI予想", 28, WHT, 400, fam=D), T(250, 124, DATE, 32, WHT, 400, fam=D),
         T(1180, 124, "◎○▲△△", 32, DIM, 400, "end", D)]
    for i, rc in enumerate(RACES):
        x, y = grid(i, 60, 160, 548, 410, 24, 24); bt = rc["tier"]
        o += [R(x, y, 548, 410, "#000", 6, "#333", 2), R(x + 16, y + 16, 92, 60, "#000", 4, AMB, 2), T(x + 62, y + 60, f'{rc["no"]}R', 40, AMB, 400, "middle", D),
              T(x + 124, y + 44, f'{rc["cls"]} {rc["dist"]}m', 24, WHT, 400, fam=D), T(x + 124, y + 74, rc["post"] + " 発走", 24, DIM, 400, fam=D)]
        if bt: o += [R(x + 548 - 16 - 116, y + 20, 116, 52, RED if bt == "battle" else "#000", 4, RED, 2), T(x + 548 - 16 - 58, y + 56, "勝負" if bt == "battle" else "狙い目", 26, "#fff" if bt == "battle" else RED, 400, "middle", D)]
        for k, (mk, n, nm, sc) in enumerate(rc["m"]):
            yy = y + 96 + k * 60
            o += [R(x + 16, yy, 52, 50, "#111", 3), T(x + 42, yy + 37, mk, 30, WHT, 400, "middle", D), R(x + 76, yy, 76, 50, "#000", 3, "#3a3320", 2),
                  T(x + 114, yy + 39, n, 38, AMB if k == 0 else "#d9981a", 400, "middle", D), T(x + 168, yy + 37, nm, 30 if k == 0 else 28, WHT if k < 3 else "#bdbdbd", 400, fam=D)]
            if sc is not None: o.append(T(x + 532, yy + 37, sc, 30, GRN if k == 0 else DIM, 400, "end", D))
    o.append(T(60, 1050, "オッズ非依存 自動算出 ／ 馬券は20歳から", 24, DIM, 400, fam=D))
    out("d03", W, 1100, o, dots)

# ---------- 04 馬券: 1レース1枚の券 ----------
def d04():
    BG, TK, INK, SUB, GOLD, LINE = "#101114", "#1d1f25", "#eef0f3", "#9097a3", "#d7b35a", "#3a3e48"; N_ = "'Oswald','Noto Sans JP',sans-serif"
    o = [R(0, 0, W, 1090, BG), T(48, 120, VENUE, 88, INK, 900), T(244, 86, "カジ競馬 AI予想", 26, SUB, 700), T(244, 124, DATE, 32, INK, 700), T(1192, 124, "勝馬予想券", 30, SUB, 700, "end")]
    for i, rc in enumerate(RACES):
        x, y = grid(i, 48, 164, 560, 420, 24, 28); bt = rc["tier"]; sx = x + 128
        o += [R(x, y, 560, 420, TK, 14), R(x, y, 560, 14, GOLD if bt == "battle" else (INK if bt == "aim" else LINE), 0, extra='clip-path="inset(0 round 14px 14px 0 0)"')]
        for cy in (y, y + 420): o.append(f'<circle cx="{sx}" cy="{cy}" r="14" fill="{BG}"/>')
        o.append(f'<line x1="{sx}" y1="{y+22}" x2="{sx}" y2="{y+398}" stroke="{LINE}" stroke-width="3" stroke-dasharray="6 8"/>')
        o += [T(x + 64, y + 96, rc["no"], 84, INK, 700, "middle", N_), T(x + 64, y + 132, "レース", 22, SUB, 700, "middle"), T(x + 64, y + 196, rc["post"], 30, INK, 500, "middle", N_),
              T(x + 64, y + 232, rc["cls"], 22, SUB, 700, "middle"), T(x + 64, y + 262, f'{rc["dist"]}m', 22, SUB, 700, "middle")]
        if bt: o.append(T(x + 64, y + 384, TIERLAB[bt], 24, GOLD if bt == "battle" else INK, 900, "middle"))
        mk, n, nm, sc = rc["m"][0]
        o += [T(sx + 30, y + 64, "本命", 24, SUB, 700), T(sx + 30, y + 170, n, 110, GOLD if bt == "battle" else INK, 700, fam=N_), T(sx + 30 + (150 if n >= 10 else 90), y + 126, nm, 36, INK, 900), T(sx + 30 + (150 if n >= 10 else 90), y + 168, f"点数 {sc}", 24, SUB, 700),
              f'<line x1="{sx+30}" y1="{y+200}" x2="{x+532}" y2="{y+200}" stroke="{LINE}" stroke-width="2"/>']
        for k, (mk, n, nm, sc) in enumerate(rc["m"][1:]):
            yy = y + 244 + k * 44
            o += [T(sx + 30, yy, {"○": "対抗", "▲": "単穴", "△": "押さえ"}[mk], 22, SUB, 700), R(sx + 118, yy - 28, 50, 36, "none", 6, INK if k < 2 else SUB, 2), T(sx + 143, yy - 1, n, 26, INK, 600, "middle", N_), T(sx + 184, yy, nm, 26, INK, 500)]
        for b in range(22):
            o.append(R(x + 540 - b * 7, y + 388, 3 if b % 3 else 5, 18, LINE))
    o.append(T(48, 1056, "これは予想です（馬券ではありません）。オッズを見る前に出しています／馬券は20歳から", 22, SUB))
    out("d04", W, 1090, o)

# ---------- 05 中継テロップ: 斜めの帯 ----------
def d05():
    INK, SUB, YEL, CY = "#ffffff", "#a9b6cc", "#ffe14a", "#3fd0ff"; G = "'Noto Sans JP',sans-serif"; N_ = "'Barlow Condensed','Noto Sans JP',sans-serif"
    defs = '<linearGradient id="bg5" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0a1024"/><stop offset="1" stop-color="#05070f"/></linearGradient><linearGradient id="bar5" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#1c4fd6"/><stop offset="1" stop-color="#0b2a7a"/></linearGradient><linearGradient id="hot5" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#ff3d6e"/><stop offset="1" stop-color="#b3123f"/></linearGradient>'
    def para(x, y, w, h, fill, k=18): return f'<polygon points="{x+k},{y} {x+w+k},{y} {x+w},{y+h} {x},{y+h}" fill="{fill}"/>'
    it = 'font-style="italic"'
    o = [R(0, 0, W, 1090, "url(#bg5)"), para(40, 52, 420, 96, "url(#bar5)", 26), T(84, 122, VENUE, 72, INK, 900, extra=it), T(250, 122, "AI予想", 40, YEL, 900, extra=it),
         para(470, 84, 330, 64, "#0d1630", 18), T(500, 128, DATE, 30, INK, 700, extra=it), T(1192, 128, "カジ競馬", 34, SUB, 900, "end", extra=it)]
    for i, rc in enumerate(RACES):
        x, y = grid(i, 48, 184, 560, 394, 24, 24); bt = rc["tier"]
        o += [para(x, y, 540, 62, "url(#hot5)" if bt == "battle" else "url(#bar5)"), T(x + 40, y + 46, f'{rc["no"]}R', 44, INK, 700, fam=N_, extra=it), T(x + 118, y + 44, f'{rc["cls"]}　{rc["dist"]}m　{rc["post"]}', 26, INK, 700, extra=it)]
        if bt: o.append(T(x + 524, y + 44, TIERLAB[bt], 28, YEL if bt == "battle" else INK, 900, "end", extra=it))
        for k, (mk, n, nm, sc) in enumerate(rc["m"]):
            big = k == 0; yy = y + 76 + (0 if big else 86 + (k - 1) * 58); h = 74 if big else 48
            o.append(para(x, yy, 540, h, YEL if big else "#111a33", 16 if big else 12))
            tc = "#0a1024" if big else INK
            o += [T(x + 36, yy + (54 if big else 35), mk, 40 if big else 28, tc, 900), para(x + 84, yy + 6, 70 if big else 56, h - 12, "#0a1024" if big else CY, 10),
                  T(x + (126 if big else 118), yy + (55 if big else 36), n, 46 if big else 30, YEL if big else "#0a1024", 700, "middle", N_, it), T(x + (182 if big else 164), yy + (53 if big else 35), nm, 33 if big else 27, tc, 900 if big else 700, extra=it)]
            if sc is not None: o.append(T(x + 520, yy + (54 if big else 35), sc, 40 if big else 26, tc if big else SUB, 700, "end", N_, it))
    o.append(T(48, 1056, "近走・騎手・血統・時計から自動算出（オッズ非依存）／馬券は20歳から", 22, SUB))
    out("d05", W, 1090, o, defs)

# ---------- 06 ナイター: ネオン管 ----------
def d06():
    BG, INK, SUB, PINK, CYAN = "#070a18", "#f4f6ff", "#8e97b8", "#ff4fa3", "#35e0ff"; G = "'M PLUS Rounded 1c','Noto Sans JP',sans-serif"
    defs = '<filter id="glow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="7" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter><radialGradient id="sky6" cx="50%" cy="0%" r="90%"><stop offset="0" stop-color="#1a1f4a"/><stop offset="1" stop-color="#070a18"/></radialGradient>'
    gl = 'filter="url(#glow)"'
    o = [R(0, 0, W, 1090, "url(#sky6)"), T(48, 128, VENUE, 96, PINK, 800, fam=G, extra=gl), T(262, 90, "カジ競馬 AI予想", 26, SUB, 700, fam=G), T(262, 130, DATE, 34, INK, 700, fam=G), T(1192, 130, "ナイター", 34, CYAN, 800, "end", G, gl)]
    for i, rc in enumerate(RACES):
        x, y = grid(i, 48, 176, 560, 400, 24, 24); bt = rc["tier"]; col = PINK if bt == "battle" else CYAN if bt == "aim" else "#3a426a"
        o += [R(x, y, 560, 400, "#0b0f24", 26), R(x + 3, y + 3, 554, 394, "none", 24, col, 4, gl if bt else ""), T(x + 30, y + 62, f'{rc["no"]}R', 42, INK, 800, fam=G), T(x + 110, y + 60, f'{rc["cls"]}　{rc["dist"]}m', 26, INK, 700, fam=G), T(x + 110 + 216, y + 60, rc["post"], 24, SUB, 500, fam=G)]
        if bt: o.append(T(x + 530, y + 60, TIERLAB[bt], 26, col, 800, "end", G, gl))
        for k, (mk, n, nm, sc) in enumerate(rc["m"]):
            big = k == 0; yy = y + 132 + (0 if big else 74 + (k - 1) * 50)
            mc = (PINK if bt == "battle" else CYAN) if big else (INK if k < 3 else SUB)
            o += [T(x + 30, yy, mk, 44 if big else 28, mc, 800, fam=G, extra=gl if big else ""), T(x + 142, yy, n, 44 if big else 28, mc if big else INK, 800, "end", G, gl if big else ""), T(x + 164, yy, nm, 36 if big else 27, INK, 800 if big else 500, fam=G)]
            if sc is not None: o.append(T(x + 530, yy, sc, 38 if big else 26, INK if big else SUB, 800, "end", G))
    o.append(T(48, 1056, "近走・騎手・血統・時計から自動算出（オッズ非依存）／馬券は20歳から", 22, SUB, fam=G))
    out("d06", W, 1090, o, defs)

# ---------- 07 特大数字: ◎の馬番を主役に ----------
def d07():
    BG, INK, SUB, LINE, ACC = "#0b0b0d", "#f3f1ea", "#8d8a82", "#2b2a2e", "#ff5a1f"; A = "'Anton','Noto Sans JP',sans-serif"; G = "'Noto Sans JP',sans-serif"
    o = [R(0, 0, W, 1080, BG), T(48, 150, VENUE, 132, INK, 900, fam=G), T(330, 104, "カジ競馬 AI予想", 28, SUB, 700), T(330, 148, DATE, 38, INK, 700), R(48, 178, 1144, 4, INK)]
    for i, rc in enumerate(RACES):
        x, y = grid(i, 48, 182, 572, 420, 0, 0); bt = rc["tier"]; mk, n, nm, sc = rc["m"][0]
        if bt == "battle": o.append(R(x, y, 572, 420, ACC))
        fg = "#0b0b0d" if bt == "battle" else INK; sb = "#3a1606" if bt == "battle" else SUB
        o += [R(x, y + 418, 572, 2, LINE), R(x + 570 if i % 2 == 0 else x, y, 2, 420, LINE),
              T(x + 28, y + 52, f'{rc["no"]}R　{rc["cls"]}　{rc["dist"]}m　{rc["post"]}', 24, fg, 700)]
        if bt: o.append(T(x + 544, y + 52, TIERLAB[bt], 24, fg if bt == "battle" else ACC, 900, "end"))
        o += [T(x + 22, y + 290, n, 250, fg if bt else INK, 400, fam=A, extra='letter-spacing="-4"'), T(x + 28, y + 344, nm, 40, fg, 900), T(x + 28, y + 388, f"◎ 本命　点数 {sc}", 24, sb, 700)]
        for k, (mk, n, nm, sc) in enumerate(rc["m"][1:]):
            yy = y + 124 + k * 52
            o += [T(x + 284, yy, mk, 24, fg, 700), T(x + 350, yy, n, 32, fg, 400, "end", A), T(x + 364, yy - 2, nm, 21, fg, 500)]
    o.append(T(48, 1056, "近走・騎手・血統・時計から自動算出（オッズ非依存）／馬券は20歳から", 22, SUB))
    out("d07", W, 1080, o)

# ---------- 08 ゲート: 枠順の並びの上に印を置く ----------
def d08():
    BG, P, INK, SUB, LINE, ACC = "#0f1317", "#171d23", "#eef2f5", "#8b98a5", "#2a333c", "#ffd23f"; N_ = "'Saira Condensed','Noto Sans JP',sans-serif"
    o = [R(0, 0, W, 1150, BG), T(48, 124, VENUE, 92, INK, 900), T(250, 88, "カジ競馬 AI予想", 26, SUB, 700), T(250, 126, DATE, 32, INK, 700), T(1192, 126, "ゲートの並びで見る予想", 26, SUB, 700, "end")]
    for i, rc in enumerate(RACES):
        x, y = grid(i, 48, 164, 560, 440, 24, 28); bt = rc["tier"]; Nn = rc["N"]; gw = (560 - 48) / Nn
        o += [R(x, y, 560, 440, P, 16, ACC if bt == "battle" else None, 3), T(x + 24, y + 54, f'{rc["no"]}R', 40, INK, 700, fam=N_), T(x + 92, y + 52, f'{rc["cls"]}　{rc["dist"]}m', 26, INK, 700), T(x + 92 + 236, y + 52, rc["post"], 26, SUB, 500, fam=N_)]
        if bt: o += [R(x + 560 - 24 - 112, y + 20, 112, 44, ACC if bt == "battle" else P, 8, ACC, 2), T(x + 560 - 24 - 56, y + 51, TIERLAB[bt], 24, "#0f1317" if bt == "battle" else ACC, 900, "middle")]
        mm = {n: mk for mk, n, _, _ in rc["m"]}
        for g in range(1, Nn + 1):
            gx = x + 24 + (g - 1) * gw; c, tc = WAKU[waku(g, Nn)]; mk = mm.get(g)
            o += [R(gx + 2, y + 150, gw - 4, 44, c, 5, "#3a3f4a" if c == "#1a1a1a" else None, 2), T(gx + gw / 2, y + 182, g, 26, tc, 700, "middle", N_)]
            if mk: o += [T(gx + gw / 2, y + (128 if mk == "◎" else 134), mk, 44 if mk == "◎" else 30, ACC if mk == "◎" else (INK if mk in "○▲" else SUB), 900, "middle")]
            if mk == "◎": o.append(R(gx + 2, y + 196, gw - 4, 6, ACC))
        o.append(R(x + 24, y + 212, 512, 2, LINE))
        for k, (mk, n, nm, sc) in enumerate(rc["m"]):
            big = k == 0; yy = y + 262 + (0 if big else 22 + k * 36)
            o += [T(x + 24, yy, mk, 34 if big else 24, ACC if big else (INK if k < 3 else SUB), 900), T(x + 104, yy, n, 36 if big else 26, INK, 700, "end", N_), T(x + 122, yy, nm, 34 if big else 24, INK, 900 if big else 500)]
            if sc is not None: o.append(T(x + 536, yy, sc, 34 if big else 24, INK if big else SUB, 700, "end", N_))
    o.append(T(48, 1116, "数字の札は馬番（色は枠の色）。印はその馬の位置に置いています／馬券は20歳から", 22, SUB))
    out("d08", W, 1150, o)

# ---------- 09 レーシングプログラム: 深緑と金 ----------
def d09():
    INK, SUB, GOLD, LINE = "#f1ecdf", "#a9b3a6", "#cfae62", "#3d5a4b"; M = "'Shippori Mincho B1','Noto Serif JP',serif"; C = "'Cormorant Garamond','Shippori Mincho B1',serif"
    defs = '<linearGradient id="bg9" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0d2a20"/><stop offset="1" stop-color="#07160f"/></linearGradient>'
    o = [R(0, 0, W, 1130, "url(#bg9)"), R(28, 28, 1184, 1074, "none", 0, GOLD, 2), R(38, 38, 1164, 1054, "none", 0, GOLD, 1),
         T(620, 118, VENUE, 80, INK, 800, "middle", M, 'letter-spacing="24"'), T(620, 164, f"カジ競馬 AI予想　{DATE}", 26, GOLD, 500, "middle", M, 'letter-spacing="4"'), R(470, 186, 300, 1.5, GOLD)]
    for i, rc in enumerate(RACES):
        x, y = grid(i, 72, 216, 536, 392, 24, 24); bt = rc["tier"]
        o += [R(x, y, 536, 392, "#0b2118", 0, GOLD if bt == "battle" else LINE, 2 if bt == "battle" else 1.5),
              T(x + 28, y + 58, f"第{rc['no']}競走", 30, INK, 700, fam=M), T(x + 168, y + 56, f'{rc["cls"]}　{rc["dist"]}m　{rc["post"]}', 22, SUB, 500, fam=M, extra='letter-spacing="-1"')]
        if bt: o.append(T(x + 508, y + 56, TIERLAB[bt], 24, GOLD, 700, "end", M))
        o.append(R(x + 28, y + 76, 480, 1.2, GOLD if bt == "battle" else LINE))
        for k, (mk, n, nm, sc) in enumerate(rc["m"]):
            big = k == 0; yy = y + 134 + (0 if big else 66 + (k - 1) * 48)
            o += [T(x + 28, yy, mk, 40 if big else 26, GOLD if big else (INK if k < 3 else SUB), 700), T(x + 122, yy + (2 if big else 1), n, 54 if big else 34, GOLD if big else INK, 600, "end", C),
                  T(x + 146, yy, nm, 36 if big else 26, INK, 800 if big else 500, fam=M)]
            if sc is not None: o.append(T(x + 508, yy + 2, sc, 44 if big else 30, GOLD if big else SUB, 600, "end", C))
    o.append(T(620, 1076, "近走・騎手・血統・時計から自動算出（オッズ非依存）／馬券は20歳から", 22, SUB, 500, "middle", M))
    out("d09", W, 1130, o, defs)

# ---------- 10 勝負服: 柄の帯 ----------
def d10():
    BG, P, INK, SUB = "#131118", "#1c1a23", "#f6f4fa", "#9a95a8"; G = "'Zen Kaku Gothic New','Noto Sans JP',sans-serif"; N_ = "'Archivo Black','Noto Sans JP',sans-serif"
    pal = [("#ff5d5d", "#ffe066"), ("#4cc9f0", "#f72585"), ("#80ed99", "#22577a"), ("#ffb703", "#8338ec")]
    defs = ""
    for i, (a, b) in enumerate(pal):
        defs += [f'<pattern id="s{i}" width="40" height="40" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="40" height="40" fill="{a}"/><rect width="20" height="40" fill="{b}"/></pattern>',
                 f'<pattern id="s{i}" width="56" height="56" patternUnits="userSpaceOnUse"><rect width="56" height="56" fill="{a}"/><polygon points="28,4 52,28 28,52 4,28" fill="{b}"/></pattern>',
                 f'<pattern id="s{i}" width="48" height="48" patternUnits="userSpaceOnUse"><rect width="48" height="48" fill="{a}"/><circle cx="24" cy="24" r="12" fill="{b}"/></pattern>',
                 f'<pattern id="s{i}" width="60" height="44" patternUnits="userSpaceOnUse"><rect width="60" height="44" fill="{a}"/><polygon points="0,44 30,10 60,44 60,26 30,-8 0,26" fill="{b}"/></pattern>'][i]
    o = [R(0, 0, W, 1090, BG), T(48, 128, VENUE, 100, INK, 900, fam=G), T(270, 92, "カジ競馬 AI予想", 26, SUB, 700, fam=G), T(270, 130, DATE, 34, INK, 700, fam=G)]
    for i, rc in enumerate(RACES):
        x, y = grid(i, 48, 176, 560, 400, 24, 24); bt = rc["tier"]; a, b = pal[i]
        o += [R(x, y, 560, 400, P, 22), f'<clipPath id="c{i}"><rect x="{x}" y="{y}" width="560" height="400" rx="22"/></clipPath>', R(x, y, 96, 400, f"url(#s{i})", 0, extra=f'clip-path="url(#c{i})"'),
              R(x + 14, y + 20, 68, 68, BG, 34), T(x + 48, y + 68, rc["no"], 40, INK, 400, "middle", N_), T(x + 48, y + 380, "R", 26, BG, 400, "middle", N_),
              T(x + 124, y + 58, f'{rc["cls"]}　{rc["dist"]}m', 26, INK, 700, fam=G), T(x + 124 + 222, y + 58, rc["post"], 22, SUB, 700, fam=G)]
        if bt: o += [R(x + 560 - 24 - 116, y + 24, 116, 46, a if bt == "battle" else P, 23, a, 2), T(x + 560 - 24 - 58, y + 56, TIERLAB[bt], 24, "#131118" if bt == "battle" else a, 900, "middle", G)]
        for k, (mk, n, nm, sc) in enumerate(rc["m"]):
            big = k == 0; yy = y + 138 + (0 if big else 70 + (k - 1) * 50)
            o += [T(x + 124, yy, mk, 40 if big else 26, a if big else (INK if k < 3 else SUB), 900, fam=G), T(x + 236, yy, n, 40 if big else 28, INK, 400, "end", N_), T(x + 254, yy, nm, 28 if big else 26, INK, 900 if big else 500, fam=G)]
            if sc is not None: o.append(T(x + 536, yy, sc, 30 if big else 24, INK if big else SUB, 400, "end", N_))
    o.append(T(48, 1056, "近走・騎手・血統・時計から自動算出（オッズ非依存）／馬券は20歳から", 22, SUB, fam=G))
    out("d10", W, 1090, o, defs)

for f in (d01, d02, d03, d04, d05, d06, d07, d08, d09, d10): f()
print("ok")
