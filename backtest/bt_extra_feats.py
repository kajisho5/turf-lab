# -*- coding: utf-8 -*-
"""時計つきモデル（40列）にさらに列を足すと良くなるか（事前登録 PREREG_extra_feats_20261113.md）

  python3 backtest/build_extra_feats.py
  python3 backtest/bt_extra_feats.py fold 2021 / fold 2022          # 選抜（順位学習だけ）
  python3 backtest/bt_extra_feats.py final <A|B|C|ALL> [保存先]      # 2023年以降。補助モデルも同じ列で作る
"""
import os, sys, json
os.environ.update(LTR_NEWFEATS="pre", LTR_NODMS="1", LTR_TC="1", LTR_TIME="1")
_args = sys.argv[1:]
sys.argv = ["x"]
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np, lightgbm as lgb
import bt_train_ltr as T
import eval_bets as E

BASE = T.FEATS
assert len(BASE) == 40
SETS = {"A": ["sv1", "svb", "sva"], "B": ["zn", "z3", "zout", "dirr"], "C": ["jdiff", "jhn", "jh3"]}
SETS["ALL"] = SETS["A"] + SETS["B"] + SETS["C"]
NEW = SETS["ALL"]
K = 2.0
P_LTR = {"objective": "lambdarank", "metric": "ndcg", "ndcg_eval_at": [1, 3], "learning_rate": 0.05,
         "num_leaves": 31, "min_data_in_leaf": 100, "feature_fraction": 0.8, "bagging_fraction": 0.8,
         "bagging_freq": 1, "label_gain": [2 ** i - 1 for i in range(30)], "verbose": -1, "seed": 42}
P_RES = {"objective": "regression", "metric": "l2", "learning_rate": 0.05, "num_leaves": 31,
         "min_data_in_leaf": 100, "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1,
         "verbose": -1, "seed": 42}


def load():
    ex = {}
    with open(os.path.join(HERE, "nardata", "extra_feats.jsonl"), encoding="utf-8") as f:
        for line in f:
            d = json.loads(line); ex[d["rid"]] = d["h"]
    races = []
    with open(T.DATA, encoding="utf-8") as f:
        for line in f:
            rc = json.loads(line)
            hs = [h for h in rc["h"] if h.get("rk") is not None]
            if len(hs) < 5:
                continue
            e = ex.get(rc["rid"], {})
            X = np.array([[T.fval(h, rc, k) for k in BASE] +
                          [e.get(str(int(h["n"])), {}).get(k, np.nan) for k in NEW] for h in hs], np.float32)
            races.append({"d": rc["d"], "X": X, "rk": [int(h["rk"]) for h in hs], "pop": [h.get("pop") for h in hs],
                          "n": [str(int(h["n"])) for h in hs], "pay": rc.get("pay") or {}})
    return races


def cols(name):
    return list(range(40)) + [40 + NEW.index(k) for k in (SETS[name] if name else [])]


def names(name):
    return BASE + (SETS[name] if name else [])


def train_ltr(races, before, name):
    c = cols(name); tr = [r for r in races if r["d"] < before]
    y = np.concatenate([[max(0, len(r["rk"]) - k + 1) for k in r["rk"]] for r in tr])
    d = lgb.Dataset(np.vstack([r["X"][:, c] for r in tr]), label=y, group=[len(r["rk"]) for r in tr],
                    feature_name=names(name), categorical_feature=["tc"])
    return lgb.train(P_LTR, d, num_boost_round=400)


def train_res(races, before, name):
    c = cols(name); tr = [r for r in races if r["d"] < before]
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
                a = cnt[(min(int(p), 12), fn)]
                Xs.append(r["X"][i, c]); ys.append((1.0 if k <= 3 else 0.0) - a[1] / a[0])
    d = lgb.Dataset(np.vstack(Xs), label=np.array(ys), feature_name=names(name), categorical_feature=["tc"])
    return lgb.train(P_RES, d, num_boost_round=300)


def z(v):
    s = v.std()
    return (v - v.mean()) / s if s > 0 else v * 0


def order(r, ltr, name, res=None):
    c = cols(name); s = ltr.predict(r["X"][:, c])
    if res is not None:
        s = z(s) + K * z(res.predict(r["X"][:, c]))
    return np.argsort(-s, kind="stable")


def top(r, o):
    i = int(o[0]); u = r["n"][i]
    return (1 if r["rk"][i] <= 3 else 0, E.pay_single(r["pay"].get("tan"), u),
            E.pay_single(r["pay"].get("fuku"), u), r["pop"][i] or 0, u)


