# -*- coding: utf-8 -*-
"""JRA-VAN会員向けソフトの画面SVGを作る。文字色と背景色の組はすべてコントラスト4.5:1以上かを検査する。
サンプルの馬名・数字はすべて架空。"""
import os, sys
OUT = os.path.dirname(os.path.abspath(__file__))
W, H = 1280, 800
FONT = "'Inter','Noto Sans JP','Noto Sans CJK JP',sans-serif"
C = dict(bg="#0B0C0E", surf="#141517", line="#26282D", text="#F2F3F5", sub="#9498A1",
         side="#08090A", sidetext="#E6E7EA", sideact="#1F2127", primary="#5E6AD2", sel="#1A1C2E", chip="#23262E",
         win="#10281E", wintext="#5FD39A", red="#FF7B72", blue="#8E9BFF", warnbg="#2B2312", warntext="#E9C05A",
         okbg="#10281E", oktext="#5FD39A", track="#23262B")
checks = []

def lum(h):
    h = h.lstrip('#'); r, g, b = [int(h[i:i+2], 16)/255 for i in (0, 2, 4)]
    f = lambda c: c/12.92 if c <= 0.03928 else ((c+0.055)/1.055)**2.4
    return 0.2126*f(r)+0.7152*f(g)+0.0722*f(b)
def ratio(a, b):
    la, lb = lum(a), lum(b); hi, lo = max(la, lb), min(la, lb); return (hi+0.05)/(lo+0.05)

class Svg:
    def __init__(s, title): s.t = title; s.p = []
    def rect(s, x, y, w, h, fill, stroke=None, r=0, sw=1):
        st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ''
        s.p.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}"{st}/>')
    def text(s, x, y, t, size=16, fill=None, bg=None, weight=400, anchor="start"):
        fill = fill or C['text']; bg = bg or C['bg']
        checks.append((s.t, t, fill, bg, ratio(fill, bg), size))
        s.p.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{t}</text>')
    def line(s, x1, y1, x2, y2, col=None, sw=1): s.p.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{col or C["line"]}" stroke-width="{sw}"/>')
    def save(s, name):
        body = "\n".join(s.p)
        open(os.path.join(OUT, name), "w", encoding="utf-8").write(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}">\n'
            f'<title>{s.t}</title>\n<rect width="{W}" height="{H}" fill="{C["bg"]}"/>\n{body}\n</svg>\n')

def frame(s, active, status="データ更新 07:02　試用期間 あと23日"):
    s.rect(0, 0, 240, H, C['side']); s.line(240, 0, 240, H)
    s.rect(20, 22, 28, 28, C['primary'], r=7); s.text(34, 43, "T", 18, "#FFFFFF", C['primary'], 700, "middle")
    s.text(60, 43, "TURF LAB", 18, C['sidetext'], C['side'], 600)
    s.text(24, 96, "ワークスペース", 16, C['sub'], C['side'])
    for i, (n, k) in enumerate([("今日のレース", "G T"), ("成績", "G R"), ("設定", "G S")]):
        y = 140 + i*48
        on = (n == active)
        if on: s.rect(10, y-28, 220, 40, C['sideact'], r=6)
        bgc = C['sideact'] if on else C['side']
        s.rect(24, y-14, 8, 8, C['primary'] if on else C['line'], r=4)
        s.text(46, y, n, 17, C['sidetext'] if on else C['sub'], bgc, 600 if on else 400)
        s.text(214, y, k, 16, C['sub'], bgc, 400, "end")
    s.line(0, H-72, 240, H-72)
    s.text(24, H-38, "Ctrl+K で検索", 16, C['sub'], C['side'])
    s.line(240, 56, W, 56)
    s.text(264, 35, status, 16, C['sub'], C['bg'])
    s.text(W-24, 35, "サンプル表示（架空データ）", 16, C['sub'], C['bg'], anchor="end")

def mark(s, x, y, m, bg=None):
    col = {"◎": C['red'], "○": C['blue'], "▲": C['text'], "△": C['sub'], "☆": C['sub']}[m]
    s.text(x, y, m, 22, col, bg or C['bg'], 700)

# 1 今日のレース
s = Svg("今日のレース"); frame(s, "今日のレース")
s.text(264, 100, "11月22日（日）の中央競馬", 26, C['text'], C['bg'], 700)
for i, (n, act) in enumerate([("東京", True), ("京都", False), ("福島", False)]):
    x = 264 + i*120
    s.rect(x, 120, 108, 40, C['chip'] if act else C['bg'], C['line'], 20)
    s.text(x+54, 147, n, 17, C['text'] if act else C['sub'], C['chip'] if act else C['bg'], 600 if act else 400, "middle")
