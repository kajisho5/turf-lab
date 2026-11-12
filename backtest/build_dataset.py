# -*- coding: utf-8 -*-
"""公式月次ZIPから全場・全レースのバックテスト用データセットを作る

設計: 月を日付順に処理し、各レースの特徴量を「その時点までの履歴」から作ってから、
      そのレースの結果を履歴に追記する。これで未来の情報が混入しない（リーク防止）。
      履歴は各馬の直近5走だけ保持するのでメモリは一定。

出力: backtest/nardata/bt_all.jsonl（1行=1レース）
{
  "rid": "202654071912", "d": "20260719", "tc": "54", "r": 12,
  "fn": 12, "surf": "ダ", "dist": 1300, "going": "不良", "cls": "C3",
  "name": "ファイナルレース",
  "h": [{"n": 馬番, "rk": 着順, "pop": 人気, "wk": 枠,
         "rest": 前走からの日数, "dchg": 距離変化, "tchg": 場替わり,
         "prk": 前走着順, "ppop": 前走人気, "pmiss": 前走の裏切り度(着順-人気),
         "trend": 着順トレンド(正=上向き), "vrank": 着順の振れ幅,
         "cn": 通算出走, "ct3": 通算複勝率, "wma": 体重の自己平均比, "swin": 勝ってからの走数,
         "ar": 近走平均着順, "fpf": 近走平均先行度, "np": 近走数,
         "lpf": 前走先行度, "bpf": 近走最小先行度,
         "wr": 当地複勝率, "dr": 当距離複勝率, "wt": 馬体重, "wd": 増減, "age": 齢}...],
  "pay": {"tan": {...}, "fuku": {...}, "wide": {...},
          "umaren": [組,配当], "umatan": [...], "sanpuku": [...], "santan": [...]}
}

使い方: python build_dataset.py [開始YYYYMM] [終了YYYYMM]
"""
import csv, glob, io, json, os, re, sys, zipfile
import datetime
from collections import defaultdict, deque

WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nardata")
OUT = os.path.join(WORK, "bt_all.jsonl")

TC = {'門別': '30', '盛岡': '35', '水沢': '36', '浦和': '42', '船橋': '43', '大井': '44',
      '川崎': '45', '金沢': '46', '笠松': '47', '名古屋': '48', '園田': '50', '姫路': '51',
      '高知': '54', '佐賀': '55'}          # 帯広ば(ばんえい)は平地と別物なので除外

N_PAST = 3
HIST_KEEP = 5


def read_zip_csv(z, suffix):
    for n in z.namelist():
        if n.endswith(suffix):
            return list(csv.reader(io.StringIO(z.read(n).decode("utf-8-sig", errors="replace"))))
    return []


def parse_corner(s, fn):
    """'(1,10),9,6' -> {馬番: 位置/頭数}。括弧内は同着扱いで平均順位。"""
    if not s or not fn:
        return {}
    out, pos = {}, 1
    for g in re.findall(r"\(([^)]*)\)|(\d+)", s):
        nums = re.findall(r"\d+", g[0] or g[1])
        if not nums:
            continue
        avg = pos + (len(nums) - 1) / 2.0
        for n in nums:
            out[n] = avg / fn
        pos += len(nums)
    return out


def rate(s):
    """'1-0-3-6' 形式の成績文字列から複勝率を出す。取れなければ None"""
    if not s:
        return None
    p = [int(x) for x in re.findall(r"\d+", s)]
    if len(p) < 4:
        return None
    tot = sum(p)
    return (p[0] + p[1] + p[2]) / tot if tot else None


def num(s, cast=float):
    try:
        return cast(s)
    except (TypeError, ValueError):
        return None


