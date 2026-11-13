# -*- coding: utf-8 -*-
"""時計の7列を足すと良くなるか（2026-11-13・事前登録 PREREG_time_feats_20261113.md）

  python3 backtest/build_dataset.py && python3 backtest/build_time_feats.py   # データ作り
  python3 backtest/bt_time_feats.py fold 2021      # 選抜用（2021年より前で学習→2021年で評価）
  python3 backtest/bt_time_feats.py fold 2022
  python3 backtest/bt_time_feats.py final [保存先フォルダ]   # 2023年以降。モデル2本も保存する
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

F40 = T.FEATS
F33 = F40[:33]
assert len(F40) == 40 and F33[-1] == "tc" and F40[33:] == T.TIME_FEATS, F40
K = 2.0
P_LTR = {"objective": "lambdarank", "metric": "ndcg", "ndcg_eval_at": [1, 3], "learning_rate": 0.05,
         "num_leaves": 31, "min_data_in_leaf": 100, "feature_fraction": 0.8, "bagging_fraction": 0.8,
         "bagging_freq": 1, "label_gain": [2 ** i - 1 for i in range(30)], "verbose": -1, "seed": 42}
P_RES = {"objective": "regression", "metric": "l2", "learning_rate": 0.05, "num_leaves": 31,
         "min_data_in_leaf": 100, "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1,
         "verbose": -1, "seed": 42}


def load():
    races = []
    with open(T.DATA, encoding="utf-8") as f:
        for line in f:
            rc = json.loads(line)
            hs = [h for h in rc["h"] if h.get("rk") is not None]
            if len(hs) < 5:
                continue
            X = np.array([[T.fval(h, rc, k) for k in F40] for h in hs], np.float32)
            pay = rc.get("pay") or {}
            races.append({"d": rc["d"], "X": X, "rk": [int(h["rk"]) for h in hs],
                          "pop": [h.get("pop") for h in hs], "n": [str(int(h["n"])) for h in hs], "pay": pay})
    return races


def train_ltr(races, before, nc):
    tr = [r for r in races if r["d"] < before]
    y = np.concatenate([[max(0, len(r["rk"]) - k + 1) for k in r["rk"]] for r in tr])
    d = lgb.Dataset(np.vstack([r["X"][:, :nc] for r in tr]), label=y, group=[len(r["rk"]) for r in tr],
                    feature_name=F40[:nc], categorical_feature=["tc"])
    return lgb.train(P_LTR, d, num_boost_round=400)


def train_res(races, before, nc):
    """補助モデル: 3着内 − 人気(12打切)×頭数の期待3着内率（期待値は学習期間だけから）"""
    tr = [r for r in races if r["d"] < before]
    cnt = {}
    for r in tr:
        fn = len(r["rk"])
        for k, p in zip(r["rk"], r["pop"]):
            if p:
                c = cnt.setdefault((min(int(p), 12), fn), [0, 0]); c[0] += 1; c[1] += k <= 3
    Xs, ys = [], []
    for r in tr:
        fn = len(r["rk"])
        for i, (k, p) in enumerate(zip(r["rk"], r["pop"])):
            if not p:
                continue
            c = cnt[(min(int(p), 12), fn)]
            Xs.append(r["X"][i, :nc]); ys.append((1.0 if k <= 3 else 0.0) - c[1] / c[0])
    d = lgb.Dataset(np.vstack(Xs), label=np.array(ys), feature_name=F40[:nc], categorical_feature=["tc"])
    return lgb.train(P_RES, d, num_boost_round=300)


def z(v):
    s = v.std()
    return (v - v.mean()) / s if s > 0 else v * 0


def order(r, ltr, nl, res=None, nr=33):
    s = ltr.predict(r["X"][:, :nl])
    if res is not None:
        s = z(s) + K * z(res.predict(r["X"][:, :nr]))
    return np.argsort(-s, kind="stable")


def top(r, o):
    i = int(o[0]); u = r["n"][i]
    return (1 if r["rk"][i] <= 3 else 0, E.pay_single(r["pay"].get("tan"), u),
            E.pay_single(r["pay"].get("fuku"), u), r["pop"][i] or 0, u)


def line(tag, a, b=None):
    n = len(a); f = lambda o, i: sum(x[i] for x in o) / n
    s = f"{tag:<22} {n:>6}R ◎3着内{f(a,0)*100:5.1f} 単{f(a,1):5.1f} 複{f(a,2):5.1f} 人気{f(a,3):.2f}"
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
    """16種類の買い方。分母は買った全レース×点数"""
    acc = {}
    for r, o in zip(rs, orders):
        if len(o) < 6 or not r["pay"].get("tan"):
            continue
        marks = [r["n"][i] for i in o[:6]]
        for name, (kind, ordered, combos) in E.plans(marks).items():
            a = acc.setdefault(name, [0, 0, 0, 0])
            a[0] += 1; a[1] += len(combos)
            got = sum(E.pay_single(r["pay"].get(kind), c[0]) if kind in ("tan", "fuku")
                      else E.pay_combo(r["pay"].get(kind), c, ordered) for c in combos)
            if got:
                a[2] += 1; a[3] += got
    return acc


def main():
    mode = _args[0]
    races = load()
    print("読み込み", len(races), flush=True)
    if mode == "fold":
        y = _args[1]; lo, hi = y + "0101", str(int(y) + 1) + "0101"
        rs = [r for r in races if lo <= r["d"] < hi]
        m33, m40 = train_ltr(races, lo, 33), train_ltr(races, lo, 40)
        b = [top(r, order(r, m33, 33)) for r in rs]; a = [top(r, order(r, m40, 40)) for r in rs]
        print(line(y + " 今(33列)", b)); print(line(y + " +7列", a, b))
        return
    out = _args[1] if len(_args) > 1 else None
    rs = [r for r in races if r["d"] >= "20230101"]
    m33, m40 = train_ltr(races, "20230101", 33), train_ltr(races, "20230101", 40)
    cur = lgb.Booster(model_file=os.path.join(HERE, "ltr_res_model.txt"))
    assert cur.feature_name() == F33
    r33, r40 = train_res(races, "20230101", 33), train_res(races, "20230101", 40)
    if out:
        os.makedirs(out, exist_ok=True)
        m40.save_model(os.path.join(out, "ltr_model_t40.txt")); r40.save_model(os.path.join(out, "ltr_res_model_t40.txt"))
    O = {
        "順位学習 今": [order(r, m33, 33) for r in rs],
        "順位学習 +7列": [order(r, m40, 40) for r in rs],
        "C12 今": [order(r, m33, 33, cur, 33) for r in rs],
        "C12 補助を作り直し(33列)": [order(r, m33, 33, r33, 33) for r in rs],
        "C12 順位学習だけ+7列": [order(r, m40, 40, cur, 33) for r in rs],
        "C12 両方+7列": [order(r, m40, 40, r40, 40) for r in rs],
    }
    R = {k: [top(r, o) for r, o in zip(rs, v)] for k, v in O.items()}
    print(line("順位学習 今", R["順位学習 今"])); print(line("順位学習 +7列", R["順位学習 +7列"], R["順位学習 今"]))
    print("  単差", ci(R["順位学習 +7列"], R["順位学習 今"], 1), "/ 複差", ci(R["順位学習 +7列"], R["順位学習 今"], 2))
    base = R["C12 今"]; print(line("C12 今", base))
    for k in ("C12 補助を作り直し(33列)", "C12 順位学習だけ+7列", "C12 両方+7列"):
        print(line(k, R[k], base))
        print("  単差", ci(R[k], base, 1), "/ 複差", ci(R[k], base, 2), "/ ◎3着内差", ci(R[k], base, 0, 100))
    new = R["C12 両方+7列"]
    for y in ("2023", "2024", "2025", "2026"):
        ix = [i for i, r in enumerate(rs) if r["d"][:4] == y]
        print(line(y + " C12 両方+7列", [new[i] for i in ix], [base[i] for i in ix]))
    A, B = bets(rs, O["C12 今"]), bets(rs, O["C12 両方+7列"])
    up = 0
    print(f"\n16種類の買い方（C12 今 → C12 両方+7列）{A['単勝◎'][0]:,}R")
    for n in A:
        ra, rb = 100 * A[n][3] / (A[n][1] * 100), 100 * B[n][3] / (B[n][1] * 100)
        ha, hb = 100 * A[n][2] / A[n][0], 100 * B[n][2] / B[n][0]
        up += rb > ra
        print(f"  {n:<16} 的中 {ha:5.1f}→{hb:5.1f} ({hb-ha:+.1f})  回収 {ra:5.1f}→{rb:5.1f} ({rb-ra:+.1f})")
    print(f"回収率が上がった買い方: {up}/16")
    imp = sorted(zip(m40.feature_name(), m40.feature_importance()), key=lambda x: -x[1])
    print("重要度:", " ".join(f"{k}:{v}" for k, v in imp[:12]))


if __name__ == "__main__":
    main()
