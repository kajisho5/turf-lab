# -*- coding: utf-8 -*-
"""案1「枠の色」で全部の投稿画像の見本を作る。python3 gen.py → w1〜w5 の .svg。名前と数字は全部架空
決まり: 色は枠の色だけ。それ以外（札・的中・回収率）は白と灰だけで描く。"""
import html
e = html.escape
BG, P, P2, INK, SUB, LINE = "#0e1014", "#181b22", "#232731", "#f5f6f8", "#9aa3b2", "#3a3f4a"
JP, NUM = "'Noto Sans JP',sans-serif", "'Barlow Condensed','Noto Sans JP',sans-serif"
WAKU = {1:("#f4f4f4","#111111"),2:("#1a1a1a","#ffffff"),3:("#e23a2e","#ffffff"),4:("#2f73e0","#ffffff"),5:("#f4cf1f","#111111"),6:("#2fa35a","#ffffff"),7:("#f28c28","#111111"),8:("#f4a3c0","#111111")}
def waku(n, N):
    if N <= 8: return n
    single = 8 - (N - 8)
    return n if n <= single else single + (n - single + 1) // 2
def T(x, y, s, size, fill=INK, w=400, anchor="start", fam=None, extra=""):
    a = f' font-family="{fam}"' if fam else ""
    return f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{w}" fill="{fill}" text-anchor="{anchor}"{a} {extra}>{e(str(s))}</text>'
def R(x, y, w, h, fill, rx=0, stroke=None, sw=0, extra=""):
    st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}"{st} {extra}/>'
