# -*- coding: utf-8 -*-
"""公開している数字（地方）を、時計つきモデル（mv 2.3・43列）で測り直す（2026-11-13）

測るもの（条件は tweet.html と同じ。分母は買った全レース。期間は 2023-01〜、モデルは2022年までで学習したもの）:
  全レース … ◎3着内率（払戻基準）・単的中率・単回収率・複回収率
  複勝推奨 … 9頭以下 × 信頼度40以上 × ◎が3番人気以内（firmness() を移植。verify_fuku_rec.py と同じ式）
  鉄板     … 10頭以下 × ◎が1番人気 × 単勝1.9倍以下（公式の確定オッズがある 2026-03〜だけ。verify_iron_rec.py と同じ条件）
並べ方は本番と同じ（順位学習43列＋補助43列・k=2.0）。
使い方: python3 backtest/verify_public_t.py
"""
import json, math, os, sys
os.environ.update(LTR_NEWFEATS="pre", LTR_NODMS="1", LTR_TC="1", LTR_TIME="2")
HERE = os.path.dirname(os.path.abspath(__file__)); sys.argv = ["x"]; sys.path.insert(0, HERE)
import numpy as np, lightgbm as lgb
import bt_train_ltr as T
from eval_bets import pay_single
from verify_fuku_rec import firmness
from verify_iron_rec import load_odds

L = lgb.Booster(model_file=os.path.join(HERE, "ltr_model_t.txt")); R = lgb.Booster(model_file=os.path.join(HERE, "ltr_res_model_t.txt"))
F = L.feature_name(); assert R.feature_name() == F and len(F) == 43
K = 2.0


def z(v):
    s = v.std(); return (v - v.mean()) / s if s > 0 else v * 0


def wilson(h, n):
    if not n: return (0, 0)
    p, zz = h / n, 1.96
    c = (p + zz * zz / (2 * n)) / (1 + zz * zz / n); d = zz * math.sqrt(p * (1 - p) / n + zz * zz / (4 * n * n)) / (1 + zz * zz / n)
    return (100 * (c - d), 100 * (c + d))


def main():
    odds = load_odds()
    A = {"n": 0, "p3": 0, "win": 0, "tan": 0, "fuku": 0}; Fk = dict(A); Ir = dict(A); yr = {}
    with open(T.DATA, encoding="utf-8") as f:
        for line in f:
            rc = json.loads(line)
            if rc["d"] < "20230101": continue
            hs = [h for h in rc["h"] if h.get("rk") is not None]
            if len(hs) < 5: continue
            X = np.array([[T.fval(h, rc, k) for k in F] for h in hs], float)
            s = L.predict(X); comb = z(s) + K * z(R.predict(X)); sc = comb.std()
            raw = s.mean() + s.std() * (comb / sc if sc > 0 else comb * 0)
            o = np.argsort(-raw, kind="stable"); top = hs[int(o[0])]; u = str(int(top["n"]))
            pay = rc.get("pay") or {}; tan, fuku = pay_single(pay.get("tan"), u), pay_single(pay.get("fuku"), u)
            def add(d):
                d["n"] += 1; d["p3"] += fuku > 0; d["win"] += tan > 0; d["tan"] += tan; d["fuku"] += fuku
            add(A)
            pop = top.get("pop"); ss = [float(raw[i]) for i in o]
            fm = firmness(ss, pop)
            if len(hs) <= 9 and fm is not None and fm >= 40 and pop and pop <= 3:
                add(Fk); y = yr.setdefault(rc["d"][:4], dict(n=0, p3=0, fuku=0)); y["n"] += 1; y["p3"] += fuku > 0; y["fuku"] += fuku
            od = odds.get(rc["rid"], {}).get(u)
            if od and len(hs) <= 10 and od[1] == 1 and od[0] <= 1.9:
                add(Ir)
    def show(tag, d):
        n = d["n"]; lo, hi = wilson(d["p3"], n)
        print(f"{tag:<8} {n:>6,}R ◎3着内 {100*d['p3']/n:.1f}%（95%の幅 {lo:.1f}〜{hi:.1f}） 単的中 {100*d['win']/n:.1f}% 単 {d['tan']/n:.1f} 複 {d['fuku']/n:.1f}")
    show("全レース", A); show("複勝推奨", Fk); show("鉄板", Ir)
    print("年別（複勝推奨）:", "  ".join(f"{y}: {v['n']:,}R {100*v['p3']/v['n']:.1f}% 複{v['fuku']/v['n']:.1f}" for y, v in sorted(yr.items())))


if __name__ == "__main__":
    main()
