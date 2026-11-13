# -*- coding: utf-8 -*-
"""F案（新聞・夜）で全部の投稿画像の見本を作る。python3 gen_f.py → f1〜f5 の .svg。名前と数字は全部架空"""
import html
BG, CARD, ROW, INK, SUB, WEAK = "#171614", "#211f1c", "#322b27", "#efe7d6", "#b8b0a0", "#6b665c"
RED, REDFILL, GOLD = "#ff7a6b", "#a3271c", "#e8c268"
JP, SERIF, NUM = "'Noto Sans JP',sans-serif", "'Noto Serif JP',serif", "'Roboto Condensed','Noto Sans JP',sans-serif"
e = html.escape
def T(x, y, s, size, fill=INK, w=400, anchor="start", fam=None, ls=None):
    a = f' font-family="{fam}"' if fam else ""; l = f' letter-spacing="{ls}"' if ls else ""
    return f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{w}" fill="{fill}" text-anchor="{anchor}"{a}{l}>{e(str(s))}</text>'
def R(x, y, w, h, fill, stroke=None, sw=0, dash=None):
    st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""; d = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}"{st}{d}/>'
def svg(name, W, H, body):
    open(name + ".svg", "w", encoding="utf-8").write(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{JP}">\n' + R(0, 0, W, H, BG) + "\n" + "\n".join(body) + "\n</svg>")
def head(W, title, tsize=96):
    return [R(48, 44, W - 96, 6, INK), R(48, 54, W - 96, 2, INK), T(48, 150, title, tsize, INK, 900, fam=SERIF)]
def foot(W, y, lines):
    o = [R(48, y, W - 96, 2, INK)]
    for i, (s, col, wt) in enumerate(lines): o.append(T(48, y + 42 + i * 36, s, 22 if i else 24, col, wt))
    return o
def tag(xr, y, lab, kind):
    w = 28 * len(lab) + 28
    if kind == "fill": return R(xr - w, y, w, 44, REDFILL) + T(xr - w / 2, y + 32, lab, 26, "#ffffff", 700, "middle")
    if kind == "red": return R(xr - w, y, w, 44, CARD, RED, 3) + T(xr - w / 2, y + 32, lab, 26, RED, 700, "middle")
    if kind == "gold": return R(xr - w, y, w, 44, CARD, GOLD, 3) + T(xr - w / 2, y + 32, lab, 26, GOLD, 700, "middle")
    return R(xr - w, y, w, 44, CARD, SUB, 2, "6 5") + T(xr - w / 2, y + 32, lab, 26, SUB, 700, "middle")
def box(x, y, w, h, kind):
    if kind == "battle": return R(x, y, w, h, CARD, INK, 4) + R(x, y, w, 10, REDFILL)
    if kind == "aim": return R(x, y, w, h, CARD, RED, 3)
    if kind == "gold": return R(x, y, w, h, CARD, GOLD, 3)
    if kind == "dash": return R(x, y, w, h, CARD, SUB, 3, "10 8")
    return R(x, y, w, h, CARD, WEAK, 2)
def rno(x, y, no, red=False):
    return R(x, y, 74, 52, REDFILL if red else INK) + T(x + 37, y + 38, f"{no}R", 30, "#ffffff" if red else BG, 700, "middle", NUM)
MK = {"◎": RED, "○": INK, "▲": INK, "△": SUB}

# ---------- 1. 今日の★勝負 ----------
def f1():
    W, H = 1240, 1010; o = head(W, "今日の★勝負", 80)
    o += [R(700, 84, 200, 72, REDFILL), T(800, 132, "★勝負 4", 30, "#ffffff", 700, "middle"),
          T(1192, 116, "全34レース中", 26, INK, 700, "end"), T(1192, 152, "11月14日（土）朝", 26, INK, 700, "end"),
          R(48, 176, W - 96, 2, INK), T(48, 216, "発走の早い順　／　◎本命　○対抗　／　オッズ前の予想です。このあと変えません", 22, SUB)]
    D = [("14:35", "潮見 1R", "C3ー5　1400m", 5, "オッターダッシュ", "近走の時計がメンバー1位", 7, "ラッコノユメ"),
         ("16:05", "鳴瀬 2R", "2歳ー3　1300m", 10, "イタチノホシ", "近走の上がりがメンバー最速", 3, "コツメスマイル"),
         ("17:35", "潮見 5R", "B3ー2　1600m", 8, "セセラギオウジ", None, 1, "カワモノガタリ"),
         ("18:20", "鳴瀬 6R", "C1ー4　1400m", 2, "ミナモノカゼ", "この場で3着内 6走中5回", 9, "シオカゼテイオー")]
    cw, ch = 554, 250
    for i, (tm, vr, cl, n1, h1, st, n2, h2) in enumerate(D):
        x = 48 + (i % 2) * (cw + 36); y = 250 + (i // 2) * (ch + 28)
        o += [box(x, y, cw, ch, "battle"), T(x + 24, y + 62, tm, 36, INK, 700, fam=NUM),
              R(x + 130, y + 28, 150, 46, INK), T(x + 205, y + 61, vr, 26, BG, 700, "middle"), T(x + 298, y + 61, cl, 24, SUB),
              R(x + 20, y + 88, cw - 40, 2, WEAK),
              T(x + 24, y + 142, "◎", 40, RED, 700), T(x + 72, y + 142, n1, 40, RED, 700, fam=NUM), T(x + 130, y + 142, h1, 40, INK, 900)]
        yy = y + 186
        if st:
            o += [R(x + 24, yy - 28, 76, 36, INK), T(x + 62, yy - 2, "強み", 22, BG, 700, "middle"), T(x + 114, yy - 2, st, 24, INK, 500)]; yy += 42
        o += [T(x + 24, yy, "○", 26, INK, 700), T(x + 58, yy, n2, 26, INK, 700, fam=NUM), T(x + 100, yy, h2, 26, SUB, 500)]
    y = 250 + 2 * (ch + 28) + 6
    o += foot(W, y, [("◎が1着なら、この投稿の返信でお知らせします", INK, 700),
                     ("全レースの予想は2枚目から　／　近走・騎手・血統・時計から自動算出（オッズ非依存）　／　馬券は20歳から", SUB, 400)])
    svg("f1_battle", W, H, o)

# ---------- 2. 場ごとの予想 ----------
def runner(o, x, y, w, k, mk, num, name, style, score, res=None):
    big = (mk == "◎"); rh = 44; yy = y + k * rh + (8 if k else 0)
    if big: o += [R(x + 14, yy - 2, w - 28, rh + 8, ROW), R(x + 14, yy - 2, 6, rh + 8, RED)]
    b = yy + (36 if big else 31)
    o += [T(x + 28, b, mk, 34 if big else 28, MK[mk], 700), T(x + 106, b, num, 34 if big else 28, INK, 700, "end", NUM),
          T(x + 126, b, name, 30 if big else 27, INK, 700 if big else 500)]
    if style:
        sx = x + 126 + len(name) * (30 if big else 27) + 12; sw = 22 * len(style) + 16
        o += [R(sx, b - 25, sw, 32, CARD if not big else ROW, SUB, 2), T(sx + sw / 2, b - 1, style, 22, SUB, 700, "middle")]
    if res:
        o.append(T(x + w - 28, b, res, 28 if big else 26, GOLD if res == "1着" else (INK if res in ("2着", "3着") else SUB), 700, "end"))
    elif score is not None:
        o.append(T(x + w - 28, b, score, 30 if big else 26, INK if big else SUB, 700, "end", NUM))
def f2():
    W, H = 1240, 1082; o = head(W, "潮見")
    o += [T(260, 112, "カジ競馬", 26, INK, 700), T(260, 150, "AI予想　11月14日（土）", 30, INK, 700),
          R(820, 84, 372, 72, REDFILL), T(1006, 132, "★勝負 3　狙い目 6", 30, "#ffffff", 700, "middle"),
          R(48, 176, W - 96, 2, INK), T(48, 216, "◎本命　○対抗　▲単穴　△押さえ　／　赤い帯＝★勝負　赤枠＝狙い目　点線＝先行推奨（オッズ前）", 22, SUB)]
    D = [(1, "C3ー5", "15:35", "晴 19℃", "battle", "★勝負", "fill",
          [("◎", 5, "オッターダッシュ", "自在", 64), ("○", 7, "ラッコノユメ", "逃", 31), ("▲", 2, "カワウソブレイブ", "追", None), ("△", 4, "セセラギキング", "差", None), ("△", 6, "ミズカキエース", "逃", None)]),
         (2, "2歳ー3", "16:05", "曇 19℃", "aim", "狙い目", "red",
          [("◎", 10, "イタチノホシ", "自在", 52), ("○", 3, "コツメスマイル", None, 45), ("▲", 6, "ナガレボシオー", "自在", None), ("△", 1, "カワベノハナ", "差", None), ("△", 2, "ツキヨノラッコ", "追", None)]),
         (3, "C2ー4", "16:40", "曇 18℃", "dash", "先行", "dash",
          [("◎", 2, "ミナモノカゼ", "逃", 47), ("○", 9, "シオカゼテイオー", "差", 41), ("▲", 4, "ハマベノユウヒ", "自在", None), ("△", 3, "ナギサブルー", "追", None), ("△", 8, "ウミネコライト", "自在", None)]),
         (4, "B3ー2", "17:15", "雨 17℃", "", None, None,
          [("◎", 8, "セセラギオウジ", "自在", 49), ("○", 1, "カワモノガタリ", "差", 44), ("▲", 5, "ヨアケノラッコ", "自在", None), ("△", 11, "ミズベノユメ", "追", None), ("△", 6, "アサナギスター", "自在", None)])]
    cw, ch = 554, 346
    for i, (no, cl, tm, we, kind, lab, tk, ms) in enumerate(D):
        x = 48 + (i % 2) * (cw + 36); y = 250 + (i // 2) * (ch + 28)
        o += [box(x, y, cw, ch, kind), rno(x + 20, y + 22, no, kind == "battle"), T(x + 110, y + 60, cl, 30, INK, 700),
              T(x + 110 + len(cl) * 30 + 14, y + 60, tm, 26, SUB, 400, fam=NUM), T(x + 110 + len(cl) * 30 + 82, y + 60, we, 22, SUB)]
        if lab: o.append(tag(x + cw - 20, y + 26, lab, tk))
        o.append(R(x + 20, y + 84, cw - 40, 2, WEAK))
        for k, (mk, num, name, stl, sc) in enumerate(ms): runner(o, x, y + 98, cw, k, mk, num, name, stl, sc)
    y = 250 + 2 * (ch + 28) + 6
    o += foot(W, y, [("近走・騎手・血統・時計から自動算出（オッズ非依存）。数字は◎○の点数　／　馬券は20歳から", SUB, 400)])
    svg("f2_track", W, H, o)

# ---------- 3. 答え合わせ ----------
def f3():
    W, H = 1240, 1182; o = head(W, "潮見")
    o += [R(262, 96, 214, 60, INK), T(369, 138, "答え合わせ", 32, BG, 700, "middle"), T(1192, 140, "11月14日（土）", 30, INK, 700, "end"),
          R(48, 176, W - 96, 2, INK), T(48, 216, "金＝1着・的中　／　赤い帯＝★勝負　赤枠＝狙い目　点線＝見送ったレースの的中（取りこぼし）", 22, SUB)]
    D = [(1, "C3ー5", "battle", "★勝負 的中", "fill", ("的中　単勝 180円／複勝 110円", GOLD),
          [("◎", 5, "オッターダッシュ", "1着"), ("○", 7, "ラッコノユメ", "3着"), ("▲", 2, "カワウソブレイブ", "6着"), ("△", 4, "セセラギキング", "2着"), ("△", 6, "ミズカキエース", "9着")]),
         (2, "2歳ー3", "aim", "狙い的中", "red", ("的中　ワイド 10-6　350円", GOLD),
          [("◎", 10, "イタチノホシ", "3着"), ("○", 3, "コツメスマイル", "5着"), ("▲", 6, "ナガレボシオー", "2着"), ("△", 1, "カワベノハナ", "4着"), ("△", 2, "ツキヨノラッコ", "10着")]),
         (3, "C2ー4", "", None, None, ("推奨的中なし", SUB),
          [("◎", 2, "ミナモノカゼ", "6着"), ("○", 9, "シオカゼテイオー", "1着"), ("▲", 4, "ハマベノユウヒ", "9着"), ("△", 3, "ナギサブルー", "8着"), ("△", 8, "ウミネコライト", "5着")]),
         (4, "B3ー2", "dash", "見送り", "dash", ("見送り的中（買っていません）　3連複 1-5-8", SUB),
          [("◎", 8, "セセラギオウジ", "1着"), ("○", 1, "カワモノガタリ", "2着"), ("▲", 5, "ヨアケノラッコ", "3着"), ("△", 11, "ミズベノユメ", "7着"), ("△", 6, "アサナギスター", "4着")])]
    cw, ch = 554, 396
    for i, (no, cl, kind, lab, tk, (bt, bc), ms) in enumerate(D):
        x = 48 + (i % 2) * (cw + 36); y = 250 + (i // 2) * (ch + 28)
        o += [box(x, y, cw, ch, kind), rno(x + 20, y + 22, no, kind == "battle"), T(x + 110, y + 60, cl, 30, INK, 700)]
        if lab: o.append(tag(x + cw - 20, y + 26, lab, tk))
        o.append(R(x + 20, y + 84, cw - 40, 2, WEAK))
        for k, (mk, num, name, rs) in enumerate(ms): runner(o, x, y + 98, cw, k, mk, num, name, None, None, rs)
        o.append(T(x + 24, y + ch - 26, bt, 24, bc, 700))
    y = 250 + 2 * (ch + 28) + 6
    o += foot(W, y, [("朝に出した予想をそのまま採点。外れも全部のせます　／　馬券は20歳から", SUB, 400)])
    svg("f3_check", W, H, o)

# ---------- 4. 回収率／場別回収率 ----------
def pc(v): return GOLD if v >= 100 else SUB
def f4():
    W, H = 1080, 1900; o = head(W, "回収率", 80)
    o += [T(1032, 116, "対象 46レース", 26, INK, 700, "end"), T(1032, 152, "11月14日（土）", 26, INK, 700, "end"), R(48, 176, W - 96, 2, INK),
          T(48, 216, "◎から買った場合の、券種ごとの回収率（100円ずつ）。金＝100%以上", 22, SUB)]
    rows = [("◎ 単勝", 207, "12/46（26%）"), ("◎ 複勝", 129, "29/46（63%）"), ("馬連 ◎ー相手", 92, "8/46（17%）"), ("馬単 ◎→相手", 65, "4/46（9%）"),
            ("ワイド ◎ー相手", 160, "26/46（57%）"), ("3連複 ◎ー相手2", 86, "6/46（13%）"), ("3連単マルチ ◎", 60, "3/46（7%）")]
    y = 250
    o += [T(48, y + 26, "券種", 24, SUB, 700), T(560, y + 26, "回収率", 24, SUB, 700, "end"), T(1032, y + 26, "的中", 24, SUB, 700, "end"), R(48, y + 40, W - 96, 2, WEAK)]; y += 52
    for i, (lab, v, hit) in enumerate(rows):
        if i % 2 == 0: o.append(R(48, y, W - 96, 56, CARD))
        o += [T(72, y + 38, lab, 26, INK, 700), T(560, y + 40, f"{v}%", 32, pc(v), 700, "end", NUM), T(1008, y + 38, hit, 24, SUB, 400, "end")]; y += 60
    y += 20
    for lab, v, a, b in [("◎軸 合計", 124, "257,600円 → 319,400円", "+61,800"), ("○軸 合計", 35, "138,000円 → 47,860円", "−90,140"), ("総合計", 93, "395,600円 → 367,260円", "−28,340")]:
        strong = lab == "総合計"
        o += [R(48, y, W - 96, 72, CARD, INK if strong else WEAK, 4 if strong else 2), T(72, y + 47, lab, 28, INK, 700), T(400, y + 50, f"{v}%", 40, pc(v), 700, "end", NUM),
              T(800, y + 46, a, 24, SUB, 400, "end", NUM), T(1008, y + 46, b, 26, GOLD if b.startswith("+") else SUB, 700, "end", NUM)]; y += 84
    y += 14; o += foot(W, y, [("100円単位・◎軸／○軸の流し。配当は確定値。分母は買った全レース　／　馬券は20歳から", SUB, 400)])
    # 2枚目: 場別（同じ画像の下に、間をあけて並べて見せる）
    y0 = 1190; o += [R(0, y0 - 40, W, 40, "#000000"), R(48, y0 + 44, W - 96, 6, INK), R(48, y0 + 54, W - 96, 2, INK), T(48, y0 + 136, "場別 回収率", 80, INK, 900, fam=SERIF),
                     T(1032, y0 + 116, "地方", 26, INK, 700, "end"), T(1032, y0 + 152, "11月14日（土）", 26, INK, 700, "end"), R(48, y0 + 176, W - 96, 2, INK)]
    y = y0 + 200; cols = [500, 670, 850, 1008]
    o += [T(72, y + 26, "場", 24, SUB, 700)] + [T(c, y + 26, s, 24, SUB, 700, "end") for c, s in zip(cols, ["レース", "推奨", "見送り込み", "狙い目"])] + [R(48, y + 40, W - 96, 2, WEAK)]; y += 52
    for i, (nm, n, a, b, c) in enumerate([("潮見", 11, 191, 175, 37), ("鳴瀬", 12, 96, 88, 115), ("白波", 12, 43, 43, 51), ("汐入", 11, 102, 94, 139), ("全場", 46, 108, 99, 86)]):
        tot = nm == "全場"
        o.append(R(48, y, W - 96, 60, CARD, INK if tot else None, 4 if tot else 0) if (i % 2 == 0 or tot) else "")
        o += [T(72, y + 41, nm, 28, INK, 700), T(cols[0], y + 41, n, 28, INK, 400, "end", NUM)] + [T(cx, y + 42, f"{v}%", 32, pc(v), 700, "end", NUM) for cx, v in zip(cols[1:], (a, b, c))]; y += 66
    y += 16; o += foot(W, y, [("◎軸／○軸 全券種1点100円換算。金＝100%以上", SUB, 400)])
    svg("f4_recovery", W, y + 90, o)

# ---------- 5. 週間まとめ／月間まとめ ----------
def f5():
    W, H = 1240, 1210; o = head(W, "先週の成績", 80)
    o += [T(1192, 116, "地方　全287レース", 26, INK, 700, "end"), T(1192, 152, "11/16（月）〜11/22（日）", 26, INK, 700, "end"), R(48, 176, W - 96, 2, INK),
          T(48, 216, "朝に出した予想を、公式の着順と払戻で採点した結果です（外れも全部入っています）", 22, SUB)]
    bw = (W - 96 - 48) / 3
    for i, (lab, v, sub) in enumerate([("◎が3着以内", "63.1", "287レース中 181回"), ("◎の複勝を全部買うと", "90.2", "100円が90円（回収率）"), ("◎の単勝を全部買うと", "79.4", "100円が79円（回収率）")]):
        x = 48 + i * (bw + 24); o += [R(x, 244, bw, 200, CARD, WEAK, 2), T(x + bw / 2, 296, lab, 26, SUB, 700, "middle"),
                                      f'<text x="{x + bw / 2}" y="382" text-anchor="middle" font-family="{NUM}" font-weight="700" fill="{INK}"><tspan font-size="84">{v}</tspan><tspan font-size="40">%</tspan></text>',
                                      T(x + bw / 2, 422, sub, 22, SUB, 400, "middle")]
    y = 478; o += [T(48, y + 28, "区分ごと", 30, INK, 900, fam=SERIF)]; y += 52
    cols = [560, 760, 960, 1168]
    o += [T(72, y + 26, "区分", 24, SUB, 700)] + [T(c, y + 26, s, 24, SUB, 700, "end") for c, s in zip(cols, ["レース", "◎3着内", "複の回収率", "単の回収率"])] + [R(48, y + 40, W - 96, 2, WEAK)]; y += 50
    for i, (nm, col, vals) in enumerate([("★勝負", RED, ["54", "79.6%", "93.5%", "85.2%"]), ("狙い目", INK, ["121", "64.5%", "90.7%", "80.3%"]), ("そのほか", SUB, ["112", "53.6%", "88.1%", "75.6%"])]):
        if i % 2 == 0: o.append(R(48, y, W - 96, 56, CARD))
        o += [T(72, y + 38, nm, 26, col, 700)] + [T(c, y + 38, v, 26, INK, 400, "end", NUM) for c, v in zip(cols, vals)]; y += 64
    y += 20; o.append(T(48, y + 28, "日ごとの◎3着内", 30, INK, 900, fam=SERIF)); y += 52
    dw = 152; dg = (W - 96 - dw * 7) / 6
    for i, (d, n, p) in enumerate([("11/16（月）", 38, "65.8"), ("11/17（火）", 46, "58.7"), ("11/18（水）", 41, "68.3"), ("11/19（木）", 36, "61.1"), ("11/20（金）", 44, "70.5"), ("11/21（土）", 34, "55.9"), ("11/22（日）", 48, "60.4")]):
        x = 48 + i * (dw + dg); o += [R(x, y, dw, 120, CARD, WEAK, 2), T(x + dw / 2, y + 34, d, 22, SUB, 400, "middle"),
                                      f'<text x="{x + dw / 2}" y="{y + 78}" text-anchor="middle" font-family="{NUM}" font-weight="700" fill="{INK}"><tspan font-size="36">{p}</tspan><tspan font-size="22">%</tspan></text>',
                                      T(x + dw / 2, y + 108, f"{n}レース", 22, SUB, 400, "middle")]
    y += 120 + 36; o.append(T(48, y + 28, "先週いちばんの的中", 30, INK, 900, fam=SERIF)); y += 52
    o += [R(48, y, W - 96, 64, CARD), f'<text x="72" y="{y + 43}" font-size="26" fill="{INK}">11/20 潮見9R　<tspan fill="{RED}" font-weight="700">◎3</tspan> ミズカキエース　単勝 <tspan font-weight="700" fill="{GOLD}">2,340円</tspan>（8番人気）</text>']
    y += 64 + 30; o += foot(W, y, [("回収率は買った全レースが分母。100%未満＝買えば増える予想ではありません　／　馬券は20歳から", SUB, 400)])
    svg("f5_weekly", W, y + 80, o)

for f in (f1, f2, f3, f4, f5): f()
print("ok")