rows = [("1R", "9:55", "3歳未勝利 ダ1600", "◎7", "ミズノアカリ", False), ("2R", "10:25", "3歳未勝利 芝1800", "◎3", "ツキノウサギ", False),
        ("3R", "10:55", "2歳新馬 芝1600", "◎11", "ハルノオトモ", False), ("4R", "11:30", "3歳以上1勝 ダ1400", "◎5", "コトリノウタ", True),
        ("5R", "12:20", "3歳以上1勝 芝2000", "◎2", "ナミノアワ", False), ("6R", "12:50", "2歳未勝利 ダ1800", "◎9", "ヒカリノミチ", False),
        ("7R", "13:25", "3歳以上2勝 芝1600", "◎6", "アサヒノカケラ", True)]
s.line(264, 220, 1256, 220)
for x, t in [(284, "R"), (350, "発走"), (440, "条件"), (740, "本命"), (1130, "勝負")]: s.text(x, 208, t, 16, C['sub'], C['bg'], 500)
for i, (r, t, cond, hon, nm, win) in enumerate(rows):
    y = 220 + i*68
    s.line(264, y+68, 1256, y+68)
    if i == 3: s.rect(264, y, 992, 68, C['sel'])
    s.text(284, y+42, r, 19, C['text'], C['bg'], 600); s.text(350, y+42, t, 17, C['sub'])
    s.text(440, y+42, cond, 17)
    mark(s, 740, y+43, "◎"); s.text(772, y+42, hon[1:], 19, C['text'], C['bg'], 600); s.text(820, y+42, nm, 17)
    if win:
        s.rect(1120, y+16, 76, 34, C['win'], r=17); s.text(1158, y+40, "勝負", 17, C['wintext'], C['win'], 600, "middle")
s.text(264, 784, "※印は発走前に確定し、後から書き換えません。", 16, C['sub'])
s.save("01_today.svg")

# 2 レース詳細
s = Svg("レース詳細"); frame(s, "今日のレース")
s.text(264, 100, "東京 4R　3歳以上1勝クラス　ダート1400m", 26, C['text'], C['bg'], 700)
s.rect(900, 70, 76, 34, C['win'], r=17); s.text(938, 94, "勝負", 17, C['wintext'], C['win'], 600, "middle")
s.line(264, 164, 954, 164)
for x, t in [(280, "枠"), (330, "番"), (380, "馬名"), (620, "印"), (700, "スコア")]: s.text(x, 152, t, 16, C['sub'], C['bg'], 500)
wk = {1: ("#F2F3F5", "#0B0C0E"), 2: ("#000000", "#FFFFFF"), 3: ("#CE0000", "#FFFFFF"), 4: ("#0017C1", "#FFFFFF"), 5: ("#FFD43D", "#1A1A1A"), 6: ("#197A4B", "#FFFFFF"), 7: ("#C74700", "#FFFFFF"), 8: ("#C00063", "#FFFFFF")}
hs = [(1, 1, "ユキノシズク", "△", 61), (2, 2, "ハナノカケラ", "", 52), (3, 3, "ミナモノヒカリ", "☆", 58), (3, 4, "アオイツバサ", "", 49),
      (4, 5, "コトリノウタ", "◎", 88), (5, 6, "ヨゾラノハナ", "▲", 70), (5, 7, "シロイキセキ", "", 47), (6, 8, "カゼノオト", "○", 77),
      (7, 9, "アカツキノウタ", "", 55), (8, 10, "ハルカナタビ", "", 44)]
for i, (w, u, nm, mk, sc) in enumerate(hs):
    y = 164 + i*52; sel = (u == 5)
    s.rect(264, y, 690, 52, C['sel'] if sel else C['bg']); s.line(264, y+52, 954, y+52)
    f, tc = wk[w]; s.rect(276, y+10, 32, 32, f, '#4A4D55', 6); s.text(292, y+33, str(w), 18, tc, f, 700, "middle")
    s.text(330, y+33, str(u), 19, C['text'], C['sel'] if sel else C['bg'], 700)
    s.text(380, y+33, nm, 19, C['text'], C['sel'] if sel else C['bg'], 700 if sel else 400)
    if mk: mark(s, 620, y+35, mk, C['sel'] if sel else C['bg'])
    s.rect(700, y+20, 180, 12, C['track'], r=6); s.rect(700, y+20, int(180*sc/100), 12, C['primary'], r=6)
    s.text(900, y+34, str(sc), 17, C['text'], C['sel'] if sel else C['bg'], 400)