def pay_of(row):
    """payback.csv 1行 -> 配当dict。列定義は docs/DATA_SOURCES.md"""
    p = {}
    if row[4] and row[5].isdigit():
        p["tan"] = {row[4]: int(row[5])}
    fuku = {}
    for a, b in [(7, 8), (10, 11), (13, 14)]:
        if row[a] and row[b].isdigit():
            fuku[row[a]] = int(row[b])
    if fuku:
        p["fuku"] = fuku
    wide = {}
    for a, b, y in [(32, 33, 34), (36, 37, 38), (40, 41, 42)]:
        if row[a] and row[b] and row[y].isdigit():
            wide["-".join(sorted([row[a], row[b]], key=int))] = int(row[y])
    if wide:
        p["wide"] = wide
    if row[24] and row[26].isdigit():
        p["umaren"] = [sorted([row[24], row[25]], key=int), int(row[26])]
    if row[28] and row[30].isdigit():
        p["umatan"] = [[row[28], row[29]], int(row[30])]
    if row[44] and row[47].isdigit():
        p["sanpuku"] = [sorted([row[44], row[45], row[46]], key=int), int(row[47])]
    if row[49] and row[52].isdigit():
        p["santan"] = [[row[49], row[50], row[51]], int(row[52])]
    return p


_MARGIN = {"ハナ":0.05, "アタマ":0.1, "クビ":0.25, "同着":0.0, "大差":10.0}
def _margin(t):
    """着差（馬身表記）→ 数値。'2.1/2'=2.5馬身。読めなければ None"""
    t = (t or "").strip()
    if not t:
        return None
    if t in _MARGIN:
        return _MARGIN[t]
    m = re.match(r"^(\d+)?(?:\.(\d)/(\d))?$", t)
    if m and (m.group(1) or m.group(2)):
        v = float(m.group(1) or 0)
        if m.group(2):
            v += float(m.group(2)) / float(m.group(3))
        return v
    m2 = re.match(r"^(\d)/(\d)$", t)
    if m2:
        return float(m2.group(1)) / float(m2.group(2))
    return None


_CLV_PAT = re.compile(r"(?<![A-Za-z])([A-C])[1-3]?(?![A-Za-z])")
def _clv(name):
    """レース名 → クラスの序数（粗い）。新馬/未勝利=0, 2-3歳条件=1, C=2, B=3, A=4"""
    import unicodedata
    n = unicodedata.normalize("NFKC", name or "").replace(" ", "")
    if "新馬" in n or "未勝利" in n:
        return 0
    m = _CLV_PAT.search(n)
    if m:
        return {"C": 2, "B": 3, "A": 4}[m.group(1)]
    if re.match(r"^[23]歳", n):
        return 1
    return None


def _days(a, b):
    """YYYYMMDD 2つの日数差。書式が壊れていたら None"""
    try:
        return (datetime.date(int(a[:4]), int(a[4:6]), int(a[6:8]))
                - datetime.date(int(b[:4]), int(b[4:6]), int(b[6:8]))).days
    except Exception:
        return None


def _wts(past):
    return [p[6] for p in past if len(p) > 6 and p[6]]


def _same_mem(prev, today_names):
    """前走で当たった相手が今日何頭いるか。
    prev = {"rk": 自分の前走着順, "m": {相手名: その相手の前走着順}}
    返す3列:
      smem  再戦頭数（前走で同じレースに居た相手が今日何頭いるか）
      sbeat そのうち前走で自分が先着した頭数
      slost そのうち前走で自分より前にいた頭数
    前走が無い/相手が今日いない場合は 0 ではなく None（欠損）にする。
    ★0と欠損を混ぜない★ 「再戦が0頭」と「前走が無いので分からない」は別物で、
    0で埋めると新馬が『相手に全部負けた』側に寄る。"""
    if not prev or not prev.get("m"):
        return {"smem": None, "sbeat": None, "slost": None}
    my = prev.get("rk")
    n = beat = lost = 0
    for nm2, rk2 in prev["m"].items():
        if nm2 not in today_names:
            continue
        n += 1
        if my is None or rk2 is None:
            continue
        if my < rk2:
            beat += 1
        elif my > rk2:
            lost += 1
    return {"smem": n, "sbeat": beat, "slost": lost}


