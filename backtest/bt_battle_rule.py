# -*- coding: utf-8 -*-
"""★勝負の判定の作り直し（事前登録 PREREG_battle_rule_20261113.md）
  python3 backtest/bt_battle_rule.py fold 2021 / fold 2022 / final <R番号> <上位2割の境目> <上位4割の境目>
"""
import os, sys, json
os.environ.update(LTR_NEWFEATS="pre", LTR_NODMS="1", LTR_TC="1", LTR_TIME="2")
_args = sys.argv[1:]; sys.argv = ["x"]
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import numpy as np, lightgbm as lgb
import bt_train_ltr as T
import eval_bets as E
F = T.FEATS; assert len(F) == 43
K, SCALE = 2.0, 0.923
P_LTR = {"objective": "lambdarank", "metric": "ndcg", "ndcg_eval_at": [1, 3], "learning_rate": 0.05, "num_leaves": 31,
         "min_data_in_leaf": 100, "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1,
         "label_gain": [2 ** i - 1 for i in range(30)], "verbose": -1, "seed": 42}
P_RES = {"objective": "regression", "metric": "l2", "learning_rate": 0.05, "num_leaves": 31, "min_data_in_leaf": 100,
         "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1, "verbose": -1, "seed": 42}


def load():
    rs = []
    with open(T.DATA, encoding="utf-8") as f:
        for line in f:
            rc = json.loads(line)
            hs = [h for h in rc["h"] if h.get("rk") is not None]
            if len(hs) < 5:
                continue
            pay = rc.get("pay") or {}
            rs.append({"d": rc["d"], "X": np.array([[T.fval(h, rc, k) for k in F] for h in hs], np.float32),
                       "rk": [int(h["rk"]) for h in hs], "pop": [h.get("pop") for h in hs],
                       "n": [str(int(h["n"])) for h in hs], "tan": pay.get("tan"), "fuku": pay.get("fuku")})
    return rs


def train(rs, before):
    tr = [r for r in rs if r["d"] < before]
    y = np.concatenate([[max(0, len(r["rk"]) - k + 1) for k in r["rk"]] for r in tr])
    L = lgb.train(P_LTR, lgb.Dataset(np.vstack([r["X"] for r in tr]), label=y, group=[len(r["rk"]) for r in tr],
                                     feature_name=F, categorical_feature=["tc"]), num_boost_round=400)
    cnt = {}
    for r in tr:
        fn = len(r["rk"])
        for k, p in zip(r["rk"], r["pop"]):
            if p:
                a = cnt.setdefault((min(int(p), 12), fn), [0, 0]); a[0] += 1; a[1] += k <= 3
    Xs, ys = [], []
    for r in tr:
        fn = len(r["rk"])
        for i, (k, p) in enumerate(zip(r["rk"], r["pop"])):
            if p:
                a = cnt[(min(int(p), 12), fn)]; Xs.append(r["X"][i]); ys.append((1.0 if k <= 3 else 0.0) - a[1] / a[0])
    R = lgb.train(P_RES, lgb.Dataset(np.vstack(Xs), label=np.array(ys), feature_name=F, categorical_feature=["tc"]), num_boost_round=300)
    return L, R


def z(v):
    s = v.std(); return (v - v.mean()) / s if s > 0 else v * 0


def signals(r, L, R):
    s = L.predict(r["X"]); comb = z(s) + K * z(R.predict(r["X"])); sc = comb.std()
    raw = s.mean() + s.std() * SCALE * (comb / sc if sc > 0 else comb * 0)
    o = np.argsort(-raw, kind="stable"); top = int(o[0]); u = r["n"][top]
    spread = float(raw.max() - raw.min()) or 1.0
    return {"fn": len(s), "gap": float(raw[o[0]] - raw[o[1]]) * 12, "agree": int(np.argmax(s)) == top,
            "c": 0.6 * (raw[top] - raw.mean()) / spread + 0.4 * (raw[o[0]] - raw[o[1]]) / spread,
            "win": r["rk"][top] == 1, "t3": r["rk"][top] <= 3, "tan": E.pay_single(r["tan"], u), "fuku": E.pay_single(r["fuku"], u),
            "y": r["d"][:4]}


def rules(S, q80=None, q60=None):
    c = np.array([x["c"] for x in S])
    if q80 is None:
        q80, q60 = np.quantile(c, 0.8), np.quantile(c, 0.6)
        print(f"  抜け具合の境目: 上位2割={q80:.4f} 上位4割={q60:.4f}")
    ok = lambda x: x["fn"] < 14
    return {
        "R0 今の決まり(点差8以上)": [ok(x) and x["gap"] >= 8 for x in S],
        "R1 一致": [ok(x) and x["agree"] for x in S],
        "R2 一致+点差4以上": [ok(x) and x["agree"] and x["gap"] >= 4 for x in S],
        "R3 一致+点差8以上": [ok(x) and x["agree"] and x["gap"] >= 8 for x in S],
        "R4 抜け具合 上位2割": [ok(x) and x["c"] >= q80 for x in S],
        "R5 一致+抜け具合 上位4割": [ok(x) and x["agree"] and x["c"] >= q60 for x in S],
        "R6 一致+10頭以下": [x["fn"] <= 10 and x["agree"] for x in S],
    }


def st(S):
    n = len(S)
    return (n, 100 * sum(x["win"] for x in S) / n, 100 * sum(x["t3"] for x in S) / n,
            sum(x["tan"] for x in S) / n, sum(x["fuku"] for x in S) / n) if n else (0, 0, 0, 0, 0)


def show(tag, S, total):
    n, w, t3, tan, fuku = st(S)
    print(f"{tag:<26} {n:>6}R（{100*n/total:4.1f}%） 1着{w:5.1f}% 3着内{t3:5.1f}% 単{tan:5.1f} 複{fuku:5.1f}", flush=True)


def main():
    rs = load(); print("読み込み", len(rs), flush=True)
    if _args[0] == "fold":
        y = _args[1]; lo, hi = y + "0101", str(int(y) + 1) + "0101"
        L, R = train(rs, lo); S = [signals(r, L, R) for r in rs if lo <= r["d"] < hi]
        show(y + " 全体", S, len(S))
        for k, m in rules(S).items():
            show(y + " " + k, [x for x, b in zip(S, m) if b], len(S))
        return
    L, R = train(rs, "20230101"); S = [signals(r, L, R) for r in rs if r["d"] >= "20230101"]
    # 境目は選抜年（2021・2022）で出した値を固定で使う（評価する期間の分布は見ない）
    q80, q60 = float(_args[2]), float(_args[3])
    show("全体", S, len(S)); RS = rules(S, q80, q60)
    rng = np.random.default_rng(20261113)
    for key in [k for k in RS if k.startswith("R0") or k.startswith(_args[1] + " ")]:
        sel = [x for x, b in zip(S, RS[key]) if b]; show(key, sel, len(S))
        for yy in ("2023", "2024", "2025", "2026"):
            a = [x for x in S if x["y"] == yy]; b = [x for x in sel if x["y"] == yy]
            print(f"   {yy}: {len(b):>5}R 単{st(b)[3]:5.1f}（全体{st(a)[3]:5.1f}） 複{st(b)[4]:5.1f}（全体{st(a)[4]:5.1f}） 1着{st(b)[1]:4.1f}%")
        # 選ばれたレースの回収率 − 全体の回収率（レース単位の並べ直し）
        m = np.array(RS[key]); tan = np.array([x["tan"] for x in S], float); fuku = np.array([x["fuku"] for x in S], float)
        dt, df = [], []
        for _ in range(2000):
            i = rng.integers(0, len(S), len(S)); mm = m[i]
            if mm.sum() == 0: continue
            dt.append(tan[i][mm].mean() - tan[i].mean()); df.append(fuku[i][mm].mean() - fuku[i].mean())
        print(f"   全体との差: 単 {tan[m].mean()-tan.mean():+.2f} [{np.percentile(dt,2.5):+.2f},{np.percentile(dt,97.5):+.2f}] / 複 {fuku[m].mean()-fuku.mean():+.2f} [{np.percentile(df,2.5):+.2f},{np.percentile(df,97.5):+.2f}]")


if __name__ == "__main__":
    main()