s.rect(976, 128, 280, 640, C['surf'], C['line'], 8)
s.text(996, 164, "5番 コトリノウタ", 22, C['text'], C['surf'], 700)
s.text(996, 192, "牝4　騎手 サンプル太郎　55.0kg", 16, C['sub'], C['surf'])
s.text(996, 232, "過去5走", 18, C['text'], C['surf'], 700)
for i, (d, rk, cl) in enumerate([("10/12 東京", "2着", "ダ1400"), ("9/21 中山", "5着", "ダ1200"), ("8/17 新潟", "1着", "ダ1400"), ("7/06 福島", "3着", "ダ1150"), ("6/08 東京", "4着", "ダ1600")]):
    y = 246 + i*34; s.text(996, y+22, d, 16, C['text'], C['surf']); s.text(1106, y+22, rk, 16, C['text'], C['surf'], 700); s.text(1166, y+22, cl, 16, C['sub'], C['surf'])
s.text(996, 450, "血統", 18, C['text'], C['surf'], 700); s.text(996, 478, "父 サンプルオー", 16, C['text'], C['surf']); s.text(996, 504, "母父 ダミーキング", 16, C['text'], C['surf'])
s.text(996, 552, "この馬が上位な理由", 18, C['text'], C['surf'], 700)
for i, t in enumerate(["ダート短距離で安定して上位", "前走の上がりが同クラスで最速級", "今回の騎手との相性が良い"]):
    s.text(996, 582+i*32, "・"+t, 16, C['text'], C['surf'])
s.text(996, 690, "予想は発走前に確定しています。", 16, C['sub'], C['surf'])
s.save("02_race_detail.svg")

# 3 成績
s = Svg("成績"); frame(s, "成績")
s.text(264, 100, "成績（このPCに貯まった予想）", 26, C['text'], C['bg'], 700)
cards = [("◎の複勝率", "63.0%", "対象 540レース"), ("勝負レースの的中", "22 / 61", "対象 61レース"), ("回収率（複勝）", "84%", "買った全540レースが分母")]
for i, (a, b, c) in enumerate(cards):
    x = 264 + i*346; s.rect(x, 128, 300, 140, C['surf'], C['line'], 8)
    s.text(x+20, 164, a, 18, C['text'], C['surf'], 700); s.text(x+20, 218, b, 45, C['text'], C['surf'], 700); s.text(x+20, 250, c, 16, C['sub'], C['surf'])
s.text(264, 316, "月ごとの◎複勝率", 20, C['text'], C['bg'], 700)
vals = [("7月", 58), ("8月", 61), ("9月", 66), ("10月", 62), ("11月", 64)]
s.line(274, 400, 1236, 400); s.line(274, 700, 1236, 700, C['text'])
for i, (m, v) in enumerate(vals):
    x = 300 + i*180; h = int(300*v/100); s.rect(x, 700-h, 90, h, C['primary'], r=4)
    s.text(x+45, 700-h-10, f"{v}%", 18, C['text'], C['bg'], 700, "middle"); s.text(x+45, 728, m, 16, C['text'], C['bg'], 400, "middle")
s.rect(264, 744, 992, 40, C['warnbg'], r=6); s.text(284, 770, "回収率は100%を下回る月もあります。数字は過去の実績で、将来の的中を約束するものではありません。", 16, C['warntext'], C['warnbg'])
s.save("03_results.svg")

# 4 セットアップ
s = Svg("初回セットアップ"); frame(s, "設定", "初回セットアップ")
s.text(264, 100, "はじめの設定", 26, C['text'], C['bg'], 700)
steps = [("JRA-VANとの接続", "接続できました（JV-Link 5.0.0）", "ok"), ("データの初回取得", "過去のレースを取っています… 62%", "run"), ("試用期間", "30日間、すべての機能が使えます（あと30日）", "trial"), ("ライセンスキー", "製品版を購入した方は、ここに入力します", "key")]
for i, (a, b, st) in enumerate(steps):
    y = 128 + i*124; s.rect(264, y, 992, 108, C['surf'], C['line'], 8)
    s.text(272, y+40, a, 20, C['text'], C['surf'], 700); s.text(272, y+76, b, 18, C['text'], C['surf'])
    if st == "ok": s.rect(1090, y+34, 140, 40, C['okbg'], r=20); s.text(1160, y+61, "完了", 18, C['oktext'], C['okbg'], 700, "middle")
    if st == "trial": s.rect(1090, y+34, 140, 40, C['okbg'], r=20); s.text(1160, y+61, "利用中", 18, C['oktext'], C['okbg'], 700, "middle")
    if st == "run":
        s.rect(272, y+88, 700, 10, C['bg'], C['line'], 5); s.rect(272, y+88, 434, 10, C['primary'], r=5)
        s.rect(1090, y+34, 140, 40, C['warnbg'], r=20); s.text(1160, y+61, "取得中", 18, C['warntext'], C['warnbg'], 700, "middle")
    if st == "key":
        s.rect(272, y+60, 460, 40, C['bg'], C['text'], 4, 2); s.text(284, y+88, "XXXX-••••-••••-••••", 18, C['text'], C['bg'])
        s.rect(1090, y+34, 140, 44, C['primary'], r=6); s.text(1160, y+63, "確認する", 18, "#FFFFFF", C['primary'], 700, "middle")
