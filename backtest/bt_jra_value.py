# -*- coding: utf-8 -*-
"""中央: 期待値買い（単勝）の検証。決まりは backtest/PREREG_jra_value_20261121.md に先に書いた。

  当てはめ=2023年 / 選ぶ=2024年 / 最終=2025-01-01〜（選んだ決まりを1回だけ採点）
出すのは集計だけ。使い方: python backtest/bt_jra_value.py
出力: 標準出力 と backtest/store/discovery/jra_value.json
"""
import json
import os
import sys

import numpy as np
import lightgbm as lgb
from scipy.optimize import minimize

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("LTR_NEWFEATS", "pre")
os.environ.setdefault("LTR_TC", "1")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bt_train_ltr import fval            # noqa: E402
from eval_bets import pay_single         # noqa: E402

DATA = os.environ.get("JRA_DATA", os.path.join(HERE, "nardata", "bt_jra.jsonl"))
ODDS = os.environ.get("JRA_ODDS", DATA + ".odds")
FIT, SEL, FIN = ("20230101", "20240101"), ("20240101", "20250101"), ("20250101", "99999999")
TS = [1.00, 1.05, 1.10, 1.15, 1.20, 1.30, 1.50]
CAPS = [None, 50, 20, 10]
MIN_SEL = 300


def load():
    odds = {}
    with open(ODDS, encoding="utf-8") as f:
        for line in f:
            rid, d = json.loads(line)
            odds[rid] = d
    B = lgb.Booster(model_file=os.path.join(HERE, "ltr_model_jra.txt"))
    F = B.feature_name()
    races, ex = [], {"払戻なし": 0, "オッズ欠け": 0, "5頭未満": 0}
    last = ""
    with open(DATA, encoding="utf-8") as f:
        for line in f:
            rc = json.loads(line)
            if rc["d"] < FIT[0]:
                continue
            last = max(last, rc["d"])
            hs = [h for h in rc["h"] if h.get("rk") is not None]
            if len(hs) < 5:
                ex["5頭未満"] += 1
                continue
            tan = (rc.get("pay") or {}).get("tan")
            if not tan:
                ex["払戻なし"] += 1
                ex["払戻なし" + rc["d"][:4]] = ex.get("払戻なし" + rc["d"][:4], 0) + 1
                continue
            od = odds.get(rc["rid"]) or {}
            o = [od.get(str(int(h["n"]))) for h in hs]
            if any(x is None or x <= 0 for x in o):
                ex["オッズ欠け"] += 1
                continue
            s = B.predict(np.array([[fval(h, rc, k) for k in F] for h in hs], float))
            o = np.array(o, float)
            q = (1 / o) / (1 / o).sum()
            races.append({"d": rc["d"], "s": s, "o": o, "lq": np.log(q),
                          "win": np.array([h["rk"] == 1 for h in hs]),
                          "pay": np.array([pay_single(tan, str(int(h["n"]))) for h in hs], float),
                          "pop": np.array([h.get("pop") or 99 for h in hs]),
                          "top": int(np.argmax(s))})
    return races, ex, last


def probs(r, kind, th):
    if kind == "A":
        z = r["s"] / th[0]
    elif kind == "M":
        z = th[0] * r["lq"]
    else:
        z = th[0] * r["lq"] + th[1] * r["s"]
    z = z - z.max()
    e = np.exp(z)
    return e / e.sum()


def fit(rs, kind):
    def nll(th):
        if kind == "A" and th[0] <= 0.01:
            return 1e9
        t = 0.0
        for r in rs:
            p = probs(r, kind, th)
            w = r["win"]
            if w.any():
                t -= np.log(max(p[w].sum(), 1e-12))
        return t / len(rs)
    x0 = {"A": [0.5], "M": [1.0], "B": [1.0, 0.5]}[kind]
    res = minimize(nll, x0, method="Nelder-Mead", options={"xatol": 1e-3, "fatol": 1e-6})
    return [float(x) for x in res.x], float(res.fun)


