# -*- coding: utf-8 -*-
"""中央: 全部入り・組み合わせありの検証。決まりは backtest/PREREG_jra_gbm_20261121.md に先に書いた。
出すのは集計だけ。使い方: python backtest/bt_jra_gbm.py
"""
import json
import os
import sys

import numpy as np
import lightgbm as lgb

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("LTR_NEWFEATS", "pre")
os.environ.setdefault("LTR_TC", "1")
os.environ.setdefault("SCREEN_FIT", "20150115,20240101")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bt_train_ltr import fval                    # noqa: E402
from eval_bets import pay_single                 # noqa: E402
import bt_jra_screen as scr                      # noqa: E402  オッズだけの当てはめ・区間の計算を共用

DATA = scr.DATA
CAND = ["sf1", "sfb", "sfa", "af1", "afb", "afa", "btf", "kin", "kchg", "blk", "blk1", "dmr", "dmt"]
CHK = ["hz", "hlast", "hl", "wz", "wlast", "wl", "cz", "cnt", "gap"]
TRAIN_END, STOP_END, SEL_END = "20230101", "20240101", "20250101"
TS = [1.00, 1.05, 1.10, 1.15, 1.20, 1.30, 1.50]
CAPS = [None, 50, 20, 10]


def load():
    B = lgb.Booster(model_file=os.path.join(HERE, "ltr_model_jra.txt"))
    F = [f for f in B.feature_name() if f != "tc"]
    side = {}
    for sfx in (".odds", ".cand", ".chokyo"):
        d = {}
        if os.path.exists(DATA + sfx):
            with open(DATA + sfx, encoding="utf-8") as f:
                for line in f:
                    rid, v = json.loads(line)
                    if rid >= "2015":
                        d[rid] = v
        side[sfx] = d
    has_ch = bool(side[".chokyo"])
    EX = [k for k in ("fn", "wt", "wd") if k not in F]       # 本番モデルの列に無いものだけ足す（同じ名前を2回入れない）
    cols = ["lq"] + F + EX + CAND + (CHK if has_ch else [])
    rows, meta = [], []
    ex = {"払戻なし": 0, "オッズ欠け・材料なし": 0}
    with open(DATA, encoding="utf-8") as f:
        for line in f:
            rc = json.loads(line)
            if rc["d"] < "20150115":
                continue
            hs = [h for h in rc["h"] if h.get("rk") is not None]
            if len(hs) < 5:
                continue
            tan = (rc.get("pay") or {}).get("tan")
            if not tan:
                ex["払戻なし"] += 1
                continue
            od, c, ck = side[".odds"].get(rc["rid"]) or {}, side[".cand"].get(rc["rid"]), side[".chokyo"].get(rc["rid"]) or {}
            ns = [str(int(h["n"])) for h in hs]
            if not c or any(od.get(n) in (None, 0) or n not in c for n in ns):
                ex["オッズ欠け・材料なし"] += 1
                continue
            win = np.array([h["rk"] == 1 for h in hs])
            if win.sum() != 1:
                continue
            o = np.array([od[n] for n in ns], float)
            q = (1 / o) / (1 / o).sum()
            X = []
            for h, n, lq in zip(hs, ns, np.log(q)):
                v = [lq] + [fval(h, rc, k) for k in F] + [len(hs) if k == "fn" else h.get(k) for k in EX] + [c[n].get(k) for k in CAND]
                if has_ch:
                    v += [(ck.get(n) or {}).get(k) for k in CHK]
                X.append([np.nan if x is None else x for x in v])
            rows.append(np.array(X, float))
            meta.append((rc["d"], win, o, np.array([pay_single(tan, n) for n in ns], float)))
    return rows, meta, cols, has_ch, ex


