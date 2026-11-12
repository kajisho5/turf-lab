# -*- coding: utf-8 -*-
"""時計の項目を順位学習に足すと良くなるか（2026-11-13・事前登録つき）

使い方:
  python3 backtest/build_time_feats.py                 # 先に付け足しデータを作る
  python3 backtest/bt_time_feats.py fold 2021          # 選抜（2021年より前で学習→2021年で評価）
  python3 backtest/bt_time_feats.py fold 2022
  python3 backtest/bt_time_feats.py final <候補名>     # 2023年以降で1回だけ
候補名: sf / af / bt / all
"""
import os, sys, json
os.environ.update(LTR_NEWFEATS="pre", LTR_NODMS="1", LTR_TC="1")
_args = sys.argv[1:]
sys.argv = ["x"]
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np, lightgbm as lgb
import bt_train_ltr as T

BASE = T.FEATS
assert len(BASE) == 33, len(BASE)
SETS = {"sf": ["sf1", "sfb", "sfa"], "af": ["af1", "afb", "afa"], "bt": ["btf"],
        "all": ["sf1", "sfb", "sfa", "af1", "afb", "afa", "btf"]}
NEW = SETS["all"]
P = {"objective": "lambdarank", "metric": "ndcg", "ndcg_eval_at": [1, 3], "learning_rate": 0.05,
     "num_leaves": 31, "min_data_in_leaf": 100, "feature_fraction": 0.8, "bagging_fraction": 0.8,
     "bagging_freq": 1, "label_gain": [2 ** i - 1 for i in range(30)], "verbose": -1, "seed": 42}


def load(lo_keep="20130101"):
    tf = {}
    with open(os.path.join(HERE, "nardata", "time_feats.jsonl"), encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            tf[d["rid"]] = d["h"]
    races = []
    with open(T.DATA, encoding="utf-8") as f:
        for line in f:
            rc = json.loads(line)
            hs = [h for h in rc["h"] if h.get("rk") is not None]
            if len(hs) < 5:
                continue
            ex = tf.get(rc["rid"], {})
            X = np.array([[T.fval(h, rc, k) for k in BASE] +
                          [ex.get(str(int(h["n"])), {}).get(k, np.nan) for k in NEW] for h in hs], np.float32)
            y = [max(0, len(hs) - int(h["rk"]) + 1) for h in hs]
            pay = rc.get("pay") or {}
            races.append((rc["d"], X, y, [(str(int(h["n"])), int(h["rk"]), h.get("pop") or 0) for h in hs],
                          pay.get("tan"), pay.get("fuku")))
    return races


def cols(name):
    return list(range(33)) + [33 + NEW.index(k) for k in (SETS[name] if name else [])]


def train(races, before, name):
    c = cols(name)
    tr = [r for r in races if r[0] < before]
    d = lgb.Dataset(np.vstack([r[1][:, c] for r in tr]), label=np.concatenate([r[2] for r in tr]),
                    group=[len(r[2]) for r in tr], feature_name=BASE + (SETS[name] if name else []),
                    categorical_feature=T.CAT_FEATS)
    return lgb.train(P, d, num_boost_round=400)


def payof(book, u):
    if isinstance(book, dict):
        return int(book.get(u, 0) or 0)
    if isinstance(book, list):
        for it in book:
            if isinstance(it, list) and it and str(int(it[0])) == u:
                return int(it[1])
    return 0


def pick(scores, r):
    u, rk, pop = r[3][int(np.argmax(scores))]
    # 買った全レースが分母（外れは0円で入る）
    return (1 if rk <= 3 else 0, payof(r[4], u), payof(r[5], u), pop, u)


def ev(m, rs, name):
    c = cols(name)
    return [pick(m.predict(r[1][:, c]), r) for r in rs]


def line(tag, a, b=None):
    n = len(a); f = lambda o, i: sum(x[i] for x in o) / n
    s = f"{tag:<10} {n:>6}R ◎3着内{f(a,0)*100:5.1f} 単{f(a,1):5.1f} 複{f(a,2):5.1f} 人気{f(a,3):.2f}"
    if b is not None:
        s += f" | 差 3着内{(f(a,0)-f(b,0))*100:+.1f} 単{f(a,1)-f(b,1):+.2f} 複{f(a,2)-f(b,2):+.2f} ◎一致{sum(x[4]==z[4] for x,z in zip(a,b))/n*100:.0f}%"
    return s


def ci(a, b, i, scale=1.0):
    d = np.array([x[i] - z[i] for x, z in zip(a, b)], float) * scale
    rng = np.random.default_rng(20261113)
    bs = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(2000)]
    return f"{d.mean():+.2f} [{np.percentile(bs,2.5):+.2f},{np.percentile(bs,97.5):+.2f}]"


def main():
    mode = _args[0]
    races = load()
    print("読み込み", len(races), flush=True)
    if mode == "fold":
        y = _args[1]
        lo, hi = y + "0101", str(int(y) + 1) + "0101"
        rs = [r for r in races if lo <= r[0] < hi]
        base = ev(train(races, lo, None), rs, None)
        print(line(f"{y} 今", base), flush=True)
        for name in ("sf", "af", "bt", "all"):
            print(line(f"{y} +{name}", ev(train(races, lo, name), rs, name), base), flush=True)
    else:
        name = _args[1]
        rs = [r for r in races if r[0] >= "20230101"]
        mb, mn = train(races, "20230101", None), train(races, "20230101", name)
        a, b = ev(mn, rs, name), ev(mb, rs, None)
        print(line("今", b)); print(line("+" + name, a, b))
        for y in ("2023", "2024", "2025", "2026"):
            ix = [i for i, r in enumerate(rs) if r[0][:4] == y]
            print(line(y + " +" + name, [a[i] for i in ix], [b[i] for i in ix]))
        print("単差", ci(a, b, 1), "/ 複差", ci(a, b, 2), "/ ◎3着内差", ci(a, b, 0, 100))
        # C12（今の補助モデルを足した並び）: z(順位学習)+2.0*z(補助)
        res = lgb.Booster(model_file=os.path.join(HERE, "ltr_res_model.txt"))
        assert res.feature_name() == BASE, "補助モデルの列が本番33列と違う"
        def z(v):
            s = v.std()
            return (v - v.mean()) / s if s > 0 else v * 0
        def c12(m, nm):
            c = cols(nm)
            return [pick(z(m.predict(r[1][:, c])) + 2.0 * z(res.predict(r[1][:, :33])), r) for r in rs]
        ca, cb = c12(mn, name), c12(mb, None)
        print(line("C12 今", cb)); print(line("C12 +" + name, ca, cb))
        print("C12 単差", ci(ca, cb, 1), "/ 複差", ci(ca, cb, 2), "/ ◎3着内差", ci(ca, cb, 0, 100))
        imp = sorted(zip(mn.feature_name(), mn.feature_importance()), key=lambda x: -x[1])
        print("重要度:", " ".join(f"{k}:{v}" for k, v in imp[:12]))


if __name__ == "__main__":
    main()