def bets(rs, kind, th, t, cap):
    """買った点ごとの払戻（100円あたり）の配列"""
    out = []
    for r in rs:
        p = probs(r, kind, th)
        m = p * r["o"] >= t
        if cap:
            m &= r["o"] <= cap
        out.extend(r["pay"][m])
    return np.array(out, float)


def stat(x, ci=False):
    if not len(x):
        return {"n": 0}
    d = {"n": int(len(x)), "roi": round(float(x.mean()), 1), "hit": round(100 * float((x > 0).mean()), 1)}
    if ci and len(x) >= 100:
        rng = np.random.default_rng(7)
        m = [x[rng.integers(0, len(x), len(x))].mean() for _ in range(2000)]
        d["ci"] = [round(float(np.percentile(m, 2.5)), 1), round(float(np.percentile(m, 97.5)), 1)]
    return d


def main():
    races, ex, last = load()
    per = lambda a: [r for r in races if a[0] <= r["d"] < a[1]]   # noqa: E731
    rf, rs, rt = per(FIT), per(SEL), per(FIN)
    print(f"データの最終日 {last}  当てはめ {len(rf):,}R / 選ぶ {len(rs):,}R / 最終 {len(rt):,}R  除外 {ex}")
    out = {"last": last, "n": {"fit": len(rf), "sel": len(rs), "fin": len(rt)}, "excluded": ex, "models": {}}

    print("\n物差し（最終期間・全レース1点ずつ）")
    base = {"fav": np.array([r["pay"][int(np.argmin(r["pop"]))] for r in rt]),
            "ai": np.array([r["pay"][r["top"]] for r in rt])}
    for k, lab in (("fav", "1番人気"), ("ai", "◎（AI）")):
        out["base_" + k] = stat(base[k], ci=True)
        print(f"  {lab}: {out['base_' + k]}")

    for kind, lab in (("A", "AIだけ"), ("M", "市場だけ"), ("B", "市場＋AI")):
        th, nll = fit(rf, kind)
        nll_sel = float(np.mean([-np.log(max(probs(r, kind, th)[r["win"]].sum(), 1e-12)) for r in rs if r["win"].any()]))
        grid = []
        for t in TS:
            for cap in CAPS:
                s = stat(bets(rs, kind, th, t, cap))
                grid.append((t, cap, s))
        ok = [g for g in grid if g[2]["n"] >= MIN_SEL]
        print(f"\n[{kind}] {lab}  係数 {[round(x, 3) for x in th]}  当たり外れの読み（小さいほど良い）2023 {nll:.4f} / 2024 {nll_sel:.4f}")
        m = {"theta": th, "nll_fit": nll, "nll_sel": nll_sel,
             "sel_grid": [{"t": t, "cap": c, **s} for t, c, s in grid]}
        if not ok:
            print("  2024年に300点以上買える決まりが無い")
            out["models"][kind] = m
            continue
        ok.sort(key=lambda g: -g[2]["roi"])
        for t, cap, s in ok[:3]:
            print(f"  2024年 上位: t≥{t} 上限{cap or 'なし'}  {s}")
        t, cap, s = ok[0]
        x = bets(rt, kind, th, t, cap)
        f = stat(x, ci=True)
        m["chosen"] = {"t": t, "cap": cap, "sel": s, "final": f}
        yr = {}
        for y in sorted({r["d"][:4] for r in rt}):
            yr[y] = stat(bets([r for r in rt if r["d"][:4] == y], kind, th, t, cap))
        m["chosen"]["final_by_year"] = yr
        v = ("数が足りず判定できない" if f["n"] < 100 else
             "合格（下側が100%超）" if f["ci"][0] > 100 else "不合格（100%は超えない）")
        m["chosen"]["verdict"] = v
        print(f"  選んだ決まり: t≥{t} 上限{cap or 'なし'}")
        print(f"  ★最終 {f}  年別 {yr}  → {v}")
        out["models"][kind] = m
    os.makedirs(os.path.join(HERE, "store", "discovery"), exist_ok=True)
    json.dump(out, open(os.path.join(HERE, "store", "discovery", "jra_value.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