s.rect(264, 636, 992, 144, C['bg'], C['line'], 8)
s.text(272, 674, "ご利用にあたって", 18, C['text'], C['bg'], 700)
for i, t in enumerate(["データはこのPCの中だけに保存します。外部には送りません。", "JRA-VANのサービスが終わったら、取得したデータは削除してください。", "お問い合わせ：support@example.com（サンプル）"]):
    s.text(272, 708+i*30, t, 16, C['text'], C['bg'])
s.save("04_setup.svg")


# 5 買い目
s = Svg("買い目"); frame(s, "今日のレース")
s.text(264, 100, "東京 4R　買い目", 26, C['text'], C['bg'], 700)
s.rect(480, 70, 76, 34, C['win'], r=17); s.text(518, 94, "勝負", 17, C['wintext'], C['win'], 600, "middle")
s.line(264, 164, 954, 164)
for x, t in [(284, "券種"), (400, "買い目"), (760, "金額")]: s.text(x, 152, t, 16, C['sub'], C['bg'], 500)
bets = [("複勝", "5　コトリノウタ", "300円"), ("ワイド", "5 - 8", "200円"), ("ワイド", "5 - 6", "200円"), ("馬連", "5 - 8", "100円")]
for i, (k, b, m) in enumerate(bets):
    y = 164 + i*64
    s.line(264, y+64, 954, y+64)
    s.text(284, y+40, k, 18, C['text'], C['bg'], 600); s.text(400, y+40, b, 18, C['text'])
    s.text(760, y+40, m, 18, C['text'], C['bg'], 600)
s.rect(264, 436, 690, 64, C['surf'], C['line'], 8)
s.text(284, 476, "合計 4点", 18, C['sub'], C['surf']); s.text(934, 476, "800円", 22, C['text'], C['surf'], 700, "end")
s.rect(264, 524, 690, 120, C['warnbg'], r=8)
s.text(284, 560, "今の実績では、買い続けると平均で損をします。", 17, C['warntext'], C['warnbg'], 700)
s.text(284, 592, "複勝の回収率は84%（買った全540レースが分母）です。", 16, C['warntext'], C['warnbg'])
s.text(284, 620, "買い目は参考です。使える金額の範囲で楽しんでください。", 16, C['warntext'], C['warnbg'])
s.rect(976, 128, 280, 640, C['surf'], C['line'], 8)
s.text(996, 164, "今日の上限", 18, C['text'], C['surf'], 700)
s.rect(996, 180, 240, 44, C['bg'], C['line'], 6); s.text(1008, 210, "3,000円", 18, C['text'], C['bg'])
s.text(996, 256, "今日ここまで 800円", 16, C['sub'], C['surf'])
s.text(996, 282, "残り 2,200円", 16, C['text'], C['surf'])
s.rect(996, 312, 240, 52, C['primary'], r=6); s.text(1116, 346, "IPATに転送", 18, "#FFFFFF", C['primary'], 700, "middle")
for i, t in enumerate(["最後の投票ボタンは", "あなたが押します。", "ソフトが勝手に投票", "することはありません。"]):
    s.text(996, 410+i*28, t, 16, C['text'], C['surf'], 700 if i < 2 else 400)
for i, t in enumerate(["IPATの画面が変わると", "転送できなくなる", "ことがあります。", "（JRAが保証した", "方法ではありません）"]):
    s.text(996, 560+i*28, t, 16, C['sub'], C['surf'])
s.save("05_bets.svg")

bad = [c for c in checks if c[4] < 4.5]
small = [c for c in checks if c[5] < 16]
print("文字色チェック:", len(checks), "件 / 4.5未満:", len(bad), "/ 16px未満:", len(small))
for c in bad: print("  NG", c)
print("最小コントラスト:", round(min(c[4] for c in checks), 2))
sys.exit(1 if (bad or small) else 0)
