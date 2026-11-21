# -*- coding: utf-8 -*-
"""地方（平地）: 期待値買い（単勝）。決まりは backtest/PREREG_nar_value_20261121.md に先に書いた。
入力: bt_all.jsonl と、公式のオッズ（月ごとの zip。NAR_ODDS_DIR）。出すのは集計だけ。
使い方: NAR_ODDS_DIR=/path/to/odds python backtest/bt_nar_value.py
"""
import csv
import glob
import io
import json
import os
import sys
import zipfile

import numpy as np
import lightgbm as lgb
from scipy.optimize import minimize

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("LTR_NEWFEATS", "pre")
os.environ.setdefault("LTR_TC", "1")
os.environ.setdefault("LTR_TIME", "2")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bt_train_ltr import fval            # noqa: E402
from eval_bets import pay_single         # noqa: E402

DATA = os.path.join(HERE, "nardata", "bt_all.jsonl")
ODIR = os.environ.get("NAR_ODDS_DIR", os.path.join(HERE, "nardata"))
TC = {'門別': '30', '盛岡': '35', '水沢': '36', '浦和': '42', '船橋': '43', '大井': '44', '川崎': '45', '金沢': '46',
      '笠松': '47', '名古屋': '48', '園田': '50', '姫路': '51', '高知': '54', '佐賀': '55'}
FIT, FIN = ("20260301", "20260801"), ("20260801", "99999999")
T_FIX, CAP_FIX = 1.10, 20


def load_odds():
    od = {}
    for zp in sorted(glob.glob(os.path.join(ODIR, "odds_2026*.zip"))):
        z = zipfile.ZipFile(zp)
        for n in z.namelist():
            for r in csv.reader(io.StringIO(z.read(n).decode("utf-8-sig", errors="replace"))):
                if len(r) < 8 or r[3] != "単勝" or r[0] not in TC:
                    continue
                try:
                    o = float(r[7])
                except ValueError:
                    continue
                rid = r[1][:4] + TC[r[0]] + r[1][4:8] + f"{int(r[2]):02d}"
                od.setdefault(rid, {})[str(int(r[4]))] = o
    return od


def ci(x, n=2000):
    rng = np.random.default_rng(7)
    m = [x[rng.integers(0, len(x), len(x))].mean() for _ in range(n)]
    return [round(float(np.percentile(m, 2.5)), 4 if abs(np.mean(x)) < 5 else 1), round(float(np.percentile(m, 97.5)), 4 if abs(np.mean(x)) < 5 else 1)]


def stat(x):
    x = np.array(x, float)
    if not len(x):
        return {"n": 0}
    d = {"n": int(len(x)), "roi": round(float(x.mean()), 1), "hit": round(100 * float((x > 0).mean()), 1)}
    if len(x) >= 100:
        d["ci"] = ci(x)
    return d


def probs(r, th):
    z = th[0] * r["lq"] + (th[1] * r["s"] if len(th) > 1 else 0)
    e = np.exp(z - z.max())
    return e / e.sum()


def fit(rs, k):
    def f(th):
        return float(np.mean([-np.log(max(probs(r, th)[r["win"]].sum(), 1e-12)) for r in rs]))
    return [float(x) for x in minimize(f, [1.0, 0.3][:k], method="Nelder-Mead", options={"xatol": 1e-3, "fatol": 1e-7}).x]


def main():
    od = load_odds()
    B = lgb.Booster(model_file=os.path.join(HERE, "ltr_model_t.txt"))
    F = B.feature_name()
    R = {"fit": [], "fin": []}
    ex = {"払戻なし": 0, "オッズなし": 0}
    last = ""
    with open(DATA, encoding="utf-8") as f:
        for line in f:
            if '"d": "2026' not in line[:80]:
                continue
            rc = json.loads(line)
            d = rc["d"]
            part = "fit" if FIT[0] <= d < FIT[1] else "fin" if FIN[0] <= d < FIN[1] else None
            if not part:
                continue
            last = max(last, d)
            hs = [h for h in rc["h"] if h.get("rk") is not None]
            if len(hs) < 5:
                continue
            tan = (rc.get("pay") or {}).get("tan")
            if not tan:
                ex["払戻なし"] += 1
                continue
            o = [(od.get(rc["rid"]) or {}).get(str(int(h["n"]))) for h in hs]
            if any(x is None or x <= 0 for x in o):
                ex["オッズなし"] += 1
                continue
            win = np.array([h["rk"] == 1 for h in hs])
            if win.sum() != 1:
                continue
            o = np.array(o, float)
            q = (1 / o) / (1 / o).sum()
            s = B.predict(np.array([[fval(h, rc, k) for k in F] for h in hs], float))
            R[part].append({"lq": np.log(q), "s": s, "win": win, "o": o,
                            "pay": np.array([pay_single(tan, str(int(h["n"]))) for h in hs], float),
                            "pop": np.array([h.get("pop") or 99 for h in hs])})
    print(f"データの最終日 {last}  当てはめ {len(R['fit']):,}R / 最終 {len(R['fin']):,}R  除外 {ex}")
    thM, thB = fit(R["fit"], 1), fit(R["fit"], 2)
    nM = np.array([-np.log(max(probs(r, thM)[r["win"]].sum(), 1e-12)) for r in R["fin"]])
    nB = np.array([-np.log(max(probs(r, thB)[r["win"]].sum(), 1e-12)) for r in R["fin"]])
    print(f"係数  オッズだけ a={thM[0]:.3f} / オッズ＋AI a={thB[0]:.3f} b={thB[1]:.3f}")
    print(f"読み（最終期間）オッズだけ {nM.mean():.4f} / オッズ＋AI {nB.mean():.4f}  差 {(nB - nM).mean():+.4f} {ci(nB - nM)}")
    out = {"last": last, "thM": thM, "thB": thB, "nll": [float(nM.mean()), float(nB.mean())], "diff_ci": ci(nB - nM)}
    print("物差し（最終期間・全レース1点）")
    print(f"  1番人気 {stat([r['pay'][int(np.argmin(r['pop']))] for r in R['fin']])}")
    print(f"  ◎（AI） {stat([r['pay'][int(np.argmax(r['s']))] for r in R['fin']])}")
    print(f"★固定の買い方（確率×オッズ≥{T_FIX}・{CAP_FIX}倍まで）最終期間")
    for nm, th in (("オッズだけ", thM), ("オッズ＋AI", thB)):
        x = []
        for r in R["fin"]:
            m = (probs(r, th) * r["o"] >= T_FIX) & (r["o"] <= CAP_FIX)
            x.extend(r["pay"][m])
        s = stat(x)
        v = ("判定できない（100点未満）" if s["n"] < 100 else "合格（下側が100%超）" if s["ci"][0] > 100 else "不合格（100%は超えない）")
        out[nm] = {**s, "verdict": v}
        print(f"  {nm}: {s} → {v}")
    os.makedirs(os.path.join(HERE, "store", "discovery"), exist_ok=True)
    json.dump(out, open(os.path.join(HERE, "store", "discovery", "nar_value.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
