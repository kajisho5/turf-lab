# -*- coding: utf-8 -*-
"""中央: 材料のふるい。決まりは backtest/PREREG_jra_screen_20261121.md に先に書いた。
出すのは集計だけ。使い方: python backtest/bt_jra_screen.py
出力: 標準出力 と backtest/store/discovery/jra_screen.json
"""
import json
import os
import sys

import numpy as np
from scipy.optimize import minimize

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from eval_bets import pay_single         # noqa: E402

DATA = os.environ.get("JRA_DATA", os.path.join(HERE, "nardata", "bt_jra.jsonl"))
FIT = tuple(os.environ.get("SCREEN_FIT", "20150101,20240101").split(","))
SEL = tuple(os.environ.get("SCREEN_SEL", "20240101,20250101").split(","))
FIN = tuple(os.environ.get("SCREEN_FIN", "20250101,99999999").split(","))
GROUPS = {"time": ["sf1", "sfb", "sfa", "af1", "afb", "afa", "btf"],
          "weight": ["kin", "kchg", "blk", "blk1"],
          "body": ["wt", "wd"],
          "mining": ["dmr", "dmt"]}
GROUPS["all"] = sum(GROUPS.values(), [])
# 調教（2026-11-21 追加）。別ファイル bt_jra.jsonl.chokyo がある時だけ。SCREEN_GROUPS=chokyo,chokyo_best のように絞れる
CHOKYO = ["hz", "hlast", "hl", "wz", "wlast", "wl", "cz", "cnt", "gap"]
HAS_CH = os.path.exists(DATA + ".chokyo")
if HAS_CH:
    GROUPS["chokyo"] = CHOKYO
    GROUPS["chokyo_best"] = ["cz"]
COLS = GROUPS["all"] + (CHOKYO if HAS_CH else [])
_only = [g for g in os.environ.get("SCREEN_GROUPS", "").split(",") if g]
if _only:
    GROUPS = {g: GROUPS[g] for g in _only}
TS = [1.00, 1.05, 1.10, 1.15, 1.20, 1.30, 1.50]
CAPS = [None, 50, 20, 10]
MIN_SEL = 300


def zrace(v):
    v = np.array([np.nan if x is None else x for x in v], float)
    ok = ~np.isnan(v)
    out = np.zeros(len(v))
    if ok.sum() >= 2:
        sd = v[ok].std()
        if sd > 1e-9:
            out[ok] = (v[ok] - v[ok].mean()) / sd
    return out


def load():
    odds, cand = {}, {}
    for path, d in ((DATA + ".odds", odds), (DATA + ".cand", cand)):
        with open(path, encoding="utf-8") as f:
            for line in f:
                rid, v = json.loads(line)
                if rid >= FIT[0][:4]:
                    d[rid] = v
    chk = {}
    if HAS_CH:
        with open(DATA + ".chokyo", encoding="utf-8") as f:
            for line in f:
                rid, v = json.loads(line)
                chk[rid] = v
    S = {"fit": [], "sel": [], "fin": []}
    ex = {"払戻なし": 0, "オッズ欠け": 0, "材料なし(障害など)": 0}
    last = ""
    with open(DATA, encoding="utf-8") as f:
        for line in f:
            rc = json.loads(line)
            d = rc["d"]
            if d < FIT[0]:
                continue
            last = max(last, d)
            part = "fit" if d < FIT[1] else "sel" if SEL[0] <= d < SEL[1] else "fin" if FIN[0] <= d < FIN[1] else None
            if not part:
                continue
            hs = [h for h in rc["h"] if h.get("rk") is not None]
            if len(hs) < 5:
                continue
            tan = (rc.get("pay") or {}).get("tan")
            if not tan:
                ex["払戻なし"] += 1
                continue
            c = cand.get(rc["rid"])
            if not c:
                ex["材料なし(障害など)"] += 1
                continue
            ns = [str(int(h["n"])) for h in hs]
            od = odds.get(rc["rid"]) or {}
            o = [od.get(n) for n in ns]
            if any(x is None or x <= 0 for x in o) or any(n not in c for n in ns):
                ex["オッズ欠け"] += 1
                continue
            o = np.array(o, float)
            q = (1 / o) / (1 / o).sum()
            X = [np.log(q)]
            ck = chk.get(rc["rid"]) or {}
            if HAS_CH and _only and all(g.startswith("chokyo") for g in _only) and not ck:
                ex["調教なし"] = ex.get("調教なし", 0) + 1
                continue
            for col in COLS:
                X.append(zrace([h.get(col) if col in ("wt", "wd") else (ck.get(n) or {}).get(col) if col in CHOKYO
                                else c[n].get(col) for h, n in zip(hs, ns)]))
            win = np.array([h["rk"] == 1 for h in hs])
            if win.sum() != 1:                      # 同着は外す（尤度の式を単純に保つ）
                continue
            S[part].append((np.array(X).T, win, o, np.array([pay_single(tan, n) for n in ns], float), d))
    return S, ex, last


def pack(rs):
    X = np.vstack([r[0] for r in rs])
    n = np.array([len(r[1]) for r in rs])
    st = np.concatenate([[0], np.cumsum(n)[:-1]])
    w = np.concatenate([r[1] for r in rs])
    return X, st, n, w


