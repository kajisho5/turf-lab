# -*- coding: utf-8 -*-
"""学習データの鮮度の検証（2026-11-13）

本番の順位学習モデルは2022年末までのデータで学習している。
評価年ごとに「2023年より前で学習(A)」と「評価年より前で学習(B)」を同じレースで比べる。
結果: 3年合算 38,843R で 単-0.58 / 複-0.20（どちらも差なし）＝学習し直しは不採用。
使い方: python3 backtest/bt_fresh_train.py   （bt_all.jsonl が要る。メモリ約5GB）
"""
import os, sys, json, random
os.environ.update(LTR_NEWFEATS="pre", LTR_NODMS="1", LTR_TC="1")
sys.argv = ["x"]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, lightgbm as lgb
import bt_train_ltr as T
F = T.FEATS; assert len(F) == 33, len(F)
races = []
with open(T.DATA, encoding="utf-8") as f:
    for line in f:
        rc = json.loads(line)
        hs = [h for h in rc["h"] if h.get("rk") is not None]
        if len(hs) < 5: continue
        X = np.array([[T.fval(h, rc, k) for k in F] for h in hs], np.float32)
        y = [max(0, len(hs) - int(h["rk"]) + 1) for h in hs]
        pay = rc.get("pay") or {}
        races.append((rc["d"], X, y, [{"n": h["n"], "rk": h["rk"], "pop": h.get("pop")} for h in hs], {"tan": pay.get("tan"), "fuku": pay.get("fuku")}))
print("races", len(races), flush=True)
P = {"objective": "lambdarank", "metric": "ndcg", "ndcg_eval_at": [1, 3], "learning_rate": 0.05,
     "num_leaves": 31, "min_data_in_leaf": 100, "feature_fraction": 0.8, "bagging_fraction": 0.8,
     "bagging_freq": 1, "label_gain": [2 ** i - 1 for i in range(30)], "verbose": -1, "seed": 42}
def train(before):
    tr = [r for r in races if r[0] < before]
    d = lgb.Dataset(np.vstack([r[1] for r in tr]), label=np.concatenate([r[2] for r in tr]),
                    group=[len(r[2]) for r in tr], feature_name=F, categorical_feature=T.CAT_FEATS)
    return lgb.train(P, d, num_boost_round=400), len(tr)
def payof(book, u):
    if isinstance(book, dict): return int(book.get(u, 0) or 0)
    if isinstance(book, list):
        for it in book:
            if isinstance(it, list) and it and str(int(it[0])) == u: return int(it[1])
    return 0
def ev(m, rs):
    out = []
    for d, X, y, hs, pay in rs:
        top = hs[int(np.argmax(m.predict(X)))]; u = str(int(top["n"]))
        out.append((int(top["rk"]) <= 3, payof(pay.get("tan"), u), payof(pay.get("fuku"), u), top.get("pop") or 0, u))
    return out
mA, nA = train("20230101"); print("A train", nA, flush=True)
allA, allB = [], []
for Y, lo, hi in (("2024", "20240101", "20250101"), ("2025", "20250101", "20260101"), ("2026", "20260101", "20261113")):
    mB, nB = train(lo)
    rs = [r for r in races if lo <= r[0] < hi]
    a, b = ev(mA, rs), ev(mB, rs)
    n = len(rs); f = lambda o, i: sum(x[i] for x in o) / n
    same = sum(x[4] == z[4] for x, z in zip(a, b)) / n * 100
    print(f"{Y} {n}R trainB {nB} | A 3着内{f(a,0)*100:.1f} 単{f(a,1):.1f} 複{f(a,2):.1f} 人気{f(a,3):.2f} | B 3着内{f(b,0)*100:.1f} 単{f(b,1):.1f} 複{f(b,2):.1f} 人気{f(b,3):.2f} | 差 単{f(b,1)-f(a,1):+.1f} 複{f(b,2)-f(a,2):+.1f} ◎一致{same:.0f}%", flush=True)
    allA += a; allB += b
n = len(allA); rnd = random.Random(20261113)
dt = np.array([b[1] - a[1] for a, b in zip(allA, allB)], float); df = np.array([b[2] - a[2] for a, b in zip(allA, allB)], float)
dh = np.array([b[0] - a[0] for a, b in zip(allA, allB)], float)
rng = np.random.default_rng(20261113)
bt, bf, bh = [], [], []
for _ in range(2000):
    i = rng.integers(0, n, n); bt.append(dt[i].mean()); bf.append(df[i].mean()); bh.append(dh[i].mean() * 100)
q = lambda v: (np.percentile(v, 2.5), np.percentile(v, 97.5))
print(f"合算 {n}R 単差 {dt.mean():+.2f} [{q(bt)[0]:+.2f},{q(bt)[1]:+.2f}] 複差 {df.mean():+.2f} [{q(bf)[0]:+.2f},{q(bf)[1]:+.2f}] 3着内差 {dh.mean()*100:+.2f} [{q(bh)[0]:+.2f},{q(bh)[1]:+.2f}]")
