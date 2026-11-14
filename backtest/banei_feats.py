# -*- coding: utf-8 -*-
"""ばんえい専用モデルの材料づくりと採点（標準ライブラリだけ。学習と毎朝の採点の両方がこれを使う＝同じ計算になる）

データ: keiba.go.jp 公式の月ごとのZIP（r201301.zip か race_201301.zip）の「帯広ば」。
材料は全部「そのレースより前に分かること」だけ。人気・オッズ・当日の馬体重・馬場の水分は使わない
（当日の馬体重は朝8:30にはまだ出ていない。水分は測ったら効かなかった。docs/FACTS.md 2026-11-14）。
"""
import csv, glob, io, json, math, os, zipfile, collections

V = "帯広ば"
NAN = float("nan")
NRUN_CAP = 10     # 出走数は10で頭打ち（データの始まりが違っても同じ値になるように）
FE = ["r3", "r5", "lastr", "bestr", "z3", "z5", "zbest", "zlast", "nrun", "cwr", "cp3", "swr", "sp3",
      "load", "loadrel", "loadchg", "age", "sex", "rest", "prize", "przchg", "przrel", "jk3", "jkn", "fn", "num"]


def num(s, d=None):
    try:
        return float(str(s).replace("+", "").replace(",", ""))
    except Exception:  # noqa: BLE001
        return d


def tsec(s):
    """ "1515" → 111.5（1分51秒5）"""
    s = str(s or "").strip()
    if not s.isdigit() or len(s) < 3:
        return None
    return int(s[:-3] or 0) * 60 + int(s[-3:-1]) + int(s[-1]) / 10


def rec4(s):
    """ "5-1-3-17" → (1着, 3着内, 出走)"""
    p = str(s or "").split("-")
    if len(p) != 4 or not all(x.strip().isdigit() for x in p):
        return None
    a = [int(x) for x in p]
    return (a[0], a[0] + a[1] + a[2], sum(a))


def days(a, b):
    """YYYYMMDD どうしの日数（b − a）"""
    import datetime
    f = lambda s: datetime.date(int(s[:4]), int(s[4:6]), int(s[6:8]))  # noqa: E731
    return (f(b) - f(a)).days


def load(cache):
    """ばんえいのレースを日付・レース番号の順に返す。これから走るレース（着順が空）も含む"""
    paths = sorted(set(glob.glob(os.path.join(cache, "r[0-9]*.zip")) + glob.glob(os.path.join(cache, "race_[0-9]*.zip"))),
                   key=lambda p: "".join(c for c in os.path.basename(p) if c.isdigit()))
    races = {}
    for zp in paths:
        z = zipfile.ZipFile(zp)

        def rd(key):
            n = [x for x in z.namelist() if key in x]
            return csv.DictReader(io.TextIOWrapper(z.open(n[0]), encoding="utf-8-sig", errors="replace")) if n else []
        for r in rd("racelist"):
            if r["競馬場"] != V:
                continue
            k = (r["競走年月日"], int(r["レース番号"]))
            races[k] = dict(d=k[0], r=k[1], prize=num(r.get("1着賞金(円)"), 0) or 0, name=r.get("レース名", ""), h=[], pay={})
        for h in rd("horselist"):
            if h["競馬場"] != V:
                continue
            k = (h["競走年月日"], int(h["レース番号"]))
            if k in races:
                races[k]["h"].append(h)
        for p in rd("payback"):
            if p["競馬場"] != V:
                continue
            k = (p["競走年月日"], int(p["レース番号"]))
            if k not in races:
                continue
            pay = races[k]["pay"]
            if p.get("単勝組番") and num(p.get("単勝払戻金（円）")):
                pay.setdefault("tan", {})[p["単勝組番"].strip()] = num(p["単勝払戻金（円）"])
            for i in "123":
                if p.get("複勝組番" + i) and num(p.get("複勝払戻金" + i + "（円）")):
                    pay.setdefault("fuku", {})[p["複勝組番" + i].strip()] = num(p["複勝払戻金" + i + "（円）"])
    return [races[k] for k in sorted(races)]


def mean(a):
    return sum(a) / len(a)