def main(start=None, end=None):
    zips = sorted(glob.glob(os.path.join(WORK, "race_*.zip")))
    if start:
        zips = [z for z in zips if start <= os.path.basename(z)[5:11] <= (end or "999912")]
    hist = defaultdict(lambda: deque(maxlen=HIST_KEEP))   # 馬名 -> 直近走
    # 馬名 -> [通算出走, 勝, 連対, 複勝, 最後に勝ってからの走数]
    # ★2026-07-29拡張★ 履歴系の特徴量（P2）のために複勝数と since_win を足した。
    car = defaultdict(lambda: [0, 0, 0, 0, 0])
    # ★2026-07-30★ 季節適性: 馬名 -> 四半期(0-3)ごとの [出走, 複勝]
    sea = defaultdict(lambda: [[0, 0], [0, 0], [0, 0], [0, 0]])
    # 騎手 -> [騎乗数, 複勝数]（リークなし: 特徴量計算の後で更新する）
    # ★なぜ足すか★ 弱点マップで「初出走馬が3割以上のレース」だけ
    # ◎複勝46.9%（通常67.4%）と-20pt落ちていた。初出走馬は近走系が全部欠損で、
    # モデルに渡せる手掛かりが枠と年齢しかない。騎手は前日発表＝事前情報で、
    # 初出走馬について唯一意味のある材料。
    # ※過去に「騎手単体は人気統制で全滅」と結論しているが、それは市場残差としての
    #   検証。LTRは市場(pop)を一切使わないので、市場と同等の情報でも足せば効く
    #   可能性がある。効かなければ却下する。
    jkr = defaultdict(lambda: [0, 0])
    # 調教師 -> [出走数, 複勝数]（同じ理屈で未検証だった列。r[18]=調教師名）
    trr = defaultdict(lambda: [0, 0])
    # 父 / 母父 -> [出走数, 複勝数]（r[11]=父馬名, r[13]=母父馬名）
    # ★騎手・厩舎とは独立した軸★ 血統は「配合で決まる素質」なので、
    #   騎手の腕・厩舎の仕上げとは別の情報を持ちうる。閾値は騎手と同じ50走。
    sir = defaultdict(lambda: [0, 0])
    dms = defaultdict(lambda: [0, 0])
    # ★2026-07-30 第9弾: 馬主・生産牧場★
    #   docs/DATA_SOURCES.md の列定義に載っていなかったが、生CSVを見たら
    #   20=馬主氏名 / 21=生産牧場名 が実在した（ドキュメントの漏れ）。
    #   これは「モデルに無い軸」に当たる。今日の実測則では効くのはこの類だけ
    #   （騎手・厩舎・父は当たり、既存列から導ける情報は4回連続で全滅）。
    #   意味づけ: 馬主＝どこに預けどう使うかの方針 / 生産＝育成の質。
    #   騎手(腕)・厩舎(仕上げ)・父(素質)のどれとも別の軸。
    own = defaultdict(lambda: [0, 0])
    brd = defaultdict(lambda: [0, 0])
    # ★2026-07-30 第6弾: 掛け合わせ★ 単体の騎手/厩舎/父が全部効いたので、
    #   「この騎手はこの競馬場が得意」「この父は短距離向き」という条件付きの強さを試す。
    #   市場は当然知っているが、モデルは持っていない情報。
    #   閾値は単体より緩める（組み合わせなので母数が小さくなる。30走以上）
    # ★2026-07-30 第7弾: 直近の調子★ 通算成績とは別の情報。
    #   「最近この騎手は乗れている/この厩舎は仕上がっている」は市場が必ず見ているが
    #   モデルは通算率しか持っていない。直近50騎乗のローリング窓で複勝率を出す。
    #   索引は毎日作り直すので本番でも同じ鮮度で引ける（daily.pyがビルドを回す）。
    jkw = defaultdict(lambda: deque(maxlen=50))   # 騎手 -> 直近50走の複勝(0/1)
    trw = defaultdict(lambda: deque(maxlen=50))   # 調教師 -> 同
    # ★2026-07-30 第8弾: 相手関係（1,690件リストの土台で唯一未実装だったもの）★
    #   「前走で当たった相手が今日何頭いるか」。単なる再戦回数ではなく
    #   **前走で自分が先着した相手 / 負けた相手** に分けて持つ。
    #   これは既存列から導けない新情報:
    #     ・近走着順(ar/prk)は「何着だったか」しか持たず、相手が誰かを知らない
    #     ・同じ3着でも、今日の上位人気を前走で負かした3着と、
    #       今日いない馬に負けた3着では意味が違う
    #   ★今日の実測則★ 効いたのは全部「モデルに無い軸」だった（騎手・厩舎・父）。
    #   既存列から導ける情報（掛け合わせ・調子・母父）は3回連続で全滅している。
    #   相手関係は前者に当たるので試す価値がある。
    #   持ち方: 馬ごとに「前走の相手と着順」だけ保持（レース全部を保持しない）。
    last_rivals = {}   # 馬名 -> {"rk": 自分の着順, "m": {相手名: 着順}}
    jkv = defaultdict(lambda: [0, 0])   # (騎手, 場) -> [走, 複勝]
    jkd = defaultdict(lambda: [0, 0])   # (騎手, 距離帯200m) -> [走, 複勝]
    sid = defaultdict(lambda: [0, 0])   # (父, 距離帯200m) -> [走, 複勝]
    nrace = nskip = 0

    # ★一時ファイルに書いてから差し替える★
    #   OUT を直接 "w" で開くと、途中で落ちた瞬間に bt_all.jsonl(440MB) が
    #   中途半端な状態で残る。この1本が壊れると人格成績・記事・DBページが
    #   まとめて道連れになる。日次で自動実行するようにしたので、
    #   失敗しても既存ファイルが無傷で残る形にしておく（2026-07-28）。
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fo:
        for zp in zips:
            with zipfile.ZipFile(zp) as z:
                rl = read_zip_csv(z, "_racelist.csv")
                hl = read_zip_csv(z, "_horselist.csv")
                pb = read_zip_csv(z, "_payback.csv")

            races = {}
            for r in rl[1:]:
                if len(r) < 66 or r[0] not in TC:
                    continue
                fn = num(r[26], int)
                if not fn:
                    continue
                last = ""
                for c in r[58:66]:
                    if c.strip():
                        last = c
                races[(r[0], r[1], r[2])] = {
                    "name": r[5], "surf": r[21], "dist": num(r[23], int), "going": r[25],
                    "fn": fn, "cls": r[27], "pf": parse_corner(last, fn),
                }

            pays = {}
            for r in pb[1:]:
                if len(r) >= 54 and r[0] in TC:
                    pays[(r[0], r[1], r[2])] = pay_of(r)

            rows = defaultdict(list)
            for r in hl[1:]:
                if len(r) >= 36 and r[0] in TC:
                    rows[(r[0], r[1], r[2])].append(r)

            # 日付順に処理（履歴の時系列を守る）
            for key in sorted(rows, key=lambda k: (k[1], k[0], int(k[2]))):
                rc = races.get(key)
                if not rc:
                    nskip += 1
                    continue
                ymd = key[1]
                rid = ymd[:4] + TC[key[0]] + ymd[4:] + key[2].zfill(2)
                # 距離帯（200m刻み）。騎手×距離・父×距離の掛け合わせキーに使う
                _band = str((rc["dist"] // 200) * 200) if rc["dist"] else "?"
                # 相手関係の突き合わせ用（このレースに出ている馬名の集合）
                _today_names = {r[6] for r in rows[key]}
                hs, after = [], []
                for r in rows[key]:
                    nm, n = r[6], r[5]
                    past = list(hist[nm])[::-1][:N_PAST]      # 新しい順
                    ranks = [p[1] for p in past if p[1] is not None]
                    pfs = [p[2] for p in past if p[2] is not None]
                    hs.append({
                        "n": n, "rk": num(r[31], int), "pop": num(r[35], int),
                        "wk": num(r[3], int), "age": num(r[8], int),
                        "ar": round(sum(ranks) / len(ranks), 3) if ranks else None,
                        "fpf": round(sum(pfs) / len(pfs), 4) if pfs else None,
                        "lpf": round(pfs[0], 4) if pfs else None,
                        "bpf": round(min(pfs), 4) if pfs else None,
                        "np": len(past),
                        "wr": rate(r[27]), "dr": rate(r[28]),
                        # ★通算勝率/連対率（無条件・密。1走以上で埋まる＝当地/当距離の穴を埋める主軸）
                        "owr": round(car[nm][1] / car[nm][0], 4) if car[nm][0] >= 1 else None,
                        "o2r": round(car[nm][2] / car[nm][0], 4) if car[nm][0] >= 1 else None,
                        "wt": num(r[22], int), "wd": num(r[23], int),
                        # ---- ★2026-07-29追加：履歴系（P2）★ ----
                        # モデルが持っていない情報を作るのが目的。
                        # past は (ymd, rk, pf, pop, dist, tc, wt) の新しい順。
                        # 古い版で作った履歴は要素が3つしかないため、添字外は
                        # 拾えず None になる（互換のため get 的に書く）。
                        "rest": _days(ymd, past[0][0]) if past else None,
                        "dchg": (rc["dist"] - past[0][4])
                                if past and len(past[0]) > 4 and past[0][4] else None,
                        "tchg": (1 if past[0][5] != key[0] else 0)
                                if past and len(past[0]) > 5 else None,
                        "prk": past[0][1] if past else None,
                        "ppop": past[0][3] if past and len(past[0]) > 3 else None,
                        # 前走で人気を裏切った度合い（着順−人気。正=裏切り）
                        "pmiss": (past[0][1] - past[0][3])
                                 if past and len(past[0]) > 3 and past[0][1] is not None
                                 and past[0][3] is not None else None,
                        # 近走の着順トレンド（古い平均−最新。正=上向き）
                        "trend": (round(sum(ranks[1:]) / len(ranks[1:]) - ranks[0], 3)
                                  if len(ranks) >= 2 else None),
                        # 着順のばらつき（範囲。大きい=気分屋）
                        "vrank": (max(ranks) - min(ranks)) if len(ranks) >= 2 else None,
                        "cn": car[nm][0] or None,
                        "ct3": round(car[nm][3] / car[nm][0], 4) if car[nm][0] >= 3 else None,
                        # 馬体重の近走平均からの差（自己比較）
                        "wma": (num(r[22], int) - round(sum(w for w in _wts(past)) / len(_wts(past))))
                               if num(r[22], int) and _wts(past) else None,
                        "swin": car[nm][4] if car[nm][0] >= 1 else None,
                        # ---- ★2026-07-30追加：第2弾（5列）★ ----
                        # 乗り替わり（前走と騎手が違うか）。騎手は前日発表なので事前情報。
                        "jkchg": (0 if past[0][7] == (r[14] or "").strip() else 1)
                                 if past and len(past[0]) > 7 and past[0][7]
                                 and (r[14] or "").strip() else None,
                        # 前走の着差（馬身。勝ち馬は空欄=None のまま）
                        "pgap": past[0][8] if past and len(past[0]) > 8 else None,
                        # 間隔の「その馬の普段」とのズレ（日）。過去の間隔2本以上で算出
                        "restdev": (lambda _g: (_days(ymd, past[0][0]) - sum(_g) / len(_g))
                                    if _g and len(_g) >= 2 and _days(ymd, past[0][0]) is not None
                                    else None)(
                                    [d for d in (_days(past[i][0], past[i + 1][0])
                                                 for i in range(len(past) - 1)) if d is not None]),
                        # クラスの昇降（今回の序数 − 前走の序数。正=昇級）
                        "clvchg": (_clv(rc["name"]) - past[0][9])
                                  if past and len(past[0]) > 9 and past[0][9] is not None
                                  and _clv(rc["name"]) is not None else None,
                        # 季節適性: その馬の「同じ四半期」の過去複勝率（3走以上のみ）
                        "sqr": (lambda _e: round(_e[1] / _e[0], 4) if _e[0] >= 3 else None)(
                                sea[nm][(int(ymd[4:6]) - 1) // 3]),
                        # ★2026-07-30 第3弾★ 騎手の事前複勝率（50騎乗以上のみ。
                        # 少数騎乗の騎手は率が暴れるので欠損にする）
                        "jkr": (lambda _e: round(_e[1] / _e[0], 4) if _e[0] >= 50 else None)(
                                jkr[(r[14] or "").strip()]),
                        # 調教師の事前複勝率（騎手と同じ扱い。50走未満は欠損）
                        "trr": (lambda _e: round(_e[1] / _e[0], 4) if _e[0] >= 50 else None)(
                                trr[(r[18] or "").strip()]),
                        # 父・母父の事前複勝率（同上）
                        "sir": (lambda _e: round(_e[1] / _e[0], 4) if _e[0] >= 50 else None)(
                                sir[(r[11] or "").strip()]),
                        "dms": (lambda _e: round(_e[1] / _e[0], 4) if _e[0] >= 50 else None)(
                                dms[(r[13] or "").strip()]),
                        # 直近の調子（20走以上入っていれば率を出す）
                        "jkf": (lambda _d: round(sum(_d) / len(_d), 4) if len(_d) >= 20 else None)(
                                jkw[(r[14] or "").strip()]),
                        "trf": (lambda _d: round(sum(_d) / len(_d), 4) if len(_d) >= 20 else None)(
                                trw[(r[18] or "").strip()]),
                        # 相手関係（前走で当たった相手が今日何頭いるか）
                        **_same_mem(last_rivals.get(nm), _today_names),
                        # 馬主・生産牧場の事前複勝率（騎手と同じ50走閾値）
                        "own": (lambda _e: round(_e[1] / _e[0], 4) if _e[0] >= 50 else None)(
                                own[(r[20] or "").strip()]),
                        "brd": (lambda _e: round(_e[1] / _e[0], 4) if _e[0] >= 50 else None)(
                                brd[(r[21] or "").strip()]),
                        # 掛け合わせ（30走以上。母数が小さいので閾値を緩める）
                        "jkv": (lambda _e: round(_e[1] / _e[0], 4) if _e[0] >= 30 else None)(
                                jkv[((r[14] or "").strip(), key[0])]),
                        "jkd": (lambda _e: round(_e[1] / _e[0], 4) if _e[0] >= 30 else None)(
                                jkd[((r[14] or "").strip(), _band)]),
                        "sid": (lambda _e: round(_e[1] / _e[0], 4) if _e[0] >= 30 else None)(
                                sid[((r[11] or "").strip(), _band)]),
                    })
                    after.append((nm, num(r[31], int), rc["pf"].get(n), num(r[35], int), num(r[22], int),
                                  (r[14] or "").strip(), _margin(r[33] if len(r) > 33 else ""),
                                  (r[18] or "").strip(),
                                  (r[11] or "").strip(), (r[13] or "").strip(),
                                  _band, (r[20] or "").strip(), (r[21] or "").strip()))

                fo.write(json.dumps({
                    "rid": rid, "d": ymd, "tc": TC[key[0]], "r": int(key[2]),
                    "fn": rc["fn"], "surf": rc["surf"], "dist": rc["dist"],
                    "going": rc["going"], "cls": rc["cls"], "name": rc["name"],
                    "h": hs, "pay": pays.get(key, {}),
                }, ensure_ascii=False) + "\n")
                nrace += 1

                # 相手関係の更新（★特徴量計算の後＝リークなし★）
                #   このレースの結果を、出走各馬の「前走の相手」として保存する。
                _res = {r[6]: num(r[31], int) for r in rows[key]}
                for _nm3, _rk3 in _res.items():
                    last_rivals[_nm3] = {"rk": _rk3,
                                         "m": {k3: v3 for k3, v3 in _res.items() if k3 != _nm3}}

                _race_clv = _clv(rc["name"])
                _q = (int(ymd[4:6]) - 1) // 3
                for nm, rk, pf, ppop, pwt, jk, mg, tr_, si_, dm_, bd_, ow_, br_ in after:  # 履歴更新は特徴量計算の後
                    hist[nm].append((ymd, rk, pf, ppop, rc["dist"], key[0], pwt, jk, mg, _race_clv))
                    if jk:                                     # 騎手の通算（リークなし）
                        j = jkr[jk]
                        j[0] += 1
                        if rk is not None:
                            j[1] += (rk <= 3)
                    if tr_:                                    # 調教師の通算（同上）
                        t_ = trr[tr_]
                        t_[0] += 1
                        if rk is not None:
                            t_[1] += (rk <= 3)
                    for _nm2, _tbl in ((si_, sir), (dm_, dms)):  # 父・母父の通算（同上）
                        if _nm2:
                            e2 = _tbl[_nm2]
                            e2[0] += 1
                            if rk is not None:
                                e2[1] += (rk <= 3)
                    # 直近の調子（窓に押し込む。特徴量計算の後＝リークなし）
                    if jk: jkw[jk].append(1 if (rk is not None and rk <= 3) else 0)
                    if tr_: trw[tr_].append(1 if (rk is not None and rk <= 3) else 0)
                    for _nm4, _tbl4 in ((ow_, own), (br_, brd)):   # 馬主・生産（同上）
                        if _nm4:
                            e4 = _tbl4[_nm4]
                            e4[0] += 1
                            if rk is not None:
                                e4[1] += (rk <= 3)
                    # 掛け合わせ（騎手×場 / 騎手×距離帯 / 父×距離帯）
                    for _k3, _tbl3 in (((jk, key[0]), jkv), ((jk, bd_), jkd), ((si_, bd_), sid)):
                        if _k3[0]:
                            e3 = _tbl3[_k3]
                            e3[0] += 1
                            if rk is not None:
                                e3[1] += (rk <= 3)
                    if rk is not None:
                        e = sea[nm][_q]
                        e[0] += 1
                        e[1] += (rk <= 3)
                    c = car[nm]                                # 通算（無条件）
                    c[0] += 1
                    if rk is not None:
                        c[1] += (rk == 1)
                        c[2] += (rk <= 2)
                        c[3] += (rk <= 3)
                        c[4] = 0 if rk == 1 else c[4] + 1     # 勝てば0に戻る
                    else:
                        c[4] += 1

            print(f"  {os.path.basename(zp)}: 累計 {nrace:,}R", flush=True)

    # ★騎手・調教師の集計をサイドカーに書き出す★（build_jockey_index.py が索引に変換）
    #   jkr/trr列は値だけで名前を持たないので、名前→成績はここで出しておく必要がある。
    try:
        for suffix, table in ((".jockeys", jkr), (".trainers", trr),
                              (".sires", sir), (".damsires", dms)):
            with open(OUT + suffix, "w", encoding="utf-8") as jf:
                for nm, (n, t3) in sorted(table.items()):
                    if n:
                        jf.write(json.dumps([nm, n, t3], ensure_ascii=False) + "\n")
    except OSError as e:
        print(f"  騎手/調教師サイドカーの書き出し失敗（本体は無事）: {e}")

    # 1レースも書けていないなら差し替えない（入力が空/壊れている時に本体を消さない）
    if nrace == 0:
        os.remove(tmp)
        raise SystemExit("1レースも書けなかったので差し替えを中止した")
    os.replace(tmp, OUT)
    print(f"完了: {nrace:,}レース / racelist欠落スキップ {nskip} -> {OUT}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None,
         sys.argv[2] if len(sys.argv) > 2 else None)
