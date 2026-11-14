# -*- coding: utf-8 -*-
"""ばんえい専用の順位学習モデルを手元で作って測る（2026-11-14・本番は触らない）

ねらい: 今の手作りの点数（baneiScore・2023年以降の◎3着内 47.6%・docs/FACTS.md）より良くなるかを確かめる。
データ: backtest/nardata/race_YYYYMM.zip（keiba.go.jp 公式）の「帯広ば」。学習 2013〜2022／検証 2023〜。
材料は全部「そのレースより前に分かること」だけ（人気・オッズは使わない）。
  近走の着順／同じレースの中での時計の良し悪し（水分の影響を消すため、そのレースの平均との差で見る）／
  そりの重さとその増減／馬体重と増減／通算成績／騎手の近1年の成績／賞金（クラスの代わり）と前走からの上げ下げ／間隔／年齢 など。
水分の使い方を3通り測る:
  none  … 水分を使わない
  prev  … 前の開催日の水分（朝の時点で分かる）
  real  … そのレースの水分（朝には分からない＝上限の目安。本番では使えない）
測るもの（検証の期間・分母は全レース）: ◎（点数1位）が3着以内の割合／単勝の的中と回収率／複勝の回収率。
くらべる相手: 1番人気を◎にした場合（同じレースで数える）。
使い方: python3 backtest/bt_banei_ltr.py
"""
import csv, io, json, math, os, sys, zipfile, glob, collections
import numpy as np, lightgbm as lgb
HERE = os.path.dirname(os.path.abspath(__file__)); ND = os.path.join(HERE, "nardata")
V = "帯広ば"; SPLIT = "20230101"
NOWT = os.environ.get("BANEI_NOWT", "1") == "1"   # 1＝当日の馬体重を使わない（朝の予想と同じ条件・既定）／0＝使う（発走の直前なら分かる）

def num(s, d=None):
    try: return float(str(s).replace("+", "").replace(",", ""))
    except Exception: return d
def tsec(s):   # "1515" → 1分51秒5
    s = str(s or "").strip()
    if not s.isdigit() or len(s) < 3: return None
    return int(s[:-3] or 0) * 60 + int(s[-3:-1]) + int(s[-1]) / 10
def rec4(s):   # "5-1-3-17" → (勝ち, 3着内, 出走)
    p = str(s or "").split("-")
    if len(p) != 4 or not all(x.strip().isdigit() for x in p): return None
    a = [int(x) for x in p]; n = sum(a)
    return (a[0], a[0] + a[1] + a[2], n)

def load():
    races = {}
    for zp in sorted(glob.glob(os.path.join(ND, "race_*.zip"))):
        z = zipfile.ZipFile(zp)
        def rd(key):
            n = [x for x in z.namelist() if key in x]
            return list(csv.DictReader(io.TextIOWrapper(z.open(n[0]), encoding="utf-8-sig", errors="replace"))) if n else []
        for r in rd("racelist"):
            if r["競馬場"] != V: continue
            k = (r["競走年月日"], int(r["レース番号"]))
            races[k] = dict(d=k[0], r=k[1], moist=num(r["馬場"]), prize=num(r["1着賞金(円)"], 0), name=r["レース名"], cond=r["条件"], h=[], pay={})
        for h in rd("horselist"):
            if h["競馬場"] != V: continue
            k = (h["競走年月日"], int(h["レース番号"]))
            if k in races: races[k]["h"].append(h)
        for p in rd("payback"):
            if p["競馬場"] != V: continue
            k = (p["競走年月日"], int(p["レース番号"]))
            if k not in races: continue
            pay = races[k]["pay"]
            if p.get("単勝組番") and num(p.get("単勝払戻金（円）")): pay.setdefault("tan", {})[p["単勝組番"].strip()] = num(p["単勝払戻金（円）"])
            for i in "123":
                if p.get("複勝組番" + i) and num(p.get("複勝払戻金" + i + "（円）")): pay.setdefault("fuku", {})[p["複勝組番" + i].strip()] = num(p["複勝払戻金" + i + "（円）"])
    return [races[k] for k in sorted(races)]

FE = ["r3", "r5", "lastr", "bestr", "z3", "z5", "zbest", "zlast", "nrun", "cwr", "cp3", "swr", "sp3",
      "load", "loadrel", "loadchg", "wt", "wd", "wtrel", "age", "sex", "rest", "prize", "przchg", "przrel",
      "jk3", "jkn", "fn", "num", "wetpref", "moist", "wet_x_pref", "lowload_wet"]