def build(races):
    """レースごとに材料を作る。返り値の要素: {d, r, n, done, num[], rk[], pop[], pay, X[[...]]}
    done＝結果が入っているか。結果が入っているレースは着順のある馬だけ、これからのレースは全頭を数える"""
    hist = collections.defaultdict(list)     # 馬名 → [(日付, 着順÷頭数, 時計の良し悪し, 賞金, そりの重さ)]
    jk = collections.defaultdict(list)       # 騎手 → [(日付, 3着内か)]
    out = []
    for rc in races:
        fin = [h for h in rc["h"] if h["着順"].strip().isdigit()]
        done = len(fin) > 0
        hs = fin if done else [h for h in rc["h"] if h["馬番"].strip().isdigit()]
        n = len(hs)
        loads = [num(h["負担重量"]) for h in hs if num(h["負担重量"])]
        X = []
        for h in hs:
            H = hist[h["馬名"]]
            f = dict.fromkeys(FE, NAN)
            rk = [x[1] for x in H]
            zz = [x[2] for x in H if x[2] is not None]
            if rk:
                f["r3"] = mean(rk[-3:]); f["r5"] = mean(rk[-5:]); f["lastr"] = rk[-1]; f["bestr"] = min(rk[-5:])
            if zz:
                f["z3"] = mean(zz[-3:]); f["z5"] = mean(zz[-5:]); f["zbest"] = max(zz[-5:]); f["zlast"] = zz[-1]
            f["nrun"] = min(len(H), NRUN_CAP)
            c = rec4(h["全成績"])
            if c and c[2]:
                f["cwr"] = c[0] / c[2]; f["cp3"] = c[1] / c[2]
            s = rec4(h["騎手成績"])
            if s and s[2]:
                f["swr"] = s[0] / s[2]; f["sp3"] = s[1] / s[2]
            ld = num(h["負担重量"])
            if ld:
                f["load"] = ld
                if loads:
                    f["loadrel"] = ld - mean(loads)
                if H and H[-1][4]:
                    f["loadchg"] = ld - H[-1][4]
            a = num(h["齢"])
            if a is not None:
                f["age"] = a
            sx = {"牡": 0, "牝": 1, "セ": 2}.get(h["性"].strip())
            if sx is not None:
                f["sex"] = sx
            f["prize"] = math.log1p(rc["prize"])
            if H:
                f["rest"] = days(H[-1][0], rc["d"])
                f["przchg"] = f["prize"] - math.log1p(H[-1][3])
                f["przrel"] = f["prize"] - mean([math.log1p(x[3]) for x in H[-5:]])
            lim = str(int(rc["d"]) - 10000)                     # 1年前の同じ日
            J = [x for x in jk[h["騎手名"]] if x[0] >= lim]
            if len(J) >= 20:
                f["jk3"] = sum(x[1] for x in J) / len(J)
            f["jkn"] = len(J)
            f["fn"] = n
            nb = num(h["馬番"])
            if nb is not None:
                f["num"] = nb
            X.append([f[k] for k in FE])
        out.append(dict(d=rc["d"], r=rc["r"], n=n, done=done, pay=rc["pay"], X=X,
                        num=[h["馬番"].strip() for h in hs], rk=[int(h["着順"]) if done else None for h in hs],
                        pop=[num(h.get("人気"), 99) for h in hs]))
        if not done:
            continue
        # そのレースの結果を、あとのレース用に積む
        ts = [tsec(h["タイム"]) for h in hs]
        tv = [t for t in ts if t]
        mu = sd = None
        if len(tv) >= 3:
            mu = mean(tv); sd = math.sqrt(mean([(t - mu) ** 2 for t in tv]))
        for h, t in zip(hs, ts):
            z = None
            if t and mu is not None and sd and sd > 0:
                z = max(-3.0, min(3.0, (mu - t) / sd))           # ＋なら同じレースの平均より速い
            hist[h["馬名"]].append((rc["d"], int(h["着順"]) / n, z, rc["prize"], num(h["負担重量"])))
            jk[h["騎手名"]].append((rc["d"], 1 if int(h["着順"]) <= 3 else 0))
    return out


def predict(model, x):
    """LightGBM の木（dump_model の形）を標準ライブラリだけでたどって点数を出す。x は FE の順の値（NaN あり）"""
    tot = 0.0
    for t in model["trees"]:
        nd = t
        while "leaf_value" not in nd:
            v = x[nd["split_feature"]]
            if v != v:                                           # NaN
                if nd.get("missing_type") == "NaN":
                    left = bool(nd.get("default_left"))
                else:
                    left = 0.0 <= nd["threshold"]               # 欠けを0として比べる（LightGBM の missing_type=None と同じ）
            else:
                left = v <= nd["threshold"]
            nd = nd["left_child"] if left else nd["right_child"]
        tot += nd["leaf_value"]
    return tot


def conf(scores):
    """抜け具合 c = 0.6×(1位−平均)/幅 + 0.4×(1位−2位)/幅（平地の★勝負の決め方と同じ式）"""
    if len(scores) < 2:
        return None
    s = sorted(scores, reverse=True)
    spread = (s[0] - s[-1]) or 1.0
    return 0.6 * (s[0] - mean(scores)) / spread + 0.4 * (s[0] - s[1]) / spread
