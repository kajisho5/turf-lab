# -*- coding: utf-8 -*-
"""中央: 人気馬の複勝を材料で絞る。決まりは backtest/PREREG_jra_favplace_20261121.md に先に書いた。
出すのは集計だけ。使い方: python backtest/bt_jra_favplace.py
"""
import json
import os
import sys

import numpy as np
import lightgbm as lgb

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from eval_bets import pay_single         # noqa: E402

DATA = os.environ.get("JRA_DATA", os.path.join(HERE, "nardata", "bt_jra.jsonl"))
BT = ["age", "np", "prk", "ppop", "rest", "dchg", "tchg", "wr", "dr", "owr", "o2r", "jkchg", "jkr", "trr", "ar", "fpf", "trend", "wt", "wd"]
CAND = ["sf1", "sfb", "sfa", "af1", "afb", "afa", "btf", "kin", "kchg", "blk", "blk1", "dmr", "dmt"]
CHK = ["hz", "hlast", "hl", "wz", "wlast", "wl", "cz", "cnt", "gap"]
T0, T1, T2 = os.environ.get("FP_T0", "20150115"), os.environ.get("FP_T1", "20220101"), os.environ.get("FP_T2", "20240101")
KEEP = [0.50, 0.33, 0.20, 0.10]


def ci(x, n=2000):
    rng = np.random.default_rng(7)
    m = [x[rng.integers(0, len(x), len(x))].mean() for _ in range(n)]
    return [round(float(np.percentile(m, 2.5)), 1), round(float(np.percentile(m, 97.5)), 1)]


def stat(x):
    x = np.array(x, float)
    if not len(x):
        return {"n": 0}
    d = {"n": int(len(x)), "roi": round(float(x.mean()), 1), "hit": round(100 * float((x > 0).mean()), 1)}
    if len(x) >= 100:
        d["ci"] = ci(x)
    return d


def main():
    side = {}
    for sfx in (".odds", ".cand", ".chokyo"):
        d = {}
        if os.path.exists(DATA + sfx):
            with open(DATA + sfx, encoding="utf-8") as f:
                for line in f:
                    rid, v = json.loads(line)
                    if rid >= T0[:4]:
                        d[rid] = v
        side[sfx] = d
    has_ch = bool(side[".chokyo"])
    cols = ["o", "o2ratio", "top3share", "fn", "surf", "dist"] + BT + CAND + (CHK if has_ch else [])
    X, y, D = [], [], []
    with open(DATA, encoding="utf-8") as f:
        for line in f:
            rc = json.loads(line)
            if rc["d"] < T0 or rc.get("surf") not in ("芝", "ダート"):
                continue
            pay = rc.get("pay") or {}
            if not pay.get("fuku"):
                continue
            hs = [h for h in rc["h"] if h.get("rk") is not None]
            od, c, ck = side[".odds"].get(rc["rid"]) or {}, side[".cand"].get(rc["rid"]) or {}, side[".chokyo"].get(rc["rid"]) or {}
            if len(hs) < 8 or any(od.get(str(int(h["n"]))) in (None, 0) for h in hs):
                continue
            fav = [h for h in hs if h.get("pop") == 1]
            if len(fav) != 1:
                continue
            h = fav[0]
            u = str(int(h["n"]))
            o = od[u]
            if o > 2.0 + 1e-9:
                continue
            os_ = sorted(od[str(int(x["n"]))] for x in hs)
            q = sorted(((1 / v) for v in os_), reverse=True)
            v = [o, os_[1] / o, sum(q[:3]) / sum(q), len(hs), 0 if rc["surf"] == "芝" else 1, rc.get("dist")]
            v += [h.get(k) for k in BT] + [(c.get(u) or {}).get(k) for k in CAND]
            if has_ch:
                v += [(ck.get(u) or {}).get(k) for k in CHK]
            X.append([np.nan if x is None else x for x in v])
            y.append(pay_single(pay["fuku"], u))
            D.append(rc["d"])
    X, y, D = np.array(X, float), np.array(y, float), np.array(D)
    tr, sel, fin = D < T1, (D >= T1) & (D < T2), D >= T2
    print(f"対象（1番人気・2.0倍以下・8頭以上）学習 {tr.sum():,} / 選ぶ {sel.sum():,} / 最終 {fin.sum():,}  列 {len(cols)}  調教 {'あり' if has_ch else 'なし'}")
    bst = lgb.train({"objective": "regression", "learning_rate": 0.03, "num_leaves": 7, "min_data_in_leaf": 100,
                     "feature_fraction": 0.8, "verbose": -1, "seed": 42},
                    lgb.Dataset(X[tr], y[tr] / 100, feature_name=cols), 300)
    p = bst.predict(X)
    imp = sorted(zip(bst.feature_importance("gain"), cols), reverse=True)[:10]
    print("効いた列（上から10）: " + " ".join(f"{c}:{g:.1f}" for g, c in imp))
    out = {"n": {"train": int(tr.sum()), "sel": int(sel.sum()), "fin": int(fin.sum())}, "sel": {}, "has_chokyo": has_ch}
    print("\n選ぶ期間（2022〜2023年）")
    print(f"  絞らない: {stat(y[sel])}")
    best = None
    for k in KEEP:
        th = np.quantile(p[tr], 1 - k)
        s = stat(y[sel & (p >= th)])
        out["sel"][str(k)] = s
        print(f"  上位{int(k * 100)}%: {s}")
        if s["n"] >= 150 and (best is None or s["roi"] > best[1]["roi"]):
            best = (k, s, th)
    print("\n★最終期間（2024年〜・1回）")
    print(f"  参考 絞らない（2.0倍以下）: {stat(y[fin])}")
    print(f"  参考 1.3倍以下: {stat(y[fin & (X[:, 0] <= 1.3 + 1e-9)])}")
    if best:
        k, _, th = best
        f = stat(y[fin & (p >= th)])
        f["verdict"] = ("判定できない（100点未満）" if f["n"] < 100 else "合格（下側が100%超）" if f["ci"][0] > 100 else "不合格（100%は超えない）")
        out["final"] = {"keep": k, **f}
        print(f"  選んだ 上位{int(k * 100)}%: {f}")
        m = fin & (p >= th)
        print(f"  選ばれた馬の単勝オッズの平均 {X[m, 0].mean():.2f}・1.3倍以下の割合 {100 * (X[m, 0] <= 1.3).mean():.0f}%")
    else:
        print("  選べる割合が無い")
    os.makedirs(os.path.join(HERE, "store", "discovery"), exist_ok=True)
    json.dump(out, open(os.path.join(HERE, "store", "discovery", "jra_favplace.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