def out(name, W, H, body, defs=""):
    open(name + ".svg", "w", encoding="utf-8").write(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{JP}"><defs>{defs}</defs>\n' + R(0, 0, W, H, BG) + "\n" + "\n".join(body) + "\n</svg>")
def chip(x, y, s, n, N, fs=None):
    c, tc = WAKU[waku(n, N)]; fs = fs or int(s * 0.68)
    return R(x, y, s, s, c, max(6, s // 7), LINE if c == "#1a1a1a" else None, 2) + T(x + s / 2, y + s / 2 + fs * 0.35, n, fs, tc, 700, "middle", NUM)
def pill(xr, y, lab, kind, h=46, fs=24):
    w = len(lab) * fs + 34; x = xr - w
    if kind == "fill": return R(x, y, w, h, INK, h / 2) + T(x + w / 2, y + h / 2 + fs * 0.36, lab, fs, BG, 700, "middle"), x
    if kind == "dash": return R(x, y, w, h, "none", h / 2, SUB, 2, 'stroke-dasharray="7 6"') + T(x + w / 2, y + h / 2 + fs * 0.36, lab, fs, SUB, 700, "middle"), x
    return R(x, y, w, h, "none", h / 2, INK, 2) + T(x + w / 2, y + h / 2 + fs * 0.36, lab, fs, INK, 700, "middle"), x
def legend(xr, y):
    o = []; x = xr
    for i in range(8, 0, -1): o.append(R(x - 34, y, 34, 34, WAKU[i][0], 5, LINE if i == 2 else None, 2)); x -= 40
    return o
def box(x, y, w, h, kind):
    if kind == "battle": return R(x, y, w, h, P, 18, INK, 4)
    if kind == "aim": return R(x, y, w, h, P, 18, SUB, 2)
    if kind == "dash": return R(x, y, w, h, P, 18, SUB, 2.5, 'stroke-dasharray="10 8"')
    return R(x, y, w, h, P, 18)
STRIPE = f'<pattern id="st" width="22" height="22" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)"><rect width="22" height="22" fill="{P}"/><rect width="2" height="22" fill="{LINE}"/></pattern>'
W = 1240
def foot(y, s): return [T(48, y, s, 22, SUB)]

# ---------- 1. 今日の★勝負 ----------
def w1():
    o = [T(48, 128, "今日の★勝負", 88, INK, 900)]
    p, px = pill(1192, 44, "★勝負 4", "fill", 52, 28); o.append(p)
    o += [T(1192, 136, "全34レース中　11月14日（土）朝", 26, SUB, 500, "end"), T(48, 178, "発走の早い順。オッズを見る前の予想です。このあと変えません", 24, SUB)] + legend(1192, 158)
    D = [("14:35", "潮見 1R", "C3ー5　1400m", 10, 5, "オッターダッシュ", "近走の時計がメンバー1位", 7, "ラッコノユメ"),
         ("16:05", "鳴瀬 2R", "2歳ー3　1300m", 12, 10, "イタチノホシ", "近走の上がりがメンバー最速", 3, "コツメスマイル"),
         ("17:35", "潮見 5R", "B3ー2　1600m", 11, 8, "セセラギオウジ", None, 1, "カワモノガタリ"),
         ("18:20", "鳴瀬 6R", "C1ー4　1400m", 9, 2, "ミナモノカゼ", "この場で3着内 6走中5回", 9, "シオカゼテイオー")]
    for i, (tm, vr, cl, N, n1, h1, st, n2, h2) in enumerate(D):
        x = 48 + (i % 2) * 584; y = 216 + (i // 2) * 304; cw, ch = 560, 280
        o += [box(x, y, cw, ch, "battle"), T(x + 28, y + 62, tm, 42, INK, 700, fam=NUM), R(x + 134, y + 24, 150, 46, INK, 23), T(x + 209, y + 57, vr, 26, BG, 700, "middle"), T(x + 302, y + 57, cl, 24, SUB, 500),
              T(x + 28, y + 150, "◎", 44, INK, 700), chip(x + 88, y + 92, 84, n1, N), T(x + 192, y + 152, h1, 42, INK, 900)]
        yy = y + 214
        if st:
            o += [R(x + 28, yy - 28, 76, 36, "none", 8, SUB, 2), T(x + 66, yy - 2, "強み", 22, SUB, 700, "middle"), T(x + 118, yy - 2, st, 24, INK, 500)]; yy += 44
        o += [T(x + 28, yy, "○", 26, INK, 700), chip(x + 66, yy - 30, 40, n2, N), T(x + 120, yy, h2, 26, SUB, 500)]
    y = 216 + 2 * 304 + 20
    o += [T(48, y + 20, "◎が1着なら、この投稿の返信でお知らせします", 26, INK, 700)] + foot(y + 60, "全レースの予想は2枚目から　／　馬番の色は枠の色　／　オッズ非依存の自動算出　／　馬券は20歳から")
    out("w1_battle", W, y + 92, o)

# ---------- 2. 場ごとの予想 ----------
RACES = [
 dict(no=1, cls="C3ー5", post="15:35", wx="晴 19℃", rel="やや堅", tier="battle", N=10,
      m=[("◎",5,"オッターダッシュ","自在",64),("○",7,"ラッコノユメ","逃",31),("▲",2,"カワウソブレイブ","追",None),("△",4,"セセラギキング","差",None),("△",9,"ミズカキエース","逃",None)]),
 dict(no=2, cls="2歳ー3", post="16:05", wx="曇 19℃", rel="やや堅", tier="aim", N=12,
      m=[("◎",10,"イタチノホシ","自在",52),("○",3,"コツメスマイル",None,45),("▲",6,"ナガレボシオー","自在",None),("△",1,"カワベノハナ","差",None),("△",12,"ツキヨノラッコ","追",None)]),
 dict(no=3, cls="ユズ特別(C3)", post="16:40", wx="曇 18℃", rel="やや堅", tier="pre", N=9,
      m=[("◎",2,"ミナモノカゼ","逃",47),("○",9,"シオカゼテイオー","差",41),("▲",4,"ハマベノユウヒ","自在",None),("△",3,"ナギサブルー","追",None),("△",8,"ウミネコライト","自在",None)]),
 dict(no=4, cls="B3ー2", post="17:15", wx="雨 17℃", rel="荒れ", tier="pass", N=11,
      m=[("◎",8,"セセラギオウジ","自在",38),("○",1,"カワモノガタリ","差",36),("▲",5,"ヨアケノラッコ","自在",None),("△",11,"ミズベノユメ","追",None),("△",6,"アサナギスター","自在",None)]),
]
def runner(o, x, y, cw, k, mk, n, N, nm, st, right, rcol=None, dim=False, rw=70):
    big = k == 0; yy = y + (0 if big else 92 + (k - 1) * 54); s = 72 if big else 44
    ink = SUB if dim else INK; nx = x + 84 + s + 20
    if big:
        fs = min(36, int((cw - (nx - x) - 28 - rw - 8) / len(nm)))
        o += [T(x + 28, yy + 52, mk, 40, ink, 700), chip(x + 84, yy, s, n, N)]
        if st:
            sw = 22 * len(st) + 16
            o += [T(nx, yy + 34, nm, fs, ink, 900), R(nx, yy + 44, sw, 30, "none", 6, SUB, 2), T(nx + sw / 2, yy + 67, st, 22, SUB, 700, "middle")]
        else: o.append(T(nx, yy + 50, nm, fs, ink, 900))
        if right is not None: o.append(T(x + cw - 28, yy + 54, right, 44, rcol or ink, 700, "end", NUM))
        return
    o += [T(x + 28, yy + 33, mk, 28, ink if k < 3 else SUB, 700), chip(x + 84, yy, s, n, N), T(nx, yy + 32, nm, 27, ink, 500)]
    if st:
        sx = nx + len(nm) * 27 + 12; sw = 22 * len(st) + 16
        o += [R(sx, yy + 8, sw, 32, "none", 6, SUB, 2), T(sx + sw / 2, yy + 32, st, 22, SUB, 700, "middle")]
    if right is not None: o.append(T(x + cw - 28, yy + 32, right, 26, rcol or SUB, 700, "end", NUM))
def w2():
    o = [T(48, 128, "潮見", 100, INK, 900), T(270, 96, "11月14日（土）の予想", 34, INK, 700), T(270, 134, "19:30時点　見送り 1", 24, SUB, 500)]
    p, px = pill(1192, 44, "狙い目 6", "line", 52, 28); o.append(p); p, px = pill(px - 12, 44, "★勝負 3", "fill", 52, 28); o.append(p)
    o += legend(1192, 112) + [T(1192 - 8 * 40 - 12, 138, "馬番の色は枠の色", 22, SUB, 400, "end")]
    cw, ch = 560, 440
    for i, rc in enumerate(RACES):
        x = 48 + (i % 2) * 584; y = 176 + (i // 2) * (ch + 24); t = rc["tier"]
        o.append(box(x, y, cw, ch, {"battle": "battle", "aim": "aim", "pre": "dash"}.get(t, "")))
        if t == "pass": o.append(R(x, y, cw, ch, "url(#st)", 18, extra='opacity=".9"'))
        o += [T(x + 28, y + 62, f'{rc["no"]}R', 44, SUB if t == "pass" else INK, 700, fam=NUM), T(x + 104, y + 60, rc["cls"], 28, SUB if t == "pass" else INK, 700)]
        lab = {"battle": ("★勝負", "fill"), "aim": ("狙い目", "line"), "pre": ("先行推奨", "dash"), "pass": ("見送り", "dash")}.get(t)
        if lab: o.append(pill(x + cw - 28, y + 26, lab[0], lab[1])[0])
        o += [T(x + 28, y + 104, rc["post"], 26, SUB, 500, fam=NUM), T(x + 104, y + 103, f'{rc["wx"]}　{rc["rel"]}', 22, SUB, 400), R(x + 28, y + 120, cw - 56, 2, LINE)]
        for k, (mk, n, nm, st, sc) in enumerate(rc["m"]): runner(o, x, y + 138, cw, k, mk, n, rc["N"], nm, st, sc, dim=(t == "pass"))
    y = 176 + 2 * (ch + 24)
    o += foot(y + 22, "白い太枠＝★勝負　細い枠＝狙い目　点線＝先行推奨（オッズを見る前）　斜線＝見送り") + foot(y + 54, "近走・騎手・血統・時計から自動算出（オッズ非依存）　／　馬券は20歳から")
    out("w2_track", W, y + 86, o, STRIPE)

# ---------- 3. 答え合わせ ----------
def w3():
    o = [T(48, 128, "潮見", 100, INK, 900)]
    o.append(R(270, 62, 222, 62, INK, 31)); o += [T(381, 106, "答え合わせ", 34, BG, 700, "middle"), T(1192, 104, "11月14日（土）", 34, INK, 700, "end")] + legend(1192, 124)
    D = [(1, "C3ー5", "hit", "★勝負 的中", "fill", "的中　単勝 180円／複勝 110円", 10, [("◎",5,"オッターダッシュ",1),("○",7,"ラッコノユメ",3),("▲",2,"カワウソブレイブ",6),("△",4,"セセラギキング",2),("△",9,"ミズカキエース",9)]),
         (2, "2歳ー3", "hit", "狙い的中", "line", "的中　ワイド 10-6　350円", 12, [("◎",10,"イタチノホシ",3),("○",3,"コツメスマイル",5),("▲",6,"ナガレボシオー",2),("△",1,"カワベノハナ",4),("△",12,"ツキヨノラッコ",10)]),
         (3, "ユズ特別(C3)", "", None, None, "推奨的中なし", 9, [("◎",2,"ミナモノカゼ",6),("○",9,"シオカゼテイオー",1),("▲",4,"ハマベノユウヒ",9),("△",3,"ナギサブルー",8),("△",8,"ウミネコライト",5)]),
         (4, "B3ー2", "miss", "見送り的中", "dash", "見送り的中（買っていません）　3連複 1-5-8", 11, [("◎",8,"セセラギオウジ",1),("○",1,"カワモノガタリ",2),("▲",5,"ヨアケノラッコ",3),("△",11,"ミズベノユメ",7),("△",6,"アサナギスター",4)])]
    cw, ch = 560, 470
    for i, (no, cl, st, lab, lk, bt, N, ms) in enumerate(D):
        x = 48 + (i % 2) * 584; y = 176 + (i // 2) * (ch + 24)
        o.append(box(x, y, cw, ch, "battle" if st == "hit" else "dash" if st == "miss" else ""))
        o += [T(x + 28, y + 62, f"{no}R", 44, INK, 700, fam=NUM), T(x + 104, y + 60, cl, 28, INK, 700), R(x + 28, y + 84, cw - 56, 2, LINE)]
        if lab: o.append(pill(x + cw - 28, y + 26, lab, lk)[0])
        for k, (mk, n, nm, rk) in enumerate(ms):
            big = k == 0; yy = y + 102 + (0 if big else 92 + (k - 1) * 54); by = yy + (52 if big else 32)
            runner(o, x, y + 102, cw, k, mk, n, N, nm, None, None, rw=96)
            if rk == 1: o += [R(x + cw - 28 - 84, by - 32, 84, 42, INK, 21), T(x + cw - 28 - 42, by - 2, "1着", 26, BG, 700, "middle")]
            else: o.append(T(x + cw - 28, by, f"{rk}着", 26, INK if rk <= 3 else SUB, 700 if rk <= 3 else 400, "end"))
        o.append(T(x + 28, y + ch - 26, bt, 24, INK if st == "hit" else SUB, 700))
    y = 176 + 2 * (ch + 24)
    o += foot(y + 22, "白い太枠＝的中　点線＝見送ったレースの的中（買っていません）") + foot(y + 54, "朝に出した予想をそのまま採点。外れも全部のせます　／　馬券は20歳から")
    out("w3_check", W, y + 86, o)

# ---------- 4. 回収率／場別 ----------
def pc(v): return (INK, 700) if v >= 100 else (SUB, 500)
def w4():
    Wd = 1080; o = [T(48, 124, "回収率", 88, INK, 900), T(1032, 92, "11月14日（土）", 30, INK, 700, "end"), T(1032, 130, "対象 46レース", 24, SUB, 500, "end"), T(48, 172, "◎から買った場合（100円ずつ）。白い太字＝100%以上", 22, SUB)]
    y = 204
    for i, (lab, v, hit) in enumerate([("◎ 単勝", 207, "12/46（26%）"), ("◎ 複勝", 129, "29/46（63%）"), ("馬連 ◎ー相手", 92, "8/46（17%）"), ("馬単 ◎→相手", 65, "4/46（9%）"), ("ワイド ◎ー相手", 160, "26/46（57%）"), ("3連複 ◎ー相手2", 86, "6/46（13%）"), ("3連単マルチ ◎", 60, "3/46（7%）")]):
        c, wt = pc(v)
        if i % 2 == 0: o.append(R(48, y, Wd - 96, 58, P, 12))
        o += [T(72, y + 39, lab, 26, INK, 700), T(560, y + 42, f"{v}%", 36, c, wt, "end", NUM), T(1008, y + 39, "的中 " + hit, 24, SUB, 400, "end")]; y += 62
    y += 16
    for lab, v, a, b in [("◎軸 合計", 124, "257,600円 → 319,400円", "+61,800"), ("○軸 合計", 35, "138,000円 → 47,860円", "−90,140"), ("総合計", 93, "395,600円 → 367,260円", "−28,340")]:
        c, wt = pc(v); strong = lab == "総合計"
        o += [R(48, y, Wd - 96, 76, P, 14, INK if strong else None, 3), T(72, y + 49, lab, 28, INK, 700), T(400, y + 54, f"{v}%", 46, c, wt, "end", NUM), T(800, y + 48, a, 24, SUB, 400, "end", NUM), T(1008, y + 48, b, 28, INK if b.startswith("+") else SUB, 700, "end", NUM)]; y += 88
    o += [T(48, y + 30, "100円単位・◎軸／○軸の流し。配当は確定値。分母は買った全レース　／　馬券は20歳から", 22, SUB)]; y += 60
    y0 = y + 40; o += [R(0, y, Wd, 40, "#000000"), T(48, y0 + 124, "場別 回収率", 88, INK, 900), T(1032, y0 + 92, "11月14日（土）", 30, INK, 700, "end"), T(1032, y0 + 130, "地方", 24, SUB, 500, "end")]
    y = y0 + 170; cols = [500, 670, 850, 1008]
    o += [T(72, y + 26, "場", 24, SUB, 700)] + [T(c, y + 26, s, 24, SUB, 700, "end") for c, s in zip(cols, ["レース", "推奨", "見送り込み", "狙い目"])]; y += 46
    for i, (nm, n, a, b, c_) in enumerate([("潮見", 11, 191, 175, 37), ("鳴瀬", 12, 96, 88, 115), ("白波", 12, 43, 43, 51), ("汐入", 11, 102, 94, 139), ("全場", 46, 108, 99, 86)]):
        tot = nm == "全場"
        if i % 2 == 0 or tot: o.append(R(48, y, Wd - 96, 62, P, 12, INK if tot else None, 3))
        o += [T(72, y + 42, nm, 28, INK, 700), T(cols[0], y + 42, n, 30, INK, 500, "end", NUM)] + [T(cx, y + 44, f"{v}%", 36, pc(v)[0], pc(v)[1], "end", NUM) for cx, v in zip(cols[1:], (a, b, c_))]; y += 68
    o += [T(48, y + 30, "◎軸／○軸 全券種1点100円換算。白い太字＝100%以上", 22, SUB)]
    out("w4_recovery", Wd, y + 62, o)

# ---------- 5. 週間まとめ ----------
def w5():
    o = [T(48, 124, "先週の成績", 88, INK, 900), T(1192, 92, "11/16（月）〜11/22（日）", 30, INK, 700, "end"), T(1192, 130, "地方　全287レース", 24, SUB, 500, "end"), T(48, 172, "朝に出した予想を、公式の着順と払戻で採点した結果です（外れも全部入っています）", 22, SUB)]
    bw = (W - 96 - 48) / 3
    for i, (lab, v, sub) in enumerate([("◎が3着以内", "63.1", "287レース中 181回"), ("◎の複勝を全部買うと", "90.2", "100円が90円（回収率）"), ("◎の単勝を全部買うと", "79.4", "100円が79円（回収率）")]):
        x = 48 + i * (bw + 24); o += [R(x, 204, bw, 204, P, 18), T(x + 28, 252, lab, 26, SUB, 700),
                                      f'<text x="{x+28}" y="350" font-family="{NUM}" font-weight="700" fill="{INK}"><tspan font-size="104">{v}</tspan><tspan font-size="44">%</tspan></text>', T(x + 28, 386, sub, 22, SUB)]
    y = 440; o.append(T(48, y + 28, "区分ごと", 30, INK, 900)); y += 50
    cols = [560, 760, 960, 1168]
    o += [T(72, y + 26, "区分", 24, SUB, 700)] + [T(c, y + 26, s, 24, SUB, 700, "end") for c, s in zip(cols, ["レース", "◎3着内", "複の回収率", "単の回収率"])]; y += 44
    for i, (nm, wt, vals) in enumerate([("★勝負", 900, ["54", "79.6%", "93.5%", "85.2%"]), ("狙い目", 700, ["121", "64.5%", "90.7%", "80.3%"]), ("そのほか", 500, ["112", "53.6%", "88.1%", "75.6%"])]):
        if i % 2 == 0: o.append(R(48, y, W - 96, 58, P, 12))
        o += [T(72, y + 39, nm, 26, INK if i < 2 else SUB, wt)] + [T(c, y + 40, v, 30, INK, 500, "end", NUM) for c, v in zip(cols, vals)]; y += 64
    y += 16; o.append(T(48, y + 28, "日ごとの◎3着内", 30, INK, 900)); y += 50
    dw = 152; dg = (W - 96 - dw * 7) / 6
    for i, (d, n, p_) in enumerate([("11/16（月）", 38, "65.8"), ("11/17（火）", 46, "58.7"), ("11/18（水）", 41, "68.3"), ("11/19（木）", 36, "61.1"), ("11/20（金）", 44, "70.5"), ("11/21（土）", 34, "55.9"), ("11/22（日）", 48, "60.4")]):
        x = 48 + i * (dw + dg); o += [R(x, y, dw, 124, P, 14), T(x + dw / 2, y + 36, d, 22, SUB, 500, "middle"),
                                      f'<text x="{x+dw/2}" y="{y+84}" text-anchor="middle" font-family="{NUM}" font-weight="700" fill="{INK}"><tspan font-size="44">{p_}</tspan><tspan font-size="24">%</tspan></text>', T(x + dw / 2, y + 112, f"{n}レース", 22, SUB, 400, "middle")]
    y += 124 + 32; o.append(T(48, y + 28, "先週いちばんの的中", 30, INK, 900)); y += 50
    o += [R(48, y, W - 96, 84, P, 14), T(72, y + 53, "11/20 潮見9R", 26, SUB, 500), T(272, y + 54, "◎", 30, INK, 700), chip(316, y + 16, 52, 3, 11), T(386, y + 54, "ミズカキエース", 30, INK, 900), T(W - 72, y + 54, "単勝 2,340円（8番人気）", 28, INK, 700, "end")]
    y += 84 + 30; o += foot(y + 10, "回収率は買った全レースが分母。100%未満＝買えば増える予想ではありません　／　馬券は20歳から")
    out("w5_weekly", W, y + 44, o)

for f in (w1, w2, w3, w4, w5): f()
print("ok")
