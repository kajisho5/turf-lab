# -*- coding: utf-8 -*-
"""ばんえい専用モデルを作って測り、本番用に書き出す（2026-11-14）

学習 〜2021／調整 2022／検証 2023〜。材料は backtest/banei_feats.py（毎朝の採点と同じ計算）。
★勝負・狙い目の境目は「抜け具合 c」で決める。境目は 2022年（調整の年）のレースで
  ★勝負＝上位20%／狙い目＝上位45%（★勝負を含む）になる値に決めて固定し、2023年以降で測る（平地の割合にそろえた）。
出力: backtest/banei_model.json（木と境目）／標準出力に検証の結果
使い方: python3 backtest/train_banei.py [--cache backtest/nardata]
"""
import argparse, json, math, os, sys
import numpy as np, lightgbm as lgb
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import banei_feats as BF

def wilson(h, n):
    if not n: return (0, 0)
    p, z = h / n, 1.96; c = (p + z * z / (2 * n)) / (1 + z * z / n); d = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (100 * (c - d), 100 * (c + d))

def tally(rows):
    S = dict(n=0, p3=0, win=0, tan=0, fuku=0)
    for o, i in rows:
        S["n"] += 1; S["p3"] += o["rk"][i] <= 3; S["win"] += o["rk"][i] == 1
        S["tan"] += o["pay"].get("tan", {}).get(o["num"][i], 0); S["fuku"] += o["pay"].get("fuku", {}).get(o["num"][i], 0)
    return S
def show(tag, S, tot=None):
    if not S["n"]: print(f"  {tag:<30} 0レース"); return
    lo, hi = wilson(S["p3"], S["n"]); share = f"（全体の{100*S['n']/tot:.1f}%）" if tot else ""
    print(f"  {tag:<30} {S['n']:>6}レース{share} ◎3着内 {100*S['p3']/S['n']:.1f}% [{lo:.1f}–{hi:.1f}]  単的中 {100*S['win']/S['n']:.1f}%  単回収 {S['tan']/S['n']:.1f}%  複回収 {S['fuku']/S['n']:.1f}%")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--cache", default=os.path.join(HERE, "nardata")); a = ap.parse_args()
    ds = [o for o in BF.build(BF.load(a.cache)) if o["done"] and o["n"] >= 5]
    tr = [o for o in ds if o["d"] < "20220101"]; va = [o for o in ds if "20220101" <= o["d"] < "20230101"]; te = [o for o in ds if o["d"] >= "20230101"]
    def pack(D): return np.array([x for o in D for x in o["X"]], float), np.array([max(0, 4 - r) for o in D for r in o["rk"]]), [o["n"] for o in D]
    Xt, yt, gt = pack(tr); Xv, yv, gv = pack(va)
    P = dict(objective="lambdarank", metric="ndcg", ndcg_eval_at=[1, 3], learning_rate=0.03, num_leaves=31, min_data_in_leaf=80,
             feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1, seed=7, deterministic=True, force_row_wise=True, num_threads=1)
    m = lgb.train(P, lgb.Dataset(Xt, yt, group=gt, feature_name=BF.FE), 2000, valid_sets=[lgb.Dataset(Xv, yv, group=gv)], callbacks=[lgb.early_stopping(100, verbose=False)])
    dump = m.dump_model(num_iteration=m.best_iteration)
    model = dict(name="banei-1", feat=BF.FE, trees=[t["tree_structure"] for t in dump["tree_info"]])
    # 標準ライブラリだけの採点が LightGBM と同じ値になるか
    chk = te[:300]; a1 = m.predict(np.array([x for o in chk for x in o["X"]], float), num_iteration=m.best_iteration)
    a2 = [BF.predict(model, x) for o in chk for x in o["X"]]
    dmax = float(np.max(np.abs(a1 - np.array(a2)))); assert dmax < 1e-6, dmax
    for D in (va, te):
        for o in D:
            o["s"] = [BF.predict(model, x) for x in o["X"]]; o["top"] = int(np.argmax(o["s"])); o["c"] = BF.conf(o["s"])
    cs = sorted(o["c"] for o in va)
    cb = cs[int(len(cs) * 0.80)]; ca = cs[int(len(cs) * 0.55)]
    model["c_battle"] = round(cb, 4); model["c_aim"] = round(ca, 4)
    json.dump(model, open(os.path.join(HERE, "banei_model.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"学習 {len(tr)}レース（〜2021）／調整 {len(va)}（2022）／検証 {len(te)}（2023〜）  木の数 {m.best_iteration}  採点の差（LightGBM との最大差） {dmax:.2e}")
    print(f"境目（2022年で決めて固定）: ★勝負 c≥{model['c_battle']}／狙い目 c≥{model['c_aim']}")
    print("検証（2023〜・分母は全レース）")
    N = len(te)
    show("専用モデルの◎（全レース）", tally([(o, o["top"]) for o in te]))
    show("1番人気を◎（比較）", tally([(o, int(np.argmin(o["pop"]))) for o in te]))
    B = [(o, o["top"]) for o in te if o["c"] >= model["c_battle"]]; A = [(o, o["top"]) for o in te if model["c_aim"] <= o["c"] < model["c_battle"]]
    R = [(o, o["top"]) for o in te if o["c"] < model["c_aim"]]
    show("★勝負", tally(B), N); show("狙い目（★勝負を除く）", tally(A), N); show("そのほか", tally(R), N)
    for y in ("2023", "2024", "2025", "2026"):
        show("  " + y + "年 全レース", tally([(o, o["top"]) for o in te if o["d"][:4] == y])); show("  " + y + "年 ★勝負", tally([x for x in B if x[0]["d"][:4] == y]))
    # ★勝負と全体の差（レースを引き直して幅を見る）
    rng = np.random.default_rng(7); isB = np.array([o["c"] >= model["c_battle"] for o in te])
    f = np.array([o["pay"].get("fuku", {}).get(o["num"][o["top"]], 0) for o in te], float); t = np.array([o["pay"].get("tan", {}).get(o["num"][o["top"]], 0) for o in te], float)
    p3 = np.array([o["rk"][o["top"]] <= 3 for o in te], float); df = []; dt = []; dp = []
    for _ in range(2000):
        i = rng.integers(0, N, N); b = isB[i]
        if b.sum() == 0: continue
        df.append(f[i][b].mean() - f[i].mean()); dt.append(t[i][b].mean() - t[i].mean()); dp.append(100 * (p3[i][b].mean() - p3[i].mean()))
    q = lambda v: (np.percentile(v, 2.5), np.percentile(v, 97.5))
    print(f"  ★勝負 − 全体: ◎3着内 {100*(p3[isB].mean()-p3.mean()):+.1f}ポイント [{q(dp)[0]:+.1f}〜{q(dp)[1]:+.1f}]  単回収 {t[isB].mean()-t.mean():+.1f} [{q(dt)[0]:+.1f}〜{q(dt)[1]:+.1f}]  複回収 {f[isB].mean()-f.mean():+.1f} [{q(df)[0]:+.1f}〜{q(df)[1]:+.1f}]")
    imp = sorted(zip(BF.FE, m.feature_importance("gain")), key=lambda x: -x[1])[:8]
    print("  効いている材料（上位8）:", "  ".join(k for k, _ in imp))
if __name__ == "__main__": main()