def line(tag, a, b=None):
    n = len(a); f = lambda o, i: sum(x[i] for x in o) / n
    s = f"{tag:<16} {n:>6}R ◎3着内{f(a,0)*100:5.1f} 単{f(a,1):5.1f} 複{f(a,2):5.1f} 人気{f(a,3):.2f}"
    if b is not None:
        s += (f" | 差 3着内{(f(a,0)-f(b,0))*100:+.1f} 単{f(a,1)-f(b,1):+.2f} 複{f(a,2)-f(b,2):+.2f}"
              f" ◎一致{sum(x[4]==y[4] for x,y in zip(a,b))/n*100:.0f}%")
    return s


def ci(a, b, i, scale=1.0):
    d = np.array([x[i] - y[i] for x, y in zip(a, b)], float) * scale
    rng = np.random.default_rng(20261113)
    bs = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(2000)]
    return f"{d.mean():+.2f} [{np.percentile(bs,2.5):+.2f},{np.percentile(bs,97.5):+.2f}]"


def bets(rs, orders):
    acc = {}
    for r, o in zip(rs, orders):
        if len(o) < 6 or not r["pay"].get("tan"):
            continue
        marks = [r["n"][i] for i in o[:6]]
        for nm, (kind, ordered, combos) in E.plans(marks).items():
            a = acc.setdefault(nm, [0, 0, 0, 0, 0]); a[0] += 1; a[1] += len(combos)
            got = sum(E.pay_single(r["pay"].get(kind), c[0]) if kind in ("tan", "fuku")
                      else E.pay_combo(r["pay"].get(kind), c, ordered) for c in combos)
            if got:
                a[2] += 1; a[3] += got; a[4] = max(a[4], got)
    return acc


def main():
    mode = _args[0]
    races = load(); print("読み込み", len(races), flush=True)
    if mode == "fold":
        y = _args[1]; lo, hi = y + "0101", str(int(y) + 1) + "0101"
        rs = [r for r in races if lo <= r["d"] < hi]
        m0 = train_ltr(races, lo, None); b = [top(r, order(r, m0, None)) for r in rs]
        print(line(y + " 今(40列)", b), flush=True)
        for nm in ("A", "B", "C", "ALL"):
            m = train_ltr(races, lo, nm)
            print(line(f"{y} +{nm}", [top(r, order(r, m, nm)) for r in rs], b), flush=True)
        return
    nm = _args[1]; out = _args[2] if len(_args) > 2 else None
    rs = [r for r in races if r["d"] >= "20230101"]
    L0, R0 = train_ltr(races, "20230101", None), train_res(races, "20230101", None)
    L1, R1 = train_ltr(races, "20230101", nm), train_res(races, "20230101", nm)
    if out:
        os.makedirs(out, exist_ok=True)
        L1.save_model(os.path.join(out, "ltr_model_x.txt")); R1.save_model(os.path.join(out, "ltr_res_model_x.txt"))
    O0 = [order(r, L0, None, R0) for r in rs]; O1 = [order(r, L1, nm, R1) for r in rs]
    a0 = [top(r, o) for r, o in zip(rs, O0)]; a1 = [top(r, o) for r, o in zip(rs, O1)]
    l0 = [top(r, order(r, L0, None)) for r in rs]; l1 = [top(r, order(r, L1, nm)) for r in rs]
    print(line("順位学習 今", l0)); print(line("順位学習 +" + nm, l1, l0))
    print(line("本番の並べ方 今", a0)); print(line("本番の並べ方 +" + nm, a1, a0))
    print("  単差", ci(a1, a0, 1), "/ 複差", ci(a1, a0, 2), "/ ◎3着内差", ci(a1, a0, 0, 100))
    for y in ("2023", "2024", "2025", "2026"):
        ix = [i for i, r in enumerate(rs) if r["d"][:4] == y]
        print(line(y, [a1[i] for i in ix], [a0[i] for i in ix]))
    A, B = bets(rs, O0), bets(rs, O1); up = 0
    print(f"\n16種類の買い方（今 → +{nm}）{A['単勝◎'][0]:,}R  ※(除1)=最高配当1本を除いた回収率の差")
    for k in A:
        ra, rb = 100 * A[k][3] / (A[k][1] * 100), 100 * B[k][3] / (B[k][1] * 100)
        xa, xb = 100 * (A[k][3] - A[k][4]) / (A[k][1] * 100), 100 * (B[k][3] - B[k][4]) / (B[k][1] * 100)
        up += rb > ra
        print(f"  {k:<16} 的中 {100*A[k][2]/A[k][0]:5.1f}→{100*B[k][2]/B[k][0]:5.1f}  回収 {ra:5.1f}→{rb:5.1f} ({rb-ra:+.1f}) (除1 {xb-xa:+.1f})")
    print(f"回収率が上がった買い方: {up}/16")
    imp = sorted(zip(L1.feature_name(), L1.feature_importance()), key=lambda x: -x[1])
    print("重要度:", " ".join(f"{k}:{v}" for k, v in imp[:14]))


if __name__ == "__main__":
    main()