def race_nll(beta, P, idx):
    X, st, n, w = P
    z = X[:, idx] @ beta
    m = np.maximum.reduceat(z, st)
    e = np.exp(z - np.repeat(m, n))
    lse = np.log(np.add.reduceat(e, st)) + m
    p = e / np.repeat(np.add.reduceat(e, st), n)
    return lse - z[w], p


def fit(P, idx):
    X, st, n, w = P
    Xi = X[:, idx]

    def f(b):
        nll, p = race_nll(b, P, idx)
        g = (Xi * (p - w)[:, None]).sum(0) / len(st)
        return nll.mean(), g
    b0 = np.zeros(len(idx))
    b0[0] = 1.0
    r = minimize(f, b0, jac=True, method="L-BFGS-B")
    return r.x


def ci(x, n=2000):
    rng = np.random.default_rng(7)
    m = [x[rng.integers(0, len(x), len(x))].mean() for _ in range(n)]
    return [round(float(np.percentile(m, 2.5)), 4 if abs(np.mean(x)) < 5 else 1),
            round(float(np.percentile(m, 97.5)), 4 if abs(np.mean(x)) < 5 else 1)]


def bets(rs, P, beta, idx, t, cap):
    _, p = race_nll(beta, P, idx)
    o = np.concatenate([r[2] for r in rs])
    pay = np.concatenate([r[3] for r in rs])
    m = p * o >= t
    if cap:
        m &= o <= cap
    return pay[m]


def main():
    S, ex, last = load()
    print(f"データの最終日 {last}  当てはめ {len(S['fit']):,}R / ふるい {len(S['sel']):,}R / 最終 {len(S['fin']):,}R  除外 {ex}")
    P = {k: pack(v) for k, v in S.items() if v}
    out = {"last": last, "n": {k: len(v) for k, v in S.items()}, "excluded": ex, "groups": {}}
    b_m = fit(P["fit"], [0])
    nll_m, _ = race_nll(b_m, P["sel"], [0])
    print(f"\nオッズだけ: 係数 {b_m[0]:.3f}  読み(ふるいの期間) {nll_m.mean():.4f}")
    out["market"] = {"a": float(b_m[0]), "nll_sel": float(nll_m.mean())}
    for g, cols in GROUPS.items():
        idx = [0] + [1 + COLS.index(c) for c in cols]
        b = fit(P["fit"], idx)
        nll, _ = race_nll(b, P["sel"], idx)
        diff = nll - nll_m
        c95 = ci(diff)
        ok = c95[1] < 0
        res = {"coef": {"lq": round(float(b[0]), 3), **{c: round(float(x), 3) for c, x in zip(cols, b[1:])}},
               "nll_sel": float(nll.mean()), "diff": float(diff.mean()), "diff_ci": c95, "pass": bool(ok)}
        print(f"\n[{g}] 読み {nll.mean():.4f}  差 {diff.mean():+.4f} {c95}  → {'ふるい通過' if ok else '通らない'}")
        print(f"   係数 {res['coef']}")
        if ok and "fin" in P and os.environ.get("SCREEN_NOFINAL") != "1":
            grid = []
            for t in TS:
                for cap in CAPS:
                    x = bets(S["sel"], P["sel"], b, idx, t, cap)
                    if len(x) >= MIN_SEL:
                        grid.append((float(x.mean()), t, cap, len(x)))
            if not grid:
                print("   2024年に300点以上買える決まりが無い")
                res["final"] = None
            else:
                grid.sort(reverse=True)
                roi, t, cap, n_ = grid[0]
                x = bets(S["fin"], P["fin"], b, idx, t, cap)
                f = {"t": t, "cap": cap, "sel_roi": round(roi, 1), "sel_n": n_, "n": int(len(x)),
                     "roi": round(float(x.mean()), 1) if len(x) else None,
                     "hit": round(100 * float((x > 0).mean()), 1) if len(x) else None,
                     "ci": ci(x) if len(x) >= 100 else None}
                f["verdict"] = ("数が足りず判定できない" if len(x) < 100 else
                                "合格（下側が100%超）" if f["ci"][0] > 100 else "不合格（100%は超えない）")
                res["final"] = f
                print(f"   選んだ決まり t≥{t} 上限{cap or 'なし'}（2024年 {n_}点 {roi:.1f}%）")
                print(f"   ★最終 {f}")
        # 案B用: 先に固定した決まり（SCREEN_FIXED="t,上限"）を、ふるいの期間で1回だけ採点する
        if os.environ.get("SCREEN_FIXED"):
            t_, cap_ = os.environ["SCREEN_FIXED"].split(",")
            x = bets(S["sel"], P["sel"], b, idx, float(t_), float(cap_) or None)
            fx = {"t": float(t_), "cap": float(cap_), "n": int(len(x)),
                  "roi": round(float(x.mean()), 1) if len(x) else None,
                  "hit": round(100 * float((x > 0).mean()), 1) if len(x) else None,
                  "ci": ci(x) if len(x) >= 100 else None}
            res["fixed"] = fx
            print(f"   固定の決まり（確率×オッズ≥{t_}・{cap_}倍まで）: {fx}")
        out["groups"][g] = res
    os.makedirs(os.path.join(HERE, "store", "discovery"), exist_ok=True)
    json.dump(out, open(os.path.join(HERE, "store", "discovery", "jra_screen.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