def build(races, moist_mode):
    hist = collections.defaultdict(list)       # 馬名 → 過去の走り [(日付, 着順率, z, 賞金, そり, 水分)]
    jk = collections.defaultdict(list)         # 騎手 → [(日付, 3着内か)]
    day_m = {}                                 # 日付 → その日の水分の平均
    for rc in races:
        if rc["moist"] is not None: day_m.setdefault(rc["d"], []).append(rc["moist"])
    days = sorted(day_m); day_avg = {d: sum(v) / len(v) for d, v in day_m.items()}
    prev_m = {d: (day_avg[days[i - 1]] if i else None) for i, d in enumerate(days)}
    allm = sorted(x for v in day_m.values() for x in v); med = allm[len(allm) // 2] if allm else 1.5
    out = []
    for rc in races:
        hs = [h for h in rc["h"] if h["着順"].strip().isdigit()]
        if len(hs) < 5: 
            hs_all = hs
        n = len(hs)
        m = rc["moist"] if moist_mode == "real" else prev_m.get(rc["d"]) if moist_mode == "prev" else None
        loads = [num(h["負担重量"]) for h in hs if num(h["負担重量"])]; wts = [num(h["馬体重"]) for h in hs if num(h["馬体重"])]
        rows = []
        for h in hs:
            nm = h["馬名"]; H = hist[nm]; f = {}
            rk = [x[1] for x in H]; zz = [x[2] for x in H if x[2] is not None]
            f["r3"] = np.mean(rk[-3:]) if rk else np.nan; f["r5"] = np.mean(rk[-5:]) if rk else np.nan
            f["lastr"] = rk[-1] if rk else np.nan; f["bestr"] = min(rk[-5:]) if rk else np.nan
            f["z3"] = np.mean(zz[-3:]) if zz else np.nan; f["z5"] = np.mean(zz[-5:]) if zz else np.nan
            f["zbest"] = max(zz[-5:]) if zz else np.nan; f["zlast"] = zz[-1] if zz else np.nan
            f["nrun"] = len(H)
            c = rec4(h["全成績"]); f["cwr"] = c[0] / c[2] if c and c[2] else np.nan; f["cp3"] = c[1] / c[2] if c and c[2] else np.nan
            s = rec4(h["騎手成績"]); f["swr"] = s[0] / s[2] if s and s[2] else np.nan; f["sp3"] = s[1] / s[2] if s and s[2] else np.nan
            ld = num(h["負担重量"]); f["load"] = ld if ld else np.nan
            f["loadrel"] = ld - np.mean(loads) if ld and loads else np.nan
            f["loadchg"] = ld - H[-1][4] if ld and H and H[-1][4] else np.nan
            w = num(h["馬体重"]); f["wt"] = w if w else np.nan; f["wd"] = num(h["馬体重増減"], np.nan); f["wtrel"] = w - np.mean(wts) if w and wts else np.nan
            f["age"] = num(h["齢"], np.nan); f["sex"] = {"牡": 0, "牝": 1, "セ": 2}.get(h["性"].strip(), np.nan)
            if H:
                a = H[-1][0]; f["rest"] = (np.datetime64(f"{rc['d'][:4]}-{rc['d'][4:6]}-{rc['d'][6:]}") - np.datetime64(f"{a[:4]}-{a[4:6]}-{a[6:]}")).astype(int)
            else: f["rest"] = np.nan
            f["prize"] = math.log1p(rc["prize"]); f["przchg"] = f["prize"] - math.log1p(H[-1][3]) if H else np.nan
            f["przrel"] = f["prize"] - np.mean([math.log1p(x[3]) for x in H[-5:]]) if H else np.nan
            J = [x for x in jk[h["騎手名"]] if x[0] >= str(int(rc["d"]) - 10000)]
            f["jk3"] = sum(x[1] for x in J) / len(J) if len(J) >= 20 else np.nan; f["jkn"] = len(J)
            f["fn"] = n; f["num"] = num(h["馬番"], np.nan)
            wet = [x[1] for x in H if x[5] is not None and x[5] >= med]; dry = [x[1] for x in H if x[5] is not None and x[5] < med]
            f["wetpref"] = (np.mean(dry) - np.mean(wet)) if len(wet) >= 3 and len(dry) >= 3 else np.nan   # ＋なら重い（水分の多い）馬場のほうが着順が良い
            f["moist"] = m if m is not None else np.nan
            f["wet_x_pref"] = f["wetpref"] * (m - med) if m is not None and not np.isnan(f["wetpref"]) else np.nan
            f["lowload_wet"] = f["loadrel"] * (m - med) if m is not None and not np.isnan(f["loadrel"]) else np.nan
            if NOWT: f["wt"] = f["wd"] = f["wtrel"] = np.nan     # 当日の馬体重は朝8:30にはまだ出ていない → 朝の予想として測る時は使わない
            rows.append(f)
        out.append(dict(d=rc["d"], r=rc["r"], n=n, pay=rc["pay"], X=[[f[k] for k in FE] for f in rows],
                        rk=[int(h["着順"]) for h in hs], num=[h["馬番"].strip() for h in hs], pop=[num(h["人気"], 99) for h in hs]))
        # そのレースの結果を、あとのレース用に積む
        ts = [tsec(h["タイム"]) for h in hs]; tv = [t for t in ts if t]
        mu = np.mean(tv) if len(tv) >= 3 else None; sd = np.std(tv) if len(tv) >= 3 else None
        for h, t in zip(hs, ts):
            z = (mu - t) / sd if t and mu is not None and sd and sd > 0 else None      # ＋なら同じレースの平均より速い
            if z is not None: z = max(-3, min(3, z))
            hist[h["馬名"]].append((rc["d"], int(h["着順"]) / n, z, rc["prize"], num(h["負担重量"]), rc["moist"]))
            jk[h["騎手名"]].append((rc["d"], 1 if int(h["着順"]) <= 3 else 0))
    return [o for o in out if o["n"] >= 5]

def wilson(h, n):
    if not n: return (0, 0)
    p, z = h / n, 1.96; c = (p + z * z / (2 * n)) / (1 + z * z / n); d = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (100 * (c - d), 100 * (c + d))

def score(ds, pick):
    S = dict(n=0, p3=0, win=0, tan=0, fuku=0)
    for o in ds:
        i = pick(o); S["n"] += 1; S["p3"] += o["rk"][i] <= 3; S["win"] += o["rk"][i] == 1
        S["tan"] += o["pay"].get("tan", {}).get(o["num"][i], 0); S["fuku"] += o["pay"].get("fuku", {}).get(o["num"][i], 0)
    return S
def show(tag, S):
    lo, hi = wilson(S["p3"], S["n"])
    print(f"  {tag:<34} {S['n']:>6}レース  ◎3着内 {100*S['p3']/S['n']:.1f}% [{lo:.1f}–{hi:.1f}]  単的中 {100*S['win']/S['n']:.1f}%  単回収 {S['tan']/S['n']:.1f}%  複回収 {S['fuku']/S['n']:.1f}%")

def main():
    races = load(); print("ばんえいのレース", len(races), races[0]["d"], "〜", races[-1]["d"], "／当日の馬体重:", "使わない（朝の条件）" if NOWT else "使う")
    res = {}
    for mode in ("none", "prev", "real"):
        ds = build(races, mode)
        tr = [o for o in ds if o["d"] < "20220101"]; va = [o for o in ds if "20220101" <= o["d"] < SPLIT]; te = [o for o in ds if o["d"] >= SPLIT]
        def pack(D):
            X = np.array([x for o in D for x in o["X"]], float); y = np.array([max(0, 4 - r) for o in D for r in o["rk"]]); g = [o["n"] for o in D]; return X, y, g
        Xt, yt, gt = pack(tr); Xv, yv, gv = pack(va)
        P = dict(objective="lambdarank", metric="ndcg", ndcg_eval_at=[1, 3], learning_rate=0.03, num_leaves=31, min_data_in_leaf=80,
                 feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1, seed=7)
        m = lgb.train(P, lgb.Dataset(Xt, yt, group=gt, feature_name=FE), 2000, valid_sets=[lgb.Dataset(Xv, yv, group=gv)],
                      callbacks=[lgb.early_stopping(100, verbose=False)])
        print(f"\n[水分の使い方: {mode}]  学習 {len(tr)}レース（〜2021）／調整 {len(va)}（2022）／検証 {len(te)}（2023〜）  木の数 {m.best_iteration}")
        def pk(o): return int(np.argmax(m.predict(np.array(o["X"], float), num_iteration=m.best_iteration)))
        S = score(te, pk); show("専用モデルの◎", S); res[mode] = S
        if mode == "none":
            show("1番人気を◎にした場合（比較）", score(te, lambda o: int(np.argmin(o["pop"]))))
            show("通算の3着内率が1位を◎（単純な比較）", score(te, lambda o: int(np.nanargmax([x[FE.index("cp3")] if not np.isnan(x[FE.index("cp3")]) else -1 for x in o["X"]]))))
            for y in ("2023", "2024", "2025", "2026"):
                show("  専用モデル " + y + "年", score([o for o in te if o["d"][:4] == y], pk))
        imp = sorted(zip(FE, m.feature_importance("gain")), key=lambda x: -x[1])[:8]
        print("  効いている材料（上位8）:", "  ".join(f"{k}" for k, _ in imp))
    print("\n今の手作りの点数（baneiScore）は 2023年以降の◎3着内 47.6%（docs/FACTS.md・今回は数え直していない）")
if __name__ == "__main__": main()