def main():
    rows, meta, cols, has_ch, ex = load()
    part = lambda a, b: [i for i, m in enumerate(meta) if a <= m[0] < b]   # noqa: E731
    I = {"tr": part("0", TRAIN_END), "st": part(TRAIN_END, STOP_END), "sel": part(STOP_END, SEL_END), "fin": part(SEL_END, "9")}
    print(f"学習 {len(I['tr']):,}R / 止め時 {len(I['st']):,}R / ふるい {len(I['sel']):,}R / 最終 {len(I['fin']):,}R  列 {len(cols)}  調教 {'あり' if has_ch else 'なし'}  除外 {ex}")
    # オッズだけ（学習＋止め時の期間で当てはめ）
    def mk(ix):
        return scr.pack([(rows[i][:, :1], meta[i][1], meta[i][2], meta[i][3], meta[i][0]) for i in ix])
    a = scr.fit(mk(I["tr"] + I["st"]), [0])[0]

    def base(ix):                       # オッズだけの確率（レース内で合計1）
        out = []
        for i in ix:
            z = a * rows[i][:, 0]
            e = np.exp(z - z.max())
            out.append(e / e.sum())
        return out

    def ds(ix, ref=None):
        X = np.vstack([rows[i] for i in ix])
        y = np.concatenate([meta[i][1] for i in ix]).astype(int)
        p = np.clip(np.concatenate(base(ix)), 1e-6, 1 - 1e-6)
        return lgb.Dataset(X, y, init_score=np.log(p / (1 - p)), feature_name=cols, reference=ref), X, p
    dtr, _, _ = ds(I["tr"])
    dst, _, _ = ds(I["st"], dtr)
    params = {"objective": "binary", "learning_rate": 0.03, "num_leaves": 15, "min_data_in_leaf": 200,
              "feature_fraction": 0.8, "lambda_l2": 10, "verbose": -1, "seed": 42}
    bst = lgb.train(params, dtr, 2000, valid_sets=[dst], callbacks=[lgb.early_stopping(100, verbose=False)])
    print(f"オッズだけの係数 {a:.3f}  止まった回数 {bst.best_iteration}")

    def probs(ix):
        out, bs = [], base(ix)
        for i, p0 in zip(ix, bs):
            p0 = np.clip(p0, 1e-6, 1 - 1e-6)
            z = np.log(p0 / (1 - p0)) + bst.predict(rows[i], num_iteration=bst.best_iteration, raw_score=True)
            p = 1 / (1 + np.exp(-z))
            out.append(p / p.sum())
        return out, bs

    def nll(ps, ix):
        return np.array([-np.log(max(p[meta[i][1]].sum(), 1e-12)) for p, i in zip(ps, ix)])
    pm, pb = probs(I["sel"])
    d = nll(pm, I["sel"]) - nll(pb, I["sel"])
    c95 = scr.ci(d)
    ok = c95[1] < 0
    print(f"ふるい(2024年): オッズだけ {nll(pb, I['sel']).mean():.4f} / 全部入り {nll(pm, I['sel']).mean():.4f}  差 {d.mean():+.4f} {c95} → {'通過' if ok else '通らない'}")
    imp = sorted(zip(bst.feature_importance("gain"), cols), reverse=True)[:12]
    print("効いた列（上から12）: " + " ".join(f"{c}:{g:.0f}" for g, c in imp))
    out = {"n": {k: len(v) for k, v in I.items()}, "a": float(a), "iters": bst.best_iteration,
           "nll_market": float(nll(pb, I["sel"]).mean()), "nll_model": float(nll(pm, I["sel"]).mean()),
           "diff": float(d.mean()), "ci": c95, "pass": bool(ok), "has_chokyo": has_ch}
    if ok:
        def bets(ps, ix, t, cap):
            x = []
            for p, i in zip(ps, ix):
                m = p * meta[i][2] >= t
                if cap:
                    m &= meta[i][2] <= cap
                x.extend(meta[i][3][m])
            return np.array(x, float)
        grid = [(bets(pm, I["sel"], t, cap), t, cap) for t in TS for cap in CAPS]
        grid = [(float(x.mean()), t, cap, len(x)) for x, t, cap in grid if len(x) >= 300]
        if grid:
            roi, t, cap, n_ = max(grid)
            pf, _ = probs(I["fin"])
            x = bets(pf, I["fin"], t, cap)
            f = {"t": t, "cap": cap, "sel_roi": round(roi, 1), "sel_n": n_, "n": int(len(x)), "roi": round(float(x.mean()), 1),
                 "hit": round(100 * float((x > 0).mean()), 1), "ci": scr.ci(x) if len(x) >= 100 else None}
            f["verdict"] = ("判定できない" if len(x) < 100 else "合格（下側が100%超）" if f["ci"][0] > 100 else "不合格（100%は超えない）")
            out["final"] = f
            print(f"選んだ決まり t≥{t} 上限{cap or 'なし'}（2024年 {n_}点 {roi:.1f}%）\n★最終 {f}")
        else:
            print("2024年に300点以上買える決まりが無い")
    os.makedirs(os.path.join(HERE, "store", "discovery"), exist_ok=True)
    json.dump(out, open(os.path.join(HERE, "store", "discovery", "jra_gbm.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
